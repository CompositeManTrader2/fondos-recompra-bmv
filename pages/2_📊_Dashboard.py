"""Página: dashboard principal de la emisora seleccionada."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import data_processor, storage, visualizations as viz

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")

ticker = st.session_state.get("ticker_activo")
if not ticker:
    st.warning("No hay activo seleccionado. Ve a **📥 Cargar Datos**.")
    st.stop()

st.title(f"📊 Dashboard · {ticker}")

df_raw = storage.cargar_operaciones(ticker)
if df_raw.empty:
    st.warning(f"No hay operaciones almacenadas para **{ticker}**.")
    st.stop()

# Garantizar aislamiento por emisora — defensa en profundidad
if "EMISORA" in df_raw.columns:
    sin_emisora = df_raw["EMISORA"].isna() | (df_raw["EMISORA"].astype(str).str.strip() == "")
    if sin_emisora.any():
        df_raw.loc[sin_emisora, "EMISORA"] = ticker
    # Mantener SOLO operaciones de la emisora seleccionada
    df_raw = df_raw[df_raw["EMISORA"].astype(str).str.upper() == ticker.upper()].copy()

if df_raw.empty:
    st.error(
        f"⚠️ Las operaciones almacenadas no pertenecen a `{ticker}`. "
        "Esto puede indicar un mezclado anterior. Ve a **📥 Cargar Datos → Mantenimiento** para reorganizar."
    )
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
# 🌟 VWAP DESTACADO (la métrica que el usuario quería ver más visible)
# ---------------------------------------------------------------------------
total = data_processor.total_global(df_f)

vwap_total = total.get("VWAP")
vwap_compra = total.get("VWAP_COMPRA")
vwap_venta = total.get("VWAP_VENTA")
spread = (vwap_venta - vwap_compra) if (pd.notna(vwap_compra) and pd.notna(vwap_venta)) else None
spread_bps = (spread / vwap_compra * 10000) if (spread is not None and pd.notna(vwap_compra) and vwap_compra > 0) else None

st.markdown("### 💎 VWAP del periodo")
v1, v2, v3, v4 = st.columns(4)
v1.metric(
    "VWAP Total",
    f"${vwap_total:,.4f}" if pd.notna(vwap_total) else "—",
    help="Volume-Weighted Average Price = Σ(precio × acciones) / Σ(acciones).",
)
v2.metric(
    "VWAP Compras",
    f"${vwap_compra:,.4f}" if pd.notna(vwap_compra) else "—",
    delta=(f"{(vwap_compra-vwap_total)/vwap_total*10000:+.0f} bps vs total"
           if pd.notna(vwap_compra) and pd.notna(vwap_total) and vwap_total else None),
)
v3.metric(
    "VWAP Ventas",
    f"${vwap_venta:,.4f}" if pd.notna(vwap_venta) else "—",
    delta=(f"{(vwap_venta-vwap_total)/vwap_total*10000:+.0f} bps vs total"
           if pd.notna(vwap_venta) and pd.notna(vwap_total) and vwap_total else None),
)
v4.metric(
    "Spread V−C",
    f"${spread:,.4f}" if spread is not None else "—",
    delta=f"{spread_bps:+.0f} bps" if spread_bps is not None else None,
    help="Diferencia entre VWAP de ventas y compras del periodo (en pesos y bps).",
)

st.divider()

# ---------------------------------------------------------------------------
# KPIs operativos
# ---------------------------------------------------------------------------
st.markdown("### 📈 Actividad")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Operaciones", f"{int(total['OPERACIONES']):,}")
c2.metric("Acciones", f"{int(total['ACCIONES']):,}")
c3.metric("Importe", f"${total['IMPORTE']:,.0f}")
rng_pct = ((total['PRECIO_MAX'] - total['PRECIO_MIN']) / total['PRECIO_MIN'] * 100) if total['PRECIO_MIN'] else None
c4.metric(
    "Rango precio",
    f"${total['PRECIO_MIN']:,.4f} – ${total['PRECIO_MAX']:,.4f}",
    delta=f"{rng_pct:.2f}%" if rng_pct is not None else None,
)

st.divider()

# ---------------------------------------------------------------------------
# Series temporales
# ---------------------------------------------------------------------------
diarios = data_processor.estadisticos_por_periodo(df_f, "FECHA")
semanales = data_processor.estadisticos_por_periodo(df_f, "SEMANA_INICIO")
mensuales = data_processor.estadisticos_por_periodo(df_f, "MES")

tabs = st.tabs([
    "💎 VWAP por periodo",
    "📅 Diario",
    "📆 Semanal",
    "🗓️ Mensual",
    "🔍 Detalle de operaciones",
])

# ----- VWAP dedicado -----
with tabs[0]:
    st.markdown("##### VWAP día por día (con compra/venta y precio mín/máx)")
    df_vwap = diarios[["FECHA", "OPERACIONES", "ACCIONES", "IMPORTE",
                       "VWAP", "VWAP_COMPRA", "VWAP_VENTA",
                       "PRECIO_MIN", "PRECIO_MAX"]].copy()
    st.dataframe(
        df_vwap,
        use_container_width=True, hide_index=True,
        column_config={
            "FECHA": st.column_config.DateColumn("Fecha", format="DD-MMM-YYYY"),
            "OPERACIONES": st.column_config.NumberColumn("# Ops", format="%d"),
            "ACCIONES": st.column_config.NumberColumn("Acciones", format="%d"),
            "IMPORTE": st.column_config.NumberColumn("Importe", format="$%d"),
            "VWAP": st.column_config.NumberColumn("VWAP", format="$%.4f"),
            "VWAP_COMPRA": st.column_config.NumberColumn("VWAP Compra", format="$%.4f"),
            "VWAP_VENTA": st.column_config.NumberColumn("VWAP Venta", format="$%.4f"),
            "PRECIO_MIN": st.column_config.NumberColumn("Mín", format="$%.4f"),
            "PRECIO_MAX": st.column_config.NumberColumn("Máx", format="$%.4f"),
        },
    )

    st.markdown("##### Gráfica VWAP")
    st.plotly_chart(
        viz.grafica_actividad_diaria(diarios, metrica="ACCIONES", incluir_vwap_lados=True),
        use_container_width=True,
    )

    csv_vwap = df_vwap.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar VWAP diario (CSV)",
        data=csv_vwap,
        file_name=f"vwap_{ticker}_{f_ini.date()}_{f_fin.date()}.csv",
        mime="text/csv",
    )

# ----- Diario -----
with tabs[1]:
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

# ----- Semanal -----
with tabs[2]:
    st.plotly_chart(
        viz.grafica_actividad_diaria(
            semanales.rename(columns={"SEMANA_INICIO": "FECHA"}),
            metrica="IMPORTE",
            incluir_vwap_lados=True,
        ),
        use_container_width=True,
    )
    st.dataframe(semanales, use_container_width=True, hide_index=True)

# ----- Mensual -----
with tabs[3]:
    st.plotly_chart(viz.grafica_actividad_mensual(mensuales), use_container_width=True)
    st.dataframe(mensuales, use_container_width=True, hide_index=True)

# ----- Detalle -----
with tabs[4]:
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
