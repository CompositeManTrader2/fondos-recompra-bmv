"""
Procesamiento financiero del DataFrame de operaciones:
  - VWAP total / compra / venta a nivel día, semana, mes
  - Comparativo VWAP vs precio de mercado (sobreprecio en bps)
  - Métricas de actividad (operaciones, acciones, importes)
  - Limpieza estandarizada de casas de bolsa
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

DIAS_SEMANA = {
    0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
    4: "Viernes", 5: "Sábado", 6: "Domingo",
}


# ---------------------------------------------------------------------------
# Limpieza
# ---------------------------------------------------------------------------

def limpiar_casa_bolsa(serie: pd.Series) -> pd.Series:
    s = serie.fillna("DESCONOCIDA").astype(str).str.upper().str.strip()
    s = s.str.replace(r"^CASA\s+DE\s+BOLSA\s*", "", regex=True)
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()
    s = s.replace({"": "DESCONOCIDA"})
    return s


def consolidar_operaciones(df: pd.DataFrame) -> pd.DataFrame:
    """Garantiza tipos, quita filas inválidas y enriquece con campos calculados."""
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    # Asegurar columnas mínimas
    for col in ["FOLIO", "OPERACION", "NUMERO_DE_ACCIONES", "PRECIO_UNITARIO",
                "IMPORTE_OPERACION", "FECHA_OPERACION", "CASA_BOLSA",
                "EMISORA", "ARCHIVO_ORIGEN"]:
        if col not in df.columns:
            df[col] = pd.NA

    df["FECHA_OPERACION"] = pd.to_datetime(df["FECHA_OPERACION"], errors="coerce")
    df["PRECIO_UNITARIO"] = pd.to_numeric(df["PRECIO_UNITARIO"], errors="coerce")
    df["NUMERO_DE_ACCIONES"] = pd.to_numeric(df["NUMERO_DE_ACCIONES"], errors="coerce")
    df["IMPORTE_OPERACION"] = pd.to_numeric(df["IMPORTE_OPERACION"], errors="coerce")

    # Si IMPORTE_OPERACION está vacío pero hay precio*acciones, se calcula
    mask = df["IMPORTE_OPERACION"].isna() & df["PRECIO_UNITARIO"].notna() & df["NUMERO_DE_ACCIONES"].notna()
    df.loc[mask, "IMPORTE_OPERACION"] = (
        df.loc[mask, "PRECIO_UNITARIO"] * df.loc[mask, "NUMERO_DE_ACCIONES"]
    )

    df = df.dropna(subset=["FECHA_OPERACION", "PRECIO_UNITARIO"])
    df = df[df["PRECIO_UNITARIO"] > 0]

    df["CASA_BOLSA"] = limpiar_casa_bolsa(df["CASA_BOLSA"])
    df["DIA_SEMANA"] = df["FECHA_OPERACION"].dt.weekday.map(DIAS_SEMANA)
    df["FECHA"] = df["FECHA_OPERACION"].dt.normalize()
    df["MES"] = df["FECHA_OPERACION"].dt.to_period("M").dt.to_timestamp()
    df["SEMANA_INICIO"] = df["FECHA_OPERACION"].apply(
        lambda d: (d - timedelta(days=d.weekday())).normalize()
    )
    df["TIPO"] = np.where(
        df["OPERACION"].astype(str).str.contains("COMPRA", case=False, na=False),
        "COMPRA",
        np.where(
            df["OPERACION"].astype(str).str.contains("VENTA", case=False, na=False),
            "VENTA",
            "OTRO",
        ),
    )

    # Quitar duplicados exactos (mismo folio + fecha + casa + emisora)
    if "FOLIO" in df.columns:
        df = df.drop_duplicates(
            subset=[c for c in ["EMISORA", "FECHA_OPERACION", "FOLIO", "CASA_BOLSA"] if c in df.columns],
            keep="first",
        )

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# VWAP y agregaciones
# ---------------------------------------------------------------------------

def _vwap(df: pd.DataFrame) -> float:
    """
    VWAP = Σ(precio × acciones) / Σ(acciones).
    Si no hay datos de acciones (todo NaN/0) → fallback al promedio simple
    de precios. Robusto frente a Int64/Float64 nullable.
    """
    if df is None or df.empty or "PRECIO_UNITARIO" not in df.columns:
        return float("nan")
    # Convertir a float64 puro para evitar bugs de pd.NA en multiplicación
    prec = pd.to_numeric(df["PRECIO_UNITARIO"], errors="coerce").astype("float64")
    if "NUMERO_DE_ACCIONES" in df.columns:
        acc = pd.to_numeric(df["NUMERO_DE_ACCIONES"], errors="coerce").astype("float64").fillna(0.0)
    else:
        acc = pd.Series([0.0] * len(df), index=df.index)
    mask = prec.notna()
    prec = prec[mask]
    acc = acc[mask]
    denom = float(acc.sum())
    if denom > 0:
        return float((prec * acc).sum() / denom)
    if not prec.empty:
        return float(prec.mean())
    return float("nan")


def _agregado(df: pd.DataFrame) -> pd.Series:
    compras = df[df["TIPO"] == "COMPRA"]
    ventas = df[df["TIPO"] == "VENTA"]
    importe = df["IMPORTE_OPERACION"].fillna(0).sum() if "IMPORTE_OPERACION" in df else 0
    if not importe:
        importe = float((df["PRECIO_UNITARIO"] * df["NUMERO_DE_ACCIONES"].fillna(0)).sum())
    return pd.Series({
        "OPERACIONES": len(df),
        "ACCIONES": int(df["NUMERO_DE_ACCIONES"].fillna(0).sum()),
        "IMPORTE": float(importe),
        "VWAP": _vwap(df) if len(df) else np.nan,
        "VWAP_COMPRA": _vwap(compras) if len(compras) else np.nan,
        "VWAP_VENTA": _vwap(ventas) if len(ventas) else np.nan,
        "PRECIO_MIN": float(df["PRECIO_UNITARIO"].min()) if len(df) else np.nan,
        "PRECIO_MAX": float(df["PRECIO_UNITARIO"].max()) if len(df) else np.nan,
        "PRECIO_PROMEDIO": float(df["PRECIO_UNITARIO"].mean()) if len(df) else np.nan,
        "DESV_ESTANDAR": float(df["PRECIO_UNITARIO"].std()) if len(df) > 1 else np.nan,
        "ACCIONES_COMPRA": int(compras["NUMERO_DE_ACCIONES"].fillna(0).sum()),
        "ACCIONES_VENTA": int(ventas["NUMERO_DE_ACCIONES"].fillna(0).sum()),
    })


def estadisticos_por_periodo(df: pd.DataFrame, periodo: str = "FECHA") -> pd.DataFrame:
    """
    periodo ∈ {'FECHA', 'SEMANA_INICIO', 'MES'}.
    Devuelve DataFrame ordenado cronológicamente con todas las métricas.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    if periodo not in df.columns:
        raise ValueError(f"Columna de periodo '{periodo}' no existe en el DataFrame.")
    out = df.groupby(periodo).apply(_agregado, include_groups=False).reset_index()
    return out.sort_values(periodo).reset_index(drop=True)


def estadisticos_por_casa(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.groupby("CASA_BOLSA").apply(_agregado, include_groups=False).reset_index()
    out = out.sort_values("IMPORTE", ascending=False).reset_index(drop=True)
    out["PARTICIPACION_IMPORTE_%"] = 100 * out["IMPORTE"] / out["IMPORTE"].sum() if out["IMPORTE"].sum() else 0
    out["PARTICIPACION_OPS_%"] = 100 * out["OPERACIONES"] / out["OPERACIONES"].sum() if out["OPERACIONES"].sum() else 0
    return out


def total_global(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    return _agregado(df).to_dict()


# ---------------------------------------------------------------------------
# Comparativo vs precio de mercado
# ---------------------------------------------------------------------------

def comparar_con_mercado(
    diarios: pd.DataFrame,
    df_mercado: pd.DataFrame,
    columna_precio: str = "Close",
) -> pd.DataFrame:
    """
    diarios: salida de estadisticos_por_periodo(df, 'FECHA')
    df_mercado: DataFrame con índice/columna de fecha y precio de cierre.
    """
    if diarios is None or diarios.empty or df_mercado is None or df_mercado.empty:
        return pd.DataFrame()

    m = df_mercado.copy()
    if "Date" in m.columns:
        m["FECHA"] = pd.to_datetime(m["Date"]).dt.normalize()
    elif m.index.name and "date" in m.index.name.lower():
        m = m.reset_index().rename(columns={m.index.name: "FECHA"})
        m["FECHA"] = pd.to_datetime(m["FECHA"]).dt.normalize()
    else:
        m = m.reset_index()
        m.columns = [str(c) for c in m.columns]
        # Toma la primera columna tipo fecha
        for col in m.columns:
            if "fecha" in col.lower() or "date" in col.lower():
                m["FECHA"] = pd.to_datetime(m[col]).dt.normalize()
                break

    if "FECHA" not in m.columns or columna_precio not in m.columns:
        return pd.DataFrame()

    m = m[["FECHA", columna_precio]].rename(columns={columna_precio: "PRECIO_MERCADO"})
    out = diarios.merge(m, how="left", left_on="FECHA", right_on="FECHA")

    for c in ["VWAP", "VWAP_COMPRA", "VWAP_VENTA"]:
        if c in out.columns:
            out[f"{c}_VS_MERCADO_%"] = 100 * (out[c] - out["PRECIO_MERCADO"]) / out["PRECIO_MERCADO"]

    out["ALERTA_SOBREPRECIO_TOTAL"] = out.get("VWAP_VS_MERCADO_%", pd.Series(dtype=float)) > 1.5
    out["ALERTA_SOBREPRECIO_COMPRA"] = out.get("VWAP_COMPRA_VS_MERCADO_%", pd.Series(dtype=float)) > 1.5
    return out


# ---------------------------------------------------------------------------
# Filtrado por ventana
# ---------------------------------------------------------------------------

def filtrar_ventana(
    df: pd.DataFrame,
    fecha_inicio: Optional[pd.Timestamp] = None,
    fecha_fin: Optional[pd.Timestamp] = None,
    casas: Optional[list[str]] = None,
    tipos: Optional[list[str]] = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    if fecha_inicio is not None:
        out = out[out["FECHA_OPERACION"] >= pd.to_datetime(fecha_inicio)]
    if fecha_fin is not None:
        out = out[out["FECHA_OPERACION"] <= pd.to_datetime(fecha_fin)]
    if casas:
        out = out[out["CASA_BOLSA"].isin(casas)]
    if tipos:
        out = out[out["TIPO"].isin(tipos)]
    return out.reset_index(drop=True)
