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


# ---------------------------------------------------------------------------
# Resolutor de tickers — convierte tickers bursátiles (AMXL, BIMBOA…) en
# la cve_emisora real de BMV (AMX, BIMBO…)
# ---------------------------------------------------------------------------

# Sufijos comunes de series accionarias mexicanas, ordenados de MÁS LARGO a
# más corto para que probemos primero "CPO" antes de "C" sólo.
_SUFIJOS_SERIE = ["CPO", "*", "A1", "B1", "B-1", "L", "O", "A", "B", "C", "1", "2"]


def _generar_variantes(ticker: str) -> list[str]:
    """Devuelve el ticker más todas sus variantes plausibles sin sufijo de serie."""
    t = (ticker or "").strip().upper()
    variantes = [t]
    for sfx in _SUFIJOS_SERIE:
        if t.endswith(sfx) and len(t) > len(sfx) + 1:
            base = t[: -len(sfx)]
            if base not in variantes:
                variantes.append(base)
    return variantes


def _post_clave_cotizacion(termino: str, token: str) -> list[dict]:
    """Llama a busquedaClaveCotizacion y devuelve los hits de instrumentos."""
    body = {
        "lang": "es",
        "payload": {
            "term": termino, "term2": "", "termT": termino,
            "searchType": "busquedaClaveCotizacion",
        },
    }
    r = requests.post(
        SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "User-Agent": UA,
        },
        json=body,
        timeout=30,
    )
    if r.status_code != 200:
        return []
    try:
        return r.json()["response"]["busquedaClaveCotizacion"]["instrumentos"]["hits"]
    except (KeyError, TypeError):
        return []


def resolver_emisora(ticker: str) -> dict:
    """
    Convierte un ticker bursátil libre (AMXL, BIMBOA, WALMEX*, etc.) en una
    cve_emisora canónica de BMV (AMX, BIMBO, WALMEX).

    Estrategia:
      1. Probar el ticker tal cual.
      2. Si no devuelve nada, probar variantes quitando sufijos comunes.
      3. Filtrar resultados al mercado de Capitales (acciones, no deuda).
      4. Si hay UNA sola cve_emisora distinta → resolver automáticamente.
      5. Si hay varias → devolver lista para que la UI haga selector.

    Devuelve:
        {
          "estado": "ok" | "ambiguo" | "no_encontrado",
          "ticker_input": <str>,
          "cve_emisora": <str|None>,
          "razon_social": <str|None>,
          "candidatos": [{cve_emisora, razon_social, instrumento, mercado, intentado_con}, ...],
          "intentos": [<términos probados>],
        }
    """
    token = obtener_token()
    intentos = []
    candidatos: dict[str, dict] = {}

    for variante in _generar_variantes(ticker):
        intentos.append(variante)
        hits = _post_clave_cotizacion(variante, token)
        for h in hits:
            src = h.get("_source", {}) or {}
            cve = (src.get("cve_emisora") or "").upper()
            if not cve:
                continue
            mercado = src.get("mercado") or ""
            if cve not in candidatos:
                candidatos[cve] = {
                    "cve_emisora": cve,
                    "razon_social": src.get("razon_social"),
                    "instrumento": src.get("instrumento"),
                    "serie": src.get("serie"),
                    "mercado": mercado,
                    "id_empresa": src.get("id_empresa"),
                    "intentado_con": variante,
                }
        # Si en esta variante encontramos algo, dejamos de probar siguientes
        if candidatos:
            break

    if not candidatos:
        return {
            "estado": "no_encontrado",
            "ticker_input": ticker,
            "cve_emisora": None,
            "razon_social": None,
            "candidatos": [],
            "intentos": intentos,
        }

    # Filtrar a Capitales (preferimos acciones)
    capitales = [c for c in candidatos.values() if (c.get("mercado") or "").lower() == "capitales"]
    pool = capitales if capitales else list(candidatos.values())

    # Match exacto: si alguna variante intentada coincide EXACTAMENTE con
    # cve_emisora de un candidato, ese gana sobre todos los demás.
    intentos_upper = {i.upper() for i in intentos}
    exacto = [c for c in pool if c["cve_emisora"] in intentos_upper]
    if len(exacto) == 1:
        elegido = exacto[0]
        return {
            "estado": "ok",
            "ticker_input": ticker,
            "cve_emisora": elegido["cve_emisora"],
            "razon_social": elegido["razon_social"],
            "candidatos": pool,
            "intentos": intentos,
        }

    # Una sola cve_emisora distinta → resolución única
    cves_unicas = {c["cve_emisora"] for c in pool}
    if len(cves_unicas) == 1:
        elegido = pool[0]
        return {
            "estado": "ok",
            "ticker_input": ticker,
            "cve_emisora": elegido["cve_emisora"],
            "razon_social": elegido["razon_social"],
            "candidatos": pool,
            "intentos": intentos,
        }

    return {
        "estado": "ambiguo",
        "ticker_input": ticker,
        "cve_emisora": None,
        "razon_social": None,
        "candidatos": pool,
        "intentos": intentos,
    }


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
    auto_resolver: bool = True,
) -> list[dict]:
    """
    Descubre todos los PDFs de recompra de una emisora.

    Acepta tickers en cualquier forma común:
      - cve_emisora pura: 'AMX', 'BIMBO', 'WALMEX'
      - ticker bursátil con sufijo de serie: 'AMXL', 'BIMBOA', 'GFNORTEO',
        'WALMEX*', 'CEMEXCPO' — el resolutor las normaliza automáticamente.

    Devuelve lista de dicts:
        {url, fecha, id_documento, cve_empresa, descripcion}

    Si `auto_resolver=False` se asume que `clave` ya es la cve_emisora exacta
    y se omite la resolución (más rápido, no recomendado para inputs libres).
    """
    if not clave or not str(clave).strip():
        raise ValueError("Debes pasar una clave de cotización (ej. 'AMX').")
    clave_input = str(clave).strip().upper()

    # ---- Resolver al cve_emisora canónico ----
    if auto_resolver:
        resol = resolver_emisora(clave_input)
        if resol["estado"] == "no_encontrado":
            raise RuntimeError(
                f"No se encontró ninguna emisora en BMV para '{clave_input}'. "
                f"Variantes intentadas: {', '.join(resol['intentos'])}. "
                "Usa la cve_emisora exacta (ej. 'AMX' en lugar de 'AMXL')."
            )
        if resol["estado"] == "ambiguo":
            opciones = ", ".join(f"{c['cve_emisora']} ({c['razon_social']})" for c in resol["candidatos"])
            raise RuntimeError(
                f"'{clave_input}' coincide con múltiples emisoras en BMV. "
                f"Especifica una: {opciones}"
            )
        clave = resol["cve_emisora"]
    else:
        clave = clave_input

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
