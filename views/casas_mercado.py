"""Casas de bolsa en el mercado de recompras: participación, ranking y oportunidades."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from src import market_store, theme as T, visualizations as viz

PUNTO = "PUNTO"
VENTANAS = {"1M": 31, "3M": 92, "6M": 183, "YTD": None, "1A": 365, "TODO": 100000}

T.header("BRKR", "Casas de bolsa", "Quién ejecuta las recompras del mercado")

act = market_store.actividad()
if act.empty:
    st.info("Aún no hay tabla de actividad. Se genera con el scanner diario.")
    st.stop()

c1, c2 = st.columns([2, 1])
ventana = c1.segmented_control("Ventana", list(VENTANAS), default="3M") or "3M"
casas_all = sorted(act["CASA_BOLSA"].dropna().unique())
destacar = c2.selectbox("Casa a resaltar", casas_all, index=casas_all.index(PUNTO) if PUNTO in casas_all else 0)

fin = act["FECHA_OPERACION"].max()
desde = pd.Timestamp(fin.year, 1, 1) if ventana == "YTD" else fin - timedelta(days=VENTANAS[ventana])
w = act[(act["FECHA_OPERACION"] > desde) & (act["FECHA_OPERACION"] <= fin)]
dur = (fin - desde)
w_prev = act[(act["FECHA_OPERACION"] > desde - dur) & (act["FECHA_OPERACION"] <= desde)]


def _liga(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["CASA_BOLSA", "IMPORTE", "PART", "EMISORAS", "SESIONES", "TOP"])
    g = df.groupby("CASA_BOLSA").agg(IMPORTE=("IMPORTE", "sum"), EMISORAS=("EMISORA", "nunique"),
                                     SESIONES=("FECHA_OPERACION", "nunique")).reset_index()
    g["PART"] = 100 * g["IMPORTE"] / g["IMPORTE"].sum()
    top = (df.groupby(["CASA_BOLSA", "EMISORA"])["IMPORTE"].sum().reset_index()
           .sort_values("IMPORTE", ascending=False).groupby("CASA_BOLSA")["EMISORA"]
           .apply(lambda s: ", ".join(s.head(4))))
    g["TOP"] = g["CASA_BOLSA"].map(top)
    g = g.sort_values("IMPORTE", ascending=False).reset_index(drop=True)
    g.insert(0, "RANK", range(1, len(g) + 1))
    return g


liga, liga_prev = _liga(w), _liga(w_prev)
fila = liga[liga["CASA_BOLSA"] == destacar]
fila_prev = liga_prev[liga_prev["CASA_BOLSA"] == destacar]
part = float(fila["PART"].iat[0]) if len(fila) else 0.0
part_prev = float(fila_prev["PART"].iat[0]) if len(fila_prev) else None
d_part = part - part_prev if part_prev is not None else None
T.tiles([
    {"label": f"Posición {destacar}", "value": f"#{int(fila['RANK'].iat[0])}" if len(fila) else "—",
     "sub": f"de {len(liga)} casas activas"},
    {"label": f"Participación {destacar}", "value": f"{part:.1f}%",
     "delta": f"{d_part:+.1f} pp vs periodo previo" if d_part is not None else None, "dir": T.dir_de(d_part)},
    {"label": f"Importe {destacar}", "value": T.fmt_mxn(fila["IMPORTE"].iat[0]) if len(fila) else "$0"},
    {"label": f"Emisoras atendidas", "value": f"{int(fila['EMISORAS'].iat[0])}" if len(fila) else "0",
     "sub": fila["TOP"].iat[0] if len(fila) else ""},
    {"label": f"Importe mercado {ventana}", "value": T.fmt_mxn(w["IMPORTE"].sum()),
     "sub": f"{w['EMISORA'].nunique()} emisoras · {w['FECHA_OPERACION'].nunique()} sesiones"},
])

izq, der = st.columns([1.1, 1])
with izq:
    st.plotly_chart(viz.grafica_liga_casas(liga, destacar=destacar), width="stretch")
with der:
    top_casas = [destacar] + [c for c in liga["CASA_BOLSA"] if c != destacar][:5]
    st.plotly_chart(viz.grafica_participacion_semanal(w, top_casas), width="stretch")

T.seccion("Liga de casas de bolsa", f"ventana {ventana}")
st.dataframe(
    liga, hide_index=True, width="stretch",
    column_config={
        "RANK": st.column_config.NumberColumn("#", format="%d", width="small"),
        "CASA_BOLSA": st.column_config.TextColumn("Casa", pinned=True),
        "IMPORTE": st.column_config.NumberColumn("Importe", format="$%,.0f"),
        "PART": st.column_config.ProgressColumn("Participación", format="%.1f%%", min_value=0, max_value=100),
        "EMISORAS": st.column_config.NumberColumn("Emisoras", format="%d"),
        "SESIONES": st.column_config.NumberColumn("Sesiones", format="%d"),
        "TOP": st.column_config.TextColumn("Principales emisoras", width="large"),
    },
)

T.seccion("Oportunidades comerciales", f"emisoras recomprando en la ventana sin {destacar}")
por_emi = w.groupby("EMISORA").agg(
    IMPORTE=("IMPORTE", "sum"), SESIONES=("FECHA_OPERACION", "nunique"), ULTIMA=("FECHA_OPERACION", "max"),
    CASAS=("CASA_BOLSA", lambda s: ", ".join(sorted(s.unique()))),
).reset_index()
con_destacada = set(w.loc[w["CASA_BOLSA"] == destacar, "EMISORA"])
oport = por_emi[~por_emi["EMISORA"].isin(con_destacada)].sort_values("IMPORTE", ascending=False)
st.caption(f"{len(oport)} emisoras con fondo de recompra activo ejecutado por otras casas. "
           "Ordenadas por importe: son los mandatos más grandes a buscar.")
st.dataframe(
    oport, hide_index=True, width="stretch",
    column_config={
        "EMISORA": st.column_config.TextColumn("Emisora", pinned=True),
        "IMPORTE": st.column_config.NumberColumn("Importe ventana", format="$%,.0f"),
        "SESIONES": st.column_config.NumberColumn("Sesiones activas", format="%d"),
        "ULTIMA": st.column_config.DateColumn("Última recompra", format="DD/MM/YYYY"),
        "CASAS": st.column_config.TextColumn("Casa(s) actual(es)"),
    },
)

T.seccion("Quién ejecuta para quién")
st.plotly_chart(viz.grafica_matriz_casas(w), width="stretch")
