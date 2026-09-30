"""
BUYB <GO> — Monitor de recompras de la Bolsa Mexicana de Valores.

Actividad de fondos de recompra de TODAS las emisoras, alimentada por el
scanner diario (GitHub Actions → data/daily/). Se ejecuta vía el router
`app.py` (st.navigation).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from src import github_storage, market_store, theme as T, visualizations as viz

REPO_DEFAULT = "CompositeManTrader2/fondos-recompra-bmv"
VENTANAS = {"5D": 7, "1M": 31, "3M": 92, "6M": 183, "YTD": None, "1A": 365, "TODO": 100000}


def _repo() -> str:
    return (github_storage.config_info() or {}).get("repo") or REPO_DEFAULT


# ---------------------------------------------------------------------------
# Estado vacío (antes de la primera corrida del scanner)
# ---------------------------------------------------------------------------

def _pantalla_vacia():
    T.header("BUYB", "Recompras BMV", "Monitor de mercado")
    url = f"https://github.com/{_repo()}/actions/workflows/daily_scan.yml"
    st.markdown(
        f"""
        ### Aún no hay datos de mercado
        El monitor se alimenta del **scanner diario** que corre en GitHub Actions
        (20:30 y 09:30 CDMX, lun–vie) y descarga las recompras de **todas** las emisoras.

        1. Abre el workflow: [{url}]({url})
        2. **Run workflow** → deja *seed_id* vacío para una primera corrida (≈ últimas 2 semanas),
           o pon un ID antiguo (ej. `1540000` ≈ mar-2026) para un backfill histórico.
        3. Al terminar, vuelve aquí y presiona **↻ Recargar**.
        """
    )
    if st.button("↻ Recargar", type="primary"):
        market_store.limpiar_cache(); st.rerun()


# ---------------------------------------------------------------------------
# Cálculos
# ---------------------------------------------------------------------------

def _agregar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.assign(PV=df["VWAP"] * df["ACCIONES"]).groupby("EMISORA").agg(
        IMPORTE=("IMPORTE", "sum"), OPERACIONES=("OPERACIONES", "sum"), ACCIONES=("ACCIONES", "sum"),
        PV=("PV", "sum"), DIAS=("FECHA", "nunique"), ULTIMA=("FECHA", "max"),
        COMPRA=("ACCIONES_COMPRA", "sum"), VENTA=("ACCIONES_VENTA", "sum"),
    ).reset_index()
    g["VWAP"] = g["PV"] / g["ACCIONES"].where(g["ACCIONES"] > 0)
    g["NETO"] = g["COMPRA"] - g["VENTA"]
    return g.drop(columns="PV").sort_values("IMPORTE", ascending=False)


def _ir_a_dashboard(emisora: str):
    st.session_state["ticker_activo"] = emisora
    st.switch_page("pages/2_📊_Dashboard.py")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    resumen = market_store.resumen_diario()
    estado = market_store.estado_scanner()
    if resumen.empty:
        _pantalla_vacia()
        return

    fechas = sorted(resumen["FECHA"].unique(), reverse=True)
    ult_run = estado.get("last_run_utc")
    ult_run_txt = (pd.Timestamp(ult_run).tz_convert(T.CDMX).strftime("%d-%b %H:%M").upper()
                   if ult_run else "—")
    T.header("BUYB", "Recompras BMV", "Monitor de mercado · todas las emisoras",
             derecha=f"ÚLT. SCAN {ult_run_txt} CDMX &nbsp;·&nbsp; <span class='live'>●</span> "
                     f"{resumen['EMISORA'].nunique()} EMISORAS")

    c1, c2, c3 = st.columns([1.2, 2.2, 0.6])
    fecha_ref = c1.selectbox("Fecha", fechas, format_func=lambda f: pd.Timestamp(f).strftime("%a %d-%b-%Y").upper())
    ventana = c2.segmented_control("Ventana", list(VENTANAS), default="1M") or "1M"
    if c3.button("↻ Recargar", width="stretch"):
        market_store.limpiar_cache(); st.rerun()

    fecha_ref = pd.Timestamp(fecha_ref)
    desde = (pd.Timestamp(fecha_ref.year, 1, 1) if ventana == "YTD"
             else fecha_ref - timedelta(days=VENTANAS[ventana]))
    win = resumen[(resumen["FECHA"] > desde) & (resumen["FECHA"] <= fecha_ref)]
    dia = resumen[resumen["FECHA"] == fecha_ref].sort_values("IMPORTE", ascending=False)
    previas = [f for f in fechas if pd.Timestamp(f) < fecha_ref]
    prev = resumen[resumen["FECHA"] == pd.Timestamp(previas[0])] if previas else pd.DataFrame(columns=resumen.columns)
    tot_20 = resumen[resumen["FECHA"].isin(previas[:20])].groupby("FECHA")["IMPORTE"].sum()

    # Color por emisora: orden estable = ranking histórico (no cambia con la ventana)
    orden_hist = resumen.groupby("EMISORA")["IMPORTE"].sum().sort_values(ascending=False).index.tolist()
    colores = T.colores_emisoras(orden_hist)

    # ---- Cinta ----
    T.ticker_tape([
        {"tk": r.EMISORA, "valor": f"{T.fmt_mxn(r.IMPORTE)} @ {r.VWAP:,.2f}",
         "extra": f"{T.fmt_num(abs((r.ACCIONES_COMPRA or 0) - (r.ACCIONES_VENTA or 0)))} acc",
         "dir": "up" if (r.ACCIONES_COMPRA or 0) >= (r.ACCIONES_VENTA or 0) else "dn"}
        for r in dia.head(40).itertuples()
    ])

    # ---- Tiles ----
    imp_dia = dia["IMPORTE"].sum()
    d_imp = (imp_dia / tot_20.mean() - 1) * 100 if len(tot_20) else None
    d_emis = len(dia) - len(prev)
    top = dia.iloc[0] if not dia.empty else None
    T.tiles([
        {"label": "Emisoras recomprando", "value": f"{len(dia)}",
         "delta": f"{d_emis:+d} vs sesión previa" if len(prev) else None, "dir": T.dir_de(d_emis)},
        {"label": "Importe del día", "value": T.fmt_mxn(imp_dia),
         "delta": f"{T.fmt_pct(d_imp)} vs prom. 20D" if d_imp is not None else None, "dir": T.dir_de(d_imp)},
        {"label": "Operaciones", "value": f"{int(dia['OPERACIONES'].sum()):,}"},
        {"label": "Acciones", "value": T.fmt_num(dia["ACCIONES"].sum())},
        {"label": f"Importe {ventana}", "value": T.fmt_mxn(win["IMPORTE"].sum()),
         "sub": f"{win['FECHA'].nunique()} sesiones · {win['EMISORA'].nunique()} emisoras"},
        {"label": "Top del día", "value": top["EMISORA"] if top is not None else "—",
         "sub": f"{T.fmt_mxn(top['IMPORTE'])} · {top['IMPORTE'] / imp_dia:.0%} del día" if top is not None and imp_dia else None},
    ])

    tab_mon, tab_hist, tab_rank, tab_scan = st.tabs(["Monitor", "Historial", "Rankings", "Scanner"])

    # ===================== MONITOR =====================
    with tab_mon:
        izq, der = st.columns([1.35, 1])
        with izq:
            T.seccion("Recompras de la sesión", f"{pd.Timestamp(fecha_ref):%d-%b-%Y} · clic en una fila → dashboard")
            tabla = dia.assign(
                PCT=dia["IMPORTE"] / imp_dia * 100 if imp_dia else 0,
                NETO=dia["ACCIONES_COMPRA"].fillna(0) - dia["ACCIONES_VENTA"].fillna(0),
            )[["EMISORA", "IMPORTE", "PCT", "OPERACIONES", "ACCIONES", "VWAP", "NETO", "N_CASAS", "REMANENTE_PRESENTE"]]
            ev = st.dataframe(
                tabla, hide_index=True, width="stretch", height=min(560, 38 + 35 * len(tabla)),
                on_select="rerun", selection_mode="single-row", key="tabla_dia",
                column_config={
                    "EMISORA": st.column_config.TextColumn("EMISORA", width="small"),
                    "IMPORTE": st.column_config.NumberColumn("IMPORTE", format="$%,.0f"),
                    "PCT": st.column_config.ProgressColumn("% DÍA", format="%.1f%%", min_value=0, max_value=100),
                    "OPERACIONES": st.column_config.NumberColumn("OPS", format="%,d"),
                    "ACCIONES": st.column_config.NumberColumn("ACCIONES", format="%,.0f"),
                    "VWAP": st.column_config.NumberColumn("VWAP", format="$%.4f"),
                    "NETO": st.column_config.NumberColumn("NETO ACC", format="%+,.0f",
                                                          help="Acciones compradas − vendidas"),
                    "N_CASAS": st.column_config.NumberColumn("CASAS", format="%,d"),
                    "REMANENTE_PRESENTE": st.column_config.NumberColumn("REMANENTE", format="$%,.0f",
                                                                        help="Recursos restantes del fondo"),
                },
            )
            if ev and ev.selection and ev.selection.rows:
                _ir_a_dashboard(tabla.iloc[ev.selection.rows[0]]["EMISORA"])
        with der:
            T.seccion("Distribución del día")
            st.plotly_chart(viz.grafica_treemap_emisoras(dia), width="stretch")

        T.seccion("Actividad del mercado", f"ventana {ventana}")
        st.plotly_chart(viz.grafica_mercado_diario(win, colores), width="stretch")

        T.seccion("Mapa de calor emisora × sesión")
        st.plotly_chart(viz.grafica_heatmap_emisoras(win, top=25, dias=30), width="stretch")

    # ===================== HISTORIAL =====================
    with tab_hist:
        agg_win = _agregar(win)
        emis_disp = sorted(resumen["EMISORA"].unique())
        h1, h2 = st.columns([2, 1])
        sel = h1.multiselect("Emisoras (máx. 8 en la gráfica)", emis_disp,
                             default=agg_win["EMISORA"].head(5).tolist())
        rango = h2.date_input("Rango", value=(desde.date() + timedelta(days=1), fecha_ref.date()),
                              min_value=resumen["FECHA"].min().date(), max_value=resumen["FECHA"].max().date())
        if isinstance(rango, tuple) and len(rango) == 2:
            h = resumen[(resumen["FECHA"] >= pd.Timestamp(rango[0])) & (resumen["FECHA"] <= pd.Timestamp(rango[1]))]
        else:
            h = win
        if sel:
            h = h[h["EMISORA"].isin(sel)]
            st.plotly_chart(viz.grafica_acumulado_emisoras(h, sel), width="stretch")
        st.dataframe(
            h.sort_values(["FECHA", "IMPORTE"], ascending=[False, False]), hide_index=True, width="stretch",
            column_config={
                "FECHA": st.column_config.DateColumn("FECHA", format="DD-MMM-YYYY"),
                "IMPORTE": st.column_config.NumberColumn("IMPORTE", format="$%,.0f"),
                "VWAP": st.column_config.NumberColumn("VWAP", format="$%.4f"),
                "VWAP_COMPRA": st.column_config.NumberColumn("VWAP C", format="$%.4f"),
                "VWAP_VENTA": st.column_config.NumberColumn("VWAP V", format="$%.4f"),
                "PRECIO_MIN": st.column_config.NumberColumn("MÍN", format="$%.4f"),
                "PRECIO_MAX": st.column_config.NumberColumn("MÁX", format="$%.4f"),
                "REMANENTE_PRESENTE": st.column_config.NumberColumn("REMANENTE", format="$%,.0f"),
            },
        )
        st.download_button("⬇ Descargar historial (CSV)", h.to_csv(index=False).encode("utf-8"),
                           file_name=f"recompras_bmv_{datetime.now():%Y%m%d}.csv", mime="text/csv")

    # ===================== RANKINGS =====================
    with tab_rank:
        agg_win = _agregar(win)
        r1, r2 = st.columns([1, 1])
        with r1:
            metrica = st.segmented_control("Métrica", ["IMPORTE", "OPERACIONES", "ACCIONES", "DIAS"],
                                           default="IMPORTE", key="rank_met") or "IMPORTE"
            st.plotly_chart(viz.grafica_ranking_emisoras(agg_win, metrica=metrica, top=15), width="stretch")
        with r2:
            T.seccion(f"Tabla {ventana}", f"{len(agg_win)} emisoras")
            st.dataframe(
                agg_win[["EMISORA", "IMPORTE", "OPERACIONES", "ACCIONES", "VWAP", "NETO", "DIAS", "ULTIMA"]],
                hide_index=True, width="stretch", height=520,
                column_config={
                    "IMPORTE": st.column_config.NumberColumn("IMPORTE", format="$%,.0f"),
                    "ACCIONES": st.column_config.NumberColumn("ACCIONES", format="%,.0f"),
                    "VWAP": st.column_config.NumberColumn("VWAP", format="$%.4f"),
                    "NETO": st.column_config.NumberColumn("NETO ACC", format="%+,.0f"),
                    "DIAS": st.column_config.NumberColumn("SESIONES", format="%,d"),
                    "ULTIMA": st.column_config.DateColumn("ÚLTIMA", format="DD-MMM-YY"),
                },
            )
        primera = resumen.groupby("EMISORA")["FECHA"].min()
        nuevas = primera[(primera > desde) & (primera <= fecha_ref)].sort_values(ascending=False)
        T.seccion("Emisoras que empezaron a recomprar en la ventana", f"{len(nuevas)}")
        if len(nuevas):
            st.markdown(" ".join(T.pill(f"{e} · {f:%d-%b}", "warn") for e, f in nuevas.items()),
                        unsafe_allow_html=True)
        else:
            st.caption("Ninguna (según el historial disponible).")

    # ===================== SCANNER =====================
    with tab_scan:
        url = f"https://github.com/{_repo()}/actions/workflows/daily_scan.yml"
        runs = pd.DataFrame(estado.get("runs", []))
        T.tiles([
            {"label": "Última corrida", "value": ult_run_txt},
            {"label": "Último ID BMV", "value": f"{int(estado.get('last_hit_id') or 0):,}"},
            {"label": "Ventana frontera", "value": f"{int(estado.get('frontier_gap') or 0):,} IDs"},
            {"label": "Documentos en registro", "value": f"{len(market_store.documentos()):,}"},
        ])
        st.markdown(f"Programado **20:30** y **09:30 CDMX** (lun–vie). Ejecución manual / backfill: [{url}]({url})")
        if not runs.empty:
            runs["emisoras"] = runs["emisoras"].map(lambda e: len(e) if isinstance(e, list) else e)
            st.dataframe(runs[[c for c in ["utc", "inicio_id", "fin_id", "ids_revisados", "docs_nuevos", "ops_nuevas",
                                           "emisoras", "errores_red", "duracion_s", "abortado"] if c in runs]],
                         hide_index=True, width="stretch")
        docs = market_store.documentos()
        if not docs.empty:
            T.seccion("Documentos más recientes")
            st.dataframe(
                docs.sort_values("ID", ascending=False).head(200)[
                    ["ID", "EMISORA", "FECHA_OPERACION", "CASA_BOLSA", "N_OPS", "IMPORTE", "ESTADO", "URL"]],
                hide_index=True, width="stretch",
                column_config={
                    "FECHA_OPERACION": st.column_config.DateColumn("FECHA", format="DD-MMM-YY"),
                    "IMPORTE": st.column_config.NumberColumn("IMPORTE", format="$%,.0f"),
                    "URL": st.column_config.LinkColumn("PDF", display_text="abrir"),
                },
            )


main()
