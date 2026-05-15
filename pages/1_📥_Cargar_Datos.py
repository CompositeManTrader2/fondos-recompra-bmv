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
    "Sube PDFs de **fondo de recompra** o usa la auto-descarga de BMV. "
    "Cada emisora se guarda en su propio activo y los análisis quedan "
    "**100 % independientes**."
)

tab1, tab2, tab3 = st.tabs(
    ["🤖 Auto-descarga BMV", "📄 Subir PDFs", "🔗 Pegar URLs BMV"]
)


# ---------------------------------------------------------------------------
# Procesador central — ahora con `ticker_forzar` EXPLÍCITO por canal de carga
# ---------------------------------------------------------------------------

def _procesar_archivos(
    archivos: list[tuple[str, bytes]],
    ticker_forzar: str | None = None,
    nombre_emisora: str | None = None,
    persistir_pdfs: bool = False,
):
    """
    Procesa los PDFs y los guarda agrupados por emisora.

    - Si `ticker_forzar` se pasa (auto-descarga, o cuando el usuario
      explícitamente lo declara), TODAS las operaciones encontradas se
      guardan bajo ese ticker, ignorando lo que diga la *Clave de
      cotización* del PDF. Esto evita que un mismo activo se parta en
      `AMX` / `AMX L` / `AMXL` etc.
    - Si NO se pasa, se agrupa por la clave detectada en cada PDF
      individualmente. Si la clave no se detecta para algún PDF, ese
      archivo va a `DESCONOCIDA` (no se mezcla con los detectados).
    """
    if not archivos:
        st.warning("No hay archivos para procesar.")
        return

    ticker_forzar = (ticker_forzar or "").strip().upper() or None

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

    # Agrupar por emisora
    por_emisora: dict[str, list[pd.DataFrame]] = {}
    metadata_remanentes: list[dict] = []
    diagnosticos: list[dict] = []

    for r in resultados:
        # Decidir el ticker destino
        if ticker_forzar:
            ticker = ticker_forzar
        elif r.emisora:
            ticker = r.emisora.upper().strip()
        else:
            ticker = "DESCONOCIDA"

        diagnosticos.append({
            "Archivo": r.archivo,
            "Emisora detectada": r.emisora or "—",
            "Ticker destino": ticker,
            "Fecha": r.fecha_operacion,
            "Casa": r.casa_bolsa or "—",
            "Operaciones": len(r.operaciones),
        })

        if not r.operaciones.empty:
            df_ops = r.operaciones.copy()
            # FORZAR la columna EMISORA al ticker destino para que la
            # agregación posterior nunca confunda emisoras.
            df_ops["EMISORA"] = ticker
            por_emisora.setdefault(ticker, []).append(df_ops)

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
        with st.expander("🔍 Diagnóstico por archivo"):
            st.dataframe(pd.DataFrame(diagnosticos), use_container_width=True, hide_index=True)
        return

    # Avisar si se mezclaron varias emisoras detectadas
    detecciones_unicas = {d["Emisora detectada"] for d in diagnosticos if d["Emisora detectada"] != "—"}
    if not ticker_forzar and len(detecciones_unicas) > 1:
        st.info(
            f"📋 Se detectaron **{len(detecciones_unicas)} emisoras distintas** en los "
            f"PDFs subidos: {', '.join(sorted(detecciones_unicas))}. "
            "Cada una se guardará por separado."
        )
    elif "DESCONOCIDA" in por_emisora and len(por_emisora) > 1:
        st.warning(
            "⚠️ Algunos PDFs no tenían la *Clave de cotización* detectable y "
            "fueron a **DESCONOCIDA**. Considera forzar el ticker para no "
            "mezclar emisoras."
        )

    # Guardar cada emisora en su propio storage
    resumen_filas = []
    for ticker, dfs in por_emisora.items():
        df_ticker = pd.concat(dfs, ignore_index=True)
        df_ticker = data_processor.consolidar_operaciones(df_ticker)
        if df_ticker.empty:
            continue
        df_ticker["EMISORA"] = ticker  # post-consolidación, garantiza la columna
        total = storage.guardar_operaciones(ticker, df_ticker, modo="append")
        if nombre_emisora and len(por_emisora) == 1:
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

    with st.expander("🔍 Diagnóstico por archivo"):
        st.dataframe(pd.DataFrame(diagnosticos), use_container_width=True, hide_index=True)

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


# =============================================================================
# TAB 1 · AUTO-DESCARGA BMV  ← canal principal
# =============================================================================
with tab1:
    st.markdown(
        "🚀 **Auto-descarga 100 % automática** vía la API REST interna de BMV. "
        "Escribe el ticker como lo conozcas (`AMXL`, `BIMBOA`, `WALMEX*`, "
        "`AMX`, `BIMBO`, `WALMEX`...) — el sistema **resuelve la clave "
        "BMV automáticamente** y descarga sólo los PDFs de recompra de esa emisora."
    )
    col_in, col_resol = st.columns([1, 2])
    clave_auto = col_in.text_input(
        "Ticker / clave",
        placeholder="AMXL, BIMBO, WALMEX...",
        key="clave_scraper",
    ).strip().upper()

    # Vista previa de la resolución (en vivo)
    cve_resuelto = None
    if clave_auto:
        try:
            resol = bmv_scraper.resolver_emisora(clave_auto)
            if resol["estado"] == "ok":
                cve_resuelto = resol["cve_emisora"]
                if cve_resuelto != clave_auto:
                    col_resol.success(
                        f"🎯 `{clave_auto}` → **{cve_resuelto}**  ·  "
                        f"_{resol['razon_social']}_"
                    )
                else:
                    col_resol.success(
                        f"🎯 **{cve_resuelto}**  ·  _{resol['razon_social']}_"
                    )
            elif resol["estado"] == "ambiguo":
                col_resol.warning(
                    f"⚠️ `{clave_auto}` coincide con varias emisoras. "
                    "Selecciona abajo."
                )
                opciones = {
                    f"{c['cve_emisora']} — {c['razon_social']}": c["cve_emisora"]
                    for c in resol["candidatos"]
                }
                pick = col_resol.selectbox(
                    "Emisora a usar",
                    list(opciones.keys()),
                    key="picker_ambiguo",
                )
                cve_resuelto = opciones[pick]
            else:
                col_resol.error(
                    f"❌ No encontré `{clave_auto}` en BMV. "
                    f"Variantes intentadas: {', '.join(resol['intentos'])}"
                )
        except Exception as e:
            col_resol.error(f"Error consultando BMV: {e}")

    col_a, col_b, col_c = st.columns(3)
    max_docs = col_a.number_input("Máx. PDFs a descubrir", 10, 5000, 500, step=50)
    page_size = col_b.number_input("Tamaño de página API", 20, 200, 100, step=20)
    descargar_todos = col_c.checkbox("Descargar y procesar PDFs", value=True)

    boton_disabled = not (clave_auto and cve_resuelto)
    if st.button(
        f"⚡ Auto-descargar **{cve_resuelto}**" if cve_resuelto else "⚡ Auto-descargar",
        type="primary",
        disabled=boton_disabled,
    ):
        with st.status(f"Buscando recompras de {cve_resuelto} en BMV…", expanded=True) as status:
            try:
                progreso = st.progress(0.0, text="Buscando documentos…")
                def _cb(actual, total):
                    if total:
                        progreso.progress(min(actual / total, 1.0), text=f"{actual}/{total} documentos…")
                # auto_resolver=False porque ya lo resolvimos en la vista previa
                docs = bmv_scraper.descubrir_pdfs(
                    cve_resuelto, max_documentos=int(max_docs), page_size=int(page_size),
                    progreso_cb=_cb, auto_resolver=False,
                )
                progreso.empty()
            except Exception as e:
                status.update(label="Error consultando BMV", state="error")
                st.error(str(e))
                st.stop()

            if not docs:
                status.update(label="Sin resultados", state="error")
                st.warning(
                    f"No se encontraron PDFs de recompra para **{clave_auto}**. "
                    "Verifica que la clave exista en BMV (`cve_emisora`)."
                )
                st.stop()

            status.update(label=f"✅ {len(docs)} PDFs de recompra encontrados.")
            st.dataframe(
                docs[:50],
                use_container_width=True, hide_index=True,
                column_config={
                    "url": st.column_config.LinkColumn("PDF"),
                    "fecha": "Fecha publicación",
                    "id_documento": "ID BMV",
                    "cve_empresa": "Emisora",
                    "descripcion": "Descripción",
                },
            )
            if len(docs) > 50:
                st.caption(f"Mostrando 50 de {len(docs)}.")

            if not descargar_todos:
                status.update(label="Solo descubrimiento — no se procesaron PDFs.")
                st.stop()

            status.update(label="Descargando PDFs…")
            barra = st.progress(0.0, text="Descargando…")
            def _cb_dl(i, total, nombre):
                barra.progress(i / total, text=f"{i}/{total} — {nombre}")
            archivos = bmv_scraper.descargar_pdfs(docs, progreso_cb=_cb_dl)
            barra.empty()
            ok = sum(1 for _, c in archivos if c)
            status.update(label=f"Descargados {ok}/{len(archivos)} PDFs. Procesando…")
        # ⬇️ AQUÍ está la garantía de aislamiento por emisora.
        # Usamos la cve_emisora resuelta (ej. "AMX") en lugar del input
        # libre del usuario (ej. "AMXL") para mantener un único ticker
        # canónico por activo.
        _procesar_archivos(archivos, ticker_forzar=cve_resuelto or clave_auto)

    with st.expander("🔖 Fallback: bookmarklet (sólo si el endpoint de BMV cambia)"):
        st.markdown(
            "Si en el futuro la API REST de BMV cambia, este bookmarklet en tu "
            "navegador siempre funciona como respaldo:"
        )
        st.markdown(
            "1. **Arrastra** este botón a tu barra de marcadores ⬇️ — o "
            "copia el JS y pégalo en la consola del navegador (F12).\n"
            "2. Entra a la página de búsqueda BMV: "
            "[`bmv.com.mx/.../simec_documentos_recompra_`]"
            "(https://www.bmv.com.mx/es/bmv/busqueda/simec_documentos_recompra_?tab=1).\n"
            "3. Escribe la clave en el buscador y abre **Documentos**.\n"
            "4. Click al marcador. Se descargará `bmv_pdfs.txt`.\n"
            "5. Súbelo en la pestaña **🔗 Pegar URLs BMV**."
        )
        st.code(bmv_scraper.generar_bookmarklet(), language="javascript")


# =============================================================================
# TAB 2 · SUBIR PDFs MANUALMENTE
# =============================================================================
with tab2:
    st.markdown(
        "Si tienes PDFs descargados a mano, súbelos aquí. La emisora se "
        "detecta automáticamente PDF por PDF leyendo la *Clave de cotización*."
    )
    archivos_subidos = st.file_uploader(
        "Selecciona uno o varios PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key="upload_pdfs_manual",
    )
    col_a, col_b = st.columns([2, 1])
    forzar_aqui = col_a.text_input(
        "Forzar ticker para TODOS los PDFs subidos (opcional)",
        value="",
        help=(
            "Si lo dejas en blanco, cada PDF se guarda bajo la clave que "
            "detecte el parser (lo recomendado si subes mezcla de emisoras). "
            "Sólo úsalo cuando estás seguro de que TODOS los PDFs son de "
            "la misma emisora y el parser falla en detectarla."
        ),
    ).upper().strip()
    nombre_aqui = col_b.text_input("Nombre legible (opcional)", value="")

    if st.button("🚀 Procesar PDFs", type="primary", disabled=not archivos_subidos, key="btn_procesar_manual"):
        archivos = [(f.name, f.read()) for f in archivos_subidos]
        _procesar_archivos(
            archivos,
            ticker_forzar=forzar_aqui or None,
            nombre_emisora=nombre_aqui or None,
            persistir_pdfs=False,
        )


# =============================================================================
# TAB 3 · PEGAR URLs (legacy / bookmarklet output)
# =============================================================================
with tab3:
    st.markdown(
        "Pega URLs de BMV (formato `bmv.com.mx/docs-pub/recompra/...pdf`) "
        "o el contenido del `bmv_pdfs.txt` del bookmarklet. "
        "Útil si la API automática falla."
    )
    raw = st.text_area(
        "URLs (una por línea o output sucio)",
        height=180,
        placeholder="https://www.bmv.com.mx/docs-pub/recompra/...pdf",
        key="urls_raw",
    )
    forzar_urls = st.text_input(
        "Forzar ticker (opcional)",
        value="",
        help="Recomendado si pegaste URLs de una sola emisora.",
        key="forzar_urls",
    ).upper().strip()

    if st.button("🌐 Descargar y procesar URLs", type="primary", disabled=not raw, key="btn_urls"):
        urls = bmv_downloader.extraer_urls(raw)
        if not urls:
            st.error("No se encontraron URLs válidas de BMV en el texto pegado.")
        else:
            st.write(f"Se detectaron **{len(urls)}** URLs únicas.")
            with st.spinner("Descargando PDFs desde BMV…"):
                archivos = bmv_downloader.descargar(urls)
            ok = sum(1 for _, c in archivos if c)
            st.write(f"Descargados correctamente: **{ok}/{len(archivos)}**")
            _procesar_archivos(archivos, ticker_forzar=forzar_urls or None)


# =============================================================================
# Activos almacenados + administración
# =============================================================================
st.divider()
st.markdown("### 🗂️ Activos actualmente almacenados")
activos = storage.listar_activos()
if not activos:
    st.info("Sin activos. Empieza arriba con la auto-descarga.")
else:
    st.dataframe(activos, use_container_width=True, hide_index=True)

    with st.expander("🛠️ Mantenimiento (mover, fusionar, eliminar)"):
        st.markdown("##### Renombrar / fusionar tickers")
        st.caption(
            "Útil si te quedaron datos en `DESCONOCIDA` o si tienes el mismo "
            "activo bajo dos claves (`AMX` y `AMXL`)."
        )
        col1, col2, col3 = st.columns([1, 1, 1])
        origen = col1.selectbox("De", [a["ticker"] for a in activos], key="rename_origen")
        destino = col2.text_input("A (ticker destino)", value="", key="rename_destino").upper().strip()
        modo_merge = col3.selectbox(
            "Si destino ya existe",
            ["Fusionar (append + dedupe)", "Sobrescribir destino"],
            key="rename_modo",
        )
        if st.button("🔀 Mover/Fusionar", type="secondary"):
            if not destino:
                st.error("Especifica el ticker destino.")
            elif destino == origen:
                st.error("El destino debe ser distinto al origen.")
            else:
                df_src = storage.cargar_operaciones(origen)
                if df_src.empty:
                    st.error(f"`{origen}` está vacío.")
                else:
                    df_src = df_src.copy()
                    df_src["EMISORA"] = destino
                    modo = "append" if modo_merge.startswith("Fusionar") else "replace"
                    n = storage.guardar_operaciones(destino, df_src, modo=modo)
                    storage.eliminar_activo(origen)
                    st.success(
                        f"✅ Movidas {len(df_src):,} operaciones de "
                        f"`{origen}` → `{destino}` (total ahora: {n:,}). "
                        "Origen eliminado."
                    )
                    st.rerun()

        st.markdown("##### Eliminar un activo")
        a_borrar = st.selectbox("Selecciona ticker a eliminar", [a["ticker"] for a in activos], key="del_select")
        confirma = st.text_input("Escribe el ticker para confirmar", value="", key="del_confirm")
        if st.button("🗑️ Eliminar permanentemente", type="secondary"):
            if confirma.strip().upper() == a_borrar:
                storage.eliminar_activo(a_borrar)
                st.success(f"Activo {a_borrar} eliminado.")
                st.rerun()
            else:
                st.error("La confirmación no coincide con el ticker.")
