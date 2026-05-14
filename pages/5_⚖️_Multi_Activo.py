"""Página: comparativo multi-activo."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import data_processor, storage, visualizations as viz

st.set_page_config(page_title="Multi-Activo", page_icon="⚖️", layout="wide")
st.title("⚖️ Comparativo multi-activo")

activos = storage.listar_activos()
tickers_disponibles = [a["ticker"] for a in activos if a["n_operaciones"] > 0]

if len(tickers_disponibles) < 2:
    st.info("Necesitas al menos **2 activos** con operaciones cargadas para comparar.")
    st.stop()

seleccion = st.multiselect(
    "Selecciona activos a comparar",
    tickers_disponibles,
    default=tickers_disponibles[: min(4, len(tickers_disponibles))],
)
if not seleccion:
    st.stop()

metrica = st.selectbox(
    "Métrica diaria",
    ["IMPORTE", "OPERACIONES", "ACCIONES", "VWAP"],
    index=0,
)

series = {}
filas_resumen = []
for t in seleccion:
    df = data_processor.consolidar_operaciones(storage.cargar_operaciones(t))
    if df.empty:
        continue
    diarios = data_processor.estadisticos_por_periodo(df, "FECHA")
    series[t] = diarios
    total = data_processor.total_global(df)
    filas_resumen.append({
        "Ticker": t,
        "Operaciones": int(total["OPERACIONES"]),
        "Acciones": int(total["ACCIONES"]),
        "Importe": float(total["IMPORTE"]),
        "VWAP": float(total["VWAP"]) if pd.notna(total["VWAP"]) else None,
        "VWAP Compra": float(total["VWAP_COMPRA"]) if pd.notna(total["VWAP_COMPRA"]) else None,
        "VWAP Venta": float(total["VWAP_VENTA"]) if pd.notna(total["VWAP_VENTA"]) else None,
        "Inicio": df["FECHA_OPERACION"].min(),
        "Fin": df["FECHA_OPERACION"].max(),
    })

st.dataframe(
    pd.DataFrame(filas_resumen),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Importe": st.column_config.NumberColumn("Importe", format="$%d"),
        "VWAP": st.column_config.NumberColumn("VWAP", format="$%.4f"),
        "VWAP Compra": st.column_config.NumberColumn("VWAP Compra", format="$%.4f"),
        "VWAP Venta": st.column_config.NumberColumn("VWAP Venta", format="$%.4f"),
    },
)

st.plotly_chart(viz.grafica_multi_activo(series, metrica=metrica), use_container_width=True)

st.markdown("### 🔥 Heatmap de actividad mensual")
filas = []
for t, diarios in series.items():
    if diarios.empty:
        continue
    aux = diarios.copy()
    aux["MES"] = pd.to_datetime(aux["FECHA"]).dt.to_period("M").dt.to_timestamp()
    aux = aux.groupby("MES")[metrica].sum().reset_index()
    aux["TICKER"] = t
    filas.append(aux)

if filas:
    heat_df = pd.concat(filas, ignore_index=True)
    pivot = heat_df.pivot(index="TICKER", columns="MES", values=metrica).fillna(0)
    import plotly.express as px
    fig = px.imshow(
        pivot,
        labels=dict(color=metrica.title()),
        aspect="auto",
        color_continuous_scale="Purples",
    )
    fig.update_layout(template="plotly_white", height=380)
    st.plotly_chart(fig, use_container_width=True)
