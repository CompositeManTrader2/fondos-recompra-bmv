"""
Recompras BMV · Punto Casa de Bolsa. Router de la app (st.navigation).

    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from src import storage, theme as T

st.set_page_config(page_title="Recompras BMV · Punto", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")
T.aplicar_tema()

paginas = st.navigation({
    "Mercado": [
        st.Page("views/resumen.py", title="Resumen", icon=":material/space_dashboard:", default=True),
        st.Page("views/actividad.py", title="Buyback Activity", icon=":material/table_view:"),
        st.Page("views/casas_mercado.py", title="Casas de bolsa", icon=":material/account_balance:"),
        st.Page("views/rankings.py", title="Rankings e historial", icon=":material/leaderboard:"),
    ],
    "Emisora": [
        st.Page("pages/2_📊_Dashboard.py", title="Dashboard", icon=":material/monitoring:"),
        st.Page("pages/3_🏛️_Casas_de_Bolsa.py", title="Intermediarios", icon=":material/groups:"),
        st.Page("pages/4_📈_Comparativo_Mercado.py", title="VWAP vs mercado", icon=":material/compare_arrows:"),
        st.Page("pages/6_⬇️_Exportar.py", title="Exportar", icon=":material/download:"),
    ],
    "Herramientas": [
        st.Page("pages/5_⚖️_Multi_Activo.py", title="Multi-activo", icon=":material/stacked_line_chart:"),
        st.Page("pages/1_📥_Cargar_Datos.py", title="Cargar datos", icon=":material/upload_file:"),
        st.Page("views/scanner.py", title="Estado del scanner", icon=":material/sync:"),
    ],
})


# ---------------------------------------------------------------------------
# Sidebar común a todas las páginas
# ---------------------------------------------------------------------------

def _sidebar_backend_status():
    info = storage.info_backend()
    if info["backend"] == "github":
        st.sidebar.markdown(
            f"{T.pill('Persistencia: GitHub', 'ok')}<br>"
            f"<span style='color:{T.MUTED};font-size:.72rem'>{info.get('repo')}@{info.get('branch')}</span>",
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(T.pill("Persistencia local (temporal)", "warn"), unsafe_allow_html=True)
        st.sidebar.caption("Configura `[github]` en Secrets para persistencia real (ver README).")


def _sidebar_selector_activo():
    activos = storage.listar_activos()
    tickers = [a["ticker"] for a in activos]
    st.sidebar.markdown("### Emisora")
    if not tickers:
        st.sidebar.info("Aún no hay emisoras cargadas.")
        st.session_state["ticker_activo"] = None
        return
    actual = st.session_state.get("ticker_activo") or tickers[0]
    if actual not in tickers:
        actual = tickers[0]
    # Si otra página cambió la emisora (clic en el resumen, carga de PDFs),
    # sincroniza el widget ANTES de instanciarlo para que no la sobrescriba.
    if st.session_state.get("selector_ticker") != actual:
        st.session_state["selector_ticker"] = actual
    elegido = st.sidebar.selectbox(
        "Análisis individual", tickers, key="selector_ticker",
        on_change=lambda: st.session_state.update(ticker_activo=st.session_state["selector_ticker"]),
    )
    st.session_state["ticker_activo"] = elegido
    info = next((a for a in activos if a["ticker"] == elegido), None)
    if info:
        st.sidebar.caption(f"{info['n_operaciones']:,} operaciones · última {info['ultima_fecha'] or 'N/D'}")


_logo = next((p for p in (T.ASSETS / "logo_punto.png", T.ASSETS / "logo_punto.svg", T.ASSETS / "wordmark.svg")
               if p.exists()), None)
if _logo:
    st.logo(str(_logo), size="large")
_sidebar_selector_activo()
_sidebar_backend_status()
paginas.run()
