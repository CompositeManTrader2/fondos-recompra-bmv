"""Rankings de emisoras y consulta histórica de recompras."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from src import market_store, theme as T, visualizations as viz

VENTANAS = {"1M": 31, "3M": 92, "6M": 183, "YTD": None, "1A": 365, "TODO": 100000}

T.header("RANK", "Rankings e historial", "Comparativo entre emisoras y consulta histórica")
resumen = market_store.resumen_diario()
if resumen.empty:
    st.info("Aún no hay datos de mercado.")
    st.stop()

fin = resumen["FECHA"].max()
ventana = st.segmented_control("Ventana", list(VENTANAS), default="3M") or "3M"
desde = pd.Timestamp(fin.year, 1, 1) if ventana == "YTD" else fin - timedelta(days=VENTANAS[ventana])
win = resumen[(resumen["FECHA"] > desde) & (resumen["FECHA"] <= fin)]


def _agregar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.assign(PV=df["VWAP"] * df["ACCIONES"]).groupby("EMISORA").agg(
        IMPORTE=("IMPORTE", "sum"), OPERACIONES=("OPERACIONES", "sum"), ACCIONES=("ACCIONES", "sum"),
        PV=("PV", "sum"), DIAS=("FECHA", "nunique"), ULTIMA=("FECHA", "max"),
        COMPRA=("ACCIONES_COMPRA", "sum"), VENTA=("ACCIONES_VENTA", "sum"),
        PRIMA=("PRIMA_PCT", "mean"), PCT_VOL=("PCT_VOLUMEN", "mean"),
    ).reset_index()
    g["VWAP"] = g["PV"] / g["ACCIONES"].where(g["ACCIONES"] > 0)
    g["NETO"] = g["COMPRA"] - g["VENTA"]
    return g.drop(columns="PV").sort_values("IMPORTE", ascending=False)


agg = _agregar(win)
tab_rank, tab_hist = st.tabs(["Rankings", "Historial"])

with tab_rank:
    r1, r2 = st.columns([1, 1.1])
    with r1:
        metrica = st.segmented_control("Métrica", ["IMPORTE", "OPERACIONES", "ACCIONES", "DIAS"],
                                       default="IMPORTE", format_func=lambda x: {"DIAS": "SESIONES"}.get(x, x)) or "IMPORTE"
        st.plotly_chart(viz.grafica_ranking_emisoras(agg, metrica=metrica, top=15), width="stretch")
    with r2:
        T.seccion(f"Tabla {ventana}", f"{len(agg)} emisoras")
        st.dataframe(
            agg[["EMISORA", "IMPORTE", "DIAS", "VWAP", "PRIMA", "PCT_VOL", "NETO", "ULTIMA"]],
            hide_index=True, width="stretch", height=560,
            column_config={
                "EMISORA": st.column_config.TextColumn("Emisora", pinned=True),
                "IMPORTE": st.column_config.NumberColumn("Importe", format="$%,.0f"),
                "DIAS": st.column_config.NumberColumn("Sesiones", format="%d"),
                "VWAP": st.column_config.NumberColumn("VWAP", format="$%.4f"),
                "PRIMA": st.column_config.NumberColumn("Prom. vs cierre", format="%+.2f%%"),
                "PCT_VOL": st.column_config.NumberColumn("Prom. % volumen", format="%.1f%%"),
                "NETO": st.column_config.NumberColumn("Neto acciones", format="%+,.0f"),
                "ULTIMA": st.column_config.DateColumn("Última", format="DD/MM/YY"),
            },
        )
    primera = resumen.groupby("EMISORA")["FECHA"].min()
    nuevas = primera[(primera > desde) & (primera <= fin)].sort_values(ascending=False)
    T.seccion("Emisoras que empezaron a recomprar en la ventana", f"{len(nuevas)}")
    st.markdown(" ".join(T.pill(f"{e} · {f:%d-%b}", "warn") for e, f in nuevas.items()) or
                "Ninguna según el historial disponible.", unsafe_allow_html=True)

with tab_hist:
    h1, h2 = st.columns([2, 1])
    sel = h1.multiselect("Emisoras (máx. 8 en la gráfica)", sorted(resumen["EMISORA"].unique()),
                         default=agg["EMISORA"].head(5).tolist())
    rango = h2.date_input("Rango", value=(desde.date() + timedelta(days=1), fin.date()),
                          min_value=resumen["FECHA"].min().date(), max_value=fin.date())
    h = resumen
    if isinstance(rango, tuple) and len(rango) == 2:
        h = h[(h["FECHA"] >= pd.Timestamp(rango[0])) & (h["FECHA"] <= pd.Timestamp(rango[1]))]
    if sel:
        h = h[h["EMISORA"].isin(sel)]
        st.plotly_chart(viz.grafica_acumulado_emisoras(h, sel), width="stretch")
    cols = [c for c in ["FECHA", "EMISORA", "SERIE", "IMPORTE", "OPERACIONES", "ACCIONES", "VWAP", "CLOSE", "PRIMA_PCT",
                        "PCT_VOLUMEN", "CASA_PRINCIPAL", "REMANENTE_PRESENTE"] if c in h]
    st.dataframe(
        h.sort_values(["FECHA", "IMPORTE"], ascending=[False, False])[cols], hide_index=True, width="stretch",
        column_config={
            "FECHA": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "IMPORTE": st.column_config.NumberColumn("Importe", format="$%,.0f"),
            "ACCIONES": st.column_config.NumberColumn("Acciones", format="%,.0f"),
            "VWAP": st.column_config.NumberColumn("VWAP", format="$%.4f"),
            "CLOSE": st.column_config.NumberColumn("Cierre", format="$%.2f"),
            "PRIMA_PCT": st.column_config.NumberColumn("vs cierre", format="%+.2f%%"),
            "PCT_VOLUMEN": st.column_config.NumberColumn("% volumen", format="%.1f%%"),
            "REMANENTE_PRESENTE": st.column_config.NumberColumn("Remanente", format="$%,.0f"),
        },
    )
    st.download_button("Descargar historial (CSV)", h[cols].to_csv(index=False).encode("utf-8"),
                       icon=":material/download:", file_name=f"recompras_bmv_{datetime.now():%Y%m%d}.csv", mime="text/csv")
