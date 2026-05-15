"""
Acceso a precios de mercado para comparar contra el VWAP del fondo de recompra.

Particularidades de los tickers mexicanos en Yahoo Finance
----------------------------------------------------------
La `cve_emisora` de BMV (AMX, BIMBO, GFNORTE) raramente coincide
directamente con el símbolo de Yahoo. En Yahoo se usa el ticker bursátil
completo + sufijo `.MX`:

    BMV         Yahoo
    AMX     →   AMXB.MX        (serie B)
    BIMBO   →   BIMBOA.MX      (serie A)
    GFNORTE →   GFNORTEO.MX    (serie O)
    CEMEX   →   CEMEXCPO.MX    (CPO)
    ICH     →   ICHB.MX        (serie B)
    WALMEX  →   WALMEX.MX      (serie *, sin sufijo)
    ALFA    →   ALFAA.MX       (serie A; ALFA dejó de cotizar pero series antiguas siguen)
    SIMEC   →   SIMECB.MX
    GAP     →   GAPB.MX
    KIMBER  →   KIMBERA.MX
    LIVERPOL→   LIVEPOLC-1.MX

`auto_resolver_yahoo()` prueba estas variantes en orden hasta encontrar
una que devuelva precios. El primer match se cachea.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    import yfinance as yf
    YF_DISPONIBLE = True
except Exception:
    YF_DISPONIBLE = False

# Caché persistente de mappings descubiertos (cve_emisora → símbolo Yahoo)
_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "yahoo_mapping.json"


def _leer_cache() -> dict:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _guardar_cache(mapping: dict) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Mapeo manual conocido (overrides comunes)
# ---------------------------------------------------------------------------
# Si la cve_emisora aparece aquí, se prueba primero esta variante antes de
# barrer sufijos genéricos. Esto evita falsos positivos.
MAPEO_MANUAL: dict[str, str] = {
    "AMX": "AMXB.MX",
    "BIMBO": "BIMBOA.MX",
    "GFNORTE": "GFNORTEO.MX",
    "CEMEX": "CEMEXCPO.MX",
    "ICH": "ICHB.MX",
    "WALMEX": "WALMEX.MX",
    "ALFA": "ALFAA.MX",
    "SIMEC": "SIMECB.MX",
    "GAP": "GAPB.MX",
    "KIMBER": "KIMBERA.MX",
    "GMEXICO": "GMEXICOB.MX",
    "ALSEA": "ALSEA.MX",
    "TLEVISA": "TLEVISACPO.MX",
    "FEMSA": "FEMSAUBD.MX",
    "MEGA": "MEGACPO.MX",
    "GENTERA": "GENTERA.MX",
    "VESTA": "VESTA.MX",
    "ASUR": "ASURB.MX",
    "OMA": "OMAB.MX",
    "ELEKTRA": "ELEKTRA.MX",
    "GCC": "GCC.MX",
    "PINFRA": "PINFRA.MX",
    "PE&OLES": "PE&OLES.MX",
    "QUALITAS": "QC.MX",
    "ALPEK": "ALPEKA.MX",
    "ORBIA": "ORBIA.MX",
    "GRUMA": "GRUMAB.MX",
    "AC": "AC.MX",
    "BBAJIO": "BBAJIOO.MX",
    "BSMX": "BSMXB.MX",
    "RA": "RA.MX",
    "GCARSO": "GCARSOA1.MX",
    "GFINBUR": "GFINBURO.MX",
    "GISSA": "GISSAA.MX",
    "GFAMSA": "GFAMSAA.MX",
    "ARA": "ARA.MX",
    "FIBRAPL": "FIBRAPL14.MX",
}

# Sufijos de serie probables, en orden de frecuencia.
# Mantenemos el set CHICO para no agotar el rate-limit de Yahoo cuando
# probamos tickers que no existen.
_SUFIJOS_YAHOO = ["", "B", "A", "O", "CPO", "L", "B-1", "UBD"]


def _normalizar_dataframe_yf(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance >=1.0 devuelve siempre MultiIndex en columnas. Aplastamos."""
    if df is None or df.empty:
        return pd.DataFrame()
    # Aplastar MultiIndex (toma el primer nivel: Open, Close, etc.)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index()
    if df.index.name and df.index.name.lower() == "date":
        df = df.reset_index()
    if "Date" not in df.columns:
        # Buscar columna que contenga la fecha
        for col in df.columns:
            if str(col).lower() in ("date", "datetime", "fecha"):
                df = df.rename(columns={col: "Date"})
                break
    if "Date" not in df.columns:
        return pd.DataFrame()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize()
    # Mantener sólo columnas relevantes
    cols_keep = ["Date"] + [c for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in df.columns]
    return df[cols_keep]


def _intentar_descarga(simbolo: str, fecha_inicio: datetime, fecha_fin: datetime) -> pd.DataFrame:
    """Descarga un símbolo Yahoo y normaliza. Devuelve DF vacío si falla."""
    if not YF_DISPONIBLE:
        return pd.DataFrame()
    try:
        df = yf.download(
            simbolo,
            start=fecha_inicio.strftime("%Y-%m-%d"),
            end=(fecha_fin + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        return _normalizar_dataframe_yf(df)
    except Exception:
        return pd.DataFrame()


def _generar_simbolos_candidatos(cve: str) -> list[str]:
    """
    Devuelve la lista ordenada de símbolos a probar para una cve_emisora BMV.
    """
    cve = (cve or "").strip().upper()
    if not cve:
        return []

    candidatos: list[str] = []
    visto: set[str] = set()

    def _add(s: str):
        s = s.upper()
        if s and s not in visto:
            visto.add(s)
            candidatos.append(s)

    # 1) Mapeo manual conocido
    if cve in MAPEO_MANUAL:
        _add(MAPEO_MANUAL[cve])

    # 2) ticker tal cual + .MX
    _add(f"{cve}.MX")

    # 3) Probar sufijos comunes
    for sfx in _SUFIJOS_YAHOO:
        if sfx:
            _add(f"{cve}{sfx}.MX")

    return candidatos


def auto_resolver_yahoo(
    cve_emisora: str,
    fecha_inicio: datetime,
    fecha_fin: datetime,
    forzar: bool = False,
) -> tuple[Optional[str], pd.DataFrame, list[str]]:
    """
    Intenta resolver y descargar precios para una cve_emisora BMV.

    Devuelve:
        (simbolo_exitoso, df_precios, lista_de_simbolos_intentados)

    Si ninguno funciona → (None, pd.DataFrame(), intentos).

    Caché persistente:
      - Si ya tenemos un mapping cve→symbol guardado en disco, lo usamos
        directo (sin barrer todas las variantes).
      - Cuando se descubre un nuevo mapping exitoso, se persiste.
      - `forzar=True` ignora el caché y vuelve a barrer.
    """
    intentos: list[str] = []
    if not YF_DISPONIBLE:
        return None, pd.DataFrame(), intentos
    cve = (cve_emisora or "").strip().upper()
    if not cve:
        return None, pd.DataFrame(), intentos

    cache = _leer_cache()

    import time as _time
    sym_cached_pending = None

    # 1) Cache hit?
    if not forzar and cve in cache:
        sym_cached = cache[cve]
        intentos.append(sym_cached)
        df = _intentar_descarga(sym_cached, fecha_inicio, fecha_fin)
        if df is not None and not df.empty:
            return sym_cached, df, intentos
        # Cache hit pero sin datos: probablemente rate-limit/red transitoria.
        # NO quitamos el cache (era válido antes); intentamos otras variantes
        # como respaldo y, si todas fallan, devolvemos el cached con DF vacío
        # para que la UI sepa que el mapping existe pero la descarga falló.
        sym_cached_pending = sym_cached

    # 2) Barrido de candidatos (con pequeño delay para no saturar Yahoo)
    candidatos = _generar_simbolos_candidatos(cve)
    for sym in candidatos:
        if sym in intentos:
            continue
        intentos.append(sym)
        df = _intentar_descarga(sym, fecha_inicio, fecha_fin)
        if df is not None and not df.empty:
            cache[cve] = sym
            _guardar_cache(cache)
            return sym, df, intentos
        _time.sleep(0.2)  # courtesy delay

    # 3) Si ya conocíamos el symbol, devolverlo aunque sin datos esta vez
    if sym_cached_pending:
        return sym_cached_pending, pd.DataFrame(), intentos

    return None, pd.DataFrame(), intentos


def cache_yahoo_mapping() -> dict:
    """Lectura pública del caché de mappings cve_emisora → símbolo Yahoo."""
    return _leer_cache()


def set_yahoo_mapping(cve_emisora: str, simbolo: str) -> None:
    """Permite a la UI fijar manualmente un mapping (override)."""
    cache = _leer_cache()
    cache[cve_emisora.strip().upper()] = simbolo.strip().upper()
    _guardar_cache(cache)


def precios_diarios(
    simbolo: str,
    fecha_inicio: Optional[datetime] = None,
    fecha_fin: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Descarga precios para un símbolo Yahoo Finance EXACTO (sin auto-resolver).
    Útil cuando el usuario hace override manual.
    """
    if not simbolo or not YF_DISPONIBLE:
        return pd.DataFrame()
    if fecha_inicio is None:
        fecha_inicio = datetime.now() - timedelta(days=365)
    if fecha_fin is None:
        fecha_fin = datetime.now()
    return _intentar_descarga(simbolo.strip().upper(), fecha_inicio, fecha_fin)
