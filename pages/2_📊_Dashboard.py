"""Página: dashboard principal de la emisora seleccionada."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import data_processor, storage, visualizations as viz

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
st.title("📊 Dashboard de operaciones")

ticker = st.session_state.get("ticker_activo")
if not ticker:
    st.warning("No hay activo seleccionado. Ve a **📥 Cargar Datos**.")
    st.stop()

df_raw = storage.cargar_operaciones(ticker)
if df_raw.empty:
    st.warning(f"No hay operaciones almacenadas para **{ticker}**.")
    st.stop()

df = data_processor.consolidar_operaciones(df_raw)

# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------
fmin = pd.to_datetime(df["FECHA_OPERACION"]).min().date()
fmax = pd.to_datetime(df["FECHA_OPERACION"]).max().date()

with st.sidebar:
    st.markdown(f"### Filtros · {ticker}")
    rango = st.date_input(
        "Rango de fechas",
        value=(max(fmin, fmax - timedelta(days=90)), fmax),
        min_value=fmin, max_value=fmax,
    )
    casas_disp = sorted(df["CASA_BOLSA"].dropna().unique().tolist())
    casas_sel = st.multiselect("Casas de bolsa", casas_disp, default=casas_disp)
    tipos_disp = ["COMPRA", "VENTA", "OTRO"]
    tipos_sel = st.multiselect("Tipo de operación", tipos_disp, default=tipos_disp)

if isinstance(rango, tuple) and len(rango) == 2:
    f_ini, f_fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
else:
    f_ini, f_fin = pd.to_datetime(fmin), pd.to_datetime(fmax)

df_f = data_processor.filtrar_ventana(df, f_ini, f_fin, casas_sel, tipos_sel)
if df_f.empty:
    st.warning("La combinación de filtros no devuelve operaciones.")
    st.stop()

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
total = data_processor.total_global(df_f)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Operaciones", f"{int(total['OPERACIONES']):,}")
c2.metric("Acciones", f"{int(total['ACCIONES']):,}")
c3.metric("Importe", f"${total['IMPORTE']:,.0f}")
c4.metric("VWAP", f"${total['VWAP']:,.4f}" if pd.notna(total["VWAP"]) else "—")
spread = (total["VWAP_VENTA"] - total["VWAP_COMPRA"]) if pd.notna(total["VWAP_COMPRA"]) and pd.notna(total["VWAP_VENTA"]) else None
c5.metric(
    "Spread VWAP V−C",
    f"${spread:,.4f}" if spread is not None else "—",
    help="Diferencia entre VWAP de ventas y VWAP de compras del periodo.",
)

st.divider()

# ---------------------------------------------------------------------------
# Series temporales
# ---------------------------------------------------------------------------
diarios = data_processor.estadisticos_por_periodo(df_f, "FECHA")
semanales = data_processor.estadisticos_por_periodo(df_f, "SEMANA_INICIO")
mensuales = data_processor.estadisticos_por_periodo(df_f, "MES")

tabs = st.tabs(["📅 Diario", "📆 Semanal", "🗓️ Mensual", "🔍 Detalle de operaciones"])

with tabs[0]:
    metrica = st.selectbox(
        "Métrica para barras",
        ["OPERACIONES", "ACCIONES", "IMPORTE"],
        key="metrica_diaria",
    )
    incluye = st.checkbox("Incluir VWAP de compra y venta", value=True)
    st.plotly_chart(
        viz.grafica_actividad_diaria(diarios, metrica=metrica, incluir_vwap_lados=incluye),
        use_container_width=True,
    )
    st.dataframe(diarios, use_container_width=True, hide_index=True)

with tabs[1]:
    st.plotly_chart(
        viz.grafica_actividad_diaria(
            semanales.rename(columns={"SEMANA_INICIO": "FECHA"}),
            metrica="IMPORTE",
            incluir_vwap_lados=True,
        ),
        use_container_width=True,
    )
    st.dataframe(semanales, use_container_width=True, hide_index=True)

with tabs[2]:
    st.plotly_chart(viz.grafica_actividad_mensual(mensuales), use_container_width=True)
    st.dataframe(mensuales, use_container_width=True, hide_index=True)

with tabs[3]:
    st.dataframe(
        df_f.sort_values(["FECHA_OPERACION", "FOLIO"]).reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        column_config={
            "FECHA_OPERACION": st.column_config.DatetimeColumn("Fecha"),
            "PRECIO_UNITARIO": st.column_config.NumberColumn("Precio", format="$%.4f"),
            "IMPORTE_OPERACION": st.column_config.NumberColumn("Importe", format="$%d"),
            "NUMERO_DE_ACCIONES": st.column_config.NumberColumn("Acciones", format="%d"),
        },
    )
