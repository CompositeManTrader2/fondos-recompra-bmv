"""
Auto-descarga de PDFs de recompra desde la API REST interna de BMV.

⚙️ Cómo se descubrió este endpoint
----------------------------------
La página `bmv.com.mx/.../simec_documentos_recompra_` es una SPA Nuxt.js
que internamente llama a una API REST WSO2:

  POST  https://www.bmv.com.mx/api/searchservice/v1
  GET   https://www.bmv.com.mx/rest/tokenservice/token?grant_type=client_credentials

Las credenciales OAuth2 (consumer key/secret) están **embebidas en el
bundle público del frontend** (`/_nuxt/22137e5.modern.js`), por lo que
son perfectamente legítimas para uso por el cliente.

El componente que renderiza la lista de documentos (`BusquedaDocumentos`)
usa **ag-grid en modo Server-Side**: cada vez que se hace scroll, manda
una request con `searchType=busquedaDocumentosPorInstrumentos` y un
campo `requestJson` (string serializado de la request de ag-grid: rango
de filas, filtros y ordenamiento).

La respuesta trae documentos de TODOS los tipos (prospectos, eventos
relevantes, recompras, etc.). Filtramos por `cve_tipo_documento=="recompra"`
y por `cve_empresa==<clave>` para quedarnos sólo con lo que importa.

Esta implementación NO requiere Playwright/Chromium → funciona en
Streamlit Cloud sin configuración extra.
"""
from __future__ import annotations

import base64
import json
import re
import time
from typing import Iterable, Optional

import requests

# Constantes (extraídas del bundle público de BMV el 14-may-2026)
TOKEN_URL = "https://www.bmv.com.mx/rest/tokenservice/token"
SEARCH_URL = "https://www.bmv.com.mx/api/searchservice/v1"
CONSUMER_KEY = "4EvENfi6au5ZFV9AcPsqLW7SiNUa"
CONSUMER_SECRET = "_jkf9KE2rRvhY6a4GUtyV4wM6OMa"
CDN_BASE = "https://www.bmv.com.mx"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Token OAuth2
# ---------------------------------------------------------------------------

_token_cache: dict = {"value": None, "expires_at": 0.0}


def obtener_token(force: bool = False) -> str:
    """Obtiene un access token y lo cachea ~50 minutos en memoria."""
    if not force and _token_cache["value"] and _token_cache["expires_at"] > time.time():
        return _token_cache["value"]

    basic = base64.b64encode(f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode()).decode()
    r = requests.get(
        f"{TOKEN_URL}?grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {basic}",
            "User-Agent": UA,
            "Accept": "application/json",
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("status"):
        raise RuntimeError(f"Token OAuth no devuelto: {data}")
    tok = data["response"]["access_token"]
    # WSO2 marca expiración enorme; cacheamos 50 min por prudencia
    _token_cache["value"] = tok
    _token_cache["expires_at"] = time.time() + 50 * 60
    return tok


# ---------------------------------------------------------------------------
# Endpoint POST /api/searchservice/v1
# ---------------------------------------------------------------------------

def _ag_grid_request(start: int, end: int, filtro_descripcion: Optional[str] = None) -> str:
    """Genera el `requestJson` que ag-grid envía al backend."""
    req = {
        "startRow": start,
        "endRow": end,
        "rowGroupCols": [],
        "valueCols": [],
        "pivotCols": [],
        "pivotMode": False,
        "groupKeys": [],
        "filterModel": {},
        "sortModel": [{"colId": "_source.fecha_recepcion", "sort": "desc"}],
    }
    if filtro_descripcion:
        req["filterModel"]["_source.descripccion_documento"] = {
            "filterType": "text",
            "type": "contains",
            "filter": filtro_descripcion,
        }
    return json.dumps(req, separators=(",", ":"))


def _post_search(termino: str, request_json: str, token: str) -> dict:
    parts = termino.strip().split(" ", 1)
    term1 = parts[0]
    term2 = parts[1] if len(parts) > 1 else ""
    body = {
        "lang": "es",
        "payload": {
            "term": term1,
            "term2": term2,
            "termT": termino.strip(),
            "searchType": "busquedaDocumentosPorInstrumentos",
        },
        "requestJson": request_json,
    }
    r = requests.post(
        SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "User-Agent": UA,
            "Origin": "https://www.bmv.com.mx",
            "Referer": f"https://www.bmv.com.mx/es/bmv/busqueda/{termino.replace(' ', '_')}?tab=1",
        },
        data=json.dumps(body),
        timeout=60,
    )
    if r.status_code == 401:
        # Token expirado: refrescar y reintentar una vez
        token = obtener_token(force=True)
        r = requests.post(
            SEARCH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "*/*",
                "User-Agent": UA,
            },
            data=json.dumps(body),
            timeout=60,
        )
    r.raise_for_status()
    return r.json()


def _extraer_hits(data: dict) -> tuple[list[dict], int]:
    """Devuelve (hits, total)."""
    try:
        instr = data["response"]["instrumentosEmisoras"]["instrumentos"]
        primera_clave = next(iter(instr.keys()))
        documentos = instr[primera_clave]["documentos"]
        return documentos.get("hits", []), int(documentos.get("total", {}).get("value", 0))
    except (KeyError, StopIteration):
        return [], 0


def _es_recompra(doc_source: dict, clave: str) -> bool:
    cve_tipo = (doc_source.get("cve_tipo_documento") or "").lower()
    cve_emp = (doc_source.get("cve_empresa") or "").upper()
    if cve_tipo != "recompra":
        return False
    if clave and cve_emp != clave.upper():
        return False
    url = ((doc_source.get("documento_html") or {}).get("url_documento") or "").lower()
    return "recompra" in url and url.endswith(".pdf")


# ---------------------------------------------------------------------------
# API pública del módulo
# ---------------------------------------------------------------------------

def descubrir_pdfs(
    clave: str,
    max_documentos: int = 1000,
    page_size: int = 100,
    progreso_cb=None,
) -> list[dict]:
    """
    Descubre todos los PDFs de recompra de una emisora (ej. 'AMX', 'BIMBO').

    Devuelve una lista de dicts con:
        - url:          URL absoluta al PDF
        - fecha:        fecha_recepcion (string YYYY-MM-DD HH:MM)
        - id_documento: ID interno BMV
        - cve_empresa:  clave de la emisora
        - descripcion:  descripcion del documento

    progreso_cb(actual, total) se llama si se pasa.
    """
    if not clave or not str(clave).strip():
        raise ValueError("Debes pasar una clave de cotización (ej. 'AMX').")
    clave = str(clave).strip().upper()

    token = obtener_token()
    documentos: list[dict] = []
    vistos: set[str] = set()

    start = 0
    intentos_vacios = 0  # corta si varias páginas seguidas no traen recompras de la clave
    total_estimado = None

    while start < max_documentos:
        end = min(start + page_size, max_documentos)
        req_json = _ag_grid_request(start, end, filtro_descripcion="Recompras")
        try:
            data = _post_search(clave, req_json, token)
        except requests.HTTPError as e:
            raise RuntimeError(f"Error HTTP de BMV: {e!s}") from e

        hits, total = _extraer_hits(data)
        if total_estimado is None:
            total_estimado = total

        if not hits:
            break

        nuevos = 0
        for h in hits:
            src = h.get("_source", {}) or {}
            if not _es_recompra(src, clave):
                continue
            url_rel = (src.get("documento_html") or {}).get("url_documento") or ""
            if not url_rel:
                continue
            url_abs = url_rel if url_rel.startswith("http") else CDN_BASE + url_rel
            if url_abs in vistos:
                continue
            vistos.add(url_abs)
            documentos.append({
                "url": url_abs,
                "fecha": src.get("fecha_recepcion"),
                "id_documento": src.get("id_documento"),
                "cve_empresa": src.get("cve_empresa"),
                "descripcion": src.get("descripccion_documento"),
            })
            nuevos += 1

        if progreso_cb:
            try:
                progreso_cb(len(documentos), total_estimado or len(documentos))
            except Exception:
                pass

        if nuevos == 0:
            intentos_vacios += 1
            if intentos_vacios >= 3:
                break
        else:
            intentos_vacios = 0

        if start + page_size >= total:
            break
        start += page_size

    documentos.sort(key=lambda d: d.get("fecha") or "", reverse=False)
    return documentos


def descargar_pdfs(
    docs: Iterable[dict],
    timeout: int = 30,
    progreso_cb=None,
) -> list[tuple[str, bytes]]:
    """Descarga una lista de docs (output de descubrir_pdfs)."""
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})
    out: list[tuple[str, bytes]] = []
    docs_list = list(docs)
    for i, d in enumerate(docs_list, start=1):
        url = d["url"] if isinstance(d, dict) else d
        nombre = url.rstrip("/").split("/")[-1] or "documento.pdf"
        try:
            r = sess.get(url, timeout=timeout)
            out.append((nombre, r.content if r.status_code == 200 else b""))
        except Exception:
            out.append((nombre, b""))
        if progreso_cb:
            try:
                progreso_cb(i, len(docs_list), nombre)
            except Exception:
                pass
    return out


# ---------------------------------------------------------------------------
# Bookmarklet (mantenido como fallback opcional)
# ---------------------------------------------------------------------------

def generar_bookmarklet() -> str:
    js = (
        "(async()=>{const s=ms=>new Promise(r=>setTimeout(r,ms));"
        "const set=new Set();const c=()=>document.querySelectorAll('a').forEach("
        "a=>{if(/recompra_.*\\.pdf$/i.test(a.href||''))set.add(a.href);});"
        "const sc=()=>document.querySelector('.cdk-virtual-scroll-viewport')||document.scrollingElement;"
        "for(let p=0;p<60;p++){c();const x=sc();if(x)x.scrollBy(0,800);await s(220);}"
        "c();const arr=Array.from(set).sort();"
        "const b=new Blob([arr.join('\\n')],{type:'text/plain'});"
        "const a=document.createElement('a');a.href=URL.createObjectURL(b);"
        "a.download='bmv_pdfs.txt';document.body.appendChild(a);a.click();a.remove();"
        "alert('PDFs encontrados: '+arr.length);})();"
    )
    return "javascript:" + js
