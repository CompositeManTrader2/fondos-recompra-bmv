"""
Sistema visual · Punto Casa de Bolsa.

Colores de marca muestreados del reporte "Buyback Activity" de Punto:
  morado #7030A0 (encabezados), lavanda #ECDEF5 (renglón alterno),
  gris #949BA1 (logotipo).

Paleta de gráficas validada con el validador de dataviz en modo claro
sobre #FFFFFF (lightness band, chroma floor, separación CVD, contraste):
todos PASS. El morado de marca es la serie 1; el gris de marca queda
reservado para "OTRAS".

Logotipo: si existe assets/logo_punto.png se usa el archivo oficial; si no,
un wordmark de texto.
"""
from __future__ import annotations

import base64
import html
from datetime import datetime, timedelta, timezone
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# ---------------------------------------------------------------------------
# Tokens de marca
# ---------------------------------------------------------------------------
PURPLE = "#7030A0"
PURPLE_DARK = "#4E1F72"
LAVENDER = "#ECDEF5"
LAVENDER_SOFT = "#F7F2FB"
GRAY_BRAND = "#949BA1"

BG = "#FFFFFF"
PANEL = "#FFFFFF"
PANEL_2 = "#F7F2FB"
BORDER = "#E3D9EC"
GRID = "#EEE8F3"
TEXT = "#1F1A26"
TEXT_2 = "#4A4453"
MUTED = "#6B6475"          # ≥4.5:1 sobre blanco (texto secundario)
AMBER_UI = PURPLE          # compatibilidad con código previo (cromo de UI)

CATEGORICA = ["#7030A0", "#0E9A94", "#2063B0", "#C5770F", "#AB3276", "#599234", "#8D481A", "#D15D4D"]
OTRAS = GRAY_BRAND
COMPRA = "#2E9E52"
VENTA = "#A9131F"
SERIE_1 = CATEGORICA[0]
SERIE_2 = CATEGORICA[1]
RANGO_FILL = "rgba(112,48,160,0.10)"
# Secuencial (magnitud): lavanda → morado profundo, un solo tono.
SECUENCIAL = [[0.0, "#F7F2FB"], [0.2, "#E4D2F0"], [0.45, "#C39BDD"], [0.7, "#9558C2"], [1.0, "#4E1F72"]]
# Divergente (polaridad): azul ↔ gris neutro ↔ coral.
DIV_NEG, DIV_MID, DIV_POS = CATEGORICA[2], "#E6E1EA", CATEGORICA[7]

FONT_SANS = "'Fira Sans', 'Segoe UI', system-ui, sans-serif"
FONT_MONO = "'Fira Code', 'Consolas', monospace"
TEMPLATE = "punto"

CDMX = timezone(timedelta(hours=-6))


# ---------------------------------------------------------------------------
# Plotly template
# ---------------------------------------------------------------------------

def _registrar_template() -> None:
    # Se re-registra siempre: pio.templates sobrevive a recargas del módulo.
    eje = dict(
        gridcolor=GRID, gridwidth=1, zeroline=False,
        linecolor=BORDER, tickcolor=BORDER, ticks="outside", ticklen=4,
        tickfont=dict(family=FONT_MONO, size=10, color=TEXT_2),
        title=dict(font=dict(family=FONT_SANS, size=11, color=MUTED)),
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikecolor=GRAY_BRAND, spikethickness=1, spikedash="dot",
    )
    tpl = go.layout.Template(layout=go.Layout(
        paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        font=dict(family=FONT_SANS, size=12, color=TEXT_2),
        colorway=CATEGORICA,
        title=dict(font=dict(family=FONT_SANS, size=13, color=PURPLE), x=0.01, xanchor="left", y=0.97),
        xaxis=eje, yaxis=eje,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    font=dict(family=FONT_SANS, size=11, color=TEXT_2), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=PURPLE, font=dict(family=FONT_MONO, size=11, color=TEXT)),
        hovermode="x unified",
        margin=dict(l=8, r=8, t=64, b=8),
        bargap=0.25, barcornerradius=3,
        colorscale=dict(sequential=SECUENCIAL),
    ))
    pio.templates[TEMPLATE] = tpl
    pio.templates["bbg"] = tpl          # alias para código previo
    pio.templates.default = TEMPLATE


_registrar_template()


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@400;500;600;700&family=Nunito:wght@600;700&display=swap');

html, body, [data-testid="stAppViewContainer"], .stApp {{ background: {BG}; color: {TEXT}; font-family: {FONT_SANS}; }}
[data-testid="stHeader"] {{ background: rgba(255,255,255,0.85); }}
#MainMenu, footer {{ visibility: hidden; }}
.block-container {{ padding-top: 3.2rem; padding-bottom: 2.5rem; max-width: 100%; }}
h1, h2, h3, h4 {{ font-family: {FONT_SANS}; color: {PURPLE_DARK}; letter-spacing: .01em; }}
h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1.15rem; }} h3 {{ font-size: 1rem; }}
p, li, label, .stMarkdown {{ font-size: .92rem; line-height: 1.55; }}
code {{ color: {PURPLE_DARK}; background: {LAVENDER_SOFT}; }}
a {{ color: {PURPLE}; }}

section[data-testid="stSidebar"] {{ background: {LAVENDER_SOFT}; border-right: 1px solid {BORDER}; }}
section[data-testid="stSidebar"] h3 {{ color: {PURPLE}; font-size: .78rem; letter-spacing: .08em; text-transform: uppercase; }}

/* Tabs → pastillas de marca */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 2px solid {LAVENDER}; }}
.stTabs [data-baseweb="tab"] {{
  font-family: {FONT_SANS}; font-size: .8rem; font-weight: 600; text-transform: uppercase; letter-spacing: .05em;
  background: {BG}; color: {TEXT_2}; padding: 7px 16px; border: 1px solid {BORDER}; border-bottom: none;
  border-radius: 6px 6px 0 0; transition: background-color .18s, color .18s;
}}
.stTabs [data-baseweb="tab"]:hover {{ background: {LAVENDER_SOFT}; color: {PURPLE}; }}
.stTabs [aria-selected="true"] {{ background: {PURPLE}; color: #FFFFFF; border-color: {PURPLE}; }}
.stTabs [data-baseweb="tab-highlight"] {{ display: none; }}

[data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-top: 3px solid {PURPLE}; padding: 10px 12px; border-radius: 6px; }}
[data-testid="stMetricLabel"] p {{ font-size: .7rem; color: {PURPLE}; text-transform: uppercase; letter-spacing: .07em; font-weight: 600; }}
[data-testid="stMetricValue"] {{ font-family: {FONT_MONO}; font-size: 1.35rem; color: {TEXT}; }}

[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 8px; background: {PANEL}; overflow: hidden; }}
[data-testid="stExpander"] {{ border: 1px solid {BORDER}; border-radius: 8px; }}
.stButton > button, .stDownloadButton > button {{ font-weight: 600; border-radius: 6px; cursor: pointer; transition: background-color .18s, border-color .18s; }}
button:focus-visible, [role="tab"]:focus-visible, a:focus-visible {{ outline: 2px solid {PURPLE} !important; outline-offset: 2px; }}

/* ---- Componentes Punto ---- */
.pt-header {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap;
  border-bottom: 3px solid {PURPLE}; padding: 4px 2px 10px; margin-bottom: 14px; }}
.pt-header .left {{ display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }}
.pt-header .code {{ background: {PURPLE}; color: #fff; font-family: {FONT_MONO}; font-weight: 600; font-size: .72rem;
  padding: 3px 8px; border-radius: 4px; letter-spacing: .05em; }}
.pt-header .title {{ color: {PURPLE}; font-size: 1.35rem; font-weight: 700; letter-spacing: .03em; text-transform: uppercase; }}
.pt-header .sub {{ color: {MUTED}; font-size: .85rem; }}
.pt-header .right {{ display: flex; align-items: center; gap: 14px; }}
.pt-header .stamp {{ color: {MUTED}; font-size: .75rem; font-family: {FONT_MONO}; text-align: right; }}
.pt-logo {{ display: inline-flex; flex-direction: column; align-items: flex-end; line-height: 1; user-select: none; }}
.pt-logo .w {{ font-family: 'Nunito', {FONT_SANS}; font-weight: 700; font-size: 1.9rem; color: {GRAY_BRAND}; letter-spacing: -.01em; }}
.pt-logo .w .o {{ color: {PURPLE}; }}
.pt-logo .c {{ font-family: 'Nunito', {FONT_SANS}; font-weight: 600; font-size: .78rem; color: {GRAY_BRAND}; margin-top: 1px; }}
.pt-logo img {{ height: 46px; }}

.pt-tape {{ overflow: hidden; white-space: nowrap; background: {LAVENDER_SOFT}; border: 1px solid {BORDER};
  border-radius: 6px; padding: 6px 0; margin-bottom: 12px; font-family: {FONT_MONO}; font-size: .8rem; }}
.pt-tape .track {{ display: inline-block; padding-left: 100%; animation: pt-scroll 80s linear infinite; }}
.pt-tape:hover .track {{ animation-play-state: paused; }}
.pt-tape .item {{ margin-right: 34px; color: {TEXT_2}; }}
.pt-tape .tk {{ color: {PURPLE}; font-weight: 600; margin-right: 6px; }}
.pt-tape .v {{ color: {TEXT}; }}
.pt-tape .up {{ color: {COMPRA}; }} .pt-tape .dn {{ color: {VENTA}; }}
@keyframes pt-scroll {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-100%); }} }}
@media (prefers-reduced-motion: reduce) {{ .pt-tape .track {{ animation: none; padding-left: 8px; }} }}

.pt-tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 4px 0 14px; }}
.pt-tile {{ background: {PANEL}; border: 1px solid {BORDER}; border-top: 3px solid {PURPLE}; padding: 10px 12px 11px;
  border-radius: 8px; min-width: 0; box-shadow: 0 1px 2px rgba(78,31,114,0.06); }}
.pt-tile .lbl {{ font-size: .68rem; color: {PURPLE}; letter-spacing: .07em; text-transform: uppercase; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.pt-tile .val {{ font-family: {FONT_MONO}; font-size: 1.45rem; color: {TEXT}; font-weight: 500; line-height: 1.25; margin-top: 4px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.pt-tile .dlt {{ font-family: {FONT_MONO}; font-size: .74rem; margin-top: 2px; color: {TEXT_2}; }}
.pt-tile .dlt.up {{ color: {COMPRA}; }} .pt-tile .dlt.dn {{ color: {VENTA}; }}
.pt-tile .sub {{ font-size: .72rem; color: {MUTED}; margin-top: 2px; }}

.pt-section {{ display: flex; align-items: baseline; gap: 10px; margin: 18px 0 8px; border-bottom: 1px solid {LAVENDER}; padding-bottom: 5px; }}
.pt-section .t {{ color: {PURPLE}; font-size: .82rem; letter-spacing: .08em; text-transform: uppercase; font-weight: 700; }}
.pt-section .n {{ color: {MUTED}; font-size: .78rem; }}

.pt-pill {{ display: inline-block; font-size: .72rem; font-weight: 600; padding: 2px 9px; border-radius: 999px;
  border: 1px solid {BORDER}; background: {BG}; margin: 2px 4px 2px 0; }}
.pt-pill.ok {{ color: {COMPRA}; border-color: {COMPRA}; }} .pt-pill.warn {{ color: {PURPLE}; border-color: {PURPLE}; background: {LAVENDER_SOFT}; }}
.pt-pill.err {{ color: {VENTA}; border-color: {VENTA}; }}

.pt-signals {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; margin-bottom: 8px; }}
.pt-signal {{ border: 1px solid {BORDER}; border-left: 4px solid {PURPLE}; border-radius: 8px; padding: 10px 12px; background: {PANEL}; }}
.pt-signal.buy {{ border-left-color: {COMPRA}; }} .pt-signal.sell {{ border-left-color: {VENTA}; }}
.pt-signal.warn {{ border-left-color: {CATEGORICA[3]}; }} .pt-signal.info {{ border-left-color: {CATEGORICA[2]}; }}
.pt-signal .h {{ display: flex; justify-content: space-between; align-items: baseline; }}
.pt-signal .t {{ font-weight: 700; color: {TEXT}; font-size: .9rem; }}
.pt-signal .k {{ font-family: {FONT_MONO}; font-weight: 600; color: {PURPLE}; font-size: 1.15rem; }}
.pt-signal .d {{ color: {MUTED}; font-size: .76rem; margin: 2px 0 6px; }}
.pt-signal .chip {{ display: inline-block; font-family: {FONT_MONO}; font-size: .72rem; background: {LAVENDER_SOFT};
  color: {PURPLE_DARK}; border: 1px solid {LAVENDER}; border-radius: 4px; padding: 1px 6px; margin: 2px 3px 0 0; }}
.pt-signal .empty {{ color: {MUTED}; font-size: .76rem; font-style: italic; }}
</style>
"""


def aplicar_tema() -> None:
    _registrar_template()
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Logotipo
# ---------------------------------------------------------------------------

def logo_html() -> str:
    for nombre in ("logo_punto.png", "logo_punto.svg"):
        p = ASSETS / nombre
        if p.exists():
            mime = "image/svg+xml" if p.suffix == ".svg" else "image/png"
            b64 = base64.b64encode(p.read_bytes()).decode()
            return f'<span class="pt-logo"><img src="data:{mime};base64,{b64}" alt="Punto Casa de Bolsa"></span>'
    return ('<span class="pt-logo" aria-label="Punto Casa de Bolsa">'
            '<span class="w">punt<span class="o">o</span></span><span class="c">casa de bolsa</span></span>')


# ---------------------------------------------------------------------------
# Componentes
# ---------------------------------------------------------------------------

def header(codigo: str, titulo: str, subtitulo: str = "", derecha: str = "") -> None:
    ahora = datetime.now(CDMX).strftime("%d-%b-%Y %H:%M").upper()
    stamp = derecha or f"{ahora} CDMX"
    st.markdown(
        f"""<div class="pt-header"><div class="left">
        <span class="code">{html.escape(codigo)}</span>
        <span class="title">{html.escape(titulo)}</span>
        <span class="sub">{html.escape(subtitulo)}</span></div>
        <div class="right"><span class="stamp">{stamp}</span>{logo_html()}</div></div>""",
        unsafe_allow_html=True,
    )


def ticker_tape(items: list[dict]) -> None:
    if not items:
        return
    partes = []
    for it in items:
        cls = {"up": "up", "dn": "dn"}.get(it.get("dir") or "", "")
        glyph = {"up": "▲", "dn": "▼"}.get(it.get("dir") or "", "")
        extra = f' <span class="{cls}">{glyph} {html.escape(str(it.get("extra", "")))}</span>' if it.get("extra") else ""
        partes.append(f'<span class="item"><span class="tk">{html.escape(str(it["tk"]))}</span>'
                      f'<span class="v">{html.escape(str(it.get("valor", "")))}</span>{extra}</span>')
    c = "".join(partes)
    st.markdown(f'<div class="pt-tape"><div class="track">{c}{c}</div></div>', unsafe_allow_html=True)


def tiles(items: list[dict]) -> None:
    celdas = []
    for it in items:
        d, dir_ = it.get("delta"), it.get("dir")
        glyph = {"up": "▲ ", "dn": "▼ "}.get(dir_ or "", "")
        dlt = f'<div class="dlt {dir_ or ""}">{glyph}{html.escape(str(d))}</div>' if d else ""
        sub = f'<div class="sub">{html.escape(str(it["sub"]))}</div>' if it.get("sub") else ""
        celdas.append(f'<div class="pt-tile"><div class="lbl">{html.escape(str(it["label"]))}</div>'
                      f'<div class="val">{html.escape(str(it["value"]))}</div>{dlt}{sub}</div>')
    st.markdown(f'<div class="pt-tiles">{"".join(celdas)}</div>', unsafe_allow_html=True)


def seccion(titulo: str, nota: str = "") -> None:
    n = f'<span class="n">{html.escape(nota)}</span>' if nota else ""
    st.markdown(f'<div class="pt-section"><span class="t">{html.escape(titulo)}</span>{n}</div>', unsafe_allow_html=True)


def pill(texto: str, tipo: str = "ok") -> str:
    return f'<span class="pt-pill {tipo}">{html.escape(texto)}</span>'


def senales(tarjetas: list[dict]) -> None:
    """tarjetas: [{titulo, descripcion, items: [str], tipo: buy|sell|warn|info}]"""
    bloques = []
    for t in tarjetas:
        items = t.get("items") or []
        chips = "".join(f'<span class="chip">{html.escape(str(i))}</span>' for i in items[:14])
        mas = f'<span class="chip">+{len(items) - 14}</span>' if len(items) > 14 else ""
        cuerpo = chips + mas if items else '<span class="empty">Ninguna en esta sesión</span>'
        bloques.append(
            f'<div class="pt-signal {t.get("tipo", "")}"><div class="h"><span class="t">{html.escape(t["titulo"])}</span>'
            f'<span class="k">{len(items)}</span></div><div class="d">{html.escape(t.get("descripcion", ""))}</div>{cuerpo}</div>'
        )
    st.markdown(f'<div class="pt-signals">{"".join(bloques)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------

def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def fmt_mxn(v, dec: int = 1) -> str:
    v = _num(v)
    if v is None:
        return "—"
    s, a = ("-" if v < 0 else ""), abs(v)
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim:
            return f"{s}${a / lim:,.{dec}f}{suf}"
    return f"{s}${a:,.0f}"


def fmt_num(v, dec: int = 1) -> str:
    v = _num(v)
    if v is None:
        return "—"
    a = abs(v)
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim:
            return f"{v / lim:,.{dec}f}{suf}"
    return f"{v:,.0f}"


def fmt_pct(v, dec: int = 1, signo: bool = True) -> str:
    v = _num(v)
    if v is None:
        return "—"
    return f"{v:+.{dec}f}%" if signo else f"{v:.{dec}f}%"


def dir_de(v) -> str | None:
    v = _num(v)
    if v is None or v == 0:
        return None
    return "up" if v > 0 else "dn"


def colores_emisoras(orden_estable: list[str], max_colores: int = 7) -> dict[str, str]:
    """Color por ENTIDAD con orden estable; el resto va a OTRAS (gris de marca)."""
    return {e: CATEGORICA[i] for i, e in enumerate(orden_estable[:max_colores])}
