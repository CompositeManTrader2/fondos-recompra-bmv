"""
Acceso a precios de mercado para comparar contra el VWAP del fondo.

Usa Yahoo Finance (yfinance). Las emisoras mexicanas suelen llevar sufijo `.MX`
(p. ej. AMXL.MX, GFNORTEO.MX, ALFAA.MX). Si el ticker que viene del PDF no
trae sufijo, lo agregamos automáticamente.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

try:
    import yfinance as yf
    YF_DISPONIBLE = True
except Exception:
    YF_DISPONIBLE = False


def _ticker_yahoo(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    if not t:
        return t
    if "." in t:
        return t
    return f"{t}.MX"


def precios_diarios(
    ticker: str,
    fecha_inicio: Optional[datetime] = None,
    fecha_fin: Optional[datetime] = None,
) -> pd.DataFrame:
    """Devuelve DataFrame con columnas Date, Open, High, Low, Close, Volume."""
    if not YF_DISPONIBLE or not ticker:
        return pd.DataFrame()
    if fecha_inicio is None:
        fecha_inicio = datetime.now() - timedelta(days=365)
    if fecha_fin is None:
        fecha_fin = datetime.now()
    sym = _ticker_yahoo(ticker)
    try:
        df = yf.download(
            sym,
            start=fecha_inicio.strftime("%Y-%m-%d"),
            end=(fecha_fin + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        # yfinance puede devolver MultiIndex en columnas si hay múltiples tickers
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
        return df
    except Exception:
        return pd.DataFrame()
