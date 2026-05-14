"""
Extracción de información de los PDFs de operaciones de fondo de recompra
publicados por la BMV.

Diseñado para correr en Streamlit Cloud (sin Java) → usa pdfplumber en lugar
de tabula-py. Devuelve DataFrames limpios listos para procesamiento.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd
import pdfplumber

# Encabezados objetivo en la tabla de operaciones (variantes detectadas en BMV)
COLUMNAS_OBJETIVO = {
    "FOLIO": ["FOLIO"],
    "OPERACION": ["OPERACION", "OPERACIÓN", "TIPO DE OPERACION", "TIPO DE OPERACIÓN"],
    "NUMERO_DE_ACCIONES": [
        "NUMERO DE ACCIONES", "NÚMERO DE ACCIONES", "ACCIONES",
    ],
    "PRECIO_UNITARIO": [
        "PRECIO UNITARIO", "PRECIO UNIT", "PRECIO UNIT.",
    ],
    "IMPORTE_OPERACION": [
        "IMPORTE DE LA OPERACION", "IMPORTE DE LA OPERACIÓN",
        "IMPORTE OPERACION", "IMPORTE OPERACIÓN", "IMPORTE",
    ],
}

DIAS_SEMANA_ES = {
    0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
    4: "Viernes", 5: "Sábado", 6: "Domingo",
}


@dataclass
class ResultadoPDF:
    """Encapsula todo lo extraído de un PDF de recompra."""
    archivo: str
    emisora: Optional[str]
    fecha_operacion: Optional[datetime]
    casa_bolsa: Optional[str]
    remanente_ultimo: Optional[float]
    remanente_presente: Optional[float]
    operaciones: pd.DataFrame  # DataFrame normalizado (puede estar vacío)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers numéricos
# ---------------------------------------------------------------------------

def _to_float_decimal(x) -> Optional[float]:
    """Convierte '1,234.56' / '1.234,56' / '$1,234' a float."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    t = re.sub(r"[^0-9,.\-]", "", str(x).strip())
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(",", "")
    elif "," in t and "." not in t:
        t = t.replace(",", ".")
    parts = t.split(".")
    if len(parts) > 2:
        t = parts[0] + "." + "".join(parts[1:])
    try:
        return float(t)
    except ValueError:
        return None


def _to_int_strict(x) -> Optional[int]:
    """Quita TODOS los separadores y convierte a int."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).strip()
    sign = "-" if s.startswith("-") else ""
    digits = re.sub(r"[^0-9]", "", s)
    if not digits:
        return None
    try:
        return int(sign + digits)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Extractores individuales sobre el texto del PDF
# ---------------------------------------------------------------------------

_PATRONES_EMISORA = [
    re.compile(r"Clave\s*de\s*cotizaci[oó]n\s*[:\-]?\s*([A-Z0-9\.\-]+)", re.IGNORECASE),
    re.compile(r"Clave\s*de\s*c[oó]tizaci[oó]n\s*[:\-]?\s*([A-Z0-9\.\-]+)", re.IGNORECASE),
]
_PATRON_FECHA = re.compile(r"FECHA\s+DE\s+OPERACI[OÓ]N", re.IGNORECASE)
_PATRON_FECHA_VALOR = re.compile(r"(\d{2}/\d{2}/\d{4})")
_PATRON_CASA = re.compile(r"CASA\s+DE\s+BOLSA", re.IGNORECASE)


def _extraer_emisora(texto: str) -> Optional[str]:
    for pat in _PATRONES_EMISORA:
        m = pat.search(texto)
        if m:
            # Limpiar puntuación final
            return m.group(1).strip().rstrip(".,;:")
    return None


def _extraer_fecha(texto: str) -> Optional[datetime]:
    for linea in texto.split("\n"):
        if _PATRON_FECHA.search(linea):
            m = _PATRON_FECHA_VALOR.search(linea)
            if m:
                try:
                    return datetime.strptime(m.group(1), "%d/%m/%Y")
                except ValueError:
                    pass
    # Fallback: primera fecha del documento
    m = _PATRON_FECHA_VALOR.search(texto)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d/%m/%Y")
        except ValueError:
            return None
    return None


def _extraer_casa_bolsa(texto: str) -> Optional[str]:
    for linea in texto.split("\n"):
        if _PATRON_CASA.search(linea):
            partes = linea.split(":")
            if len(partes) > 1:
                nombre = partes[-1].strip()
                # Algunos PDFs ponen la casa en la siguiente línea sin ":"
                return re.sub(r"^CASA\s+DE\s+BOLSA\s*", "", nombre, flags=re.IGNORECASE).strip() or nombre
            # Sin ":": tomar lo que sigue de la frase
            limpio = re.sub(r".*CASA\s+DE\s+BOLSA\s*", "", linea, flags=re.IGNORECASE).strip()
            if limpio:
                return limpio
    return None


def _extraer_remanente(texto: str) -> tuple[Optional[float], Optional[float]]:
    ultimo, presente = None, None
    lineas = texto.split("\n")
    for i, linea in enumerate(lineas):
        if "REMANENTE DE RECURSOS" in linea.upper():
            for j in range(i, min(i + 6, len(lineas))):
                up = lineas[j].upper()
                ultimo_token = lineas[j].split()[-1] if lineas[j].split() else ""
                valor = _to_float_decimal(ultimo_token)
                if valor is None:
                    continue
                if "ÚLTIMO REPORTE" in up or "ULTIMO REPORTE" in up:
                    ultimo = valor
                elif "PRESENTE" in up and "REPORTE" not in up:
                    presente = valor
            break
    return ultimo, presente


# ---------------------------------------------------------------------------
# Extracción de la tabla de operaciones con pdfplumber
# ---------------------------------------------------------------------------

def _normalizar_header(h: str) -> str:
    h = (h or "").upper().strip()
    h = re.sub(r"\s+", " ", h)
    return h


def _mapear_columnas(headers: list[str]) -> dict[int, str]:
    """Devuelve {idx_col_original: nombre_objetivo} basado en los encabezados."""
    mapping = {}
    norm = [_normalizar_header(h) for h in headers]
    for objetivo, alias in COLUMNAS_OBJETIVO.items():
        for i, h in enumerate(norm):
            if any(a in h for a in alias):
                if i not in mapping:  # primera coincidencia
                    mapping[i] = objetivo
                break
    return mapping


def _es_tabla_operaciones(headers: list[str]) -> bool:
    norm = " | ".join(_normalizar_header(h) for h in headers)
    return ("FOLIO" in norm) and ("PRECIO" in norm or "ACCION" in norm)


def _extraer_tablas(pdf: pdfplumber.PDF) -> pd.DataFrame:
    """Itera todas las páginas y consolida las filas de operaciones."""
    filas: list[dict] = []
    for page in pdf.pages:
        # Estrategia mixta: primero intentamos lattice (líneas), luego stream
        configs = [
            {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
            {"vertical_strategy": "text",  "horizontal_strategy": "text"},
        ]
        tablas = []
        for cfg in configs:
            try:
                t = page.extract_tables(cfg)
                if t:
                    tablas = t
                    break
            except Exception:
                continue
        for tabla in tablas or []:
            if not tabla or len(tabla) < 2:
                continue
            headers = tabla[0]
            if not _es_tabla_operaciones(headers):
                continue
            mapping = _mapear_columnas(headers)
            if not mapping or "PRECIO_UNITARIO" not in mapping.values():
                continue
            for fila in tabla[1:]:
                registro = {}
                for idx_col, destino in mapping.items():
                    if idx_col < len(fila):
                        registro[destino] = fila[idx_col]
                if registro:
                    filas.append(registro)

    if not filas:
        return pd.DataFrame(
            columns=list(COLUMNAS_OBJETIVO.keys())
        )

    df = pd.DataFrame(filas)
    # Tipos numéricos
    if "FOLIO" in df.columns:
        df["FOLIO"] = df["FOLIO"].map(_to_int_strict).astype("Int64")
    if "NUMERO_DE_ACCIONES" in df.columns:
        df["NUMERO_DE_ACCIONES"] = df["NUMERO_DE_ACCIONES"].map(_to_int_strict).astype("Int64")
    if "IMPORTE_OPERACION" in df.columns:
        df["IMPORTE_OPERACION"] = df["IMPORTE_OPERACION"].map(_to_int_strict).astype("Int64")
    if "PRECIO_UNITARIO" in df.columns:
        df["PRECIO_UNITARIO"] = df["PRECIO_UNITARIO"].map(_to_float_decimal).astype("Float64")
    if "OPERACION" in df.columns:
        df["OPERACION"] = (
            df["OPERACION"].astype(str).str.upper().str.strip()
            .str.replace(r"\s+", " ", regex=True)
        )

    # Eliminar filas basura (sin precio o sin acciones)
    df = df.dropna(subset=["PRECIO_UNITARIO"])
    df = df[df.get("PRECIO_UNITARIO", pd.Series(dtype=float)) > 0]
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def parsear_pdf(file_or_bytes, nombre_archivo: str = "documento.pdf") -> ResultadoPDF:
    """
    Punto único de entrada. Acepta:
      - ruta str
      - bytes
      - file-like (UploadedFile de Streamlit)
    """
    try:
        if isinstance(file_or_bytes, (bytes, bytearray)):
            pdf_ctx = pdfplumber.open(io.BytesIO(file_or_bytes))
        elif hasattr(file_or_bytes, "read"):
            data = file_or_bytes.read()
            try:
                file_or_bytes.seek(0)  # por si luego se reusa
            except Exception:
                pass
            pdf_ctx = pdfplumber.open(io.BytesIO(data))
        else:
            pdf_ctx = pdfplumber.open(file_or_bytes)

        with pdf_ctx as pdf:
            texto_total = "\n".join((p.extract_text() or "") for p in pdf.pages)
            emisora = _extraer_emisora(texto_total)
            fecha = _extraer_fecha(texto_total)
            casa = _extraer_casa_bolsa(texto_total)
            ultimo, presente = _extraer_remanente(texto_total)
            ops = _extraer_tablas(pdf)

        if not ops.empty:
            if fecha is not None:
                ops["FECHA_OPERACION"] = fecha
                ops["DIA_SEMANA"] = DIAS_SEMANA_ES[fecha.weekday()]
            if casa is not None:
                ops["CASA_BOLSA"] = casa
            if emisora is not None:
                ops["EMISORA"] = emisora
            ops["ARCHIVO_ORIGEN"] = nombre_archivo

        return ResultadoPDF(
            archivo=nombre_archivo,
            emisora=emisora,
            fecha_operacion=fecha,
            casa_bolsa=casa,
            remanente_ultimo=ultimo,
            remanente_presente=presente,
            operaciones=ops,
        )
    except Exception as e:
        return ResultadoPDF(
            archivo=nombre_archivo,
            emisora=None, fecha_operacion=None, casa_bolsa=None,
            remanente_ultimo=None, remanente_presente=None,
            operaciones=pd.DataFrame(columns=list(COLUMNAS_OBJETIVO.keys())),
            error=str(e),
        )
