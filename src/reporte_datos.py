"""
Cálculos del reporte mensual "Net Buybacks" (todas las emisoras de la BMV).

Definiciones
------------
- Recompra neta (MXN)  = importe de compras − importe de ventas del fondo.
- Acciones netas       = acciones compradas − acciones vendidas.
- Buyback yield        = acciones netas / acciones en circulación (del PDF de BMV).
- Yield sectorial      = recompra neta del sector / valor de mercado del sector
                         (circulación × cierre de Yahoo Finance a la fecha de corte).
- Cobertura            = fecha desde la que el scanner tiene TODO el mercado
                         (primer reporte del registro). Un periodo que empieza
                         antes se marca "n.d." en lugar de mostrar cifras parciales.

Insumos (data/daily): actividad.parquet, documentos.parquet, mercado.parquet,
y data/sectores.csv (editable).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DAILY = REPO / "data" / "daily"
SECTORES_CSV = REPO / "data" / "sectores.csv"
ORDEN_SECTORES = ["RETAIL", "METALS AND MINING", "MEDIA AND TELECOM", "CONSUMER STAPLES", "FINANCIALS",
                  "BUILDING MATERIALS", "ENERGY", "CAPITAL GOODS", "INFRASTRUCTURE", "PETROCHEMICALS",
                  "OTHERS", "REAL ESTATE", "HOUSING"]
TOLERANCIA_COBERTURA = timedelta(days=10)


# ---------------------------------------------------------------------------
# Insumos
# ---------------------------------------------------------------------------

def _a_float(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        if pd.api.types.is_extension_array_dtype(df[c].dtype) and pd.api.types.is_numeric_dtype(df[c].dtype):
            df[c] = df[c].astype("float64")
    return df


def cargar_locales() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(actividad, documentos, mercado) desde data/daily del checkout local."""
    leer = lambda n: _a_float(pd.read_parquet(DAILY / n)) if (DAILY / n).exists() else pd.DataFrame()
    return leer("actividad.parquet"), leer("documentos.parquet"), leer("mercado.parquet")


def sectores() -> dict[str, str]:
    if not SECTORES_CSV.exists():
        return {}
    s = pd.read_csv(SECTORES_CSV)
    return dict(zip(s["EMISORA"].str.upper().str.strip(), s["SECTOR"].str.upper().str.strip()))


# ---------------------------------------------------------------------------
# Periodos y cobertura
# ---------------------------------------------------------------------------

@dataclass
class Periodo:
    clave: str
    etiqueta: str
    ini: date
    fin: date


def periodos(corte: date) -> dict[str, Periodo]:
    y = corte.year
    try:
        corte_ant = corte.replace(year=y - 1)
    except ValueError:            # 29-feb
        corte_ant = corte.replace(year=y - 1, day=28)
    return {
        "Y2": Periodo("Y2", f"{y - 2} 12M", date(y - 2, 1, 1), date(y - 2, 12, 31)),
        "Y1": Periodo("Y1", f"{y - 1} 12M", date(y - 1, 1, 1), date(y - 1, 12, 31)),
        "LTM": Periodo("LTM", f"{y} Last 12M", corte - timedelta(days=364), corte),
        "YTD1": Periodo("YTD1", f"{y - 1} YTD", date(y - 1, 1, 1), corte_ant),
        "YTD": Periodo("YTD", f"{y} YTD", date(y, 1, 1), corte),
    }


def cobertura(docs: pd.DataFrame) -> date | None:
    """Fecha desde la que el registro del scanner cubre todo el mercado."""
    if docs is None or docs.empty:
        return None
    col = "FECHA_REPORTE" if "FECHA_REPORTE" in docs and docs["FECHA_REPORTE"].notna().any() else "FECHA_OPERACION"
    return pd.to_datetime(docs[col]).min().date()


def cubierto(p_ini: date, cob: date | None) -> bool:
    return cob is not None and p_ini >= cob - TOLERANCIA_COBERTURA


# ---------------------------------------------------------------------------
# Bases por emisora
# ---------------------------------------------------------------------------

def _con_signo(act: pd.DataFrame) -> pd.DataFrame:
    a = act.copy()
    a["FECHA_OPERACION"] = pd.to_datetime(a["FECHA_OPERACION"])
    signo = a["TIPO"].map({"COMPRA": 1.0, "VENTA": -1.0}).fillna(0.0)
    a["NETO_MXN"] = a["IMPORTE"].fillna(0) * signo
    a["NETO_ACC"] = a["ACCIONES"].fillna(0) * signo
    es_c, es_v = a["TIPO"] == "COMPRA", a["TIPO"] == "VENTA"
    a["C_MXN"], a["C_ACC"] = a["IMPORTE"].where(es_c, 0), a["ACCIONES"].where(es_c, 0)
    a["V_MXN"], a["V_ACC"] = a["IMPORTE"].where(es_v, 0), a["ACCIONES"].where(es_v, 0)
    return a


def neto(a: pd.DataFrame, ini: date, fin: date) -> pd.DataFrame:
    """Por emisora: neto MXN/acciones y compras/ventas en el periodo [ini, fin]."""
    m = a[(a["FECHA_OPERACION"].dt.date >= ini) & (a["FECHA_OPERACION"].dt.date <= fin)]
    return m.groupby("EMISORA")[["NETO_MXN", "NETO_ACC", "C_MXN", "C_ACC", "V_MXN", "V_ACC"]].sum()


def circulacion(docs: pd.DataFrame, corte: date) -> pd.Series:
    """Acciones en circulación por emisora: último dato ≤ corte (si no, el más reciente)."""
    if docs.empty or "CIRCULACION" not in docs:
        return pd.Series(dtype=float)
    d = docs.dropna(subset=["CIRCULACION"]).copy()
    d = d[d["CIRCULACION"] > 0]
    d["F"] = pd.to_datetime(d["FECHA_OPERACION"]).dt.date
    previo = d[d["F"] <= corte].sort_values("ID").groupby("EMISORA")["CIRCULACION"].last()
    cualquiera = d.sort_values("ID").groupby("EMISORA")["CIRCULACION"].last()
    return previo.combine_first(cualquiera)


def remanente(docs: pd.DataFrame, corte: date) -> pd.Series:
    if docs.empty or "REMANENTE_PRESENTE" not in docs:
        return pd.Series(dtype=float)
    d = docs.dropna(subset=["REMANENTE_PRESENTE"]).copy()
    d = d[pd.to_datetime(d["FECHA_OPERACION"]).dt.date <= corte]
    return d.sort_values("ID").groupby("EMISORA")["REMANENTE_PRESENTE"].last()


def cierre(mercado: pd.DataFrame, corte: date) -> pd.Series:
    if mercado is None or mercado.empty:
        return pd.Series(dtype=float)
    m = mercado.copy()
    m = m[pd.to_datetime(m["FECHA"]).dt.date <= corte].dropna(subset=["CLOSE"])
    return m.sort_values("FECHA").groupby("EMISORA")["CLOSE"].last()


# ---------------------------------------------------------------------------
# Secciones del reporte
# ---------------------------------------------------------------------------

@dataclass
class Datos:
    corte: date
    cobertura: date | None
    periodos: dict
    sectores: pd.DataFrame        # filas = sector + TOTAL
    top_yield_ltm: pd.DataFrame
    top_compradores_ltm: pd.DataFrame
    mensual: pd.DataFrame
    ranking_ytd: pd.DataFrame
    ranking_5y: pd.DataFrame
    detalle: pd.DataFrame
    anios: list[int]
    ini_5y: date


def preparar(actividad: pd.DataFrame, docs: pd.DataFrame, mercado: pd.DataFrame, corte: date) -> Datos:
    a = _con_signo(actividad[pd.to_datetime(actividad["FECHA_OPERACION"]).dt.date <= corte])
    cob = cobertura(docs)
    per = periodos(corte)
    circ = circulacion(docs, corte)
    precio = cierre(mercado, corte)
    mcap = (circ * precio).dropna()
    mapa = sectores()
    sector_de = lambda e: mapa.get(e, "OTHERS")

    # --- Tabla por sector ---
    filas = []
    netos = {k: neto(a, p.ini, p.fin) for k, p in per.items()}
    univ = pd.DataFrame({"MCAP": mcap})
    univ["SECTOR"] = [sector_de(e) for e in univ.index]
    mcap_sector = univ.groupby("SECTOR")["MCAP"].sum()
    for sec in ORDEN_SECTORES + ["TOTAL"]:
        fila = {"SECTOR": sec}
        for k, p in per.items():
            n = netos[k]
            emis = n.index if sec == "TOTAL" else [e for e in n.index if sector_de(e) == sec]
            sub = n.loc[list(emis)] if len(emis) else n.iloc[0:0]
            ok = cubierto(p.ini, cob)
            monto = sub["NETO_MXN"].sum() / 1e6 if ok else np.nan
            con_mcap = [e for e in sub.index if e in mcap.index]
            den = mcap.sum() if sec == "TOTAL" else mcap_sector.get(sec, np.nan)
            fila[f"{k}_MONTO"] = monto
            fila[f"{k}_YIELD"] = (100 * sub.loc[con_mcap, "NETO_MXN"].sum() / den) if ok and den and den > 0 else np.nan
            fila[f"{k}_EMIS"] = int((sub["C_ACC"] > 0).sum()) if ok else np.nan
        for k_act, k_ant in (("Y1", "Y2"), ("YTD", "YTD1")):
            act_, ant_ = fila[f"{k_act}_MONTO"], fila[f"{k_ant}_MONTO"]
            fila[f"{k_act}_YOY"] = (100 * (act_ / ant_ - 1)) if pd.notna(act_) and pd.notna(ant_) and ant_ not in (0,) else np.nan
            if pd.notna(act_) and pd.notna(ant_) and ant_ < 0:
                fila[f"{k_act}_YOY"] = np.nan           # variación sobre base negativa no es interpretable
        filas.append(fila)
    tab_sec = pd.DataFrame(filas)
    # Sectores sin ninguna actividad en ningún periodo se omiten (salvo TOTAL)
    montos = tab_sec[[c for c in tab_sec if c.endswith("_MONTO")]].abs().sum(axis=1)
    tab_sec = tab_sec[(montos > 0) | (tab_sec["SECTOR"] == "TOTAL")].reset_index(drop=True)

    # --- LTM: top yield y top compradores ---
    ltm = netos["LTM"].copy()
    ltm["YIELD"] = 100 * ltm["NETO_ACC"] / circ.reindex(ltm.index)
    ltm["PRECIO_PROM"] = ltm["C_MXN"] / ltm["C_ACC"].where(ltm["C_ACC"] > 0)
    top_yield = ltm.dropna(subset=["YIELD"]).sort_values("YIELD", ascending=False).head(20)
    top_comp = ltm.sort_values("NETO_MXN", ascending=False).head(20)

    # --- Mensual: 13 meses (excluye el mes en curso si el corte es a inicio de mes) ---
    ult_mes = pd.Timestamp(corte).to_period("M")
    if corte.day < 25:
        ult_mes -= 1
    meses = pd.period_range(ult_mes - 12, ult_mes, freq="M")
    a["MES"] = a["FECHA_OPERACION"].dt.to_period("M")
    am = a[a["MES"].isin(meses)]
    por_mes = am.groupby(["MES", "EMISORA"])[["NETO_MXN", "NETO_ACC"]].sum().reset_index()
    por_mes["YIELD"] = 100 * por_mes["NETO_ACC"] / por_mes["EMISORA"].map(circ)
    filas_m = []
    for mes in meses:
        g = por_mes[por_mes["MES"] == mes]
        ok = cubierto(mes.start_time.date(), cob)
        top3 = g.dropna(subset=["YIELD"]).sort_values("YIELD", ascending=False).head(3)
        filas_m.append({"MES": mes, "NETO_MXN": g["NETO_MXN"].sum() / 1e6 if ok else np.nan,
                        "TOP": [(e, y) for e, y in zip(top3["EMISORA"], top3["YIELD"])] if ok else []})
    mensual = pd.DataFrame(filas_m)

    # --- Rankings ---
    def _ranking(ini: date, fin: date) -> pd.DataFrame:
        n = neto(a, ini, fin)
        r = pd.DataFrame({"MONTO": n["NETO_MXN"] / 1e6, "YIELD": 100 * n["NETO_ACC"] / circ.reindex(n.index)})
        return r[(r["MONTO"].abs() >= 0.5) | (r["YIELD"].abs() >= 0.05)]
    rk_ytd = _ranking(per["YTD"].ini, corte)
    ini_5y = date(corte.year - 4, 1, 1)
    ini_5y_real = max(ini_5y, cob) if cob else ini_5y
    rk_5y = _ranking(ini_5y_real, corte)

    # --- Detalle por emisora (orden: yield 5 años) ---
    anios = list(range(corte.year - 4, corte.year + 1))
    det = pd.DataFrame(index=sorted(set(a["EMISORA"])))
    for y in anios:
        ini, fin = date(y, 1, 1), min(date(y, 12, 31), corte)
        n = neto(a, ini, fin).reindex(det.index).fillna(0)
        ok = cubierto(ini, cob) or (cob is not None and fin >= cob and y == corte.year)
        det[f"Y{y}"] = (100 * n["NETO_ACC"] / circ.reindex(det.index)) if ok else np.nan
        det[f"M{y}"] = (n["NETO_MXN"] / 1e6) if ok else np.nan
        det[f"A{y}"] = (n["NETO_ACC"] / 1e6) if ok else np.nan
    tot = neto(a, ini_5y_real, corte).reindex(det.index).fillna(0)
    det["YTOT"] = 100 * tot["NETO_ACC"] / circ.reindex(det.index)
    det["MTOT"] = tot["NETO_MXN"] / 1e6
    det["ATOT"] = tot["NETO_ACC"] / 1e6
    ytd = netos["YTD"].reindex(det.index)
    det["PX_COMPRA"] = ytd["C_MXN"] / ytd["C_ACC"].where(ytd["C_ACC"] > 0)
    det["PX_VENTA"] = ytd["V_MXN"] / ytd["V_ACC"].where(ytd["V_ACC"] > 0)
    det["REMANENTE"] = remanente(docs, corte).reindex(det.index) / 1e6
    det = det[(det["MTOT"].abs() >= 0.5) | (det[[f"M{y}" for y in anios]].abs().sum(axis=1) >= 0.5)]
    det = det.sort_values(["YTOT", "MTOT"], ascending=False, na_position="last")

    return Datos(corte=corte, cobertura=cob, periodos=per, sectores=tab_sec, top_yield_ltm=top_yield,
                 top_compradores_ltm=top_comp, mensual=mensual, ranking_ytd=rk_ytd, ranking_5y=rk_5y,
                 detalle=det, anios=anios, ini_5y=ini_5y_real)
