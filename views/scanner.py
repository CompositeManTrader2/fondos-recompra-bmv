"""Estado del scanner diario (GitHub Actions) y registro de documentos."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import github_storage, market_store, theme as T

REPO_DEFAULT = "CompositeManTrader2/fondos-recompra-bmv"
repo = (github_storage.config_info() or {}).get("repo") or REPO_DEFAULT
url = f"https://github.com/{repo}/actions/workflows/daily_scan.yml"

T.header("SCAN", "Estado del scanner", "Descarga diaria de recompras de toda la BMV")
estado = market_store.estado_scanner()
docs = market_store.documentos()
ult = estado.get("last_run_utc")
ult_txt = pd.Timestamp(ult).tz_convert(T.CDMX).strftime("%d-%b-%Y %H:%M").upper() if ult else "—"

T.tiles([
    {"label": "Última corrida", "value": ult_txt, "sub": "hora CDMX"},
    {"label": "Último ID de BMV", "value": f"{int(estado.get('last_hit_id') or 0):,}"},
    {"label": "Documentos registrados", "value": f"{len(docs):,}"},
    {"label": "IDs pendientes de reintento", "value": f"{len(estado.get('ids_error', [])):,}"},
])
st.markdown(f"Corre a las **20:30** y **09:30 CDMX**, de lunes a viernes. Ejecución manual o carga histórica "
            f"(`seed_id`): [{url}]({url})")
if st.button("Actualizar datos", icon=":material/refresh:"):
    market_store.limpiar_cache(); st.rerun()

runs = pd.DataFrame(estado.get("runs", []))
if not runs.empty:
    T.seccion("Corridas recientes")
    runs["emisoras"] = runs["emisoras"].map(lambda e: len(e) if isinstance(e, list) else e)
    runs["utc"] = pd.to_datetime(runs["utc"]).dt.tz_convert(T.CDMX).dt.strftime("%d-%b %H:%M")
    st.dataframe(
        runs[[c for c in ["utc", "ids_revisados", "docs_nuevos", "ops_nuevas", "emisoras", "errores_red",
                          "duracion_s", "abortado"] if c in runs]],
        hide_index=True, width="stretch",
        column_config={"utc": "Hora CDMX", "ids_revisados": "IDs revisados", "docs_nuevos": "Docs nuevos",
                       "ops_nuevas": "Operaciones", "emisoras": "Emisoras", "errores_red": "Errores de red",
                       "duracion_s": st.column_config.NumberColumn("Duración", format="%d s"), "abortado": "Detenido por"},
    )
if not docs.empty:
    T.seccion("Documentos más recientes")
    cols = [c for c in ["ID", "EMISORA", "SERIE", "FECHA_REPORTE", "FECHA_OPERACION", "CASA_BOLSA", "N_OPS",
                        "IMPORTE", "ESTADO", "URL"] if c in docs]
    st.dataframe(
        docs.sort_values("ID", ascending=False).head(300)[cols], hide_index=True, width="stretch",
        column_config={
            "FECHA_REPORTE": st.column_config.DateColumn("Reporte", format="DD/MM/YY"),
            "FECHA_OPERACION": st.column_config.DateColumn("Operación", format="DD/MM/YY"),
            "IMPORTE": st.column_config.NumberColumn("Importe", format="$%,.0f"),
            "URL": st.column_config.LinkColumn("PDF", display_text="abrir"),
        },
    )
