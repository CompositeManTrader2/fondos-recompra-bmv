"""
Métricas y señales por emisora para decidir (sobre resumen_diario).

Calendario: las "sesiones" son las fechas en las que al menos una emisora
reportó recompra (proxy robusto de días hábiles de la BMV).

Por emisora, a una fecha de referencia:
  IMPORTE_DIA, OPS_DIA, ACC_DIA, VWAP_DIA, PRIMA_DIA (%), PCT_VOL_DIA (%)
  PROM_20       importe promedio por sesión en las 20 sesiones PREVIAS
  INTENSIDAD    IMPORTE_DIA / PROM_20 (veces)
  ACELERACION   promedio 5 sesiones (incl. hoy) / PROM_20
  RACHA         sesiones consecutivas recomprando hasta hoy
  SIN_RECOMPRA  sesiones desde la última recompra (0 = hoy)
  IMPORTE_20, NETO_20 (acciones compra − venta), PCT_CIRC_20 (% de circulación)
  REMANENTE     recursos restantes del fondo (último reporte)
  RUNWAY        sesiones de fondo al ritmo de PROM_20 (REMANENTE / PROM_20)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sesiones(resumen: pd.DataFrame) -> list[pd.Timestamp]:
    return sorted(pd.to_datetime(resumen["FECHA"]).unique())


def metricas(resumen: pd.DataFrame, fecha_ref: pd.Timestamp) -> pd.DataFrame:
    if resumen is None or resumen.empty:
        return pd.DataFrame()
    fecha_ref = pd.Timestamp(fecha_ref)
    ses = [s for s in sesiones(resumen) if s <= fecha_ref]
    if not ses:
        return pd.DataFrame()
    idx = {s: i for i, s in enumerate(ses)}
    ult60 = set(ses[-60:])
    previas20 = ses[-21:-1]
    ult5, ult20 = ses[-5:], ses[-20:]

    r = resumen[resumen["FECHA"].isin(ult60)].copy()
    r["COMPRA"] = pd.to_numeric(r.get("ACCIONES_COMPRA"), errors="coerce").fillna(0)
    r["VENTA"] = pd.to_numeric(r.get("ACCIONES_VENTA"), errors="coerce").fillna(0)
    filas = []
    for emi, g in r.groupby("EMISORA"):
        g = g.sort_values("FECHA")
        hoy = g[g["FECHA"] == fecha_ref]
        imp_hoy = float(hoy["IMPORTE"].sum()) if not hoy.empty else 0.0
        prom20 = g[g["FECHA"].isin(previas20)]["IMPORTE"].sum() / max(len(previas20), 1)
        prom5 = g[g["FECHA"].isin(ult5)]["IMPORTE"].sum() / max(len(ult5), 1)
        g20 = g[g["FECHA"].isin(ult20)]
        # racha y días sin recompra (en sesiones de mercado)
        activos = {idx[f] for f in g["FECHA"] if f in idx and g.loc[g["FECHA"] == f, "IMPORTE"].sum() > 0}
        n = len(ses) - 1
        racha, k = 0, n
        while k in activos:
            racha += 1; k -= 1
        ult_activo = max(activos) if activos else None
        sin = (n - ult_activo) if ult_activo is not None else None
        # remanente: último conocido
        rem = pd.to_numeric(g["REMANENTE_PRESENTE"], errors="coerce").dropna()
        remanente = float(rem.iloc[-1]) if len(rem) else np.nan
        circ = pd.to_numeric(g.get("CIRCULACION"), errors="coerce").dropna()
        circ_ult = float(circ.iloc[-1]) if len(circ) else np.nan
        serie = g["SERIE"].dropna().iloc[-1] if "SERIE" in g and g["SERIE"].notna().any() else ""
        casa = g20["CASA_PRINCIPAL"].dropna().mode() if "CASA_PRINCIPAL" in g20 else pd.Series(dtype=str)
        filas.append({
            "EMISORA": emi,
            "SERIE": serie,
            "IMPORTE_DIA": imp_hoy,
            "OPS_DIA": float(hoy["OPERACIONES"].sum()) if not hoy.empty else 0.0,
            "ACC_DIA": float(hoy["ACCIONES"].sum()) if not hoy.empty else 0.0,
            "VWAP_DIA": float(hoy["VWAP"].iloc[0]) if not hoy.empty else np.nan,
            "PRIMA_DIA": float(pd.to_numeric(hoy.get("PRIMA_PCT"), errors="coerce").iloc[0]) if not hoy.empty and "PRIMA_PCT" in hoy else np.nan,
            "PCT_VOL_DIA": float(pd.to_numeric(hoy.get("PCT_VOLUMEN"), errors="coerce").iloc[0]) if not hoy.empty and "PCT_VOLUMEN" in hoy else np.nan,
            "PROM_20": float(prom20),
            "INTENSIDAD": imp_hoy / prom20 if prom20 > 0 else (np.inf if imp_hoy > 0 else np.nan),
            "ACELERACION": prom5 / prom20 if prom20 > 0 else (np.inf if prom5 > 0 else np.nan),
            "RACHA": racha,
            "SIN_RECOMPRA": sin,
            "SESIONES_20": int(g20["FECHA"].nunique()),
            "IMPORTE_20": float(g20["IMPORTE"].sum()),
            "NETO_20": float(g20["COMPRA"].sum() - g20["VENTA"].sum()),
            "PCT_CIRC_20": 100 * g20["COMPRA"].sum() / circ_ult if circ_ult and circ_ult > 0 else np.nan,
            "REMANENTE": remanente,
            "RUNWAY": remanente / prom20 if prom20 > 0 and remanente == remanente else np.nan,
            "CASA": casa.iat[0] if len(casa) else None,
            "PRIMERA": g["FECHA"].min(),
        })
    m = pd.DataFrame(filas)
    primera_hist = resumen.groupby("EMISORA")["FECHA"].min()
    m["PRIMERA_HIST"] = m["EMISORA"].map(primera_hist)
    return m.sort_values(["IMPORTE_DIA", "IMPORTE_20"], ascending=False).reset_index(drop=True)


def tarjetas(m: pd.DataFrame, sesiones_hist: int) -> list[dict]:
    """Señales accionables a partir de metricas()."""
    if m.empty:
        return []
    fmt = lambda s: [f"{e}" for e in s]
    hoy = m[m["IMPORTE_DIA"] > 0]
    inusual = hoy[(hoy["INTENSIDAD"] >= 2.5) & (hoy["PROM_20"] > 0)].sort_values("INTENSIDAD", ascending=False)
    acel = m[(m["ACELERACION"] >= 1.5) & (m["PROM_20"] > 0) & (m["SIN_RECOMPRA"] == 0)].sort_values("ACELERACION", ascending=False)
    reanudan = hoy[(hoy["PROM_20"] == 0)]
    pausa = m[(m["SESIONES_20"] >= 5) & (m["SIN_RECOMPRA"].fillna(0) >= 5)]
    runway = m[(m["RUNWAY"] < 20) & (m["SIN_RECOMPRA"].fillna(99) <= 5)].sort_values("RUNWAY")
    venta = m[m["NETO_20"] < 0].sort_values("NETO_20")
    prima = hoy[hoy["PRIMA_DIA"] > 0.5].sort_values("PRIMA_DIA", ascending=False)
    nota_hist = "" if sesiones_hist >= 21 else " (historial aún corto: se afina con el backfill)"
    return [
        {"titulo": "Volumen inusual hoy", "tipo": "buy",
         "descripcion": "Importe ≥ 2.5× su promedio de 20 sesiones" + nota_hist,
         "items": [f"{e} {x:.1f}×" for e, x in zip(inusual["EMISORA"], inusual["INTENSIDAD"])]},
        {"titulo": "Acelerando", "tipo": "buy",
         "descripcion": "Ritmo de 5 sesiones ≥ 1.5× el de 20 y compró hoy",
         "items": [f"{e} {x:.1f}×" for e, x in zip(acel["EMISORA"], acel["ACELERACION"])]},
        {"titulo": "Inician o reanudan", "tipo": "info",
         "descripcion": "Recompraron hoy sin actividad en las 20 sesiones previas",
         "items": fmt(reanudan["EMISORA"])},
        {"titulo": "Pagando prima vs cierre", "tipo": "info",
         "descripcion": "VWAP de compra > 0.5% arriba del cierre del día",
         "items": [f"{e} {x:+.1f}%" for e, x in zip(prima["EMISORA"], prima["PRIMA_DIA"])]},
        {"titulo": "En pausa", "tipo": "warn",
         "descripcion": "Activas en 20 sesiones pero sin recomprar en las últimas 5",
         "items": [f"{e} {int(s)}s" for e, s in zip(pausa["EMISORA"], pausa["SIN_RECOMPRA"])]},
        {"titulo": "Fondo por agotarse", "tipo": "warn",
         "descripcion": "Menos de 20 sesiones de remanente al ritmo actual",
         "items": [f"{e} {x:.0f}s" for e, x in zip(runway["EMISORA"], runway["RUNWAY"])]},
        {"titulo": "Venta neta (20 sesiones)", "tipo": "sell",
         "descripcion": "Vendieron más acciones de las que compraron",
         "items": fmt(venta["EMISORA"])},
    ]
