"""Página: análisis por casa de bolsa."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import data_processor, storage, visualizations as viz

st.set_page_config(page_title="Casas de Bolsa", page_icon="🏛️", layout="wide")
st.title("🏛️ Concentración por casa de bolsa")

ticker = st.session_state.get("ticker_activo")
if not ticker:
    st.warning("No hay activo seleccionado. Ve a **📥 Cargar Datos**.")
    st.stop()

df = data_processor.consolidar_operaciones(storage.cargar_operaciones(ticker))
if df.empty:
    st.warning(f"Sin operaciones para **{ticker}**.")
    st.stop()

st.caption(f"Activo: **{ticker}** · {len(df):,} operaciones totales")

por_casa = data_processor.estadisticos_por_casa(df)

c1, c2, c3 = st.columns(3)
c1.metric("Casas distintas", len(por_casa))
top1 = por_casa.iloc[0]
c2.metric(f"Top 1 ({top1['CASA_BOLSA']})", f"{top1['PARTICIPACION_IMPORTE_%']:.1f}%")
hhi = float((por_casa["PARTICIPACION_IMPORTE_%"] ** 2).sum())  # Herfindahl
c3.metric("HHI (concentración)", f"{hhi:,.0f}", help="Índice Herfindahl-Hirschman; >2500 indica alta concentración.")

col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(viz.grafica_pastel_casas(por_casa, "IMPORTE"), use_container_width=True)
with col2:
    st.plotly_chart(viz.grafica_pastel_casas(por_casa, "OPERACIONES"), use_container_width=True)

st.plotly_chart(viz.grafica_monto_por_casa(por_casa, top_n=15), use_container_width=True)

st.dataframe(
    por_casa,
    use_container_width=True,
    hide_index=True,
    column_config={
        "IMPORTE": st.column_config.NumberColumn("Importe", format="$%d"),
        "PARTICIPACION_IMPORTE_%": st.column_config.NumberColumn("% importe", format="%.2f%%"),
        "PARTICIPACION_OPS_%": st.column_config.NumberColumn("% ops", format="%.2f%%"),
        "VWAP": st.column_config.NumberColumn("VWAP", format="$%.4f"),
        "VWAP_COMPRA": st.column_config.NumberColumn("VWAP Compra", format="$%.4f"),
        "VWAP_VENTA": st.column_config.NumberColumn("VWAP Venta", format="$%.4f"),
    },
)
