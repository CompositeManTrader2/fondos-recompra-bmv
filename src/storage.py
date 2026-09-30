"""
Capa de persistencia con dos backends:
  - **github**:  parquets se commitean al mismo repo de GitHub (persistente).
  - **local**:   filesystem local (efímero en Streamlit Cloud).

Selección automática:
  - Si `st.secrets["github"]` (o env vars `GITHUB_TOKEN` + `GITHUB_REPO`)
    existen → backend GitHub.
  - Si no → backend local en `data/activos/`.

Estructura lógica idéntica en ambos:
    {base}/{TICKER}/operations.parquet
    {base}/_index.json
"""
from __future__ import annotations

import io
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src import github_storage

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "activos"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
INDEX_FILE = DATA_ROOT / "_index.json"

# Caché en memoria para lecturas vía GitHub API (evita N requests por rerun).
_CACHE_TTL_S = 120
_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL_S:
        return hit[1]
    return None


def _cache_set(key: str, value) -> None:
    _cache[key] = (time.time(), value)


def _cache_drop(key: str) -> None:
    _cache.pop(key, None)


# ---------------------------------------------------------------------------
# Selección de backend
# ---------------------------------------------------------------------------

def backend_actual() -> str:
    # El scanner diario (GitHub Actions) escribe directo al checkout y hace
    # un solo commit al final: fuerza backend local con STORAGE_BACKEND=local.
    if os.environ.get("STORAGE_BACKEND", "").lower() == "local":
        return "local"
    return "github" if github_storage.is_enabled() else "local"


def info_backend() -> dict:
    if github_storage.is_enabled():
        info = github_storage.config_info()
        info["backend"] = "github"
        return info
    return {"backend": "local", "path": str(DATA_ROOT)}


# ---------------------------------------------------------------------------
# Helpers de tickers
# ---------------------------------------------------------------------------

def _normalizar_ticker(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    t = re.sub(r"[^A-Z0-9\.\-]", "", t)
    return t or "DESCONOCIDA"


def _parquet_relpath(ticker: str) -> str:
    return f"{_normalizar_ticker(ticker)}/operations.parquet"


# ---------------------------------------------------------------------------
# Lectura/escritura del índice
# ---------------------------------------------------------------------------

def _leer_indice() -> dict:
    if backend_actual() == "github":
        cached = _cache_get("_index.json")
        if cached is not None:
            return dict(cached)
        try:
            data = github_storage.read_bytes("_index.json")
            idx = json.loads(data.decode("utf-8")) if data else {}
        except Exception:
            idx = {}
        _cache_set("_index.json", idx)
        return dict(idx)
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _guardar_indice(idx: dict) -> None:
    payload = json.dumps(idx, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if backend_actual() == "github":
        github_storage.write_bytes("_index.json", payload, mensaje="chore(data): update index")
        _cache_set("_index.json", idx)
        return
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_bytes(payload)


# ---------------------------------------------------------------------------
# Listar / registrar / eliminar activos
# ---------------------------------------------------------------------------

def listar_activos() -> list[dict]:
    """
    Lista activos usando SOLO los metadatos del índice (n_operaciones,
    ultima_fecha), sin descargar cada parquet. Con 100+ emisoras cargadas
    por el scanner diario, leer todos los parquets en cada rerun sería
    inviable.
    """
    idx = _leer_indice()
    out = []
    for ticker, meta in idx.items():
        out.append({
            "ticker": ticker,
            "nombre": meta.get("nombre", ticker),
            "creado": meta.get("creado"),
            "actualizado": meta.get("actualizado"),
            "n_operaciones": int(meta.get("n_operaciones") or 0),
            "ultima_fecha": meta.get("ultima_fecha"),
        })
    return sorted(out, key=lambda x: x["ticker"])


def _meta_desde_df(df: pd.DataFrame) -> dict:
    meta = {"n_operaciones": int(len(df))}
    if "FECHA_OPERACION" in df.columns and not df.empty:
        ult = pd.to_datetime(df["FECHA_OPERACION"], errors="coerce").max()
        if pd.notna(ult):
            meta["ultima_fecha"] = ult.date().isoformat()
    return meta


def registrar_activo(ticker: str, nombre: Optional[str] = None, meta: Optional[dict] = None) -> str:
    ticker = _normalizar_ticker(ticker)
    idx = _leer_indice()
    ahora = datetime.now().isoformat(timespec="seconds")
    entrada = idx.get(ticker) or {"nombre": nombre or ticker, "creado": ahora}
    entrada["actualizado"] = ahora
    if nombre:
        entrada["nombre"] = nombre
    if meta:
        entrada.update(meta)
    idx[ticker] = entrada
    _guardar_indice(idx)
    return ticker


def reconstruir_metadatos_indice() -> int:
    """Recalcula n_operaciones/ultima_fecha de todo el índice leyendo los parquets."""
    idx = _leer_indice()
    for ticker in list(idx.keys()):
        df = cargar_operaciones(ticker)
        idx[ticker].update(_meta_desde_df(df))
    _guardar_indice(idx)
    return len(idx)


def eliminar_activo(ticker: str) -> None:
    ticker = _normalizar_ticker(ticker)
    idx = _leer_indice()
    if ticker in idx:
        del idx[ticker]
        _guardar_indice(idx)
    _cache_drop(_parquet_relpath(ticker))
    if backend_actual() == "github":
        try:
            github_storage.delete_path(_parquet_relpath(ticker), mensaje=f"chore(data): drop {ticker}")
        except Exception:
            pass
        return
    carpeta = DATA_ROOT / ticker
    if carpeta.exists():
        for f in carpeta.rglob("*"):
            if f.is_file():
                try: f.unlink()
                except Exception: pass
        for d in sorted([p for p in carpeta.rglob("*") if p.is_dir()], reverse=True):
            try: d.rmdir()
            except Exception: pass
        try: carpeta.rmdir()
        except Exception: pass


# ---------------------------------------------------------------------------
# Operaciones (parquet)
# ---------------------------------------------------------------------------

def cargar_operaciones(ticker: str) -> pd.DataFrame:
    ticker = _normalizar_ticker(ticker)
    if backend_actual() == "github":
        key = _parquet_relpath(ticker)
        cached = _cache_get(key)
        if cached is not None:
            return cached.copy()
        try:
            data = github_storage.read_bytes(key)
            df = pd.read_parquet(io.BytesIO(data)) if data else pd.DataFrame()
        except Exception:
            df = pd.DataFrame()
        _cache_set(key, df)
        return df.copy()
    path = DATA_ROOT / ticker / "operations.parquet"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def guardar_operaciones(ticker: str, df: pd.DataFrame, modo: str = "append") -> int:
    """
    modo='append' → fusiona con lo existente y deduplica.
    modo='replace' → sobrescribe.
    Devuelve número total de filas tras guardar.
    """
    ticker = _normalizar_ticker(ticker)
    if df is None or df.empty:
        return len(cargar_operaciones(ticker))

    df = df.copy()
    if modo == "append":
        existente = cargar_operaciones(ticker)
        if not existente.empty:
            df = pd.concat([existente, df], ignore_index=True)

    keys = [c for c in ["EMISORA", "FECHA_OPERACION", "FOLIO", "CASA_BOLSA", "PRECIO_UNITARIO"] if c in df.columns]
    if keys:
        # keep="last": una re-lectura (p.ej. parser nuevo con SERIE) reemplaza a la anterior.
        df = df.drop_duplicates(subset=keys, keep="last")
    registrar_activo(ticker, meta=_meta_desde_df(df))
    _cache_drop(_parquet_relpath(ticker))

    # Serializar a parquet en memoria
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, compression="snappy")
    payload = buf.getvalue()

    if backend_actual() == "github":
        github_storage.write_bytes(
            _parquet_relpath(ticker),
            payload,
            mensaje=f"data({ticker}): {len(df):,} operaciones",
        )
    else:
        out = DATA_ROOT / ticker / "operations.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(payload)

    return len(df)


def guardar_pdf_bytes(ticker: str, nombre: str, contenido: bytes) -> Optional[str]:
    """
    En modo local persiste el PDF original. En modo github lo omite (los
    PDFs son recuperables vía la URL pública de BMV cuando se quiera).
    """
    ticker = registrar_activo(ticker)
    if backend_actual() == "github":
        return None  # No spamear el repo con PDFs
    destino = DATA_ROOT / ticker / "raw_pdfs" / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return str(destino)
