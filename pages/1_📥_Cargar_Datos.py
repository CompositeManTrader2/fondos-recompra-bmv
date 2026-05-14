"""Página: carga de PDFs y URLs de BMV."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Permitir imports relativos al ejecutar Streamlit Cloud
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import bmv_downloader, bmv_scraper, data_processor, pdf_parser, storage

st.set_page_config(page_title="Cargar Datos", page_icon="📥", layout="wide")
st.title("📥 Cargar datos")

st.markdown(
    "Sube uno o varios PDFs de operación de **fondo de recompra** o pega "
    "directamente las URLs de BMV. El sistema detecta automáticamente la "
    "emisora desde la *Clave de cotización* del documento."
)

ticker_default = st.session_state.get("ticker_activo") or ""

with st.expander("⚙️ Opciones avanzadas", expanded=False):
    forzar_ticker = st.text_input(
        "Forzar ticker (opcional)",
        value=ticker_default,
        help="Si lo dejas en blanco se usará la *Clave de cotización* extraída de cada PDF.",
    ).upper().strip()
    nombre_emisora = st.text_input("Nombre de la emisora (opcional)", value="")
    persistir_pdfs = st.checkbox("Guardar PDFs originales en disco", value=False)

tab1, tab2, tab3 = st.tabs(
    ["📄 Subir PDFs", "🔗 Pegar URLs BMV", "🤖 Auto-descarga BMV"]
)


# ---------------------------------------------------------------------------
def _procesar_archivos(archivos: list[tuple[str, bytes]]):
    if not archivos:
        st.warning("No hay archivos para procesar.")
        return

    progreso = st.progress(0.0, text="Procesando PDFs…")
    resultados: list[pdf_parser.ResultadoPDF] = []
    errores: list[str] = []

    for i, (nombre, contenido) in enumerate(archivos, start=1):
        if not contenido:
            errores.append(f"{nombre}: descarga vacía")
            continue
        res = pdf_parser.parsear_pdf(contenido, nombre_archivo=nombre)
        if res.error:
            errores.append(f"{nombre}: {res.error}")
        resultados.append(res)
        progreso.progress(i / len(archivos), text=f"Procesando {i}/{len(archivos)} — {nombre}")

    progreso.empty()

    if not resultados:
        st.error("Ningún PDF se pudo procesar.")
        return

    # Agrupar por emisora (o por ticker forzado)
    por_emisora: dict[str, list[pd.DataFrame]] = {}
    metadata_remanentes: list[dict] = []
    for r in resultados:
        ticker = (forzar_ticker or r.emisora or "DESCONOCIDA").upper()
        if not r.operaciones.empty:
            por_emisora.setdefault(ticker, []).append(r.operaciones)
        if r.fecha_operacion is not None:
            metadata_remanentes.append({
                "EMISORA": ticker,
                "FECHA": r.fecha_operacion,
                "CASA_BOLSA": r.casa_bolsa,
                "REMANENTE_ULTIMO": r.remanente_ultimo,
                "REMANENTE_PRESENTE": r.remanente_presente,
                "ARCHIVO": r.archivo,
            })

    if not por_emisora:
        st.error("No se encontraron tablas de operaciones en los PDFs procesados.")
        with st.expander("Detalles"):
            for r in resultados:
                st.write(f"**{r.archivo}** — emisora: `{r.emisora}` · fecha: `{r.fecha_operacion}` · casa: `{r.casa_bolsa}`")
                if r.error:
                    st.error(r.error)
        return

    resumen_filas = []
    for ticker, dfs in por_emisora.items():
        df_ticker = pd.concat(dfs, ignore_index=True)
        df_ticker = data_processor.consolidar_operaciones(df_ticker)
        if df_ticker.empty:
            continue
        if "EMISORA" not in df_ticker.columns or df_ticker["EMISORA"].isna().all():
            df_ticker["EMISORA"] = ticker
        total = storage.guardar_operaciones(ticker, df_ticker, modo="append")
        if nombre_emisora:
            storage.registrar_activo(ticker, nombre=nombre_emisora)
        resumen_filas.append({
            "Emisora": ticker,
            "Operaciones añadidas": len(df_ticker),
            "Total acumulado": total,
        })

    if persistir_pdfs:
        for ticker in por_emisora.keys():
            for nombre, contenido in archivos:
                if contenido:
                    storage.guardar_pdf_bytes(ticker, nombre, contenido)

    st.success(f"✅ {len(resultados)} PDFs procesados.")
    st.dataframe(pd.DataFrame(resumen_filas), use_container_width=True, hide_index=True)

    if metadata_remanentes:
        with st.expander("📑 Remanente de recursos detectado"):
            st.dataframe(pd.DataFrame(metadata_remanentes), use_container_width=True, hide_index=True)

    if errores:
        with st.expander(f"⚠️ {len(errores)} archivo(s) con problemas"):
            for e in errores:
                st.text(e)

    # Setear el primer ticker como activo del dashboard
    if por_emisora:
        st.session_state["ticker_activo"] = next(iter(por_emisora.keys()))
        st.info(f"Se seleccionó **{st.session_state['ticker_activo']}** como activo en análisis. Ve a 📊 Dashboard.")


# ---------------------------------------------------------------------------
with tab1:
    archivos_subidos = st.file_uploader(
        "Selecciona uno o varios PDFs",
        type=["pdf"],
        accept_multiple_files=True,
    )
    if st.button("🚀 Procesar PDFs subidos", type="primary", disabled=not archivos_subidos):
        archivos = [(f.name, f.read()) for f in archivos_subidos]
        _procesar_archivos(archivos)


with tab2:
    raw = st.text_area(
        "Pega aquí URLs de BMV (una por línea, o el output sucio de la consola del navegador)",
        height=180,
        placeholder="https://www.bmv.com.mx/docs-pub/recompra/...pdf",
    )
    if st.button("🌐 Descargar y procesar URLs", type="primary", disabled=not raw):
        urls = bmv_downloader.extraer_urls(raw)
        if not urls:
            st.error("No se encontraron URLs válidas de BMV en el texto pegado.")
        else:
            st.write(f"Se detectaron **{len(urls)}** URLs únicas.")
            with st.spinner("Descargando PDFs desde BMV…"):
                archivos = bmv_downloader.descargar(urls)
            ok = sum(1 for _, c in archivos if c)
            st.write(f"Descargados correctamente: **{ok}/{len(archivos)}**")
            _procesar_archivos(archivos)


with tab3:
    st.markdown(
        "Esta opción **descarga sola** los PDFs desde la página pública de BMV. "
        "Tiene dos rutas:"
    )
    sub1, sub2 = st.tabs(["⚡ Modo automático (servidor)", "🔖 Modo bookmarklet (1-click navegador)"])

    # ---------------- AUTOMÁTICO (Playwright) ----------------
    with sub1:
        st.markdown(
            "El servidor abre Chromium en *headless*, escribe la clave, espera "
            "que cargue la lista y captura todos los URLs. Funciona localmente "
            "sin configuración. En **Streamlit Cloud** la primera ejecución "
            "tarda ~30 s instalando el browser."
        )
        clave_auto = st.text_input(
            "Clave de cotización a descargar",
            value=(forzar_ticker or "").upper(),
            placeholder="AMXL, GFNORTEO, ALFAA…",
            key="clave_scraper",
        ).strip().upper()
        col_a, col_b = st.columns(2)
        max_pag = col_a.number_input("Máx. páginas a recorrer", 1, 100, 20)
        timeout_s = col_b.number_input("Timeout (segundos)", 10, 180, 60)

        if st.button("⚡ Ejecutar auto-descarga", type="primary", disabled=not clave_auto):
            if not bmv_scraper.playwright_disponible():
                st.error(
                    "Playwright no está instalado en este entorno. Añade "
                    "`playwright>=1.45` a requirements.txt y reinicia la app."
                )
            else:
                with st.status("Preparando Chromium…", expanded=True) as status:
                    ok, msg = bmv_scraper.asegurar_playwright(con_deps=False)
                    st.write(msg)
                    if not ok:
                        status.update(label="No fue posible inicializar Chromium", state="error")
                        st.stop()
                    status.update(label="Buscando documentos en BMV…")
                    try:
                        urls = bmv_scraper.descubrir_pdfs(
                            clave_auto, max_paginas=int(max_pag), timeout_ms=int(timeout_s) * 1000
                        )
                    except Exception as e:
                        status.update(label="Error en el scraping", state="error")
                        st.error(str(e))
                        st.stop()
                    status.update(label=f"Encontrados {len(urls)} PDFs. Descargando…")
                    st.write(f"Encontrados **{len(urls)}** PDFs únicos.")
                    if not urls:
                        st.warning("No se encontraron PDFs. Revisa la clave o usa el modo bookmarklet.")
                        st.stop()
                    archivos = bmv_downloader.descargar(urls)
                    status.update(label="Procesando PDFs…")
                _procesar_archivos(archivos)

    # ---------------- BOOKMARKLET ----------------
    with sub2:
        st.markdown(
            "Si el modo automático no funciona (anti-bot, captcha) este "
            "fallback **siempre funciona** porque corre en *tu* navegador, "
            "que ya está autenticado para ver la página. Pasos:"
        )
        st.markdown(
            "1. **Arrastra** este botón a tu barra de marcadores ⬇️ — o "
            "copia el JS y pégalo en la consola del navegador (F12).\n"
            "2. Entra a la página de búsqueda BMV: "
            "[`bmv.com.mx/.../simec_documentos_recompra_`]"
            "(https://www.bmv.com.mx/es/bmv/busqueda/simec_documentos_recompra_?tab=1).\n"
            "3. Escribe la clave en el buscador (ej. `AMXL recompra`) y abre "
            "**Documentos**.\n"
            "4. Click al marcador. Se descargará `bmv_pdfs.txt`.\n"
            "5. Súbelo en la pestaña **🔗 Pegar URLs BMV** o aquí abajo."
        )
        bk = bmv_scraper.generar_bookmarklet()
        st.code(bk, language="javascript")

        st.markdown("##### O sube directamente el `bmv_pdfs.txt`")
        archivo_txt = st.file_uploader("Archivo TXT con URLs", type=["txt"], key="upload_bookmarklet_txt")
        if st.button("⬇️ Descargar y procesar URLs del TXT", disabled=not archivo_txt):
            raw_txt = archivo_txt.read().decode("utf-8", errors="ignore")
            urls = bmv_downloader.extraer_urls(raw_txt)
            st.write(f"URLs detectadas: **{len(urls)}**")
            if urls:
                with st.spinner("Descargando PDFs desde BMV…"):
                    archivos = bmv_downloader.descargar(urls)
                _procesar_archivos(archivos)
            else:
                st.error("El TXT no contenía URLs válidas de BMV.")


st.divider()
st.markdown("### 🗂️ Activos actualmente almacenados")
activos = storage.listar_activos()
if not activos:
    st.info("Sin activos. Sube PDFs arriba para empezar.")
else:
    st.dataframe(activos, use_container_width=True, hide_index=True)

    with st.expander("🗑️ Eliminar un activo"):
        a_borrar = st.selectbox("Selecciona ticker a eliminar", [a["ticker"] for a in activos])
        confirma = st.text_input("Escribe el ticker para confirmar", value="")
        if st.button("Eliminar permanentemente", type="secondary"):
            if confirma.strip().upper() == a_borrar:
                storage.eliminar_activo(a_borrar)
                st.success(f"Activo {a_borrar} eliminado.")
                st.rerun()
            else:
                st.error("La confirmación no coincide con el ticker.")
