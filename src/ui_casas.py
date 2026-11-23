"""
Sección "Casas de bolsa y fondos de recompra" de la página principal (Streamlit).

Cuatro vistas:
  1. Todos los fondos   — panorama emisora × casa (la vista original) con gráficas.
  2. Liga y mandatos    — análisis de casas: liga, mandatos, cambios, oportunidades, dinámica.
  3. Por casa de bolsa  — todos los fondos que opera una casa, consolidados.
  4. Fondo individual   — ficha de una emisora: casas, precio vs compras, actividad.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import casas_analisis as ca
from src import casas_vistas as cv
from src import emisoras_casas as ec
from src import market_store
from src import theme as T

PERIODOS = {"3M": 92, "6M": 183, "YTD": None, "1 año": 365, "2 años": 730, "Personalizado": 0}
CAT = cv.PALETA
GANA, PIERDE, NARANJA = "#2E9E52", "#A9131F", "#C5770F"
ESTATUS_COLOR = {"Activo": "#2E9E52", "En pausa": "#C5770F", "Inactivo": "#8C8496"}
TIPO_COLOR = {"Exclusivo": "#7030A0", "Principal + secundaria": "#0E9A94", "Compartido": "#C5770F"}


# ---------------------------------------------------------------------------
# Datos en caché
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, max_entries=12)
def _analisis(ini: date, fin: date, destacada: str, version: str) -> ca.AnalisisCasas:
    return ca.analizar(market_store.actividad(), market_store.documentos(), market_store.mercado(), ini, fin, destacada)


@st.cache_data(show_spinner=False, max_entries=6)
def _descargas_analisis(ini: date, fin: date, destacada: str, version: str) -> tuple[bytes, bytes]:
    from src import reporte_casas_pdf as rp
    an = _analisis(ini, fin, destacada, version)
    return rp.generar_pdf(an), rp.excel_bytes(an)


@st.cache_data(show_spinner=False, max_entries=12)
def _panorama(ini: date, fin: date, medida: str, destacada: str, version: str):
    act = market_store.actividad()
    tab, cols = ec.matriz(act, ini, fin, medida, incluir=(destacada,))
    return tab, cols, ec.resumen_casas(act, ini, fin), ec.detalle(act, ini, fin)


@st.cache_data(show_spinner=False, max_entries=6)
def _descargas_panorama(ini: date, fin: date, medida: str, destacada: str, version: str) -> tuple[bytes, bytes]:
    tab, cols, casas, det = _panorama(ini, fin, medida, destacada, version)
    return (ec.pdf_bytes(tab, cols, casas, ini, fin, medida),
            ec.excel_bytes(tab, cols, det, casas, ini, fin, medida))


@st.cache_data(show_spinner=False, max_entries=24)
def _perfil(casa: str, ini: date, fin: date, destacada: str, version: str) -> dict:
    an = _analisis(ini, fin, destacada, version)
    return cv.perfil_casa(market_store.actividad(), an.mandatos, casa, ini, fin)


@st.cache_data(show_spinner=False, max_entries=24)
def _ficha(emisora: str, ini: date, fin: date, version: str) -> dict:
    return cv.ficha_emisora(market_store.actividad(), market_store.mercado(), emisora, ini, fin)


# ---------------------------------------------------------------------------
# Utilidades de tablas
# ---------------------------------------------------------------------------

def _css_celda(v) -> str:
    """Fondo interpolado entre lavanda y morado Punto según el % (0–100)."""
    if pd.isna(v) or v <= 0:
        return ""
    k = min(float(v), 100) / 100
    a, b = (0xF7, 0xF2, 0xFB), (0x70, 0x30, 0xA0)
    r, g, bl = (round(x + (y - x) * k) for x, y in zip(a, b))
    return f"background-color: #{r:02X}{g:02X}{bl:02X}; color: {'#FFFFFF' if k > 0.55 else '#1F1A26'}"


def _pct_txt(v) -> str:
    return "" if pd.isna(v) or v <= 0 else ("<1%" if v < 1 else f"{v:.0f}%")


def _estilo_estatus(df: pd.DataFrame, col: str = "ESTATUS", col_tipo: str | None = "TIPO"):
    """Estatus y tipo de mandato como texto de color con un punto, para leerlos de un vistazo."""
    d = df.copy()
    if col in d:
        d[col] = d[col].map(lambda v: f"● {v}" if isinstance(v, str) and v else v)
    sty = d.style
    if col in d:
        sty = sty.map(lambda v: f"color: {ESTATUS_COLOR.get(str(v)[2:], '#4A4453')}; font-weight: 600"
                      if isinstance(v, str) else "", subset=[col])
    if col_tipo and col_tipo in d:
        sty = sty.map(lambda v: f"color: {TIPO_COLOR.get(v, '#4A4453')}; font-weight: 600"
                      if isinstance(v, str) else "", subset=[col_tipo])
    return sty


def _fig_base(fig: go.Figure, alto: int, titulo: str = "", leyenda: bool = False, t: int | None = None) -> go.Figure:
    fig.update_layout(template="punto", height=alto, title=titulo,
                      margin=dict(l=10, r=14, t=t if t is not None else (58 if leyenda else 44), b=10),
                      showlegend=leyenda,
                      legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom", font=dict(size=11)))
    return fig


def _subtitulo(texto: str, nota: str = "") -> None:
    import html
    n = f'<span class="n">{html.escape(nota)}</span>' if nota else ""
    st.markdown(f'<div class="pt-sub">{html.escape(texto)}{n}</div>', unsafe_allow_html=True)


def _eje_meses(fig: go.Figure) -> go.Figure:
    fig.update_xaxes(type="date", tickformat="%b %y", dtick="M2", tickangle=0, showgrid=False)
    return fig


def _meses_txt(fechas) -> list[str]:
    return [pd.Timestamp(m).strftime("%b %y").capitalize() for m in fechas]


# ---------------------------------------------------------------------------
# Gráficas compartidas
# ---------------------------------------------------------------------------

def _fig_dona(valores: pd.Series, colores: dict, titulo: str, centro: str, top: int = 7) -> go.Figure:
    v = valores.sort_values(ascending=False)
    if len(v) > top:
        v = pd.concat([v.iloc[:top], pd.Series({"OTRAS": v.iloc[top:].sum()})])
    fig = go.Figure(go.Pie(
        labels=v.index, values=v.values, hole=0.62, sort=False, direction="clockwise",
        marker=dict(colors=[colores.get(c, cv.GRIS) for c in v.index], line=dict(color="#FFFFFF", width=2)),
        texttemplate="%{percent:.0%}", textposition="inside", insidetextorientation="horizontal",
        textfont=dict(color="#FFFFFF", size=12),
        hovertemplate="<b>%{label}</b><br>%{value:,.1f}<br>%{percent:.1%}<extra></extra>"))
    fig.add_annotation(text=centro, showarrow=False, font=dict(size=15, color="#4E1F72"))
    fig = _fig_base(fig, 360, titulo, leyenda=True, t=44)
    fig.update_layout(uniformtext=dict(minsize=10, mode="hide"), hovermode="closest",
                      legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.04, yanchor="top"),
                      margin=dict(l=10, r=10, t=44, b=56))
    return fig


def _fig_barras_h(etiquetas, valores, colores, titulo: str, fmt: str = "{:,.0f}", alto: int = 330,
                  sufijo: str = "") -> go.Figure:
    fig = go.Figure(go.Bar(
        x=valores, y=etiquetas, orientation="h", marker_color=colores,
        text=[fmt.format(v) + sufijo for v in valores], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,.1f}" + sufijo + "<extra></extra>"))
    fig = _fig_base(fig, alto, titulo)
    vmax = max(float(np.nanmax(np.asarray(valores, dtype=float))) if len(valores) else 1, 1e-9)
    fig.update_layout(yaxis=dict(autorange="reversed"), hovermode="closest",
                      xaxis=dict(showticklabels=False, showgrid=False, range=[0, vmax * 1.22]),
                      margin=dict(l=10, r=16, t=44, b=10))
    return fig


# ---------------------------------------------------------------------------
# Vista 1 · Todos los fondos
# ---------------------------------------------------------------------------

def _vista_todos(ini, fin, destacada, version, colores):
    c1, _ = st.columns([1.3, 3])
    medida = c1.segmented_control("Ponderar por", list(ec.MEDIDAS), default="IMPORTE", key="cb_medida",
                                  format_func=lambda m: {"IMPORTE": "Importe", "N_OPS": "Operaciones"}[m]) or "IMPORTE"
    tab, cols, casas, det = _panorama(ini, fin, medida, destacada, version)
    if tab.empty:
        st.info("Sin operaciones en el periodo elegido.")
        return
    compartidas = int((tab["N_CASAS"] > 1).sum())
    T.tiles([
        {"label": "Emisoras con recompras", "value": f"{len(tab)}", "sub": f"{ini:%d/%m/%Y} – {fin:%d/%m/%Y}"},
        {"label": "Casas de bolsa activas", "value": f"{len(casas)}", "sub": ", ".join(casas["CASA_BOLSA"].head(3))},
        {"label": "Emisoras con más de una casa", "value": f"{compartidas}",
         "sub": f"{100 * compartidas / len(tab):.0f}% de las emisoras"},
        {"label": "Casa líder", "value": casas["CASA_BOLSA"].iat[0],
         "sub": f"{casas['PART_IMPORTE'].iat[0]:.1f}% del importe · {casas['EMISORAS'].iat[0]} emisoras"},
        {"label": "Importe operado", "value": T.fmt_mxn(tab["IMPORTE"].sum() * 1e6), "sub": "compras + ventas"},
    ])

    g1, g2, g3 = st.columns([1.15, 1, 0.85])
    part = casas.set_index("CASA_BOLSA")["PART_IMPORTE" if medida == "IMPORTE" else "PART_OPS"]
    g1.plotly_chart(_fig_dona(part, colores, "Participación por casa",
                              f"<b>{len(casas)}</b><br>casas"), width="stretch")
    vig = tab["CASA_VIGENTE"].value_counts().head(10)
    g2.plotly_chart(_fig_barras_h(vig.index, vig.values, [colores.get(c, cv.GRIS) for c in vig.index],
                                  "Emisoras por casa vigente"), width="stretch")
    nc = cv.emisoras_por_n_casas(tab)
    fig = go.Figure(go.Bar(x=nc.index, y=nc.values, marker_color=["#7030A0", "#9B66C7", "#C39BDD", "#E4D2F0"],
                           text=nc.values, textposition="outside", cliponaxis=False,
                           hovertemplate="%{x}: %{y} emisoras<extra></extra>"))
    fig = _fig_base(fig, 360, "Casas por emisora")
    fig.update_layout(yaxis=dict(showticklabels=False, showgrid=False, range=[0, nc.max() * 1.2]), hovermode="closest")
    g3.plotly_chart(fig, width="stretch")

    # Treemap: tamaño = importe, color = casa vigente
    tm = tab.dropna(subset=["CASA_VIGENTE"])
    fig = go.Figure(go.Treemap(
        labels=tm["EMISORA"], parents=[""] * len(tm), values=tm["IMPORTE"],
        marker=dict(colors=[colores.get(c, cv.GRIS) for c in tm["CASA_VIGENTE"]], line=dict(color="#FFFFFF", width=2)),
        customdata=tm[["CASA_VIGENTE", "N_CASAS", "REPARTO_4S"]].values,
        texttemplate="<b>%{label}</b><br>%{customdata[0]}", textfont=dict(color="#FFFFFF"),
        hovertemplate="<b>%{label}</b><br>Importe $%{value:,.0f} M<br>Casa vigente %{customdata[0]}"
                      "<br>%{customdata[1]} casa(s) · %{customdata[2]}<extra></extra>"))
    fig = _fig_base(fig, 430, "Mapa de los fondos: tamaño = importe operado · color = casa vigente", t=40)
    fig.update_layout(margin=dict(l=4, r=4, t=40, b=4))
    st.plotly_chart(fig, width="stretch")

    # Mapa de calor emisora × casa
    top = tab.head(30)
    z = top[cols].fillna(0).values
    fig = go.Figure(go.Heatmap(
        z=z, x=cols, y=top["EMISORA"], zmin=0, zmax=100,
        colorscale=[[0, "#FFFFFF"], [0.01, "#F3ECF9"], [0.3, "#C39BDD"], [0.65, "#9558C2"], [1, "#4E1F72"]],
        text=[[_pct_txt(v) for v in fila] for fila in z], texttemplate="%{text}", textfont=dict(size=10),
        xgap=2, ygap=2, colorbar=dict(title="%", ticksuffix="%", thickness=10),
        hovertemplate="<b>%{y}</b> con %{x}: %{z:.1f}%<extra></extra>"))
    fig = _fig_base(fig, max(420, 24 * len(top) + 90),
                    f"Quién opera cada fondo · % del {ec.MEDIDAS[medida].lower()} (30 emisoras más grandes)", t=44)
    fig.update_layout(yaxis=dict(autorange="reversed"), xaxis=dict(side="top"), margin=dict(l=10, r=10, t=80, b=10))
    st.plotly_chart(fig, width="stretch")

    with st.expander(f"Tabla completa · {len(tab)} emisoras", expanded=False, icon=":material/table_view:"):
        vista = tab[["EMISORA", "IMPORTE", "N_OPS", "N_CASAS", "CASA_VIGENTE", "DESDE", "REPARTO_4S"] + cols]
        disp = vista.copy()
        disp[cols] = vista[cols].map(_pct_txt)
        css = pd.DataFrame("", index=vista.index, columns=vista.columns)
        css[cols] = vista[cols].map(_css_celda)
        st.dataframe(
            disp.style.apply(lambda _: css, axis=None), hide_index=True, width="stretch",
            height=min(640, 40 + 35 * len(vista)),
            column_config={
                "EMISORA": st.column_config.TextColumn("Emisora", pinned=True),
                "IMPORTE": st.column_config.NumberColumn("Importe (MXN M)", format="$%,.1f"),
                "N_OPS": st.column_config.NumberColumn("Operaciones", format="%,d"),
                "N_CASAS": st.column_config.NumberColumn("Casas", format="%d"),
                "CASA_VIGENTE": st.column_config.TextColumn("Casa vigente", help="Casa del aviso más reciente"),
                "DESDE": st.column_config.DateColumn("Opera con ella desde", format="DD/MM/YYYY"),
                "REPARTO_4S": st.column_config.TextColumn("Reparto últimas 4 semanas", width="medium"),
                **{c: st.column_config.Column(c, help=ec.nombre(c), width="small") for c in cols},
            })
        st.caption(f"Celdas = % del {ec.MEDIDAS[medida].lower()} de cada emisora ejecutado con cada casa. "
                   "Casas fuera de las 12 principales del periodo se agrupan en OTRAS.")

    pdf, xlsx = _descargas_panorama(ini, fin, medida, destacada, version)
    d1, d2, _ = st.columns([1, 1, 2.4])
    d1.download_button("PDF emisoras y casas", pdf, file_name=f"Emisoras_casas_{ini:%Y%m%d}_{fin:%Y%m%d}.pdf",
                       mime="application/pdf", icon=":material/picture_as_pdf:", type="primary", width="stretch",
                       key="dl_pan_pdf")
    d2.download_button("Excel emisoras y casas", xlsx, file_name=f"Emisoras_casas_{ini:%Y%m%d}_{fin:%Y%m%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       icon=":material/table_view:", width="stretch", key="dl_pan_xlsx")


# ---------------------------------------------------------------------------
# Vista 2 · Liga y mandatos
# ---------------------------------------------------------------------------

def _fig_participacion(liga: pd.DataFrame, destacada: str) -> go.Figure:
    d = liga.head(12)
    if destacada in liga.index and destacada not in d.index:
        d = pd.concat([d.iloc[:11], liga.loc[[destacada]]])
    colores = [NARANJA if c == destacada else CAT[0] for c in d.index]
    texto = [f"{p:.1f}%  ({dp:+.1f} pp)" if pd.notna(dp) else f"{p:.1f}%" for p, dp in zip(d["PART"], d["DELTA_PP"])]
    fig = go.Figure(go.Bar(
        x=d["PART"], y=d.index, orientation="h", marker_color=colores, text=texto, textposition="outside",
        cliponaxis=False, customdata=d[["NOMBRE", "IMPORTE", "EMISORAS", "EXCLUSIVOS"]].values,
        hovertemplate="<b>%{y}</b> · %{customdata[0]}<br>Participación %{x:.1f}%<br>Importe $%{customdata[1]:,.0f} M"
                      "<br>%{customdata[2]} emisoras · %{customdata[3]} exclusivas<extra></extra>"))
    fig = _fig_base(fig, 420, "Participación por importe · cambio vs periodo previo")
    fig.update_layout(yaxis=dict(autorange="reversed"), hovermode="closest",
                      xaxis=dict(ticksuffix="%", range=[0, d["PART"].max() * 1.45]))
    return fig


def _fig_cambio_pp(liga: pd.DataFrame) -> go.Figure:
    d = liga.dropna(subset=["DELTA_PP"])
    d = d[d["DELTA_PP"].abs() >= 0.05].sort_values("DELTA_PP")
    fig = go.Figure(go.Bar(
        x=d["DELTA_PP"], y=d.index, orientation="h", marker_color=[GANA if v > 0 else PIERDE for v in d["DELTA_PP"]],
        text=[f"{v:+.1f}" for v in d["DELTA_PP"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:+.1f} pp<extra></extra>"))
    fig = _fig_base(fig, 420, "Quién ganó y quién perdió mercado (pp)")
    lo, hi = min(d["DELTA_PP"].min(), 0), max(d["DELTA_PP"].max(), 0)
    pad = (hi - lo) * 0.16
    fig.update_layout(xaxis=dict(zeroline=True, zerolinecolor="#8C8496", range=[lo - pad, hi + pad]), hovermode="closest")
    return fig


def _fig_ejecucion(liga: pd.DataFrame) -> go.Figure:
    d = liga.dropna(subset=["PRIMA_BPS"])
    d = d[d["N_OPS"] >= 200].sort_values("PRIMA_BPS")
    fig = go.Figure(go.Bar(
        x=d.index, y=d["PRIMA_BPS"], marker_color=[GANA if v < 0 else PIERDE for v in d["PRIMA_BPS"]],
        text=[f"{v:+.0f}" for v in d["PRIMA_BPS"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Compra vs cierre: %{y:+.1f} bps<extra></extra>"))
    fig = _fig_base(fig, 330, "Disciplina de precio: compra vs cierre (bps · verde = por debajo del cierre)")
    lo, hi = min(d["PRIMA_BPS"].min(), 0), max(d["PRIMA_BPS"].max(), 0)
    pad = (hi - lo) * 0.15
    fig.update_layout(yaxis=dict(range=[lo - pad, hi + pad], zeroline=True, zerolinecolor="#8C8496"),
                      xaxis=dict(showgrid=False), hovermode="closest")
    return fig


def _fig_mensual(mensual: pd.DataFrame, colores: dict) -> go.Figure:
    fig = go.Figure()
    x = mensual.index.to_timestamp()
    for c in mensual.columns:
        fig.add_scatter(x=x, y=mensual[c], name=c, mode="lines", stackgroup="uno", line=dict(width=0.6, color="#FFFFFF"),
                        fillcolor=colores.get(c, cv.GRIS),
                        hovertemplate=f"<b>{c}</b> · %{{x}}<br>%{{y:.1f}}% del importe<extra></extra>")
    fig = _fig_base(fig, 400, "Participación mensual por casa (% del importe de cada mes)", leyenda=True, t=70)
    fig.update_layout(yaxis=dict(ticksuffix="%", range=[0, 100]), hovermode="x unified")
    return _eje_meses(fig)


def _vista_liga(an: ca.AnalisisCasas, ini, fin, destacada, version, colores):
    k = an.kpis
    T.tiles([
        {"label": "Importe operado", "value": T.fmt_mxn(k["importe"] * 1e6), "sub": f"{ini:%d/%m/%Y} – {fin:%d/%m/%Y}"},
        {"label": "Emisoras con fondo activo", "value": f"{k['emisoras']}", "sub": f"{k['casas']} casas de bolsa"},
        {"label": "Mandatos exclusivos", "value": f"{k['exclusivos']}", "sub": f"{k['compartidos']} compartidos"},
        {"label": "Concentración top 3", "value": f"{k['top3']:.0f}%", "sub": f"HHI {k['hhi']:,.0f}"},
        {"label": "Cambios de mandato", "value": f"{k['cambios']}", "sub": "en el periodo"},
        {"label": f"Posición {destacada}", "value": f"#{k['dest_rank']}" if k["dest_rank"] else "—",
         "delta": f"{k['dest_part']:.1f}% · {k['dest_delta']:+.1f} pp" if pd.notna(k["dest_delta"]) else None,
         "dir": T.dir_de(k["dest_delta"])},
    ])
    izq, der = st.columns([1.5, 1])
    with izq.container(border=True):
        st.markdown("**Hallazgos principales**")
        st.markdown("\n".join("- " + h.replace("<b>", "**").replace("</b>", "**").replace("$", "\\$")
                              for h in an.hallazgos))
    with der:
        pdf, xlsx = _descargas_analisis(ini, fin, destacada, version)
        st.download_button("Reporte PDF completo", pdf, file_name=f"Casas_fondos_recompra_{ini:%Y%m%d}_{fin:%Y%m%d}.pdf",
                           mime="application/pdf", icon=":material/picture_as_pdf:", type="primary", width="stretch",
                           key="dl_an_pdf")
        st.download_button("Excel completo", xlsx, file_name=f"Casas_fondos_recompra_{ini:%Y%m%d}_{fin:%Y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           icon=":material/table_view:", width="stretch", key="dl_an_xlsx")
        tipos = an.mandatos["TIPO"].value_counts()
        st.plotly_chart(_fig_dona(tipos, TIPO_COLOR, "Mandatos por tipo", f"<b>{int(tipos.sum())}</b><br>emisoras"),
                        width="stretch")

    sub = st.segmented_control(
        "Ver", ["Liga", "Mandatos", "Cambios de mandato", f"Oportunidades {destacada}", "Dinámica mensual"],
        default="Liga", key="cb_sub_liga", label_visibility="collapsed") or "Liga"

    if sub == "Liga":
        g1, g2 = st.columns([1.25, 1])
        g1.plotly_chart(_fig_participacion(an.liga, destacada), width="stretch")
        g2.plotly_chart(_fig_cambio_pp(an.liga), width="stretch")
        st.plotly_chart(_fig_ejecucion(an.liga), width="stretch")
        liga = an.liga.reset_index()
        st.dataframe(
            liga[["RANK", "NOMBRE", "IMPORTE", "PART", "DELTA_PP", "EMISORAS", "EXCLUSIVOS", "COMPARTIDOS", "TOP"]],
            hide_index=True, width="stretch", height=40 + 35 * len(liga),
            column_config={
                "RANK": st.column_config.NumberColumn("#", format="%d", width="small"),
                "NOMBRE": st.column_config.TextColumn("Casa de bolsa"),
                "IMPORTE": st.column_config.NumberColumn("Importe (MXN M)", format="$%,.0f"),
                "PART": st.column_config.ProgressColumn("Participación", format="%.1f%%", min_value=0,
                                                        max_value=float(liga["PART"].max())),
                "DELTA_PP": st.column_config.NumberColumn("Cambio (pp)", format="%+.1f"),
                "EMISORAS": st.column_config.NumberColumn("Emisoras", format="%d"),
                "EXCLUSIVOS": st.column_config.NumberColumn("Exclusivas", format="%d",
                                                            help="Emisoras donde la casa ejecuta ≥90% del importe"),
                "COMPARTIDOS": st.column_config.NumberColumn("Compartidas", format="%d"),
                "TOP": st.column_config.TextColumn("Principales emisoras", width="large"),
            })

    elif sub == "Mandatos":
        f1, f2, f3 = st.columns(3)
        estatus = f1.multiselect("Estatus", list(ESTATUS_COLOR), default=list(ESTATUS_COLOR), key="cb_estatus")
        tipos_sel = f2.multiselect("Tipo de mandato", list(TIPO_COLOR), default=list(TIPO_COLOR), key="cb_tipos")
        casa_f = f3.multiselect("Casa principal", sorted(an.mandatos["CASA_PRINCIPAL"].dropna().unique()), key="cb_casa_f")
        m = an.mandatos[an.mandatos["ESTATUS"].isin(estatus) & an.mandatos["TIPO"].isin(tipos_sel)]
        if casa_f:
            m = m[m["CASA_PRINCIPAL"].isin(casa_f)]
        g1, g2 = st.columns(2)
        est = m["ESTATUS"].value_counts().reindex(list(ESTATUS_COLOR)).fillna(0)
        g1.plotly_chart(_fig_barras_h(est.index, est.values, [ESTATUS_COLOR[e] for e in est.index],
                                      "Fondos por estatus", alto=240), width="stretch")
        mf = m.dropna(subset=["MESES_FONDO"]).sort_values("MESES_FONDO").head(12)
        g2.plotly_chart(_fig_barras_h(mf["EMISORA"], mf["MESES_FONDO"], [TIPO_COLOR.get(t, cv.GRIS) for t in mf["TIPO"]],
                                      "Fondos que se agotan antes (meses de fondo)", fmt="{:.1f}", alto=240),
                        width="stretch")
        cols_m = ["EMISORA", "SECTOR", "TIPO", "CASA_PRINCIPAL", "PCT_PRINCIPAL", "CASA_VIGENTE", "DESDE", "ESTATUS",
                  "ULTIMA", "INTENSIDAD", "IMPORTE", "REMANENTE", "MESES_FONDO", "REPARTO_4S"]
        st.dataframe(
            _estilo_estatus(m[cols_m].reset_index(drop=True)), hide_index=True, width="stretch",
            height=min(640, 40 + 35 * len(m)),
            column_config={
                "EMISORA": st.column_config.TextColumn("Emisora", pinned=True), "SECTOR": "Sector",
                "TIPO": "Tipo de mandato", "CASA_PRINCIPAL": "Casa principal",
                "PCT_PRINCIPAL": st.column_config.ProgressColumn("Peso principal", format="%.0f%%", min_value=0,
                                                                 max_value=100),
                "CASA_VIGENTE": "Casa vigente", "DESDE": st.column_config.DateColumn("Desde", format="DD/MM/YYYY"),
                "ESTATUS": "Estatus", "ULTIMA": st.column_config.DateColumn("Última operación", format="DD/MM/YYYY"),
                "INTENSIDAD": st.column_config.ProgressColumn("Intensidad", format="%.0f%%", min_value=0, max_value=100,
                                                              help="Sesiones con recompra / sesiones del periodo"),
                "IMPORTE": st.column_config.NumberColumn("Importe (MXN M)", format="$%,.0f"),
                "REMANENTE": st.column_config.NumberColumn("Fondo remanente (M)", format="$%,.0f"),
                "MESES_FONDO": st.column_config.NumberColumn("Meses de fondo", format="%.1f",
                                                             help="Remanente / compras mensuales promedio (3 meses)"),
                "REPARTO_4S": st.column_config.TextColumn("Reparto 4 semanas", width="medium"),
            })
        st.caption("Exclusivo: ≥90% del importe con una casa · Principal + secundaria: 60–90% · Compartido: <60%. "
                   "Activo: operó en los últimos 30 días · En pausa: 31–120 · Inactivo: >120.")

    elif sub == "Cambios de mandato":
        if an.cambios.empty:
            st.info("No se detectaron cambios de casa principal en el periodo.")
        else:
            cam = an.cambios.sort_values("FECHA").copy()
            col = [GANA if a == destacada else (PIERDE if d == destacada else CAT[0]) for d, a in zip(cam["DE"], cam["A"])]
            fig = go.Figure(go.Scatter(
                x=cam["FECHA"], y=cam["EMISORA"], mode="markers+text", text=cam["DE"] + " → " + cam["A"],
                textposition="middle right", marker=dict(size=13, color=col, line=dict(color="#FFFFFF", width=1.5)),
                customdata=cam[["IMPORTE_DESDE"]].values, cliponaxis=False,
                hovertemplate="<b>%{y}</b> · %{x|%d/%m/%Y}<br>%{text}<br>Importe con la nueva $%{customdata[0]:,.1f} M"
                              "<extra></extra>"))
            fig = _fig_base(fig, max(300, 30 * cam["EMISORA"].nunique() + 90), "Línea de tiempo de cambios de mandato")
            fig.update_layout(xaxis=dict(range=[pd.Timestamp(ini), pd.Timestamp(fin) + pd.Timedelta(days=60)]),
                              margin=dict(l=10, r=10, t=44, b=10))
            st.plotly_chart(fig, width="stretch")
            cam["RESULTADO"] = cam.apply(lambda r: f"Ganó {destacada}" if r["A"] == destacada else
                                         (f"Perdió {destacada}" if r["DE"] == destacada else ""), axis=1)
            st.dataframe(cam.sort_values("FECHA", ascending=False), hide_index=True, width="stretch", column_config={
                "FECHA": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"), "EMISORA": "Emisora",
                "DE": "Casa anterior", "A": "Casa nueva",
                "SESIONES_PREVIA": st.column_config.NumberColumn("Sesiones casa anterior", format="%d"),
                "SESIONES_NUEVA": st.column_config.NumberColumn("Sesiones casa nueva", format="%d"),
                "IMPORTE_DESDE": st.column_config.NumberColumn("Importe con la nueva (M)", format="$%,.1f"),
                "RESULTADO": f"Para {destacada}"})
            st.caption("Cambio = la casa de mayor importe de cada sesión cambia durante un tramo consolidado; "
                       "las alternancias cortas de mandatos compartidos no cuentan.")

    elif sub.startswith("Oportunidades"):
        op = an.oportunidades
        g1, g2 = st.columns(2)
        sd = op["sin_destacada"].dropna(subset=["REMANENTE"]).head(12)
        g1.plotly_chart(_fig_barras_h(sd["EMISORA"], sd["REMANENTE"], [colores.get(c, cv.GRIS) for c in sd["CASA_VIGENTE"]],
                                      f"Fondo disponible en emisoras sin {destacada} (MXN M)", alto=380), width="stretch")
        fs = op["fondos_sin_operar"].dropna(subset=["REMANENTE"]).sort_values("REMANENTE", ascending=False).head(12)
        g2.plotly_chart(_fig_barras_h(fs["EMISORA"], fs["REMANENTE"], [CAT[3]] * len(fs),
                                      "Fondos con remanente sin operar 45+ días (MXN M)", alto=380), width="stretch")
        a1, a2 = st.columns(2)
        with a1:
            _subtitulo(f"Emisoras activas sin {destacada}", "ordenadas por fondo disponible")
            st.dataframe(op["sin_destacada"][["EMISORA", "CASA_VIGENTE", "TIPO", "IMPORTE", "REMANENTE", "ULTIMA"]],
                         hide_index=True, width="stretch", height=360, column_config={
                             "EMISORA": "Emisora", "CASA_VIGENTE": "Casa vigente", "TIPO": "Tipo",
                             "IMPORTE": st.column_config.NumberColumn("Importe (M)", format="$%,.0f"),
                             "REMANENTE": st.column_config.NumberColumn("Fondo rem. (M)", format="$%,.0f"),
                             "ULTIMA": st.column_config.DateColumn("Última op.", format="DD/MM/YYYY")})
            _subtitulo("Mandatos en movimiento", "compartidos o con cambio reciente")
            st.dataframe(op["en_movimiento"][["EMISORA", "CASA_PRINCIPAL", "PCT_PRINCIPAL", "REPARTO_4S", "IMPORTE"]],
                         hide_index=True, width="stretch", height=320, column_config={
                             "EMISORA": "Emisora", "CASA_PRINCIPAL": "Principal",
                             "PCT_PRINCIPAL": st.column_config.ProgressColumn("Peso principal", format="%.0f%%",
                                                                              min_value=0, max_value=100),
                             "REPARTO_4S": st.column_config.TextColumn("Reparto 4 semanas", width="medium"),
                             "IMPORTE": st.column_config.NumberColumn("Importe (M)", format="$%,.0f")})
        with a2:
            _subtitulo("Fondos disponibles sin operar", "45+ días sin recompras")
            st.dataframe(op["fondos_sin_operar"][["EMISORA", "CASA_ULTIMA", "ULTIMA", "DIAS_SIN", "REMANENTE", "SECTOR"]],
                         hide_index=True, width="stretch", height=360, column_config={
                             "EMISORA": "Emisora", "CASA_ULTIMA": "Última casa", "SECTOR": "Sector",
                             "ULTIMA": st.column_config.DateColumn("Última op.", format="DD/MM/YYYY"),
                             "DIAS_SIN": st.column_config.NumberColumn("Días sin operar", format="%d"),
                             "REMANENTE": st.column_config.NumberColumn("Fondo rem. (M)", format="$%,.0f")})
            _subtitulo(f"Clientes actuales de {destacada}")
            st.dataframe(op["clientes"], hide_index=True, width="stretch", height=320, column_config={
                "IMPORTE": st.column_config.NumberColumn("Importe (M)", format="$%,.1f"),
                "N_OPS": st.column_config.NumberColumn("Operaciones", format="%,d"),
                "PCT_IMPORTE": st.column_config.ProgressColumn(f"Peso {destacada}", format="%.0f%%",
                                                               min_value=0, max_value=100),
                "ULTIMA": st.column_config.DateColumn("Última op.", format="DD/MM/YYYY"),
                "REMANENTE": st.column_config.NumberColumn("Fondo rem. (M)", format="$%,.0f")})

    else:
        st.plotly_chart(_fig_mensual(an.mensual, colores), width="stretch")


# ---------------------------------------------------------------------------
# Vista 3 · Por casa de bolsa (todos sus fondos juntos)
# ---------------------------------------------------------------------------

def _vista_casa(an: ca.AnalisisCasas, ini, fin, destacada, version, colores):
    orden = list(an.liga.index)
    c1, _ = st.columns([1.3, 3])
    casa = c1.selectbox("Casa de bolsa", orden, index=orden.index(destacada) if destacada in orden else 0,
                        format_func=lambda c: f"{an.liga.loc[c, 'RANK']:.0f}. {ec.nombre(c)}", key="cb_casa_perfil")
    p = _perfil(casa, ini, fin, destacada, version)
    f, s = p["fondos"], p["serie"]
    if f.empty:
        st.info("Esta casa no operó fondos de recompra en el periodo.")
        return
    r = an.liga.loc[casa]
    col_casa = CAT[0]
    vigentes = int(f["ES_VIGENTE"].sum())
    T.tiles([
        {"label": "Lugar en la liga", "value": f"#{int(r['RANK'])}",
         "sub": f"antes #{int(r['RANK_PREV'])}" if pd.notna(r["RANK_PREV"]) else "sin periodo previo"},
        {"label": "Participación", "value": f"{r['PART']:.1f}%",
         "delta": f"{r['DELTA_PP']:+.1f} pp vs previo" if pd.notna(r["DELTA_PP"]) else None, "dir": T.dir_de(r["DELTA_PP"])},
        {"label": "Importe operado", "value": T.fmt_mxn(p["total"]), "sub": f"{int(r['N_OPS']):,} operaciones"},
        {"label": "Fondos que opera", "value": f"{len(f)}",
         "sub": f"{int(r['EXCLUSIVOS'])} exclusivos · {int(r['COMPARTIDOS'])} compartidos"},
        {"label": "Es casa vigente en", "value": f"{vigentes}", "sub": "emisoras (aviso más reciente)"},
        {"label": "Ticket promedio", "value": T.fmt_mxn(r["TICKET"]), "sub": "importe / operación"},
    ])

    g1, g2 = st.columns(2)
    fig = go.Figure(go.Bar(x=s["MES"], y=s["IMPORTE"], marker_color=col_casa, xperiod="M1", xperiodalignment="middle",
                           customdata=s[["EMISORAS"]].values,
                           hovertemplate="%{x|%b %Y}<br>$%{y:,.1f} M · %{customdata[0]} emisoras<extra></extra>"))
    fig = _eje_meses(_fig_base(fig, 320, f"Importe operado por mes · {ec.nombre(casa)} (MXN M)"))
    fig.update_layout(hovermode="closest")
    g1.plotly_chart(fig, width="stretch")
    fig = go.Figure(go.Scatter(x=s["MES"], y=s["PART"], mode="lines+markers", line=dict(color=col_casa, width=2.5),
                               fill="tozeroy", fillcolor="rgba(112,48,160,0.08)", marker=dict(size=6),
                               hovertemplate="%{x|%b %Y}<br>%{y:.2f}% del mercado<extra></extra>"))
    fig = _eje_meses(_fig_base(fig, 320, "Participación de mercado por mes"))
    fig.update_layout(yaxis=dict(ticksuffix="%", rangemode="tozero"), hovermode="closest")
    g2.plotly_chart(fig, width="stretch")

    g3, g4 = st.columns([1, 1.2])
    libro = f.set_index("EMISORA")["IMPORTE"]
    col_emis = {e: CAT[i] if i < len(CAT) else cv.GRIS for i, e in enumerate(libro.index)}
    g3.plotly_chart(_fig_dona(libro, col_emis, "¿De qué fondos viene su importe?", f"<b>{len(f)}</b><br>fondos"),
                    width="stretch")
    top = f.head(15)
    fig = go.Figure(go.Bar(
        x=top["PCT_IMPORTE"], y=top["EMISORA"], orientation="h",
        marker_color=[col_casa if v else "#CDBFE0" for v in top["ES_VIGENTE"]],
        text=[f"{v:.0f}%" for v in top["PCT_IMPORTE"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:.0f}% del fondo lo ejecuta esta casa<extra></extra>"))
    fig = _fig_base(fig, 360, "Peso de la casa en cada fondo · morado = casa vigente, lila = ya no")
    fig.update_layout(yaxis=dict(autorange="reversed"), xaxis=dict(range=[0, 118], ticksuffix="%"), hovermode="closest",
                      bargap=0.35 if len(top) > 3 else 0.6)
    g4.plotly_chart(fig, width="stretch")

    _subtitulo(f"Fondos que opera {ec.nombre(casa)}", "barras = peso relativo · columna mensual = importe de cada mes")
    vista = f[["EMISORA", "SECTOR", "IMPORTE", "PCT_LIBRO", "PCT_IMPORTE", "TENDENCIA", "N_OPS", "SESIONES",
               "ULTIMA", "TIPO", "ESTATUS", "CASA_VIGENTE", "REMANENTE"]].copy()
    st.dataframe(
        _estilo_estatus(vista), hide_index=True, width="stretch", height=min(620, 40 + 35 * len(vista)),
        column_config={
            "EMISORA": st.column_config.TextColumn("Emisora", pinned=True), "SECTOR": "Sector",
            "IMPORTE": st.column_config.NumberColumn("Importe (MXN M)", format="$%,.1f"),
            "PCT_LIBRO": st.column_config.ProgressColumn("% de su importe", format="%.1f%%", min_value=0,
                                                         max_value=float(max(vista["PCT_LIBRO"].max(), 1))),
            "PCT_IMPORTE": st.column_config.ProgressColumn("Peso en el fondo", format="%.0f%%", min_value=0, max_value=100,
                                                           help="% del importe de la emisora ejecutado por esta casa"),
            "TENDENCIA": st.column_config.BarChartColumn("Importe mensual", y_min=0),
            "N_OPS": st.column_config.NumberColumn("Operaciones", format="%,d"),
            "SESIONES": st.column_config.NumberColumn("Sesiones", format="%d"),
            "ULTIMA": st.column_config.DateColumn("Última op.", format="DD/MM/YYYY"),
            "TIPO": "Tipo de mandato", "ESTATUS": "Estatus", "CASA_VIGENTE": "Casa vigente",
            "REMANENTE": st.column_config.NumberColumn("Fondo rem. (M)", format="$%,.0f"),
        })


# ---------------------------------------------------------------------------
# Vista 4 · Fondo individual
# ---------------------------------------------------------------------------

def _vista_fondo(an: ca.AnalisisCasas, ini, fin, version, colores):
    man = an.mandatos.set_index("EMISORA")
    orden = list(an.mandatos.sort_values("IMPORTE", ascending=False)["EMISORA"])
    c1, _ = st.columns([1.3, 3])
    emi = c1.selectbox("Emisora", orden, key="cb_emisora_ficha")
    d = _ficha(emi, ini, fin, version)
    if not d:
        st.info("Esta emisora no tiene operaciones en el periodo.")
        return
    m = man.loc[emi]
    casas = d["casas"]
    T.tiles([
        {"label": "Casa vigente", "value": str(m["CASA_VIGENTE"]),
         "sub": f"desde {pd.Timestamp(m['DESDE']):%d/%m/%Y}" if pd.notna(m["DESDE"]) else ""},
        {"label": "Tipo de mandato", "value": str(m["TIPO"]), "sub": f"{m['CASA_PRINCIPAL']} ejecuta {m['PCT_PRINCIPAL']:.0f}%"},
        {"label": "Importe operado", "value": T.fmt_mxn(d["importe"] * 1e6), "sub": f"{int(d['n_ops']):,} operaciones"},
        {"label": "Sesiones con recompra", "value": f"{d['sesiones']}", "sub": f"intensidad {m['INTENSIDAD']:.0f}%"},
        {"label": "Fondo remanente", "value": T.fmt_mxn(m["REMANENTE"] * 1e6) if pd.notna(m["REMANENTE"]) else "—",
         "sub": f"≈ {m['MESES_FONDO']:.1f} meses al ritmo actual" if pd.notna(m["MESES_FONDO"]) else ""},
        {"label": "Estatus", "value": str(m["ESTATUS"]), "sub": f"última operación {d['ultima']:%d/%m/%Y}"},
    ])

    # Precio de cierre vs precio de compra del fondo (misma escala: pesos por acción)
    px, vw = d["precio"], d["vwap"]
    if not px.empty or not vw.empty:
        fig = go.Figure()
        if not px.empty:
            fig.add_scatter(x=px["FECHA"], y=px["CLOSE"], name="Cierre", mode="lines", line=dict(color="#8C8496", width=1.6),
                            hovertemplate="%{x|%d/%m/%Y}<br>Cierre $%{y:,.2f}<extra></extra>")
        if not vw.empty:
            fig.add_scatter(x=vw["FECHA_OPERACION"], y=vw["VWAP"], name="Precio de compra del fondo", mode="markers",
                            marker=dict(color=CAT[0], size=6, opacity=0.85),
                            hovertemplate="%{x|%d/%m/%Y}<br>Compró a $%{y:,.2f}<extra></extra>")
        st.plotly_chart(_fig_base(fig, 330, f"{emi}: precio de cierre y precio al que compró el fondo (MXN por acción)",
                                  leyenda=True, t=70), width="stretch")

    g1, g2 = st.columns([1.5, 1])
    sem = d["semanal"]
    fig = go.Figure()
    for c in sem.columns:
        fig.add_bar(x=sem.index, y=sem[c], name=c, marker_color=colores.get(c, cv.GRIS),
                    hovertemplate=f"<b>{c}</b> · semana %{{x|%d/%m/%Y}}<br>$%{{y:,.1f}} M<extra></extra>")
    fig = _fig_base(fig, 360, "Importe semanal por casa (MXN M)", leyenda=True, t=70)
    fig.update_layout(barmode="stack", bargap=0.15, hovermode="x unified")
    fig.update_xaxes(showgrid=False)
    g1.plotly_chart(fig, width="stretch")
    g2.plotly_chart(_fig_dona(casas.set_index("CASA_BOLSA")["IMPORTE"], colores, "Reparto entre casas",
                              f"<b>{len(casas)}</b><br>casa(s)"), width="stretch")

    # Línea de tiempo: cada punto es una sesión, tamaño = importe
    dia = d["diario"]
    orden_c = list(casas["CASA_BOLSA"])
    fig = go.Figure()
    mx = max(dia["IMPORTE"].max(), 1e-9)
    for c in orden_c:
        dc = dia[dia["CASA_BOLSA"] == c]
        fig.add_scatter(x=dc["FECHA_OPERACION"], y=[c] * len(dc), mode="markers", name=c,
                        marker=dict(size=6 + 22 * np.sqrt(dc["IMPORTE"] / mx), color=colores.get(c, cv.GRIS), opacity=0.75,
                                    line=dict(color="#FFFFFF", width=0.8)),
                        customdata=dc[["IMPORTE", "N_OPS"]].values,
                        hovertemplate=f"<b>{c}</b> · %{{x|%d/%m/%Y}}<br>$%{{customdata[0]:,.1f}} M · "
                                      f"%{{customdata[1]:,.0f}} operaciones<extra></extra>")
    fig = _fig_base(fig, max(200, 46 * len(orden_c) + 90), "Línea de tiempo por casa · cada punto es una sesión (tamaño = importe)")
    fig.update_layout(yaxis=dict(categoryorder="array", categoryarray=orden_c[::-1]))
    st.plotly_chart(fig, width="stretch")

    _subtitulo(f"Casas que operaron el fondo de {emi}")
    st.dataframe(
        casas[["NOMBRE", "IMPORTE", "PCT_IMPORTE", "TENDENCIA", "N_OPS", "SESIONES", "TICKET", "PRIMERA", "ULTIMA"]],
        hide_index=True, width="stretch",
        column_config={
            "NOMBRE": st.column_config.TextColumn("Casa de bolsa", pinned=True),
            "IMPORTE": st.column_config.NumberColumn("Importe (MXN M)", format="$%,.1f"),
            "PCT_IMPORTE": st.column_config.ProgressColumn("Peso", format="%.0f%%", min_value=0, max_value=100),
            "TENDENCIA": st.column_config.BarChartColumn("Importe mensual", y_min=0),
            "N_OPS": st.column_config.NumberColumn("Operaciones", format="%,d"),
            "SESIONES": st.column_config.NumberColumn("Sesiones", format="%d"),
            "TICKET": st.column_config.NumberColumn("Ticket prom.", format="$%,.0f"),
            "PRIMERA": st.column_config.DateColumn("Primera op.", format="DD/MM/YYYY"),
            "ULTIMA": st.column_config.DateColumn("Última op.", format="DD/MM/YYYY"),
        })
    cam = an.cambios[an.cambios["EMISORA"] == emi] if not an.cambios.empty else pd.DataFrame()
    if not cam.empty:
        _subtitulo("Cambios de mandato detectados")
        for r in cam.sort_values("FECHA").itertuples():
            st.markdown(f"- {pd.Timestamp(r.FECHA):%d/%m/%Y}: **{r.DE} → {r.A}**")


# ---------------------------------------------------------------------------
# Sección
# ---------------------------------------------------------------------------

@st.fragment
def render():
    act = market_store.actividad()
    T.seccion("Casas de bolsa y fondos de recompra",
              "quién opera cada fondo, cómo se reparte el mercado y dónde están las oportunidades")
    if act.empty:
        st.info("Aún no hay tabla de actividad.")
        return
    ult = act["FECHA_OPERACION"].max().date()
    casas_todas = sorted(act["CASA_BOLSA"].dropna().astype(str).unique())
    c1, c2, c3 = st.columns([2.4, 1.1, 1.5])
    per = c1.segmented_control("Periodo", list(PERIODOS), default="1 año", key="cb_periodo") or "1 año"
    destacada = c2.selectbox("Casa a destacar", casas_todas,
                             index=casas_todas.index("PUNTO") if "PUNTO" in casas_todas else 0, key="cb_destacada")
    if per == "Personalizado":
        rango = c3.date_input("Rango", (ult - timedelta(days=365), ult), max_value=ult, format="DD/MM/YYYY",
                              key="cb_rango")
        if not isinstance(rango, (list, tuple)) or len(rango) != 2:
            st.caption("Elige la fecha final del rango.")
            return
        ini, fin = rango
    else:
        fin = ult
        ini = date(ult.year, 1, 1) if per == "YTD" else ult - timedelta(days=PERIODOS[per])
    version = f"{len(act)}-{ult:%Y%m%d}"
    with st.spinner("Analizando mandatos…"):
        an = _analisis(ini, fin, destacada, version)
    if an.liga.empty:
        st.info("Sin operaciones en el periodo elegido.")
        return
    colores = cv.colores_casas(list(an.liga.index))

    t_todos, t_liga, t_casa, t_fondo = st.tabs([
        ":material/dashboard: Todos los fondos", ":material/leaderboard: Liga y mandatos",
        ":material/account_balance: Por casa de bolsa", ":material/search: Fondo individual"])
    with t_todos:
        _vista_todos(ini, fin, destacada, version, colores)
    with t_liga:
        _vista_liga(an, ini, fin, destacada, version, colores)
    with t_casa:
        _vista_casa(an, ini, fin, destacada, version, colores)
    with t_fondo:
        _vista_fondo(an, ini, fin, version, colores)

    with st.expander("¿Se puede saber con quién tiene contrato cada fondo de recompra?", icon=":material/help:"):
        st.markdown(
            "No hay un registro público de los contratos entre emisoras y casas de bolsa para operar el fondo de "
            "recompra. Lo que sí es público es la **casa que ejecuta cada operación**, porque la emisora la reporta "
            "en cada aviso a la BMV. Con eso se infiere el mandato: **casa vigente** (aviso más reciente), "
            "**desde cuándo** la usa sin interrupción, el **tipo de mandato** (exclusivo, principal + secundaria o "
            "compartido) y los **cambios de casa principal**.")
