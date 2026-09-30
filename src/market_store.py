"""
Lectura de los datos de mercado que produce el scanner diario
(data/daily/*). Prefiere la copia más fresca en GitHub cuando el backend
GitHub está activo; si no, usa el checkout local.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src import github_storage

DAILY_ROOT = Path(__file__).resolve().parent.parent / "data" / "daily"


def _leer(nombre: str) -> bytes | None:
    if github_storage.is_enabled():
        try:
            data = github_storage.read_bytes(f"data/daily/{nombre}", absolute=True)
            if data:
                return data
        except Exception:
            pass
    local = DAILY_ROOT / nombre
    return local.read_bytes() if local.exists() else None


@st.cache_data(ttl=600, show_spinner=False)
def resumen_diario() -> pd.DataFrame:
    data = _leer("resumen_diario.parquet")
    if not data:
        return pd.DataFrame()
    df = pd.read_parquet(io.BytesIO(data))
    df["FECHA"] = pd.to_datetime(df["FECHA"]).dt.normalize()
    return df


@st.cache_data(ttl=600, show_spinner=False)
def documentos() -> pd.DataFrame:
    data = _leer("documentos.parquet")
    if not data:
        return pd.DataFrame()
    df = pd.read_parquet(io.BytesIO(data))
    df["FECHA_OPERACION"] = pd.to_datetime(df["FECHA_OPERACION"], errors="coerce")
    return df


@st.cache_data(ttl=600, show_spinner=False)
def estado_scanner() -> dict:
    data = _leer("_state.json")
    if not data:
        return {}
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return {}


@st.cache_data(ttl=600, show_spinner=False)
def actividad() -> pd.DataFrame:
    """Agregado por (fecha reporte, fecha operación, emisora, serie, casa, lado)."""
    data = _leer("actividad.parquet")
    if not data:
        return pd.DataFrame()
    df = pd.read_parquet(io.BytesIO(data))
    for c in ["FECHA_REPORTE", "FECHA_OPERACION"]:
        df[c] = pd.to_datetime(df[c]).dt.normalize()
    return df


def limpiar_cache() -> None:
    resumen_diario.clear(); documentos.clear(); estado_scanner.clear(); actividad.clear()
