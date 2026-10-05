"""Buyback Activity: la tabla diaria con el formato del reporte de Punto."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import market_store, reporte_buyback as rb, theme as T

T.header("BBA", "Buyback Activity", "Operaciones de recompra por emisora, casa y lado")

act = market_store.actividad()
if act.empty:
    st.info("Aún no hay tabla de actividad. Se genera con el scanner diario (ver **Estado del scanner**).")
    st.stop()

c1, c2 = st.columns([1.4, 1.6])
por = c2.segmented_control(
    "Agrupar por", ["Fecha de reporte", "Fecha de operación"], default="Fecha de reporte",
    help="El reporte de Punto usa la fecha de publicación: el del 11/03 incluye operaciones del 09 y 10/03.",
) or "Fecha de reporte"
col = "FECHA_REPORTE" if por == "Fecha de reporte" else "FECHA_OPERACION"
fechas = sorted(act[col].dropna().unique(), reverse=True)
# El reporte del día en curso se sigue llenando: abrir por defecto el último completo.
n_emis = act.groupby(col)["EMISORA"].nunique().reindex(fechas)
mediana = n_emis.iloc[1:11].median() if len(n_emis) > 1 else n_emis.iloc[0]
parciales = {f for f in fechas[:2] if n_emis[f] < 0.5 * mediana}
idx = next((i for i, f in enumerate(fechas) if f not in parciales), 0)
fecha = pd.Timestamp(c1.selectbox(
    "Fecha", fechas, index=idx,
    format_func=lambda f: pd.Timestamp(f).strftime("%d/%m/%Y · %A") + ("  · parcial" if f in parciales else ""))).date()

del_dia = act[act[col].dt.date == fecha]
with st.expander("Filtros", icon=":material/filter_list:"):
    f1, f2, f3 = st.columns(3)
    emis = f1.multiselect("Emisoras", sorted(del_dia["EMISORA"].unique()))
    casas = f2.multiselect("Casas de bolsa", sorted(del_dia["CASA_BOLSA"].unique()))
    lados = f3.multiselect("Lado", ["COMPRA", "VENTA"], format_func=lambda x: rb.LADO[x])

tabla = rb.construir_tabla(act, fecha, "reporte" if col == "FECHA_REPORTE" else "operacion", emis, casas, lados)

compras = tabla[tabla["B/S"] == "BOUGHT"]["GROSS MXN"].sum()
ventas = tabla[tabla["B/S"] == "SOLD"]["GROSS MXN"].sum()
T.tiles([
    {"label": "Renglones", "value": f"{len(tabla):,}"},
    {"label": "Emisoras", "value": f"{tabla['STOCK'].str.split().str[0].nunique()}"},
    {"label": "Importe comprado", "value": T.fmt_mxn(compras), "sub": f"${compras:,.0f}"},
    {"label": "Importe vendido", "value": T.fmt_mxn(ventas), "sub": f"${ventas:,.0f}"},
    {"label": "Casas de bolsa", "value": f"{tabla['BROKER'].nunique()}"},
])

d0, d1, d2, _ = st.columns([1, 1, 1, 2])
d0.download_button("Descargar PNG", rb.png_bytes(tabla, fecha), icon=":material/image:",
                   file_name=f"Buyback_Activity_{fecha:%Y%m%d}.png", mime="image/png",
                   width="stretch", type="primary")
d1.download_button("Descargar Excel", rb.excel_bytes(tabla, fecha), icon=":material/table:",
                   file_name=f"Buyback_Activity_{fecha:%Y%m%d}.xlsx", width="stretch",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
d2.download_button("Descargar HTML (correo)", rb.html_documento(tabla, fecha, T.logo_html()).encode("utf-8"),
                   icon=":material/mail:", file_name=f"Buyback_Activity_{fecha:%Y%m%d}.html",
                   mime="text/html", width="stretch")

st.markdown(
    f'<div style="background:#fff;border:1px solid {T.BORDER};border-radius:8px;padding:18px 20px;overflow-x:auto">'
    f'{rb.html_tabla(tabla, fecha, T.logo_html())}</div>',
    unsafe_allow_html=True,
)
