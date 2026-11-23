"""Sección "Casas de bolsa y fondos de recompra" de la página principal (Streamlit)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import casas_analisis as ca
from src import emisoras_casas as ec
from src import market_store
from src import theme as T

PERIODOS = {"3M": 92, "6M": 183, "YTD": None, "1 año": 365, "2 años": 730, "Personalizado": 0}
CAT = ["#7030A0", "#0E9A94", "#2063B0", "#C5770F", "#AB3276", "#599234"]
GANA, PIERDE = "#2E9E52", "#A9131F"


@st.cache_data(show_spinner=False, max_entries=12)
def _analisis(ini: date, fin: date, destacada: str, version: str) -> ca.AnalisisCasas:
    return ca.analizar(market_store.actividad(), market_store.documentos(), market_store.mercado(), ini, fin, destacada)


@st.cache_data(show_spinner=False, max_entries=6)
def _descargas(ini: date, fin: date, destacada: str, version: str) -> tuple[bytes, bytes]:
    from src import reporte_casas_pdf as rp
    an = _analisis(ini, fin, destacada, version)
    return rp.generar_pdf(an), rp.excel_bytes(an)


@st.cache_data(show_spinner=False, max_entries=12)
def _matriz(ini: date, fin: date, medida: str, destacada: str, version: str):
    return ec.matriz(market_store.actividad(), ini, fin, medida, incluir=(destacada,))


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


# ---------------------------------------------------------------------------
# Gráficas
# ---------------------------------------------------------------------------

def _fig_participacion(liga: pd.DataFrame, destacada: str) -> go.Figure:
    d = liga.head(12)
    if destacada in liga.index and destacada not in d.index:
        d = pd.concat([d.iloc[:11], liga.loc[[destacada]]])
    d = d.iloc[::-1]
    colores = [CAT[3] if c == destacada else CAT[0] for c in d.index]
    texto = [f"{p:.1f}%  ({dp:+.1f} pp)" if pd.notna(dp) else f"{p:.1f}%" for p, dp in zip(d["PART"], d["DELTA_PP"])]
    fig = go.Figure(go.Bar(
        x=d["PART"], y=d.index, orientation="h", marker_color=colores, text=texto, textposition="outside",
        customdata=d[["NOMBRE", "IMPORTE", "EMISORAS", "EXCLUSIVOS"]].values,
        hovertemplate="<b>%{y}</b> · %{customdata[0]}<br>Participación %{x:.1f}%<br>Importe $%{customdata[1]:,.0f} M"
                      "<br>%{customdata[2]} emisoras · %{customdata[3]} exclusivas<extra></extra>"))
    fig.update_layout(template="punto", height=430, margin=dict(l=10, r=40, t=40, b=10),
                      title="Participación por importe operado · cambio vs periodo previo",
                      xaxis=dict(ticksuffix="%", range=[0, d["PART"].max() * 1.35]), showlegend=False)
    return fig


def _fig_mensual(mensual: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    nombres = [c for c in mensual.columns if c != "OTRAS"]
    for i, c in enumerate(mensual.columns):
        fig.add_bar(x=[m.strftime("%b %Y") for m in mensual.index.to_timestamp()], y=mensual[c], name=c,
                    marker_color=CAT[nombres.index(c) % len(CAT)] if c != "OTRAS" else "#C9BFD3",
                    hovertemplate=f"<b>{c}</b> · %{{x}}<br>%{{y:.1f}}% del importe<extra></extra>")
    fig.update_layout(template="punto", barmode="stack", height=380, margin=dict(l=10, r=10, t=60, b=10),
                      title="Participación mensual por casa (% del importe de cada mes)",
                      yaxis=dict(ticksuffix="%", range=[0, 100]),
                      legend=dict(orientation="h", y=1.08, x=0, yanchor="bottom"))
    return fig


def _fig_ejecucion(liga: pd.DataFrame, destacada: str) -> go.Figure:
    d = liga.dropna(subset=["PRIMA_BPS"])
    d = d[d["N_OPS"] >= 200].sort_values("PRIMA_BPS")
    fig = go.Figure(go.Bar(
        x=d.index, y=d["PRIMA_BPS"], marker_color=[GANA if v < 0 else PIERDE for v in d["PRIMA_BPS"]],
        text=[f"{v:+.0f}" for v in d["PRIMA_BPS"]], textposition="outside",
        hovertemplate="<b>%{x}</b><br>Compra vs cierre: %{y:+.1f} bps<extra></extra>"))
    fig.update_layout(template="punto", height=320, margin=dict(l=10, r=10, t=50, b=10), showlegend=False,
                      title="Disciplina de precio: compra vs cierre del día (bps; verde = por debajo del cierre)")
    return fig


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
    with st.container(border=True):
        st.markdown("**Hallazgos principales**")
        st.markdown("\n".join("- " + h.replace("<b>", "**").replace("</b>", "**").replace("$", "\\$")
                              for h in an.hallazgos))

    pdf, xlsx = _descargas(ini, fin, destacada, version)
    d1, d2, _ = st.columns([1.2, 1.2, 3])
    d1.download_button("Reporte PDF completo", pdf, file_name=f"Casas_fondos_recompra_{ini:%Y%m%d}_{fin:%Y%m%d}.pdf",
                       mime="application/pdf", icon=":material/picture_as_pdf:", type="primary", width="stretch")
    d2.download_button("Excel completo", xlsx,
                       file_name=f"Casas_fondos_recompra_{ini:%Y%m%d}_{fin:%Y%m%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       icon=":material/table_view:", width="stretch")

    t_liga, t_mat, t_man, t_cam, t_op, t_din = st.tabs(
        [":material/leaderboard: Liga de casas", ":material/grid_on: Quién opera cada fondo",
         ":material/handshake: Mandatos", ":material/swap_horiz: Cambios de mandato",
         f":material/target: Oportunidades {destacada}", ":material/insights: Dinámica mensual"])

    with t_liga:
        izq, der = st.columns([1, 1])
        izq.plotly_chart(_fig_participacion(an.liga, destacada), width="stretch")
        der.plotly_chart(_fig_ejecucion(an.liga, destacada), width="stretch")
        liga = an.liga.reset_index()
        st.dataframe(
            liga[["RANK", "CASA_BOLSA", "NOMBRE", "IMPORTE", "PART", "DELTA_PP", "RANK_PREV", "EMISORAS", "EXCLUSIVOS",
                  "COMPARTIDOS", "N_OPS", "TICKET", "PRIMA_BPS", "TOP"]],
            hide_index=True, width="stretch",
            column_config={
                "RANK": st.column_config.NumberColumn("#", format="%d", width="small"),
                "CASA_BOLSA": st.column_config.TextColumn("Casa", pinned=True),
                "NOMBRE": "Nombre",
                "IMPORTE": st.column_config.NumberColumn("Importe (MXN M)", format="$%,.0f"),
                "PART": st.column_config.ProgressColumn("Participación", format="%.1f%%", min_value=0, max_value=100),
                "DELTA_PP": st.column_config.NumberColumn("Cambio (pp)", format="%+.1f"),
                "RANK_PREV": st.column_config.NumberColumn("Lugar previo", format="%d"),
                "EMISORAS": st.column_config.NumberColumn("Emisoras", format="%d"),
                "EXCLUSIVOS": st.column_config.NumberColumn("Exclusivas", format="%d",
                                                            help="Emisoras donde la casa ejecuta ≥90% del importe"),
                "COMPARTIDOS": st.column_config.NumberColumn("Compartidas", format="%d"),
                "N_OPS": st.column_config.NumberColumn("Operaciones", format="%,d"),
                "TICKET": st.column_config.NumberColumn("Ticket prom.", format="$%,.0f"),
                "PRIMA_BPS": st.column_config.NumberColumn("Compra vs cierre (bps)", format="%+.1f",
                                                           help="Negativo = compró por debajo del cierre del día"),
                "TOP": st.column_config.TextColumn("Principales emisoras", width="large"),
            })

    with t_mat:
        medida = st.segmented_control("Ponderar por", list(ec.MEDIDAS), default="IMPORTE", key="cb_medida",
                                      format_func=lambda m: {"IMPORTE": "Importe", "N_OPS": "Operaciones"}[m]) or "IMPORTE"
        tab, cols = _matriz(ini, fin, medida, destacada, version)
        tipo = an.mandatos.set_index("EMISORA")["TIPO"]
        vista = tab[["EMISORA", "IMPORTE", "N_OPS", "CASA_VIGENTE", "DESDE", "REPARTO_4S"] + cols].copy()
        vista.insert(3, "TIPO", vista["EMISORA"].map(tipo))
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
                "TIPO": "Tipo de mandato",
                "CASA_VIGENTE": st.column_config.TextColumn("Casa vigente", help="Casa del aviso más reciente"),
                "DESDE": st.column_config.DateColumn("Desde", format="DD/MM/YYYY"),
                "REPARTO_4S": st.column_config.TextColumn("Reparto últimas 4 semanas", width="medium"),
                **{c: st.column_config.Column(c, help=ec.nombre(c), width="small") for c in cols},
            })
        st.caption(f"Celdas = % del {ec.MEDIDAS[medida].lower()} de cada emisora ejecutado con cada casa.")

    with t_man:
        f1, f2, f3 = st.columns(3)
        estatus = f1.multiselect("Estatus", ["Activo", "En pausa", "Inactivo"], default=["Activo", "En pausa", "Inactivo"],
                                 key="cb_estatus")
        tipos = f2.multiselect("Tipo de mandato", ["Exclusivo", "Principal + secundaria", "Compartido"],
                               default=["Exclusivo", "Principal + secundaria", "Compartido"], key="cb_tipos")
        casa_f = f3.multiselect("Casa principal", sorted(an.mandatos["CASA_PRINCIPAL"].dropna().unique()), key="cb_casa_f")
        m = an.mandatos[an.mandatos["ESTATUS"].isin(estatus) & an.mandatos["TIPO"].isin(tipos)]
        if casa_f:
            m = m[m["CASA_PRINCIPAL"].isin(casa_f)]
        st.dataframe(
            m[["EMISORA", "SECTOR", "TIPO", "CASA_PRINCIPAL", "PCT_PRINCIPAL", "CASA_VIGENTE", "DESDE", "ESTATUS", "ULTIMA",
               "INTENSIDAD", "IMPORTE", "NETO", "REMANENTE", "MESES_FONDO", "PRIMA_BPS", "REPARTO_4S"]],
            hide_index=True, width="stretch", height=min(640, 40 + 35 * len(m)),
            column_config={
                "EMISORA": st.column_config.TextColumn("Emisora", pinned=True), "SECTOR": "Sector",
                "TIPO": "Tipo de mandato", "CASA_PRINCIPAL": "Casa principal",
                "PCT_PRINCIPAL": st.column_config.ProgressColumn("Peso principal", format="%.0f%%", min_value=0, max_value=100),
                "CASA_VIGENTE": "Casa vigente", "DESDE": st.column_config.DateColumn("Desde", format="DD/MM/YYYY"),
                "ESTATUS": "Estatus", "ULTIMA": st.column_config.DateColumn("Última operación", format="DD/MM/YYYY"),
                "INTENSIDAD": st.column_config.NumberColumn("Intensidad", format="%.0f%%",
                                                            help="Sesiones con recompra / sesiones del periodo"),
                "IMPORTE": st.column_config.NumberColumn("Importe (MXN M)", format="$%,.0f"),
                "NETO": st.column_config.NumberColumn("Neto (MXN M)", format="$%,.0f"),
                "REMANENTE": st.column_config.NumberColumn("Fondo remanente (M)", format="$%,.0f"),
                "MESES_FONDO": st.column_config.NumberColumn("Meses de fondo", format="%.1f",
                                                             help="Remanente / compras mensuales promedio de los últimos 3 meses"),
                "PRIMA_BPS": st.column_config.NumberColumn("Compra vs cierre (bps)", format="%+.1f"),
                "REPARTO_4S": st.column_config.TextColumn("Reparto 4 semanas", width="medium"),
            })
        st.caption("Exclusivo: ≥90% del importe con una casa · Principal + secundaria: 60–90% · Compartido: <60%. "
                   "Activo: operó en los últimos 30 días · En pausa: 31–120 · Inactivo: >120.")

    with t_cam:
        if an.cambios.empty:
            st.info("No se detectaron cambios de casa principal en el periodo.")
        else:
            cam = an.cambios.copy()
            cam["RESULTADO"] = cam.apply(lambda r: f"Ganó {destacada}" if r["A"] == destacada else
                                         (f"Perdió {destacada}" if r["DE"] == destacada else ""), axis=1)
            st.dataframe(cam, hide_index=True, width="stretch", column_config={
                "FECHA": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"), "EMISORA": "Emisora",
                "DE": "Casa anterior", "A": "Casa nueva",
                "SESIONES_PREVIA": st.column_config.NumberColumn("Sesiones casa anterior", format="%d"),
                "SESIONES_NUEVA": st.column_config.NumberColumn("Sesiones casa nueva", format="%d"),
                "IMPORTE_DESDE": st.column_config.NumberColumn("Importe con la nueva (M)", format="$%,.1f"),
                "RESULTADO": f"Para {destacada}"})
            st.caption("Cambio = la casa de mayor importe de cada sesión cambia durante un tramo consolidado; "
                       "las alternancias cortas de mandatos compartidos no cuentan.")

    with t_op:
        op = an.oportunidades
        a1, a2 = st.columns(2)
        with a1:
            st.markdown(f"**Emisoras activas sin {destacada}** · ordenadas por fondo disponible")
            st.dataframe(op["sin_destacada"][["EMISORA", "CASA_VIGENTE", "TIPO", "IMPORTE", "REMANENTE", "ULTIMA"]],
                         hide_index=True, width="stretch", height=360, column_config={
                             "IMPORTE": st.column_config.NumberColumn("Importe (M)", format="$%,.0f"),
                             "REMANENTE": st.column_config.NumberColumn("Fondo rem. (M)", format="$%,.0f"),
                             "ULTIMA": st.column_config.DateColumn("Última op.", format="DD/MM/YYYY")})
            st.markdown("**Mandatos en movimiento** · compartidos o con cambio reciente")
            st.dataframe(op["en_movimiento"][["EMISORA", "CASA_PRINCIPAL", "PCT_PRINCIPAL", "REPARTO_4S", "IMPORTE"]],
                         hide_index=True, width="stretch", height=320, column_config={
                             "PCT_PRINCIPAL": st.column_config.NumberColumn("Peso principal", format="%.0f%%"),
                             "IMPORTE": st.column_config.NumberColumn("Importe (M)", format="$%,.0f")})
        with a2:
            st.markdown("**Fondos disponibles sin operar** · 45+ días sin recompras")
            st.dataframe(op["fondos_sin_operar"][["EMISORA", "CASA_ULTIMA", "ULTIMA", "DIAS_SIN", "REMANENTE", "SECTOR"]],
                         hide_index=True, width="stretch", height=360, column_config={
                             "ULTIMA": st.column_config.DateColumn("Última op.", format="DD/MM/YYYY"),
                             "DIAS_SIN": st.column_config.NumberColumn("Días sin operar", format="%d"),
                             "REMANENTE": st.column_config.NumberColumn("Fondo rem. (M)", format="$%,.0f")})
            st.markdown(f"**Clientes actuales de {destacada}**")
            st.dataframe(op["clientes"], hide_index=True, width="stretch", height=320, column_config={
                "IMPORTE": st.column_config.NumberColumn("Importe (M)", format="$%,.1f"),
                "N_OPS": st.column_config.NumberColumn("Operaciones", format="%,d"),
                "PCT_IMPORTE": st.column_config.NumberColumn(f"Peso {destacada}", format="%.0f%%"),
                "ULTIMA": st.column_config.DateColumn("Última op.", format="DD/MM/YYYY"),
                "REMANENTE": st.column_config.NumberColumn("Fondo rem. (M)", format="$%,.0f")})

    with t_din:
        st.plotly_chart(_fig_mensual(an.mensual), width="stretch")

    with st.expander("¿Se puede saber con quién tiene contrato cada fondo de recompra?"):
        st.markdown(
            "No hay un registro público de los contratos entre emisoras y casas de bolsa para operar el fondo de "
            "recompra. Lo que sí es público es la **casa que ejecuta cada operación**, porque la emisora la reporta "
            "en cada aviso a la BMV. Con eso se infiere el mandato: **casa vigente** (aviso más reciente), "
            "**desde cuándo** la usa sin interrupción, el **tipo de mandato** (exclusivo, principal + secundaria o "
            "compartido) y los **cambios de casa principal**.")
