"""Página: comparativo VWAP del fondo vs precio de mercado."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import data_processor, market_data, storage, visualizations as viz

st.set_page_config(page_title="Comparativo Mercado", page_icon="📈", layout="wide")
st.title("📈 VWAP del fondo vs Precio de Mercado")

ticker = st.session_state.get("ticker_activo")
if not ticker:
    st.warning("No hay activo seleccionado. Ve a **📥 Cargar Datos**.")
    st.stop()

df = data_processor.consolidar_operaciones(storage.cargar_operaciones(ticker))
if df.empty:
    st.warning(f"Sin operaciones para **{ticker}**.")
    st.stop()

if not market_data.YF_DISPONIBLE:
    st.error("yfinance no está instalado. Agrega `yfinance` a requirements.txt.")
    st.stop()

with st.sidebar:
    st.markdown(f"### Mercado · {ticker}")
    fuente = st.radio(
        "Fuente de precios",
        ["Yahoo Finance (.MX)", "Subir Excel propio"],
        index=0,
    )
    sym_override = st.text_input(
        "Override de símbolo Yahoo",
        value="",
        help="Útil si el ticker BMV no coincide (p.ej. 'BIMBOA.MX').",
    )

fmin = pd.to_datetime(df["FECHA_OPERACION"]).min()
fmax = pd.to_datetime(df["FECHA_OPERACION"]).max()

precios = pd.DataFrame()

if fuente == "Yahoo Finance (.MX)":
    sym = sym_override.strip() or ticker
    with st.spinner(f"Descargando {sym} desde Yahoo Finance…"):
        precios = market_data.precios_diarios(
            sym,
            fecha_inicio=fmin - timedelta(days=5),
            fecha_fin=fmax + timedelta(days=2),
        )
    if precios.empty:
        st.error("Yahoo Finance no devolvió datos. Verifica el símbolo (suele ir con sufijo `.MX`).")
        st.stop()
    columna_precio = "Close"
else:
    archivo = st.file_uploader(
        "Sube un Excel/CSV con columnas FECHA y PRECIO_MERCADO (o Close)",
        type=["xlsx", "xls", "csv"],
    )
    if archivo is None:
        st.info("Carga un archivo para continuar.")
        st.stop()
    precios = pd.read_excel(archivo) if archivo.name.endswith(("xlsx", "xls")) else pd.read_csv(archivo)
    precios.columns = [c.strip() for c in precios.columns]
    if "FECHA" in precios.columns:
        precios["Date"] = pd.to_datetime(precios["FECHA"], errors="coerce")
    columna_precio = (
        "PRECIO_MERCADO" if "PRECIO_MERCADO" in precios.columns
        else "Close" if "Close" in precios.columns
        else next((c for c in precios.columns if "cierre" in c.lower() or "close" in c.lower()), None)
    )
    if columna_precio is None:
        st.error("No encontré columna de precio (PRECIO_MERCADO/Close/Cierre).")
        st.stop()

diarios = data_processor.estadisticos_por_periodo(df, "FECHA")
comp = data_processor.comparar_con_mercado(diarios, precios, columna_precio=columna_precio)

if comp.empty:
    st.error("No se pudo cruzar el VWAP con los precios de mercado.")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Días con cruce", int(comp["PRECIO_MERCADO"].notna().sum()))
medio = comp["VWAP_VS_MERCADO_%"].mean() if "VWAP_VS_MERCADO_%" in comp else None
c2.metric("Sobreprecio promedio", f"{medio:.2f}%" if pd.notna(medio) else "—")
alertas = int(comp.get("ALERTA_SOBREPRECIO_TOTAL", pd.Series(dtype=bool)).sum())
c3.metric("Días con alerta (>1.5%)", alertas)

st.plotly_chart(viz.grafica_vwap_vs_mercado(comp), use_container_width=True)

st.dataframe(
    comp,
    use_container_width=True,
    hide_index=True,
    column_config={
        "VWAP": st.column_config.NumberColumn("VWAP", format="$%.4f"),
        "PRECIO_MERCADO": st.column_config.NumberColumn("Mercado", format="$%.4f"),
        "VWAP_VS_MERCADO_%": st.column_config.NumberColumn("Δ VWAP vs Mkt", format="%.2f%%"),
    },
)
