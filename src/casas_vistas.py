"""
Datos para las vistas de la sección "Casas de bolsa y fondos de recompra":
perfil consolidado de una casa (todos los fondos que opera) y ficha
individual de un fondo (emisora). Funciones puras de pandas, sin Streamlit.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src import emisoras_casas as ec

PALETA = ["#7030A0", "#0E9A94", "#2063B0", "#C5770F", "#AB3276", "#599234", "#8D481A", "#D15D4D",
          "#4F6D8F", "#9B66C7", "#3F8F6B", "#B5893A", "#6E5A7E", "#2F9FC4"]
GRIS = "#B9B1C2"


def colores_casas(orden: list[str]) -> dict[str, str]:
    """Color fijo por casa según su lugar en la liga; las que pasan de la paleta van en gris."""
    m = {c: PALETA[i] if i < len(PALETA) else GRIS for i, c in enumerate(orden)}
    m["OTRAS"] = GRIS
    return m


def _meses(ini: date, fin: date) -> pd.PeriodIndex:
    return pd.period_range(pd.Timestamp(ini), pd.Timestamp(fin), freq="M")


def base(act: pd.DataFrame, ini: date, fin: date) -> pd.DataFrame:
    a = ec._base(act, ini, fin)
    a["MES"] = a["FECHA_OPERACION"].dt.to_period("M")
    return a


# ---------------------------------------------------------------------------
# Todos los fondos
# ---------------------------------------------------------------------------

def emisoras_por_n_casas(tab: pd.DataFrame) -> pd.Series:
    etiquetas = tab["N_CASAS"].clip(upper=4).map({1: "1 casa", 2: "2 casas", 3: "3 casas", 4: "4 o más"})
    return etiquetas.value_counts().reindex(["1 casa", "2 casas", "3 casas", "4 o más"]).fillna(0).astype(int)


# ---------------------------------------------------------------------------
# Perfil de una casa: todos sus fondos juntos
# ---------------------------------------------------------------------------

def perfil_casa(act: pd.DataFrame, mandatos: pd.DataFrame, casa: str, ini: date, fin: date) -> dict:
    a = base(act, ini, fin)
    meses = _meses(ini, fin)
    ac = a[a["CASA_BOLSA"] == casa]
    tot_mes = a.groupby("MES")["IMPORTE"].sum().reindex(meses, fill_value=0)
    casa_mes = ac.groupby("MES")["IMPORTE"].sum().reindex(meses, fill_value=0)
    emis_mes = ac.groupby("MES")["EMISORA"].nunique().reindex(meses, fill_value=0)
    serie = pd.DataFrame({"MES": meses.to_timestamp(), "IMPORTE": casa_mes.values / 1e6,
                          "PART": np.where(tot_mes.values > 0, 100 * casa_mes.values / np.maximum(tot_mes.values, 1), np.nan),
                          "EMISORAS": emis_mes.values})

    det = ec.detalle(act, ini, fin)
    f = det[det["CASA_BOLSA"] == casa].copy()
    if f.empty:
        return {"serie": serie, "fondos": pd.DataFrame(), "total": 0.0}
    total = f["IMPORTE"].sum()
    f["IMPORTE"] = f["IMPORTE"] / 1e6
    f["PCT_LIBRO"] = 100 * f["IMPORTE"] / f["IMPORTE"].sum()
    f["TICKET"] = f["IMPORTE"] * 1e6 / f["N_OPS"].where(f["N_OPS"] > 0)
    piv = (ac.groupby(["EMISORA", "MES"])["IMPORTE"].sum().unstack().reindex(columns=meses, fill_value=0).fillna(0) / 1e6)
    f["TENDENCIA"] = f["EMISORA"].map(lambda e: [round(v, 2) for v in piv.loc[e].tolist()] if e in piv.index else [])
    m = mandatos.set_index("EMISORA")
    for c in ("SECTOR", "TIPO", "CASA_VIGENTE", "ESTATUS", "REMANENTE"):
        f[c] = f["EMISORA"].map(m[c]) if c in m.columns else None
    f["ES_VIGENTE"] = f["CASA_VIGENTE"] == casa
    f["SECTOR"] = f["SECTOR"].fillna("").astype(str).str.title()
    return {"serie": serie, "fondos": f.sort_values("IMPORTE", ascending=False).reset_index(drop=True), "total": total}


# ---------------------------------------------------------------------------
# Ficha individual de un fondo (emisora)
# ---------------------------------------------------------------------------

def ficha_emisora(act: pd.DataFrame, mercado: pd.DataFrame, emisora: str, ini: date, fin: date) -> dict:
    a = base(act, ini, fin)
    ae = a[a["EMISORA"] == emisora].copy()
    if ae.empty:
        return {}
    ae["SEMANA"] = ae["FECHA_OPERACION"] - pd.to_timedelta(ae["FECHA_OPERACION"].dt.weekday, unit="D")
    semanal = ae.pivot_table(index="SEMANA", columns="CASA_BOLSA", values="IMPORTE", aggfunc="sum").fillna(0) / 1e6
    semanal = semanal[semanal.sum().sort_values(ascending=False).index]

    diario = (ae.groupby(["FECHA_OPERACION", "CASA_BOLSA"])
              .agg(IMPORTE=("IMPORTE", "sum"), N_OPS=("N_OPS", "sum"), ACCIONES=("ACCIONES", "sum")).reset_index())
    diario["IMPORTE"] = diario["IMPORTE"] / 1e6

    comp = ae[ae["TIPO"].astype(str).str.upper().str.startswith("COMPRA")]
    vwap = comp.groupby("FECHA_OPERACION").agg(IMPORTE=("IMPORTE", "sum"), ACCIONES=("ACCIONES", "sum"))
    vwap = (vwap["IMPORTE"] / vwap["ACCIONES"].where(vwap["ACCIONES"] > 0)).dropna().rename("VWAP").reset_index()
    px = pd.DataFrame()
    if mercado is not None and not mercado.empty:
        px = mercado[mercado["EMISORA"] == emisora][["FECHA", "CLOSE"]].copy()
        px["FECHA"] = pd.to_datetime(px["FECHA"])
        px = px[(px["FECHA"].dt.date >= ini) & (px["FECHA"].dt.date <= fin)].dropna().sort_values("FECHA")

    casas = ec.detalle(act, ini, fin)
    casas = casas[casas["EMISORA"] == emisora].copy()
    casas["IMPORTE"] = casas["IMPORTE"] / 1e6
    casas["TICKET"] = casas["IMPORTE"] * 1e6 / casas["N_OPS"].where(casas["N_OPS"] > 0)
    meses = _meses(ini, fin)
    piv = ae.groupby(["CASA_BOLSA", "MES"])["IMPORTE"].sum().unstack().reindex(columns=meses, fill_value=0).fillna(0) / 1e6
    casas["TENDENCIA"] = casas["CASA_BOLSA"].map(lambda c: [round(v, 2) for v in piv.loc[c].tolist()] if c in piv.index else [])

    mensual = ae.groupby("MES").agg(IMPORTE=("IMPORTE", "sum"), N_OPS=("N_OPS", "sum"),
                                    SESIONES=("FECHA_OPERACION", "nunique")).reindex(meses, fill_value=0)
    mensual["IMPORTE"] = mensual["IMPORTE"] / 1e6
    mensual.index = mensual.index.to_timestamp()

    neto_compra = comp["IMPORTE"].sum() / 1e6
    return {"semanal": semanal, "diario": diario, "vwap": vwap, "precio": px, "casas": casas.reset_index(drop=True),
            "mensual": mensual.reset_index(names="MES"), "sesiones": ae["FECHA_OPERACION"].nunique(),
            "importe": ae["IMPORTE"].sum() / 1e6, "compras": neto_compra, "n_ops": ae["N_OPS"].sum(),
            "ultima": ae["FECHA_OPERACION"].max().date()}
