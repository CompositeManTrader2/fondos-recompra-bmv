"""
Auto-descarga de PDFs desde la página pública de BMV.

La página `bmv.com.mx/es/bmv/busqueda/simec_documentos_recompra_` es una SPA
Angular: NO hay endpoint REST público, así que no podemos usar `requests`.
Solución: lanzar un Chromium headless con Playwright.

Modos disponibles:
  - playwright_disponible(): True si el navegador está listo en este host.
  - asegurar_playwright(): hace `playwright install chromium` lazy en el
    primer arranque (útil en Streamlit Cloud).
  - descubrir_pdfs(clave, max_paginas): devuelve la lista de URLs únicas.
  - generar_bookmarklet(): cadena `javascript:` lista para fallback manual.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

URL_BUSQUEDA = "https://www.bmv.com.mx/es/bmv/busqueda/simec_documentos_recompra_?tab=1"


def playwright_disponible() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except Exception:
        return False


def asegurar_playwright(con_deps: bool = False) -> tuple[bool, str]:
    """
    Garantiza que Chromium esté instalado. En Streamlit Cloud el binario no
    está pre-descargado; este helper lo instala bajo demanda y cachea el
    resultado en disco. Devuelve (ok, mensaje).
    """
    if not playwright_disponible():
        return False, "El paquete `playwright` no está instalado. Añádelo a requirements.txt."

    # Si ya hay un browser cacheado, salir
    cache_dir = Path.home() / ".cache" / "ms-playwright"
    if cache_dir.exists() and any(cache_dir.glob("chromium*")):
        return True, "Chromium ya disponible en caché."

    cmd = [sys.executable, "-m", "playwright", "install"]
    if con_deps:
        cmd.append("--with-deps")
    cmd.append("chromium")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        return True, "Chromium instalado correctamente."
    except subprocess.CalledProcessError as e:
        return False, f"Error instalando Chromium: {e.stderr or e.stdout}"
    except Exception as e:
        return False, f"Excepción instalando Chromium: {e!s}"


def descubrir_pdfs(
    clave: str,
    max_paginas: int = 20,
    timeout_ms: int = 45000,
    headless: bool = True,
) -> list[str]:
    """
    Lanza Chromium, busca la `clave` (p.ej. AMXL, GFNORTEO), abre la pestaña
    'Documentos' y recolecta todos los enlaces a `recompra_*.pdf` paginando
    hasta `max_paginas`.

    Devuelve la lista única ordenada por nombre de archivo.
    Si falla (red, anti-bot, captcha) lanza RuntimeError con detalle.
    """
    if not clave or not str(clave).strip():
        raise ValueError("Debes pasar una clave de cotización (ej. 'AMXL').")
    clave = str(clave).strip().upper()

    from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

    pdfs: set[str] = set()

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=headless, args=["--no-sandbox"])
        except Exception as e:
            raise RuntimeError(
                "No se pudo lanzar Chromium. En Streamlit Cloud llama primero "
                "a `asegurar_playwright(con_deps=True)`. Detalle: " + str(e)
            )

        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="es-MX",
        )
        page = ctx.new_page()

        try:
            page.goto(URL_BUSQUEDA, wait_until="domcontentloaded", timeout=timeout_ms)

            # 1) Escribir la clave en el cuadro de búsqueda principal y enviar
            #    El selector es genérico porque BMV no expone ids estables.
            try:
                inp = page.wait_for_selector("input[type='search'], input[type='text']", timeout=10000)
                inp.click()
                inp.fill(f"{clave} recompra")
                page.keyboard.press("Enter")
            except PWTimeout:
                pass  # algunos layouts cargan otro buscador interno

            page.wait_for_timeout(1500)

            # 2) Click en pestaña 'Documentos' si existe
            try:
                page.get_by_role("tab", name="Documentos").click(timeout=5000)
            except Exception:
                # fallback: buscar texto "DOCUMENTOS" cualquier elemento
                try:
                    page.get_by_text("DOCUMENTOS", exact=False).first.click(timeout=4000)
                except Exception:
                    pass
            page.wait_for_timeout(1500)

            # 3) Filtrar por "recompra" en la columna Asunto si hay input
            try:
                filtros = page.locator("input").all()
                for f in filtros:
                    ph = (f.get_attribute("placeholder") or "").lower()
                    if "asunto" in ph:
                        f.click(); f.fill("recompra")
                        page.keyboard.press("Enter")
                        break
            except Exception:
                pass
            page.wait_for_timeout(1200)

            # 4) Recolectar PDFs visibles + paginar
            for _ in range(max_paginas):
                # scroll hasta el fondo del scroller interno (varios intentos)
                for _ in range(8):
                    pdfs_pagina = page.eval_on_selector_all(
                        "a", "els => els.map(e => e.href).filter(h => /recompra_.*\\.pdf$/i.test(h))"
                    )
                    pdfs.update(pdfs_pagina)
                    page.evaluate(
                        "() => { const sc = document.querySelector('.cdk-virtual-scroll-viewport') || document.scrollingElement; "
                        "if (sc) sc.scrollBy(0, 800); }"
                    )
                    page.wait_for_timeout(250)

                # intentar siguiente página
                avanzo = False
                for sel in [
                    "button[aria-label*='Siguiente' i]",
                    "a[aria-label*='Siguiente' i]",
                    ".pagination .next",
                    "button:has-text('Siguiente')",
                    "button:has-text('Más')",
                ]:
                    try:
                        btn = page.locator(sel).first
                        if btn.is_visible(timeout=500) and btn.is_enabled():
                            btn.click(timeout=3000)
                            page.wait_for_timeout(1500)
                            avanzo = True
                            break
                    except Exception:
                        continue
                if not avanzo:
                    break

        finally:
            browser.close()

    return sorted(pdfs)


def generar_bookmarklet() -> str:
    """
    Devuelve un bookmarklet (`javascript:...`) que extrae todos los PDFs
    visibles en la página de búsqueda BMV y los descarga como .txt.

    El usuario puede arrastrarlo a la barra de marcadores y ejecutarlo
    desde la propia página de BMV — funciona aunque la app esté en
    Streamlit Cloud sin Playwright.
    """
    js = """
(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const set = new Set();
  const collect = () => document.querySelectorAll('a').forEach(a => {
    if (/recompra_.*\\.pdf$/i.test(a.href || '')) set.add(a.href);
  });
  const findScroll = () => document.querySelector('.cdk-virtual-scroll-viewport')
    || document.scrollingElement;
  for (let p = 0; p < 60; p++) {
    collect();
    const sc = findScroll();
    if (sc) sc.scrollBy(0, 800);
    await sleep(220);
    const next = document.querySelector("button[aria-label*='Siguiente' i], a[aria-label*='Siguiente' i], .pagination .next");
    if (sc && Math.abs(sc.scrollTop + sc.clientHeight - sc.scrollHeight) < 4 && next && !next.disabled) {
      next.click(); await sleep(1200);
    }
  }
  collect();
  const arr = Array.from(set).sort();
  const txt = arr.join('\\n');
  const blob = new Blob([txt], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'bmv_pdfs.txt';
  document.body.appendChild(a); a.click(); a.remove();
  console.log('PDFs encontrados:', arr.length);
  alert('Listo: ' + arr.length + ' PDFs. Se descargó bmv_pdfs.txt — súbelo a la app.');
})();
""".strip()
    # Compactar a una línea apta para barra de marcadores
    compacto = " ".join(line.strip() for line in js.splitlines() if line.strip())
    return "javascript:" + compacto


def descargar_lista(urls: Iterable[str], timeout: int = 30) -> list[tuple[str, bytes]]:
    """Wrapper sobre bmv_downloader.descargar para mantener una sola API."""
    from src.bmv_downloader import descargar
    return descargar(list(urls), timeout=timeout)
