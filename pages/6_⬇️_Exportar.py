"""Página: exportar Excel consolidado equivalente al notebook original."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import data_processor, storage

st.set_page_config(page_title="Exportar", page_icon="⬇️", layout="wide")
st.title("⬇️ Exportar resultados")

ticker = st.session_state.get("ticker_activo")
if not ticker:
    st.warning("No hay activo seleccionado. Ve a **📥 Cargar Datos**.")
    st.stop()

df = data_processor.consolidar_operaciones(storage.cargar_operaciones(ticker))
if df.empty:
    st.warning(f"Sin operaciones para **{ticker}**.")
    st.stop()


def _construir_excel(df: pd.DataFrame) -> bytes:
    diarios = data_processor.estadisticos_por_periodo(df, "FECHA")
    semanales = data_processor.estadisticos_por_periodo(df, "SEMANA_INICIO")
    mensuales = data_processor.estadisticos_por_periodo(df, "MES")
    por_casa = data_processor.estadisticos_por_casa(df)
    total = data_processor.total_global(df)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.sort_values(["FECHA_OPERACION", "FOLIO"], na_position="last").to_excel(
            writer, sheet_name="TODAS_OPERACIONES", index=False
        )
        diarios.assign(NIVEL="Día").to_excel(writer, sheet_name="DIARIO", index=False)
        semanales.assign(NIVEL="Semana").to_excel(writer, sheet_name="SEMANAL", index=False)
        mensuales.assign(NIVEL="Mes").to_excel(writer, sheet_name="MENSUAL", index=False)
        por_casa.to_excel(writer, sheet_name="POR_CASA_BOLSA", index=False)
        pd.DataFrame([total]).to_excel(writer, sheet_name="TOTAL", index=False)
    return buf.getvalue()


excel_bytes = _construir_excel(df)
st.success(f"Excel listo para **{ticker}** — {len(df):,} operaciones.")

st.download_button(
    label="📥 Descargar Excel consolidado",
    data=excel_bytes,
    file_name=f"recompra_{ticker}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
)

st.markdown("### Vista previa")
st.dataframe(df.head(50), use_container_width=True, hide_index=True)
