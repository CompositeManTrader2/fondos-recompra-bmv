"""Resumen de recompras del mercado: qué pasó hoy, qué cambió y dónde actuar."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from src import market_store, senales, theme as T, visualizations as viz

PUNTO = "PUNTO"
VENTANAS = {"1M": 31, "3M": 92, "6M": 183, "YTD": None, "1A": 365, "TODO": 100000}
DASHBOARD = "pages/2_📊_Dashboard.py"


def _estado_vacio():
    T.header("BUYB", "Resumen de recompras", "Todas las emisoras · BMV")
    st.info("Aún no hay datos de mercado. El scanner diario los genera (20:30 y 09:30 CDMX, lun–vie). "
            "Consulta **Estado del scanner** para ejecutarlo manualmente.")


resumen = market_store.resumen_diario()
if resumen.empty:
    _estado_vacio()
    st.stop()

estado = market_store.estado_scanner()
actividad = market_store.actividad()
fechas = sorted(resumen["FECHA"].unique(), reverse=True)
ult_run = estado.get("last_run_utc")
ult_txt = pd.Timestamp(ult_run).tz_convert(T.CDMX).strftime("%d-%b %H:%M").upper() if ult_run else "—"
T.header("BUYB", "Resumen de recompras", f"{resumen['EMISORA'].nunique()} emisoras con historial · BMV",
         derecha=f"Último scan {ult_txt} CDMX")

# Una sesión con muchas menos emisoras que lo habitual suele ser la del día en
# curso (reportes aún publicándose): se abre por defecto la última completa.
n_emis = resumen.groupby("FECHA")["EMISORA"].nunique().reindex(fechas)
mediana = n_emis.iloc[1:11].median() if len(n_emis) > 1 else n_emis.iloc[0]
parciales = {f for f in fechas[:2] if n_emis[f] < 0.5 * mediana}
idx_default = next((i for i, f in enumerate(fechas) if f not in parciales), 0)

c1, c2, c3 = st.columns([1.3, 2.2, 0.7])
fecha_ref = pd.Timestamp(c1.selectbox(
    "Sesión", fechas, index=idx_default,
    format_func=lambda f: pd.Timestamp(f).strftime("%a %d-%b-%Y") + ("  · parcial" if f in parciales else "")))
ventana = c2.segmented_control("Ventana de gráficas", list(VENTANAS), default="1M") or "1M"
if c3.button("Actualizar datos", icon=":material/refresh:", width="stretch"):
    market_store.limpiar_cache(); st.rerun()

if fecha_ref in parciales:
    st.warning("Sesión en curso: las emisoras siguen publicando sus reportes; las comparaciones contra el "
               "promedio no son representativas hasta el cierre del día.", icon=":material/schedule:")
desde = pd.Timestamp(fecha_ref.year, 1, 1) if ventana == "YTD" else fecha_ref - timedelta(days=VENTANAS[ventana])
win = resumen[(resumen["FECHA"] > desde) & (resumen["FECHA"] <= fecha_ref)]
dia = resumen[resumen["FECHA"] == fecha_ref].sort_values("IMPORTE", ascending=False)
m = senales.metricas(resumen, fecha_ref)
ses = [s for s in senales.sesiones(resumen) if s <= fecha_ref]
previas = ses[-21:-1]
tot_prev = resumen[resumen["FECHA"].isin(previas)].groupby("FECHA")["IMPORTE"].sum()

# ---- Cinta ----
T.ticker_tape([
    {"tk": f"{r.EMISORA} {r.SERIE if isinstance(r.SERIE, str) else ''}".strip(),
     "valor": f"{T.fmt_mxn(r.IMPORTE)} @ {r.VWAP:,.2f}",
     "extra": f"{T.fmt_num(abs((r.ACCIONES_COMPRA or 0) - (r.ACCIONES_VENTA or 0)))} acc",
     "dir": "up" if (r.ACCIONES_COMPRA or 0) >= (r.ACCIONES_VENTA or 0) else "dn"}
    for r in dia.head(40).itertuples()
])

# ---- Indicadores ----
imp = dia["IMPORTE"].sum()
d_imp = (imp / tot_prev.mean() - 1) * 100 if len(tot_prev) and tot_prev.mean() else None
prev_n = resumen[resumen["FECHA"] == ses[-2]]["EMISORA"].nunique() if len(ses) > 1 else None
top3 = dia["IMPORTE"].head(3).sum() / imp * 100 if imp else None
act_dia = actividad[actividad["FECHA_OPERACION"] == fecha_ref] if not actividad.empty else pd.DataFrame()
part_punto = (act_dia.loc[act_dia["CASA_BOLSA"] == PUNTO, "IMPORTE"].sum() / act_dia["IMPORTE"].sum() * 100
              if not act_dia.empty and act_dia["IMPORTE"].sum() else None)
T.tiles([
    {"label": "Emisoras recomprando", "value": f"{len(dia)}",
     "delta": f"{len(dia) - prev_n:+d} vs sesión previa" if prev_n is not None else None, "dir": T.dir_de(len(dia) - (prev_n or len(dia)))},
    {"label": "Importe de la sesión", "value": T.fmt_mxn(imp),
     "delta": f"{T.fmt_pct(d_imp)} vs prom. 20 ses." if d_imp is not None else None, "dir": T.dir_de(d_imp)},
    {"label": "Operaciones", "value": f"{int(dia['OPERACIONES'].sum()):,}", "sub": f"{T.fmt_num(dia['ACCIONES'].sum())} acciones"},
    {"label": "Concentración top 3", "value": f"{top3:.0f}%" if top3 is not None else "—",
     "sub": ", ".join(dia["EMISORA"].head(3))},
    {"label": "Participación Punto", "value": f"{part_punto:.1f}%" if part_punto is not None else "—",
     "sub": "del importe ejecutado en la sesión"},
    {"label": f"Importe {ventana}", "value": T.fmt_mxn(win["IMPORTE"].sum()),
     "sub": f"{win['FECHA'].nunique()} sesiones · {win['EMISORA'].nunique()} emisoras"},
])

# ---- Señales ----
T.seccion("Señales de la sesión", "qué cambió respecto al comportamiento habitual de cada emisora")
T.senales(senales.tarjetas(m, len(ses)))

# ---- Tablero ----
T.seccion("Tablero de emisoras", "clic en una fila para abrir su dashboard")
solo_hoy = st.toggle("Solo emisoras que recompraron en la sesión", value=True)
tab = m[m["IMPORTE_DIA"] > 0] if solo_hoy else m
tab = tab.replace([np.inf, -np.inf], np.nan)
cols = ["EMISORA", "SERIE", "IMPORTE_DIA", "INTENSIDAD", "ACELERACION", "RACHA", "PCT_VOL_DIA", "PRIMA_DIA",
        "IMPORTE_20", "PCT_CIRC_20", "REMANENTE", "RUNWAY", "CASA", "SIN_RECOMPRA"]
ev = st.dataframe(
    tab[cols], hide_index=True, width="stretch", height=min(620, 40 + 35 * max(len(tab), 1)),
    on_select="rerun", selection_mode="single-row", key="tablero",
    column_config={
        "EMISORA": st.column_config.TextColumn("Emisora", pinned=True),
        "SERIE": st.column_config.TextColumn("Serie", width="small"),
        "IMPORTE_DIA": st.column_config.NumberColumn("Importe sesión", format="$%,.0f"),
        "INTENSIDAD": st.column_config.NumberColumn("× prom. 20", format="%.1f×",
                                                    help="Importe de la sesión / promedio de sus 20 sesiones previas"),
        "ACELERACION": st.column_config.NumberColumn("Aceleración", format="%.1f×",
                                                     help="Ritmo de 5 sesiones / ritmo de 20 sesiones"),
        "RACHA": st.column_config.NumberColumn("Racha", format="%d ses.", help="Sesiones consecutivas recomprando"),
        "PCT_VOL_DIA": st.column_config.NumberColumn("% del volumen", format="%.1f%%",
                                                     help="Acciones recompradas / volumen operado en el mercado (Yahoo)"),
        "PRIMA_DIA": st.column_config.NumberColumn("vs cierre", format="%+.2f%%",
                                                   help="VWAP de compra vs precio de cierre del día"),
        "IMPORTE_20": st.column_config.NumberColumn("Importe 20 ses.", format="$%,.0f"),
        "PCT_CIRC_20": st.column_config.NumberColumn("% circulación 20s", format="%.3f%%",
                                                     help="Acciones recompradas en 20 sesiones / acciones en circulación"),
        "REMANENTE": st.column_config.NumberColumn("Remanente fondo", format="$%,.0f"),
        "RUNWAY": st.column_config.NumberColumn("Fondo para", format="%.0f ses.",
                                                help="Sesiones de remanente al ritmo de las últimas 20"),
        "CASA": st.column_config.TextColumn("Casa principal"),
        "SIN_RECOMPRA": st.column_config.NumberColumn("Sesiones sin recomprar", format="%d"),
    },
)
if ev and ev.selection and ev.selection.rows:
    st.session_state["ticker_activo"] = tab.iloc[ev.selection.rows[0]]["EMISORA"]
    st.switch_page(DASHBOARD)

with st.expander("Cómo leer el tablero"):
    st.markdown(
        "- **× prom. 20**: cuántas veces el importe de hoy supera su promedio reciente. >2.5× = actividad inusual.\n"
        "- **Aceleración**: el ritmo de la última semana contra el del último mes. >1.5× = la empresa está acelerando.\n"
        "- **% del volumen**: qué parte del volumen del mercado fue la propia empresa comprando — soporte de demanda.\n"
        "- **vs cierre**: negativo = compró por debajo del cierre (disciplina de precio); positivo = pagó prima.\n"
        "- **Fondo para**: sesiones que le alcanzan al remanente al ritmo actual. Pocas sesiones = la demanda puede "
        "desaparecer pronto (o viene una ampliación del fondo en asamblea).\n"
        "- Los precios y volúmenes de mercado vienen de Yahoo Finance; si Yahoo no responde, esas columnas quedan vacías."
    )

# ---- Emisoras × casas de bolsa ----
PERIODOS_CASAS = {"3M": 92, "6M": 183, "YTD": None, "1 año": 365, "2 años": 730, "Personalizado": 0}


@st.cache_data(show_spinner=False, max_entries=16)
def _casas_periodo(ini, fin, medida: str, version: str):
    from src import emisoras_casas as ec
    act = market_store.actividad()
    tab, cols = ec.matriz(act, ini, fin, medida)
    return tab, cols, ec.resumen_casas(act, ini, fin), ec.detalle(act, ini, fin)


@st.cache_data(show_spinner=False, max_entries=8)
def _casas_descargas(ini, fin, medida: str, version: str):
    from src import emisoras_casas as ec
    tab, cols, casas, det = _casas_periodo(ini, fin, medida, version)
    return ec.pdf_bytes(tab, cols, casas, ini, fin, medida), ec.excel_bytes(tab, cols, det, casas, ini, fin, medida)


@st.fragment
def seccion_casas():
    from src import emisoras_casas as ec
    T.seccion("Emisoras y casas de bolsa", "con quién opera cada fondo de recompra y qué peso tiene cada casa")
    if actividad.empty:
        st.info("Aún no hay tabla de actividad.")
        return
    ult = actividad["FECHA_OPERACION"].max().date()
    c1, c2, c3 = st.columns([2.2, 1.6, 1.4])
    per = c1.segmented_control("Periodo", list(PERIODOS_CASAS), default="1 año", key="casas_periodo") or "1 año"
    if per == "Personalizado":
        rango = c3.date_input("Rango", (ult - timedelta(days=365), ult), max_value=ult, format="DD/MM/YYYY",
                              key="casas_rango")
        if not isinstance(rango, (list, tuple)) or len(rango) != 2:
            st.caption("Elige la fecha final del rango.")
            return
        ini, fin = rango
    else:
        fin = ult
        ini = date(ult.year, 1, 1) if per == "YTD" else ult - timedelta(days=PERIODOS_CASAS[per])
    medida = c2.segmented_control("Ponderar por", list(ec.MEDIDAS), default="IMPORTE", key="casas_medida",
                                  format_func=lambda m: {"IMPORTE": "Importe", "N_OPS": "Operaciones"}[m]) or "IMPORTE"
    version = f"{len(actividad)}-{ult:%Y%m%d}"
    tab, cols, casas, det = _casas_periodo(ini, fin, medida, version)
    if tab.empty:
        st.info("Sin operaciones en el periodo elegido.")
        return

    compartidas = int((tab["N_CASAS"] > 1).sum())
    T.tiles([
        {"label": "Emisoras con recompras", "value": f"{len(tab)}", "sub": f"{ini:%d/%m/%Y} – {fin:%d/%m/%Y}"},
        {"label": "Casas de bolsa activas", "value": f"{len(casas)}",
         "sub": ", ".join(casas["CASA_BOLSA"].head(3))},
        {"label": "Emisoras con más de una casa", "value": f"{compartidas}",
         "sub": f"{100 * compartidas / len(tab):.0f}% de las emisoras"},
        {"label": "Casa líder", "value": casas["CASA_BOLSA"].iat[0],
         "sub": f"{casas['PART_IMPORTE'].iat[0]:.1f}% del importe · {casas['EMISORAS'].iat[0]} emisoras"},
    ])

    vista = tab[["EMISORA", "IMPORTE", "N_OPS", "N_CASAS", "CASA_VIGENTE", "DESDE", "REPARTO_4S"] + cols]
    # Celdas de casas como texto ("62%") y color proporcional a la ponderación (lavanda → morado Punto).
    disp = vista.copy()
    disp[cols] = vista[cols].map(lambda v: "" if pd.isna(v) or v <= 0 else ("<1%" if v < 1 else f"{v:.0f}%"))
    css = pd.DataFrame("", index=vista.index, columns=vista.columns)
    css[cols] = vista[cols].map(_css_celda)
    estilo = disp.style.apply(lambda _: css, axis=None)
    st.dataframe(
        estilo, hide_index=True, width="stretch", height=min(640, 40 + 35 * len(vista)),
        column_config={
            "EMISORA": st.column_config.TextColumn("Emisora", pinned=True),
            "IMPORTE": st.column_config.NumberColumn("Importe operado (MXN M)", format="$%,.1f",
                                                     help="Compras + ventas del fondo en el periodo"),
            "N_OPS": st.column_config.NumberColumn("Operaciones", format="%,d"),
            "N_CASAS": st.column_config.NumberColumn("Casas", format="%d"),
            "CASA_VIGENTE": st.column_config.TextColumn("Casa vigente", help="Casa del aviso más reciente de la emisora"),
            "DESDE": st.column_config.DateColumn("Opera con ella desde", format="DD/MM/YYYY",
                                                 help="Desde cuándo usa ininterrumpidamente la casa vigente"),
            "REPARTO_4S": st.column_config.TextColumn("Reparto últimas 4 semanas", width="medium"),
            **{c: st.column_config.Column(c, help=ec.nombre(c), width="small") for c in cols},
        },
    )
    st.caption(f"Celdas = % del {ec.MEDIDAS[medida].lower()} de cada emisora ejecutado con cada casa. "
               "Casas fuera de las 12 principales del periodo se agrupan en OTRAS.")

    pdf, xlsx = _casas_descargas(ini, fin, medida, version)
    d1, d2, _ = st.columns([1, 1, 2])
    d1.download_button("Descargar PDF", pdf, file_name=f"Emisoras_casas_{ini:%Y%m%d}_{fin:%Y%m%d}.pdf",
                       mime="application/pdf", icon=":material/picture_as_pdf:", type="primary", width="stretch")
    d2.download_button("Descargar Excel", xlsx, file_name=f"Emisoras_casas_{ini:%Y%m%d}_{fin:%Y%m%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       icon=":material/table_view:", width="stretch")

    with st.expander("¿Se puede saber con quién tiene contrato cada fondo de recompra?"):
        st.markdown(
            "No hay un registro público de los contratos entre emisoras y casas de bolsa para operar el fondo de "
            "recompra. Lo que sí es público es la **casa que ejecuta cada operación**, porque la emisora la debe "
            "reportar en cada aviso a la BMV. Por eso esta tabla muestra:\n"
            "- **Casa vigente**: la del aviso más reciente, que en la práctica es la que tiene el mandato hoy.\n"
            "- **Opera con ella desde**: cuándo empezó a usarla sin interrupción. Un cambio reciente suele indicar "
            "un mandato nuevo.\n"
            "- **Reparto últimas 4 semanas**: si la emisora reparte entre varias casas, el mandato es compartido.")


def _css_celda(v) -> str:
    """Fondo interpolado entre lavanda (#F7F2FB) y morado Punto (#7030A0) según el % (0–100)."""
    if pd.isna(v) or v <= 0:
        return ""
    k = min(float(v), 100) / 100
    a, b = (0xF7, 0xF2, 0xFB), (0x70, 0x30, 0xA0)
    r, g, bl = (round(x + (y - x) * k) for x, y in zip(a, b))
    texto = "#FFFFFF" if k > 0.55 else "#1F1A26"
    return f"background-color: #{r:02X}{g:02X}{bl:02X}; color: {texto}"


seccion_casas()

# ---- Gráficas ----
izq, der = st.columns([1, 1.35])
with izq:
    T.seccion("Distribución de la sesión")
    st.plotly_chart(viz.grafica_treemap_emisoras(dia), width="stretch")
with der:
    reciente = resumen[resumen["FECHA"] > resumen["FECHA"].max() - timedelta(days=90)]
    colores = T.colores_emisoras(reciente.groupby("EMISORA")["IMPORTE"].sum().sort_values(ascending=False).index.tolist())
    T.seccion("Recompras del mercado", f"ventana {ventana}")
    st.plotly_chart(viz.grafica_mercado_diario(win, colores), width="stretch")

T.seccion("Mapa de calor emisora × sesión")
st.plotly_chart(viz.grafica_heatmap_emisoras(win, top=25, dias=30), width="stretch")
