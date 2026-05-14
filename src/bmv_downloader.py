"""
Utilidades para descargar PDFs directamente desde URLs públicas de la BMV.
"""
from __future__ import annotations

import re
from typing import Iterable

import requests

URL_REGEX = re.compile(
    r"https://www\.bmv\.com\.mx/docs-pub/recompra/[^\s\"'<>]+\.pdf",
    re.IGNORECASE,
)


def extraer_urls(raw: str) -> list[str]:
    """De un texto sucio (paste de consola del navegador) saca y deduplica URLs."""
    urls = URL_REGEX.findall(raw or "")
    # Preservar orden pero deduplicar
    vistos = set()
    out = []
    for u in urls:
        if u not in vistos:
            vistos.add(u)
            out.append(u)
    return out


def descargar(urls: Iterable[str], timeout: int = 30) -> list[tuple[str, bytes]]:
    """Descarga cada URL y devuelve [(nombre_archivo, contenido_bytes), ...].

    Si algún URL falla, se omite silenciosamente y se reporta como tupla con bytes vacíos
    para que el caller pueda detectarlo.
    """
    results = []
    sess = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FondosRecompraBMV/1.0)"}
    for url in urls:
        nombre = url.rstrip("/").split("/")[-1] or "documento.pdf"
        try:
            r = sess.get(url, timeout=timeout, headers=headers)
            if r.status_code == 200 and r.content:
                results.append((nombre, r.content))
            else:
                results.append((nombre, b""))
        except Exception:
            results.append((nombre, b""))
    return results
