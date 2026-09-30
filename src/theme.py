"""
Sistema visual estilo terminal Bloomberg.

Paleta validada con el validador de dataviz (modo oscuro, superficie
#0B0D10): lightness band, chroma floor, separación CVD (daltonismo) y
contraste — todos PASS.

  CATEGORICA: ámbar, azul, teal, magenta, oliva, violeta, cian, óxido
              (orden FIJO: el color sigue a la entidad, nunca al rango)
  COMPRA/VENTA: verde #36AC62 / rojo #BE2E31 (siempre con ▲/▼)
"""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
BG = "#07090C"          # fondo de la app
PANEL = "#0B0D10"       # superficie de gráficas (validada)
PANEL_2 = "#11151B"     # tiles / tooltips
BORDER = "#1F252D"
GRID = "#171C22"
TEXT = "#E6E6E6"
TEXT_2 = "#A0A6AE"
MUTED = "#6B7280"
AMBER_UI = "#FF9F1C"    # cromo de UI (títulos, etiquetas), no es color de serie

CATEGORICA = ["#D37E01", "#2C5DBD", "#12A7A7", "#AB2F80", "#959A17", "#724AAB", "#2EA2D0", "#B23B1D"]
OTRAS = "#4B535E"       # neutro para "OTRAS" (nunca un 9º tono)
COMPRA = "#36AC62"
VENTA = "#BE2E31"
SERIE_1 = CATEGORICA[0]
SERIE_2 = CATEGORICA[1]
RANGO_FILL = "rgba(160,166,174,0.10)"
# Secuencial (magnitud): un solo tono, de superficie a ámbar brillante.
SECUENCIAL = [[0.0, "#12161C"], [0.15, "#2A1E0C"], [0.45, "#6E4305"], [0.75, "#B56C04"], [1.0, "#F2A93B"]]
# Divergente (polaridad): azul ↔ gris neutro ↔ óxido.
DIV_NEG, DIV_MID, DIV_POS = CATEGORICA[1], "#3A3F47", CATEGORICA[7]

FONT_MONO = "'IBM Plex Mono', 'JetBrains Mono', Consolas, monospace"
FONT_SANS = "'IBM Plex Sans', 'Inter', system-ui, sans-serif"

CDMX = timezone(timedelta(hours=-6))


# ---------------------------------------------------------------------------
# Plotly template "bbg"
# ---------------------------------------------------------------------------

def _registrar_template() -> None:
    if "bbg" in pio.templates:
        pio.templates.default = "bbg"
        return
    eje = dict(
        gridcolor=GRID, gridwidth=1, zeroline=False,
        linecolor=BORDER, tickcolor=BORDER, ticks="outside", ticklen=4,
        tickfont=dict(family=FONT_MONO, size=10, color=TEXT_2),
        title=dict(font=dict(family=FONT_MONO, size=10, color=MUTED)),
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikecolor=MUTED, spikethickness=1, spikedash="dot",
    )
    pio.templates["bbg"] = go.layout.Template(layout=go.Layout(
        paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        font=dict(family=FONT_MONO, size=11, color=TEXT_2),
        colorway=CATEGORICA,
        title=dict(font=dict(family=FONT_MONO, size=12, color=TEXT), x=0.01, xanchor="left", y=0.98),
        xaxis=eje, yaxis=eje,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
            font=dict(family=FONT_MONO, size=10, color=TEXT_2), bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(bgcolor=PANEL_2, bordercolor=AMBER_UI,
                        font=dict(family=FONT_MONO, size=11, color=TEXT)),
        hovermode="x unified",
        margin=dict(l=8, r=8, t=44, b=8),
        bargap=0.25, barcornerradius=3,
        colorscale=dict(sequential=SECUENCIAL),
    ))
    pio.templates.default = "bbg"


_registrar_template()


# ---------------------------------------------------------------------------
# CSS global
# ---------------------------------------------------------------------------

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, [data-testid="stAppViewContainer"], .stApp {{ background: {BG}; color: {TEXT}; font-family: {FONT_SANS}; }}
[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer {{ visibility: hidden; }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 2rem; max-width: 100%; }}
h1, h2, h3, h4 {{ font-family: {FONT_MONO}; letter-spacing: .02em; color: {TEXT}; }}
h1 {{ font-size: 1.35rem; }} h2 {{ font-size: 1.1rem; }} h3 {{ font-size: .95rem; }}
p, li, label, .stMarkdown {{ font-size: .88rem; }}
code {{ color: {AMBER_UI}; background: {PANEL_2}; }}

section[data-testid="stSidebar"] {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
section[data-testid="stSidebar"] * {{ font-family: {FONT_MONO}; }}

/* Tabs → teclas de función de terminal */
.stTabs [data-baseweb="tab-list"] {{ gap: 2px; border-bottom: 1px solid {BORDER}; }}
.stTabs [data-baseweb="tab"] {{
  font-family: {FONT_MONO}; font-size: .74rem; text-transform: uppercase; letter-spacing: .06em;
  background: {PANEL}; color: {TEXT_2}; padding: 6px 14px; border: 1px solid {BORDER}; border-bottom: none;
  border-radius: 3px 3px 0 0;
}}
.stTabs [aria-selected="true"] {{ background: {AMBER_UI}; color: #000; font-weight: 600; }}
.stTabs [data-baseweb="tab-highlight"] {{ display: none; }}

/* st.metric (fallback) */
[data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-left: 3px solid {AMBER_UI}; padding: 10px 12px; border-radius: 3px; }}
[data-testid="stMetricLabel"] p {{ font-family: {FONT_MONO}; font-size: .68rem; color: {AMBER_UI}; text-transform: uppercase; letter-spacing: .08em; }}
[data-testid="stMetricValue"] {{ font-family: {FONT_MONO}; font-size: 1.35rem; color: {TEXT}; }}

[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 3px; background: {PANEL}; }}
[data-testid="stExpander"] {{ border: 1px solid {BORDER}; background: {PANEL}; }}
.stButton > button, .stDownloadButton > button {{ font-family: {FONT_MONO}; text-transform: uppercase; font-size: .74rem; letter-spacing: .05em; border-radius: 3px; }}

/* ---- Componentes BBG ---- */
.bbg-header {{
  display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
  background: linear-gradient(90deg, #1A1204 0%, {PANEL} 55%); border: 1px solid {BORDER};
  border-left: 4px solid {AMBER_UI}; padding: 8px 14px; margin-bottom: 10px; font-family: {FONT_MONO};
}}
.bbg-header .left {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }}
.bbg-header .code {{ background: {AMBER_UI}; color: #000; font-weight: 600; padding: 2px 8px; font-size: .8rem; letter-spacing: .06em; }}
.bbg-header .go {{ color: {AMBER_UI}; font-size: .72rem; margin-left: 4px; }}
.bbg-header .title {{ color: {TEXT}; font-size: 1.05rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }}
.bbg-header .sub {{ color: {TEXT_2}; font-size: .78rem; }}
.bbg-header .right {{ color: {TEXT_2}; font-size: .74rem; text-align: right; }}
.bbg-header .live {{ color: {COMPRA}; }}

.bbg-tape {{ overflow: hidden; white-space: nowrap; border-top: 1px solid {BORDER}; border-bottom: 1px solid {BORDER};
  background: #000; padding: 5px 0; margin-bottom: 12px; font-family: {FONT_MONO}; font-size: .78rem; }}
.bbg-tape .track {{ display: inline-block; padding-left: 100%; animation: bbg-scroll 70s linear infinite; }}
.bbg-tape:hover .track {{ animation-play-state: paused; }}
.bbg-tape .item {{ margin-right: 34px; color: {TEXT_2}; }}
.bbg-tape .tk {{ color: {AMBER_UI}; font-weight: 600; margin-right: 6px; }}
.bbg-tape .v {{ color: {TEXT}; }}
.bbg-tape .up {{ color: {COMPRA}; }} .bbg-tape .dn {{ color: {VENTA}; }}
@keyframes bbg-scroll {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-100%); }} }}
@media (prefers-reduced-motion: reduce) {{ .bbg-tape .track {{ animation: none; padding-left: 0; }} }}

.bbg-tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 8px; margin: 4px 0 12px; }}
.bbg-tile {{ background: {PANEL}; border: 1px solid {BORDER}; border-top: 2px solid {AMBER_UI}; padding: 9px 12px 10px; border-radius: 3px; min-width: 0; }}
.bbg-tile .lbl {{ font-family: {FONT_MONO}; font-size: .64rem; color: {AMBER_UI}; letter-spacing: .09em; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.bbg-tile .val {{ font-family: {FONT_MONO}; font-size: 1.45rem; color: {TEXT}; font-weight: 500; line-height: 1.25; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.bbg-tile .dlt {{ font-family: {FONT_MONO}; font-size: .72rem; margin-top: 2px; color: {TEXT_2}; }}
.bbg-tile .dlt.up {{ color: {COMPRA}; }} .bbg-tile .dlt.dn {{ color: {VENTA}; }}
.bbg-tile .sub {{ font-family: {FONT_MONO}; font-size: .68rem; color: {MUTED}; margin-top: 2px; }}

.bbg-section {{ display: flex; align-items: center; gap: 10px; margin: 16px 0 6px; font-family: {FONT_MONO};
  border-bottom: 1px solid {BORDER}; padding-bottom: 4px; }}
.bbg-section .t {{ color: {AMBER_UI}; font-size: .78rem; letter-spacing: .1em; text-transform: uppercase; font-weight: 600; }}
.bbg-section .n {{ color: {MUTED}; font-size: .72rem; }}

.bbg-pill {{ display: inline-block; font-family: {FONT_MONO}; font-size: .68rem; padding: 1px 8px; border-radius: 2px; border: 1px solid {BORDER}; }}
.bbg-pill.ok {{ color: {COMPRA}; border-color: {COMPRA}; }} .bbg-pill.warn {{ color: {AMBER_UI}; border-color: {AMBER_UI}; }}
.bbg-pill.err {{ color: {VENTA}; border-color: {VENTA}; }}
</style>
"""


def aplicar_tema() -> None:
    """Inyecta CSS y activa el template Plotly. Llamar al inicio de cada página."""
    _registrar_template()
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Componentes
# ---------------------------------------------------------------------------

def header(codigo: str, titulo: str, subtitulo: str = "", derecha: str = "") -> None:
    ahora = datetime.now(CDMX).strftime("%d-%b-%Y %H:%M").upper()
    der = derecha or f"{ahora} CDMX"
    st.markdown(
        f"""<div class="bbg-header"><div class="left">
        <span><span class="code">{html.escape(codigo)}</span><span class="go">&lt;GO&gt;</span></span>
        <span class="title">{html.escape(titulo)}</span>
        <span class="sub">{html.escape(subtitulo)}</span></div>
        <div class="right">{der}</div></div>""",
        unsafe_allow_html=True,
    )


def ticker_tape(items: list[dict]) -> None:
    """items: [{tk, valor, extra, dir: 'up'|'dn'|None}]"""
    if not items:
        return
    partes = []
    for it in items:
        cls = {"up": "up", "dn": "dn"}.get(it.get("dir") or "", "")
        glyph = {"up": "▲", "dn": "▼"}.get(it.get("dir") or "", "")
        extra = f' <span class="{cls}">{glyph} {html.escape(str(it.get("extra", "")))}</span>' if it.get("extra") else ""
        partes.append(
            f'<span class="item"><span class="tk">{html.escape(str(it["tk"]))}</span>'
            f'<span class="v">{html.escape(str(it.get("valor", "")))}</span>{extra}</span>'
        )
    contenido = "".join(partes)
    st.markdown(f'<div class="bbg-tape"><div class="track">{contenido}{contenido}</div></div>',
                unsafe_allow_html=True)


def tiles(items: list[dict]) -> None:
    """items: [{label, value, delta?, dir?: 'up'|'dn', sub?}]"""
    celdas = []
    for it in items:
        d = it.get("delta")
        dir_ = it.get("dir")
        glyph = {"up": "▲ ", "dn": "▼ "}.get(dir_ or "", "")
        dlt = f'<div class="dlt {dir_ or ""}">{glyph}{html.escape(str(d))}</div>' if d else ""
        sub = f'<div class="sub">{html.escape(str(it["sub"]))}</div>' if it.get("sub") else ""
        celdas.append(
            f'<div class="bbg-tile"><div class="lbl">{html.escape(str(it["label"]))}</div>'
            f'<div class="val">{html.escape(str(it["value"]))}</div>{dlt}{sub}</div>'
        )
    st.markdown(f'<div class="bbg-tiles">{"".join(celdas)}</div>', unsafe_allow_html=True)


def seccion(titulo: str, nota: str = "") -> None:
    n = f'<span class="n">{html.escape(nota)}</span>' if nota else ""
    st.markdown(f'<div class="bbg-section"><span class="t">{html.escape(titulo)}</span>{n}</div>',
                unsafe_allow_html=True)


def pill(texto: str, tipo: str = "ok") -> str:
    return f'<span class="bbg-pill {tipo}">{html.escape(texto)}</span>'


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------

def fmt_mxn(v, dec: int = 1) -> str:
    """$1.23B / $456.7M / $12.3K (B = mil millones)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v != v:
        return "—"
    s = "-" if v < 0 else ""
    a = abs(v)
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim:
            return f"{s}${a / lim:,.{dec}f}{suf}"
    return f"{s}${a:,.0f}"


def fmt_num(v, dec: int = 1) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v != v:
        return "—"
    a = abs(v)
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim:
            return f"{v / lim:,.{dec}f}{suf}"
    return f"{v:,.0f}"


def fmt_pct(v, dec: int = 1, signo: bool = True) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v != v:
        return "—"
    return f"{v:+.{dec}f}%" if signo else f"{v:.{dec}f}%"


def dir_de(v) -> str | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v != v or v == 0:
        return None
    return "up" if v > 0 else "dn"


def colores_emisoras(orden_estable: list[str], max_colores: int = 7) -> dict[str, str]:
    """
    Asigna color por ENTIDAD con un orden estable (p.ej. ranking histórico),
    de modo que un filtro de ventana no repinte a los sobrevivientes. Las
    que no alcanzan color van a OTRAS (neutro).
    """
    return {e: CATEGORICA[i] for i, e in enumerate(orden_estable[:max_colores])}
