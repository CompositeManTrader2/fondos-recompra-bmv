"""Reporte mensual Net Buybacks en PDF: generar a cualquier fecha de corte y archivo mensual."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src import market_store, reporte_datos as rd, theme as T

REPORTES = Path(__file__).resolve().parent.parent / "reportes"

T.header("RPT", "Reporte Net Buybacks", "PDF mensual de recompras de todas las emisoras")

act = market_store.actividad()
docs = market_store.documentos()
merc = market_store.mercado()
if act.empty or docs.empty:
    st.info("Aún no hay datos suficientes. El reporte se arma con la información del scanner diario.")
    st.stop()

fechas = sorted(act["FECHA_OPERACION"].dt.date.unique(), reverse=True)
c1, c2, c3 = st.columns([1.3, 1, 1.4])
corte = c1.selectbox("Datos al (fecha de corte)", fechas, format_func=lambda f: f.strftime("%d/%m/%Y"))
idioma = c2.segmented_control("Idioma", ["en", "es"], default="en",
                              format_func=lambda x: {"en": "Inglés", "es": "Español"}[x]) or "en"

cob = rd.cobertura(docs)
per = rd.periodos(corte)
sin_cob = [p.etiqueta for p in per.values() if not rd.cubierto(p.ini, cob)]
if sin_cob:
    st.warning(
        f"La cobertura de todo el mercado inicia el **{cob:%d/%m/%Y}**. Estos periodos saldrán como *n.d.* "
        f"hasta que termine la carga histórica: {', '.join(sin_cob)}.", icon=":material/history:")

T.tiles([
    {"label": "Fecha de corte", "value": corte.strftime("%d/%m/%Y")},
    {"label": "Cobertura desde", "value": cob.strftime("%d/%m/%Y") if cob else "—"},
    {"label": "Emisoras con recompra", "value": f"{act[act['FECHA_OPERACION'].dt.date <= corte]['EMISORA'].nunique()}"},
    {"label": "Precios de mercado", "value": f"{merc['EMISORA'].nunique() if not merc.empty else 0} emisoras",
     "sub": "para el yield sectorial"},
])


@st.cache_data(show_spinner=False, max_entries=8)
def _pdf(corte_iso: str, idioma: str, version_datos: str) -> bytes:
    from src import reporte_pdf
    return reporte_pdf.generar_pdf(market_store.actividad(), market_store.documentos(), market_store.mercado(),
                                   pd.Timestamp(corte_iso).date(), idioma=idioma)


version = f"{len(act)}-{act['FECHA_OPERACION'].max():%Y%m%d}-{len(docs)}"
if c3.button("Generar reporte PDF", type="primary", icon=":material/picture_as_pdf:", width="stretch"):
    with st.spinner("Armando el reporte (tablas, gráficas y rankings)…"):
        st.session_state["reporte_pdf"] = (corte, idioma, _pdf(corte.isoformat(), idioma, version))

if st.session_state.get("reporte_pdf"):
    r_corte, r_idioma, data = st.session_state["reporte_pdf"]
    st.success(f"Reporte listo · datos al {r_corte:%d/%m/%Y} · {len(data) / 1024:,.0f} KB", icon=":material/check_circle:")
    st.download_button("Descargar PDF", data, file_name=f"Buybacks_{r_corte:%Y-%m-%d}_{r_idioma}.pdf",
                       mime="application/pdf", type="primary", icon=":material/download:")

d = rd.preparar(act, docs, merc, corte)


@st.cache_data(show_spinner=False, max_entries=8)
def _hallazgos(corte_iso: str, version_datos: str) -> list[str]:
    from src import reporte_analisis as ra
    an = ra.analizar(market_store.actividad(), market_store.documentos(), market_store.mercado(),
                     pd.Timestamp(corte_iso).date())
    return an.hallazgos["es"]


T.seccion("Hallazgos principales", "lo que dirá el resumen ejecutivo del PDF")
for h in _hallazgos(corte.isoformat(), version):
    st.markdown("- " + h.replace("<b>", "**").replace("</b>", "**").replace("$", "\\$"))

T.seccion("Vista previa · recompra neta por sector", "millones de pesos")
vista = d.sectores[["SECTOR", "YTD_MONTO", "YTD_YIELD", "YTD_EMIS", "LTM_MONTO", "Y1_MONTO"]]
st.dataframe(
    vista, hide_index=True, width="stretch",
    column_config={
        "SECTOR": "Sector",
        "YTD_MONTO": st.column_config.NumberColumn(f"{corte.year} YTD", format="%,.0f"),
        "YTD_YIELD": st.column_config.NumberColumn("Buyback yield YTD", format="%.2f%%"),
        "YTD_EMIS": st.column_config.NumberColumn("Emisoras YTD", format="%d"),
        "LTM_MONTO": st.column_config.NumberColumn("Últimos 12M", format="%,.0f"),
        "Y1_MONTO": st.column_config.NumberColumn(f"{corte.year - 1} 12M", format="%,.0f"),
    },
)
st.caption("Las celdas vacías corresponden a periodos sin cobertura completa (n.d. en el PDF). "
           "Clasificación sectorial editable en data/sectores.csv.")

archivo = sorted(REPORTES.glob("Buybacks_*.pdf"), reverse=True) if REPORTES.exists() else []
if archivo:
    T.seccion("Archivo mensual", "generado automáticamente el primer día hábil de cada mes")
    for p in archivo[:12]:
        st.download_button(p.stem.replace("_", " "), p.read_bytes(), file_name=p.name, mime="application/pdf",
                           icon=":material/description:", key=f"arch-{p.name}")
