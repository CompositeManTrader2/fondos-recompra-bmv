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
st.title("📈 VWAP del fondo vs precio de mercado")

ticker = st.session_state.get("ticker_activo")
if not ticker:
    st.warning("No hay activo seleccionado. Ve a **📥 Cargar Datos**.")
    st.stop()

df = data_processor.consolidar_operaciones(storage.cargar_operaciones(ticker))
if df.empty:
    st.warning(f"Sin operaciones para **{ticker}**.")
    st.stop()

if not market_data.YF_DISPONIBLE:
    st.error("`yfinance` no está instalado. Agrega `yfinance` a requirements.txt.")
    st.stop()

st.caption(f"Activo: **{ticker}** · {len(df):,} operaciones")

# ---------------------------------------------------------------------------
# Selección de fuente
# ---------------------------------------------------------------------------
fmin = pd.to_datetime(df["FECHA_OPERACION"]).min()
fmax = pd.to_datetime(df["FECHA_OPERACION"]).max()

@st.cache_data(ttl=900, show_spinner=False)
def _cache_auto_resolver(cve: str, ini_iso: str, fin_iso: str):
    return market_data.auto_resolver_yahoo(
        cve, pd.to_datetime(ini_iso).to_pydatetime(), pd.to_datetime(fin_iso).to_pydatetime()
    )

@st.cache_data(ttl=900, show_spinner=False)
def _cache_descarga_directa(symbol: str, ini_iso: str, fin_iso: str):
    return market_data.precios_diarios(
        symbol, pd.to_datetime(ini_iso).to_pydatetime(), pd.to_datetime(fin_iso).to_pydatetime()
    )

with st.sidebar:
    st.markdown(f"### Fuente de precios · {ticker}")
    fuente = st.radio(
        "Origen",
        ["🪄 Auto-resolver Yahoo Finance", "✏️ Símbolo Yahoo manual", "📂 Subir Excel/CSV"],
        index=0,
    )

# ---------------------------------------------------------------------------
# Resolución del precio de mercado
# ---------------------------------------------------------------------------
precios = pd.DataFrame()
sym_usado: str | None = None
intentos: list[str] = []

if fuente == "🪄 Auto-resolver Yahoo Finance":
    st.markdown(
        "El sistema prueba automáticamente las variantes Yahoo de tu cve_emisora "
        "BMV (`AMX`→`AMXB.MX`, `BIMBO`→`BIMBOA.MX`, `CEMEX`→`CEMEXCPO.MX`...) "
        "hasta encontrar una que devuelva precios."
    )
    with st.spinner(f"Buscando símbolo Yahoo para {ticker}…"):
        sym_usado, precios, intentos = _cache_auto_resolver(
            ticker,
            (fmin - timedelta(days=5)).isoformat(),
            (fmax + timedelta(days=2)).isoformat(),
        )

    col_l, col_r = st.columns([3, 1])
    if sym_usado:
        col_l.success(f"✅ Símbolo Yahoo encontrado: **`{sym_usado}`** · {len(precios)} días con precios.")
    else:
        col_l.error(
            f"❌ No se encontró ningún símbolo Yahoo válido para `{ticker}`."
        )
    with col_r.expander(f"Variantes probadas ({len(intentos)})"):
        for s in intentos:
            mark = "✓" if s == sym_usado else "·"
            st.text(f"{mark} {s}")

    if not sym_usado:
        st.info(
            "**Soluciones**:\n"
            "1. Cambia el origen a **✏️ Símbolo Yahoo manual** y prueba el "
            "ticker exacto en https://finance.yahoo.com/quote/. \n"
            "2. Sube un Excel con `FECHA` y `Close` desde tu propio data feed."
        )
        st.stop()

elif fuente == "✏️ Símbolo Yahoo manual":
    cache_actual = market_data.cache_yahoo_mapping().get(ticker.upper())
    valor_default = (
        cache_actual
        or market_data.MAPEO_MANUAL.get(ticker.upper())
        or f"{ticker}.MX"
    )
    sym_in = st.text_input(
        "Símbolo Yahoo (con sufijo)",
        value=valor_default,
        help="Ejemplos: AMXB.MX, BIMBOA.MX, WALMEX.MX, CEMEXCPO.MX. "
             "Verifica primero en https://finance.yahoo.com/quote/",
    ).strip().upper()
    col_b1, col_b2 = st.columns([1, 1])
    if col_b1.button("🔎 Descargar", type="primary", disabled=not sym_in):
        with st.spinner(f"Descargando {sym_in} de Yahoo Finance…"):
            precios = _cache_descarga_directa(
                sym_in,
                (fmin - timedelta(days=5)).isoformat(),
                (fmax + timedelta(days=2)).isoformat(),
            )
        if precios.empty:
            st.error(
                f"❌ Yahoo no devolvió datos para `{sym_in}`. "
                "Verifica el símbolo en https://finance.yahoo.com/quote/."
            )
            st.stop()
        sym_usado = sym_in
        st.success(f"✅ {len(precios)} días con precios.")
        if col_b2.button("💾 Guardar como mapping default", help="Persiste para que el auto-resolver lo use siempre."):
            market_data.set_yahoo_mapping(ticker, sym_in)
            st.toast(f"✅ {ticker} → {sym_in} guardado.")
    else:
        st.stop()

else:  # Subir Excel
    archivo = st.file_uploader(
        "Sube un archivo con columnas FECHA y Close (o PRECIO_MERCADO/CIERRE)",
        type=["xlsx", "xls", "csv"],
    )
    if archivo is None:
        st.info("Carga un archivo para continuar.")
        st.stop()
    try:
        if archivo.name.lower().endswith(("xlsx", "xls")):
            precios = pd.read_excel(archivo)
        else:
            precios = pd.read_csv(archivo)
        precios.columns = [str(c).strip() for c in precios.columns]
        st.success(f"✅ {len(precios)} filas leídas del archivo.")
        st.dataframe(precios.head(10), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error leyendo el archivo: {e}")
        st.stop()
    sym_usado = archivo.name

# ---------------------------------------------------------------------------
# Cruce y visualización
# ---------------------------------------------------------------------------
diarios = data_processor.estadisticos_por_periodo(df, "FECHA")
comp = data_processor.comparar_con_mercado(diarios, precios)

if comp.empty:
    st.error(
        "No se pudo cruzar el VWAP con los precios de mercado. "
        "Revisa que el archivo tenga las columnas `FECHA` (o `Date`) y "
        "`Close` (o `PRECIO_MERCADO`/`CIERRE`)."
    )
    if not precios.empty:
        with st.expander("🔍 Columnas detectadas en la fuente de precios"):
            st.write(list(precios.columns))
            st.dataframe(precios.head(5), use_container_width=True, hide_index=True)
    st.stop()

# KPIs
dias_cruce = int(comp["PRECIO_MERCADO"].notna().sum())
sobreprecio_promedio = comp["VWAP_VS_MERCADO_%"].mean() if "VWAP_VS_MERCADO_%" in comp else None
alertas = int(comp.get("ALERTA_SOBREPRECIO_TOTAL", pd.Series(dtype=bool)).sum())
spread_max = comp["VWAP_VS_MERCADO_%"].max() if "VWAP_VS_MERCADO_%" in comp else None
spread_min = comp["VWAP_VS_MERCADO_%"].min() if "VWAP_VS_MERCADO_%" in comp else None

c1, c2, c3, c4 = st.columns(4)
c1.metric("Días con cruce", dias_cruce)
c2.metric(
    "Sobreprecio promedio",
    f"{sobreprecio_promedio:+.3f}%" if pd.notna(sobreprecio_promedio) else "—",
    help="Negativo = el fondo compró por debajo del precio de mercado (eficiente).",
)
c3.metric("Días con alerta (>1.5%)", alertas)
c4.metric(
    "Rango sobreprecio",
    f"{spread_min:+.2f}% / {spread_max:+.2f}%" if pd.notna(spread_max) else "—",
)

# Gráfica
st.plotly_chart(viz.grafica_vwap_vs_mercado(comp), use_container_width=True)

# Tabla
st.markdown(f"##### Detalle (fuente: `{sym_usado}`)")
cols_show = [c for c in [
    "FECHA", "VWAP", "VWAP_COMPRA", "VWAP_VENTA", "PRECIO_MERCADO",
    "VWAP_VS_MERCADO_%", "VWAP_COMPRA_VS_MERCADO_%", "VWAP_VENTA_VS_MERCADO_%",
    "ALERTA_SOBREPRECIO_TOTAL", "ALERTA_SOBREPRECIO_COMPRA",
] if c in comp.columns]
st.dataframe(
    comp[cols_show],
    use_container_width=True, hide_index=True,
    column_config={
        "FECHA": st.column_config.DateColumn("Fecha", format="DD-MMM-YYYY"),
        "VWAP": st.column_config.NumberColumn("VWAP", format="$%.4f"),
        "VWAP_COMPRA": st.column_config.NumberColumn("VWAP Compra", format="$%.4f"),
        "VWAP_VENTA": st.column_config.NumberColumn("VWAP Venta", format="$%.4f"),
        "PRECIO_MERCADO": st.column_config.NumberColumn("Mercado", format="$%.4f"),
        "VWAP_VS_MERCADO_%": st.column_config.NumberColumn("Δ VWAP", format="%.2f%%"),
        "VWAP_COMPRA_VS_MERCADO_%": st.column_config.NumberColumn("Δ Compra", format="%.2f%%"),
        "VWAP_VENTA_VS_MERCADO_%": st.column_config.NumberColumn("Δ Venta", format="%.2f%%"),
    },
)

st.download_button(
    "⬇️ Descargar comparativo (CSV)",
    data=comp[cols_show].to_csv(index=False).encode("utf-8"),
    file_name=f"comparativo_{ticker}_{sym_usado}.csv",
    mime="text/csv",
)
