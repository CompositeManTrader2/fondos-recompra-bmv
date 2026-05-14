"""
Capa de persistencia local (parquet por activo).

Estructura en disco:
    data/activos/{TICKER}/operations.parquet   ← histórico consolidado
    data/activos/{TICKER}/raw_pdfs/*.pdf       ← (opcional) PDFs originales
    data/activos/_index.json                   ← lista maestra de activos

Streamlit Cloud: el filesystem es efímero entre reinicios. Esto sirve durante
la sesión y como cache local. Para algo permanente conviene un bucket S3 /
GCS / Supabase (ver README → Roadmap).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "activos"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
INDEX_FILE = DATA_ROOT / "_index.json"


# ---------------------------------------------------------------------------
# Helpers de tickers
# ---------------------------------------------------------------------------

def _normalizar_ticker(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    t = re.sub(r"[^A-Z0-9\.\-]", "", t)
    return t or "DESCONOCIDA"


def _carpeta_ticker(ticker: str) -> Path:
    p = DATA_ROOT / _normalizar_ticker(ticker)
    p.mkdir(parents=True, exist_ok=True)
    (p / "raw_pdfs").mkdir(parents=True, exist_ok=True)
    return p


def _parquet_path(ticker: str) -> Path:
    return _carpeta_ticker(ticker) / "operations.parquet"


# ---------------------------------------------------------------------------
# Índice maestro
# ---------------------------------------------------------------------------

def _leer_indice() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _guardar_indice(idx: dict) -> None:
    INDEX_FILE.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")


def listar_activos() -> list[dict]:
    """Devuelve lista de dicts con info por activo (ticker, nombre, n_ops, etc.)."""
    idx = _leer_indice()
    out = []
    for ticker, meta in idx.items():
        path = _parquet_path(ticker)
        n_ops = 0
        ult = None
        if path.exists():
            try:
                df = pd.read_parquet(path)
                n_ops = len(df)
                if "FECHA_OPERACION" in df.columns and not df.empty:
                    ult = pd.to_datetime(df["FECHA_OPERACION"]).max()
            except Exception:
                pass
        out.append({
            "ticker": ticker,
            "nombre": meta.get("nombre", ticker),
            "creado": meta.get("creado"),
            "actualizado": meta.get("actualizado"),
            "n_operaciones": n_ops,
            "ultima_fecha": ult.isoformat() if pd.notna(ult) and ult is not None else None,
        })
    return sorted(out, key=lambda x: x["ticker"])


def registrar_activo(ticker: str, nombre: Optional[str] = None) -> str:
    """Crea/actualiza la entrada del activo en el índice."""
    ticker = _normalizar_ticker(ticker)
    idx = _leer_indice()
    ahora = datetime.now().isoformat(timespec="seconds")
    if ticker not in idx:
        idx[ticker] = {
            "nombre": nombre or ticker,
            "creado": ahora,
            "actualizado": ahora,
        }
    else:
        idx[ticker]["actualizado"] = ahora
        if nombre:
            idx[ticker]["nombre"] = nombre
    _guardar_indice(idx)
    return ticker


def eliminar_activo(ticker: str) -> None:
    ticker = _normalizar_ticker(ticker)
    idx = _leer_indice()
    if ticker in idx:
        del idx[ticker]
        _guardar_indice(idx)
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
    path = _parquet_path(ticker)
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
    Devuelve el número total de filas tras guardar.
    """
    ticker = registrar_activo(ticker)
    if df is None or df.empty:
        return len(cargar_operaciones(ticker))

    df = df.copy()
    if modo == "append":
        existente = cargar_operaciones(ticker)
        if not existente.empty:
            df = pd.concat([existente, df], ignore_index=True)

    # Dedupe por una llave razonable
    keys = [c for c in ["EMISORA", "FECHA_OPERACION", "FOLIO", "CASA_BOLSA", "PRECIO_UNITARIO"] if c in df.columns]
    if keys:
        df = df.drop_duplicates(subset=keys, keep="first")

    df.to_parquet(_parquet_path(ticker), index=False)
    return len(df)


def guardar_pdf_bytes(ticker: str, nombre: str, contenido: bytes) -> Path:
    """Persiste el PDF original en data/activos/{TICKER}/raw_pdfs/."""
    ticker = registrar_activo(ticker)
    destino = _carpeta_ticker(ticker) / "raw_pdfs" / nombre
    destino.write_bytes(contenido)
    return destino
