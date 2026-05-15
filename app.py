"""
Fondos de Recompra BMV — Tracker multi-activo
=============================================

Punto de entrada de la app Streamlit. Las pestañas viven en `pages/`.

Ejecuta localmente:
    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from src import storage

st.set_page_config(
    page_title="Fondos de Recompra BMV",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _sidebar_backend_status():
    info = storage.info_backend()
    if info["backend"] == "github":
        st.sidebar.success(
            f"💾 Persistencia: **GitHub**\n\n"
            f"`{info.get('repo')}@{info.get('branch')}`\n"
            f"`{info.get('base_path')}`"
        )
    else:
        st.sidebar.warning(
            "💾 Persistencia: **Local (efímera)**\n\n"
            "En Streamlit Cloud los datos se borrarán al reiniciar.\n"
            "Configura `[github]` en *Secrets* para persistencia real "
            "(ver README)."
        )


def _sidebar_selector_activo():
    """Selector global de activo. Se persiste en st.session_state."""
    activos = storage.listar_activos()
    tickers = [a["ticker"] for a in activos]

    st.sidebar.markdown("### 🎯 Activo en análisis")
    if not tickers:
        st.sidebar.info("Aún no hay activos cargados. Empieza en **📥 Cargar Datos**.")
        st.session_state["ticker_activo"] = None
        return

    actual = st.session_state.get("ticker_activo") or tickers[0]
    if actual not in tickers:
        actual = tickers[0]

    elegido = st.sidebar.selectbox(
        "Emisora",
        options=tickers,
        index=tickers.index(actual),
        key="selector_ticker",
    )
    st.session_state["ticker_activo"] = elegido

    info = next((a for a in activos if a["ticker"] == elegido), None)
    if info:
        st.sidebar.caption(
            f"**{info['nombre']}**  ·  {info['n_operaciones']:,} operaciones  ·  "
            f"última fecha: {info['ultima_fecha'] or 'N/D'}"
        )


def main():
    st.title("📈 Fondos de Recompra BMV")
    st.caption(
        "Tracker multi-activo de operaciones de fondo de recompra publicadas en la BMV."
    )

    _sidebar_backend_status()
    _sidebar_selector_activo()

    col1, col2, col3 = st.columns(3)
    activos = storage.listar_activos()
    col1.metric("Activos cargados", len(activos))
    col2.metric(
        "Operaciones totales",
        f"{sum(a['n_operaciones'] for a in activos):,}",
    )
    ult = max(
        (a["ultima_fecha"] for a in activos if a["ultima_fecha"]),
        default=None,
    )
    col3.metric("Última operación", ult.split("T")[0] if ult else "—")

    st.divider()

    st.markdown(
        """
        ### ¿Cómo se usa?
        1. **📥 Cargar Datos** — sube los PDFs de la BMV (uno o varios) o
           pega URLs de `bmv.com.mx/docs-pub/recompra/...`. La app extrae
           automáticamente fecha, casa de bolsa, remanente y la tabla de
           operaciones.
        2. **📊 Dashboard** — VWAP diario / semanal / mensual,
           ejecuciones, acciones, importes y comparativo vs precio de mercado.
        3. **🏛️ Casas de Bolsa** — concentración por intermediario, ranking
           y participación.
        4. **⚖️ Multi-Activo** — compara la actividad de recompra entre
           varias emisoras al mismo tiempo.
        5. **⬇️ Exportar** — descarga el Excel consolidado con todas las hojas.

        > 💡 Cada emisora se guarda como un parquet independiente en
        > `data/activos/{TICKER}/` para que puedas ir construyendo un
        > histórico personalizado sin perder lo previo.
        """
    )

    if activos:
        st.markdown("### Activos cargados")
        st.dataframe(
            activos,
            use_container_width=True,
            column_config={
                "ticker": "Ticker",
                "nombre": "Nombre",
                "n_operaciones": st.column_config.NumberColumn("# Operaciones", format="%d"),
                "ultima_fecha": "Última fecha",
                "creado": "Creado",
                "actualizado": "Actualizado",
            },
            hide_index=True,
        )


if __name__ == "__main__":
    main()
