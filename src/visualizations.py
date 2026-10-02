"""
Gráficas Plotly con la identidad de Punto Casa de Bolsa (template de src/theme.py).

Reglas que se cumplen en todo el módulo:
  - Nunca doble eje Y: dos medidas de escala distinta van en paneles
    apilados con eje X compartido (precio arriba, volumen abajo).
  - Ejes diarios sin fines de semana (rangebreaks sat→mon).
  - Color por entidad con orden fijo; más de 7 entidades → "OTRAS" neutro.
  - Compra/venta siempre con ▲/▼ además del color.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src import theme as T

MERCADO = "#3F3947"   # línea de referencia (precio de mercado): neutro oscuro
VOLUMEN = T.CATEGORICA[1]
NEUTRO_BAR = T.GRAY_BRAND


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sin_fines(fig: go.Figure) -> go.Figure:
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


def _base(fig: go.Figure, titulo: str, alto: int = 440, leyenda: bool = True) -> go.Figure:
    fig.update_layout(title=dict(text=titulo.upper()), height=alto, showlegend=leyenda, template=T.TEMPLATE)
    return fig


def _vacio(msg: str = "Sin datos", alto: int = 260) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(color=T.MUTED, size=12))
    fig.update_xaxes(visible=False); fig.update_yaxes(visible=False)
    return _base(fig, "", alto, leyenda=False)


def _doble_panel(alturas=(0.64, 0.36)) -> go.Figure:
    return make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.035, row_heights=list(alturas))


def _barras_kw() -> dict:
    # 2px de separación de superficie entre barras / segmentos apilados
    return dict(marker_line_color=T.PANEL, marker_line_width=1)


# ---------------------------------------------------------------------------
# Emisora individual
# ---------------------------------------------------------------------------

def grafica_actividad_diaria(diarios: pd.DataFrame, metrica: str = "OPERACIONES",
                             incluir_vwap_lados: bool = True) -> go.Figure:
    """Panel superior: VWAP (+ compra/venta y banda mín–máx). Inferior: métrica de volumen."""
    if diarios is None or diarios.empty:
        return _vacio()
    d = diarios.sort_values("FECHA").copy()
    x = pd.to_datetime(d["FECHA"])
    fig = _doble_panel()

    if {"PRECIO_MIN", "PRECIO_MAX"} <= set(d.columns):
        fig.add_trace(go.Scatter(x=x, y=d["PRECIO_MAX"], mode="lines", line=dict(width=0),
                                 hoverinfo="skip", showlegend=False), 1, 1)
        fig.add_trace(go.Scatter(x=x, y=d["PRECIO_MIN"], mode="lines", line=dict(width=0),
                                 fill="tonexty", fillcolor=T.RANGO_FILL, name="Rango mín–máx",
                                 hovertemplate="Mín $%{y:,.4f}<extra></extra>"), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=d["VWAP"], name="VWAP", mode="lines+markers",
                             line=dict(color=T.SERIE_1, width=2), marker=dict(size=5),
                             hovertemplate="VWAP $%{y:,.4f}<extra></extra>"), 1, 1)
    if incluir_vwap_lados:
        if "VWAP_COMPRA" in d and d["VWAP_COMPRA"].notna().any():
            fig.add_trace(go.Scatter(x=x, y=d["VWAP_COMPRA"], name="▲ VWAP compra", mode="markers",
                                     marker=dict(symbol="triangle-up", size=8, color=T.COMPRA),
                                     hovertemplate="▲ Compra $%{y:,.4f}<extra></extra>"), 1, 1)
        if "VWAP_VENTA" in d and d["VWAP_VENTA"].notna().any():
            fig.add_trace(go.Scatter(x=x, y=d["VWAP_VENTA"], name="▼ VWAP venta", mode="markers",
                                     marker=dict(symbol="triangle-down", size=8, color=T.VENTA),
                                     hovertemplate="▼ Venta $%{y:,.4f}<extra></extra>"), 1, 1)

    fmt = {"IMPORTE": "$,.0f"}.get(metrica, ",.0f")
    fig.add_trace(go.Bar(x=x, y=d[metrica], name=metrica.title(), marker_color=VOLUMEN, **_barras_kw(),
                         hovertemplate=metrica.title() + " %{y:" + fmt + "}<extra></extra>"), 2, 1)
    fig.update_yaxes(title_text="PRECIO", tickprefix="$", row=1, col=1)
    fig.update_yaxes(title_text=metrica, tickformat="~s", row=2, col=1)
    titulo = {"OPERACIONES": "VWAP y ejecuciones diarias", "ACCIONES": "VWAP y acciones recompradas",
              "IMPORTE": "VWAP e importe diario"}.get(metrica, metrica)
    return _sin_fines(_base(fig, titulo, 520))


def grafica_actividad_mensual(mensuales: pd.DataFrame) -> go.Figure:
    if mensuales is None or mensuales.empty:
        return _vacio()
    m = mensuales.sort_values("MES")
    x = pd.to_datetime(m["MES"]).dt.strftime("%b-%y").str.upper()   # categórico: sin huecos
    fig = _doble_panel((0.5, 0.5))
    fig.add_trace(go.Scatter(x=x, y=m["VWAP"], name="VWAP", mode="lines+markers",
                             line=dict(color=T.SERIE_1, width=2), marker=dict(size=8),
                             hovertemplate="VWAP $%{y:,.4f}<extra></extra>"), 1, 1)
    fig.add_trace(go.Bar(x=x, y=m["IMPORTE"], name="Importe", marker_color=VOLUMEN, **_barras_kw(),
                         hovertemplate="Importe $%{y:,.0f}<extra></extra>"), 2, 1)
    fig.update_yaxes(title_text="VWAP", tickprefix="$", row=1, col=1)
    fig.update_yaxes(title_text="IMPORTE", tickprefix="$", tickformat="~s", row=2, col=1)
    return _base(fig, "VWAP e importe mensual", 460)


def grafica_acumulado(diarios: pd.DataFrame) -> go.Figure:
    if diarios is None or diarios.empty:
        return _vacio()
    d = diarios.sort_values("FECHA").copy()
    netas = d.get("ACCIONES_COMPRA", d["ACCIONES"]).fillna(0) - d.get("ACCIONES_VENTA", 0 * d["ACCIONES"]).fillna(0)
    x = pd.to_datetime(d["FECHA"])
    fig = _doble_panel((0.5, 0.5))
    fig.add_trace(go.Scatter(x=x, y=netas.cumsum(), name="Acciones netas acumuladas", mode="lines",
                             line=dict(color=T.SERIE_1, width=2), fill="tozeroy",
                             fillcolor="rgba(112,48,160,0.14)",
                             hovertemplate="Netas %{y:,.0f}<extra></extra>"), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=d["IMPORTE"].fillna(0).cumsum(), name="Importe acumulado", mode="lines",
                             line=dict(color=T.SERIE_2, width=2),
                             hovertemplate="Importe $%{y:,.0f}<extra></extra>"), 2, 1)
    fig.update_yaxes(title_text="ACCIONES", tickformat="~s", row=1, col=1)
    fig.update_yaxes(title_text="MXN", tickprefix="$", tickformat="~s", row=2, col=1)
    return _sin_fines(_base(fig, "Posición acumulada del fondo", 480))


def grafica_vwap_rolling(diarios: pd.DataFrame, ventanas: tuple[int, ...] = (5, 10, 20)) -> go.Figure:
    if diarios is None or diarios.empty or "VWAP" not in diarios:
        return _vacio()
    d = diarios.sort_values("FECHA")
    x = pd.to_datetime(d["FECHA"])
    pv, acc = d["VWAP"] * d["ACCIONES"].fillna(0), d["ACCIONES"].fillna(0)
    fig = go.Figure(go.Scatter(x=x, y=d["VWAP"], name="VWAP diario", mode="lines",
                               line=dict(color=T.TEXT_2, width=1), opacity=0.7,
                               hovertemplate="VWAP $%{y:,.4f}<extra></extra>"))
    for i, w in enumerate(ventanas):
        if len(d) >= w:
            roll = pv.rolling(w).sum() / acc.rolling(w).sum().replace(0, np.nan)
            fig.add_trace(go.Scatter(x=x, y=roll, name=f"VWAP {w}D", mode="lines",
                                     line=dict(color=T.CATEGORICA[i], width=2),
                                     hovertemplate=f"VWAP {w}D $%{{y:,.4f}}<extra></extra>"))
    fig.update_yaxes(tickprefix="$")
    return _sin_fines(_base(fig, "VWAP diario y medias móviles ponderadas", 420))


def grafica_dispersion_intradia(df_ops: pd.DataFrame, max_dias: int = 60) -> go.Figure:
    if df_ops is None or df_ops.empty:
        return _vacio()
    d = df_ops.copy()
    d["FECHA"] = pd.to_datetime(d["FECHA_OPERACION"]).dt.normalize()
    dias = sorted(d["FECHA"].unique())[-max_dias:]
    d = d[d["FECHA"].isin(dias)]
    fig = go.Figure(go.Box(x=d["FECHA"], y=d["PRECIO_UNITARIO"], name="Precio", boxpoints="outliers",
                           marker=dict(color=T.SERIE_1, size=4), line=dict(color=T.SERIE_1, width=1),
                           fillcolor="rgba(112,48,160,0.18)",
                           hovertemplate="$%{y:,.4f}<extra></extra>"))
    fig.update_yaxes(tickprefix="$")
    return _sin_fines(_base(fig, f"Dispersión intradía · últimos {len(dias)} días", 420, leyenda=False))


def grafica_compra_vs_venta(diarios: pd.DataFrame) -> go.Figure:
    if diarios is None or diarios.empty:
        return _vacio()
    d = diarios.sort_values("FECHA")
    x = pd.to_datetime(d["FECHA"])
    fig = go.Figure()
    if "ACCIONES_COMPRA" in d:
        fig.add_trace(go.Bar(x=x, y=d["ACCIONES_COMPRA"].fillna(0), name="▲ Compra",
                             marker_color=T.COMPRA, **_barras_kw(),
                             hovertemplate="▲ Compra %{y:,.0f}<extra></extra>"))
    if "ACCIONES_VENTA" in d:
        v = d["ACCIONES_VENTA"].fillna(0)
        fig.add_trace(go.Bar(x=x, y=-v, name="▼ Venta", marker_color=T.VENTA, customdata=v, **_barras_kw(),
                             hovertemplate="▼ Venta %{customdata:,.0f}<extra></extra>"))
    fig.update_layout(barmode="relative")
    fig.update_yaxes(title_text="ACCIONES  ▲ compra / ▼ venta", tickformat="~s")
    return _sin_fines(_base(fig, "Compra vs venta por día", 400))


def grafica_heatmap_calendario(diarios: pd.DataFrame, metrica: str = "ACCIONES") -> go.Figure:
    if diarios is None or diarios.empty:
        return _vacio()
    d = diarios[["FECHA", metrica]].copy()
    d["FECHA"] = pd.to_datetime(d["FECHA"])
    base = pd.DataFrame({"FECHA": pd.bdate_range(d["FECHA"].min(), d["FECHA"].max())})
    base = base.merge(d, on="FECHA", how="left").fillna({metrica: 0})
    base["DOW"] = base["FECHA"].dt.weekday
    base["SEMANA"] = (base["FECHA"] - pd.to_timedelta(base["DOW"], unit="D")).dt.strftime("%d-%b-%y")
    orden_sem = list(dict.fromkeys(base.sort_values("FECHA")["SEMANA"]))
    piv = base.pivot_table(index="DOW", columns="SEMANA", values=metrica, aggfunc="sum").reindex(columns=orden_sem)
    piv = piv.reindex(range(5))
    fig = go.Figure(go.Heatmap(
        z=piv.values, x=piv.columns, y=["LUN", "MAR", "MIÉ", "JUE", "VIE"], colorscale=T.SECUENCIAL,
        xgap=2, ygap=2, colorbar=dict(title=dict(text=metrica, font=dict(size=10)), tickformat="~s"),
        hovertemplate="Semana %{x} · %{y}<br>" + metrica.title() + " %{z:,.0f}<extra></extra>",
    ))
    fig.update_xaxes(showspikes=False, tickangle=-45, gridcolor=T.PANEL)
    fig.update_yaxes(showspikes=False, gridcolor=T.PANEL, autorange="reversed")
    fig.update_layout(hovermode="closest")
    return _base(fig, f"Calendario de {metrica.lower()}", 300, leyenda=False)


def grafica_histograma_precios(df_ops: pd.DataFrame, bins: int = 40) -> go.Figure:
    if df_ops is None or df_ops.empty:
        return _vacio()
    p = pd.to_numeric(df_ops["PRECIO_UNITARIO"], errors="coerce")
    a = pd.to_numeric(df_ops["NUMERO_DE_ACCIONES"], errors="coerce").fillna(0)
    ok = p.notna()
    p, a = p[ok], a[ok]
    vwap = float((p * a).sum() / a.sum()) if a.sum() else float(p.mean())
    fig = go.Figure(go.Histogram(x=p, y=a, histfunc="sum", nbinsx=bins, marker_color=T.SERIE_1,
                                 **_barras_kw(), name="Acciones",
                                 hovertemplate="$%{x}<br>Acciones %{y:,.0f}<extra></extra>"))
    fig.add_vline(x=vwap, line=dict(color=T.TEXT, width=1.5, dash="dash"),
                  annotation=dict(text=f"VWAP ${vwap:,.4f}", font=dict(color=T.TEXT, size=10)),
                  annotation_position="top right")
    fig.update_xaxes(tickprefix="$")
    fig.update_yaxes(title_text="ACCIONES", tickformat="~s")
    fig.update_layout(hovermode="closest")
    return _base(fig, "Perfil de volumen por precio", 400, leyenda=False)


def grafica_tamano_operacion(diarios: pd.DataFrame) -> go.Figure:
    if diarios is None or diarios.empty:
        return _vacio()
    d = diarios.sort_values("FECHA")
    ops = d["OPERACIONES"].replace(0, np.nan)
    x = pd.to_datetime(d["FECHA"])
    fig = _doble_panel((0.5, 0.5))
    fig.add_trace(go.Bar(x=x, y=d["ACCIONES"] / ops, name="Acciones / operación", marker_color=T.SERIE_1,
                         **_barras_kw(), hovertemplate="%{y:,.0f} acc/op<extra></extra>"), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=d["IMPORTE"] / ops, name="MXN / operación", mode="lines+markers",
                             line=dict(color=T.SERIE_2, width=2), marker=dict(size=5),
                             hovertemplate="$%{y:,.0f} /op<extra></extra>"), 2, 1)
    fig.update_yaxes(title_text="ACC/OP", tickformat="~s", row=1, col=1)
    fig.update_yaxes(title_text="MXN/OP", tickprefix="$", tickformat="~s", row=2, col=1)
    return _sin_fines(_base(fig, "Tamaño promedio de operación", 440))


# ---------------------------------------------------------------------------
# Casas de bolsa (color por casa estable: ranking por importe)
# ---------------------------------------------------------------------------

def _mapa_casas(por_casa: pd.DataFrame) -> dict[str, str]:
    orden = por_casa.sort_values("IMPORTE", ascending=False)["CASA_BOLSA"].tolist()
    return T.colores_emisoras(orden)


def grafica_monto_por_casa(por_casa: pd.DataFrame, top_n: int = 15) -> go.Figure:
    if por_casa is None or por_casa.empty:
        return _vacio()
    df = por_casa.sort_values("IMPORTE").tail(top_n)
    fig = go.Figure(go.Bar(x=df["IMPORTE"], y=df["CASA_BOLSA"], orientation="h", marker_color=T.SERIE_1,
                           **_barras_kw(), text=[T.fmt_mxn(v) for v in df["IMPORTE"]], textposition="outside",
                           textfont=dict(color=T.TEXT_2, size=10),
                           hovertemplate="<b>%{y}</b><br>$%{x:,.0f}<extra></extra>"))
    fig.update_xaxes(tickprefix="$", tickformat="~s")
    fig.update_layout(hovermode="closest")
    return _base(fig, f"Top {top_n} casas de bolsa por importe", max(320, 28 * len(df) + 80), leyenda=False)


def grafica_pastel_casas(por_casa: pd.DataFrame, metrica: str = "IMPORTE") -> go.Figure:
    if por_casa is None or por_casa.empty:
        return _vacio()
    mapa = _mapa_casas(por_casa)
    df = por_casa.copy()
    df["GRUPO"] = df["CASA_BOLSA"].where(df["CASA_BOLSA"].isin(mapa), "OTRAS")
    g = df.groupby("GRUPO")[metrica].sum().sort_values(ascending=False)
    colores = [mapa.get(k, T.OTRAS) for k in g.index]
    fig = go.Figure(go.Pie(labels=g.index, values=g.values, hole=0.55, sort=False,
                           marker=dict(colors=colores, line=dict(color=T.PANEL, width=2)),
                           textinfo="percent", textfont=dict(color=T.TEXT, size=10),
                           hovertemplate="<b>%{label}</b><br>%{value:,.0f} · %{percent}<extra></extra>"))
    fig.update_layout(legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.05, yanchor="top"),
                      margin=dict(l=8, r=8, t=44, b=60))
    titulo = "Participación por importe" if metrica == "IMPORTE" else "Participación por # operaciones"
    return _base(fig, titulo, 440)


def grafica_actividad_casas_temporal(df_ops: pd.DataFrame, top_n: int = 7) -> go.Figure:
    if df_ops is None or df_ops.empty:
        return _vacio()
    d = df_ops.copy()
    d["FECHA"] = pd.to_datetime(d["FECHA_OPERACION"]).dt.normalize()
    rank = d.groupby("CASA_BOLSA")["IMPORTE_OPERACION"].sum().sort_values(ascending=False)
    mapa = T.colores_emisoras(rank.index.tolist(), max_colores=min(top_n, 7))
    d["GRUPO"] = d["CASA_BOLSA"].where(d["CASA_BOLSA"].isin(mapa), "OTRAS")
    piv = d.pivot_table(index="FECHA", columns="GRUPO", values="IMPORTE_OPERACION", aggfunc="sum").fillna(0)
    fig = go.Figure()
    for casa in list(mapa) + (["OTRAS"] if "OTRAS" in piv else []):
        if casa in piv:
            fig.add_trace(go.Bar(x=piv.index, y=piv[casa], name=casa, marker_color=mapa.get(casa, T.OTRAS),
                                 **_barras_kw(), hovertemplate=f"{casa} $%{{y:,.0f}}<extra></extra>"))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    return _sin_fines(_base(fig, "Importe diario por casa de bolsa", 440))


# ---------------------------------------------------------------------------
# VWAP vs mercado
# ---------------------------------------------------------------------------

def grafica_vwap_vs_mercado(comparativo: pd.DataFrame) -> go.Figure:
    if comparativo is None or comparativo.empty:
        return _vacio("Sin datos de mercado")
    df = comparativo.sort_values("FECHA")
    x = pd.to_datetime(df["FECHA"])
    fig = _doble_panel((0.62, 0.38))
    fig.add_trace(go.Scatter(x=x, y=df["VWAP"], name="VWAP fondo", mode="lines+markers",
                             line=dict(color=T.SERIE_1, width=2), marker=dict(size=5),
                             hovertemplate="VWAP $%{y:,.4f}<extra></extra>"), 1, 1)
    if "PRECIO_MERCADO" in df:
        fig.add_trace(go.Scatter(x=x, y=df["PRECIO_MERCADO"], name="Cierre mercado", mode="lines",
                                 line=dict(color=MERCADO, width=1.5, dash="dot"),
                                 hovertemplate="Cierre $%{y:,.4f}<extra></extra>"), 1, 1)
    if "VWAP_VS_MERCADO_%" in df:
        v = df["VWAP_VS_MERCADO_%"]
        fig.add_trace(go.Bar(x=x, y=v, name="Δ vs cierre (%)", showlegend=False, **_barras_kw(),
                             marker_color=[T.DIV_POS if (val or 0) > 0 else T.DIV_NEG for val in v.fillna(0)],
                             hovertemplate="Δ %{y:+.2f}%<extra></extra>"), 2, 1)
    fig.update_yaxes(title_text="PRECIO", tickprefix="$", row=1, col=1)
    fig.update_yaxes(title_text="Δ % (óxido = arriba)", ticksuffix="%", row=2, col=1)
    return _sin_fines(_base(fig, "VWAP del fondo vs cierre de mercado", 500))


# ---------------------------------------------------------------------------
# Multi-activo
# ---------------------------------------------------------------------------

def grafica_multi_activo(series_por_ticker: dict[str, pd.DataFrame], metrica: str = "IMPORTE") -> go.Figure:
    if not series_por_ticker:
        return _vacio()
    fig = go.Figure()
    for i, (tk, d) in enumerate(list(series_por_ticker.items())[:8]):
        if d is None or d.empty:
            continue
        d = d.sort_values("FECHA")
        fig.add_trace(go.Scatter(x=pd.to_datetime(d["FECHA"]), y=d[metrica], name=tk, mode="lines+markers",
                                 line=dict(color=T.CATEGORICA[i], width=2), marker=dict(size=5)))
    fig.update_yaxes(tickprefix="$" if metrica in ("IMPORTE", "VWAP") else "", tickformat="~s")
    return _sin_fines(_base(fig, f"Comparativo · {metrica.lower()} diario", 440))


# ---------------------------------------------------------------------------
# 🆕 Mercado completo (resumen_diario del scanner)
# ---------------------------------------------------------------------------

def grafica_mercado_diario(resumen: pd.DataFrame, colores: dict[str, str]) -> go.Figure:
    """Arriba: importe diario apilado por emisora. Abajo: # emisoras recomprando."""
    if resumen is None or resumen.empty:
        return _vacio()
    d = resumen.copy()
    d["GRUPO"] = d["EMISORA"].where(d["EMISORA"].isin(colores), "OTRAS")
    piv = d.pivot_table(index="FECHA", columns="GRUPO", values="IMPORTE", aggfunc="sum").fillna(0).sort_index()
    activas = d.groupby("FECHA")["EMISORA"].nunique().reindex(piv.index)
    fig = _doble_panel((0.72, 0.28))
    for emi in list(colores) + (["OTRAS"] if "OTRAS" in piv else []):
        if emi in piv:
            fig.add_trace(go.Bar(x=piv.index, y=piv[emi], name=emi, marker_color=colores.get(emi, T.OTRAS),
                                 **_barras_kw(), hovertemplate=f"{emi} $%{{y:,.0f}}<extra></extra>"), 1, 1)
    fig.add_trace(go.Bar(x=activas.index, y=activas.values, name="# emisoras", showlegend=False,
                         marker_color=NEUTRO_BAR, **_barras_kw(),
                         hovertemplate="%{y} emisoras<extra></extra>"), 2, 1)
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title_text="IMPORTE", tickprefix="$", tickformat="~s", row=1, col=1)
    fig.update_yaxes(title_text="EMISORAS", tickformat="d", rangemode="tozero",
                     dtick=max(1, int(np.ceil((activas.max() or 1) / 4))), row=2, col=1)
    return _sin_fines(_base(fig, "Recompras del mercado por día", 500))


def grafica_treemap_emisoras(res_dia: pd.DataFrame) -> go.Figure:
    if res_dia is None or res_dia.empty:
        return _vacio()
    d = res_dia[res_dia["IMPORTE"] > 0].sort_values("IMPORTE", ascending=False)
    z = np.log10(d["IMPORTE"] + 1)
    rel = (z - z.min()) / (z.max() - z.min()) if z.max() > z.min() else z * 0 + 1
    # Texto blanco sobre morado profundo, oscuro sobre lavanda (contraste).
    color_txt = ["#FFFFFF" if r > 0.55 else T.TEXT for r in rel]
    fig = go.Figure(go.Treemap(
        labels=d["EMISORA"], parents=[""] * len(d), values=d["IMPORTE"],
        customdata=np.stack([[T.fmt_mxn(v) for v in d["IMPORTE"]], d["OPERACIONES"]], axis=-1),
        marker=dict(colors=z, colorscale=T.SECUENCIAL, line=dict(color=T.PANEL, width=2)),
        texttemplate="<b>%{label}</b><br>%{customdata[0]}<br>%{percentRoot:.1%}",
        textfont=dict(family=T.FONT_MONO, color=color_txt, size=12),
        hovertemplate="<b>%{label}</b><br>%{customdata[0]} · %{customdata[1]} ops<br>%{percentRoot:.1%} del día<extra></extra>",
        tiling=dict(pad=1),
    ))
    fig.update_layout(margin=dict(l=4, r=4, t=40, b=4))
    return _base(fig, "Mapa del día · importe por emisora", 440, leyenda=False)


def grafica_heatmap_emisoras(resumen: pd.DataFrame, top: int = 25, dias: int = 30) -> go.Figure:
    if resumen is None or resumen.empty:
        return _vacio()
    fechas = sorted(resumen["FECHA"].unique())[-dias:]
    d = resumen[resumen["FECHA"].isin(fechas)]
    orden = d.groupby("EMISORA")["IMPORTE"].sum().sort_values(ascending=False).head(top).index
    piv = (d[d["EMISORA"].isin(orden)]
           .pivot_table(index="EMISORA", columns="FECHA", values="IMPORTE", aggfunc="sum")
           .reindex(index=orden, columns=fechas))
    etiquetas = [pd.Timestamp(f).strftime("%d-%b").upper() for f in piv.columns]
    texto = piv.map(lambda v: T.fmt_mxn(v) if pd.notna(v) else "sin recompra")
    fig = go.Figure(go.Heatmap(
        z=np.log10(piv.fillna(0) + 1).where(piv.notna()), x=etiquetas, y=piv.index,
        colorscale=T.SECUENCIAL, xgap=2, ygap=2, showscale=False,
        customdata=texto.values, hovertemplate="<b>%{y}</b> · %{x}<br>%{customdata}<extra></extra>",
    ))
    fig.update_xaxes(showspikes=False, tickangle=-45, gridcolor=T.PANEL, type="category")
    fig.update_yaxes(showspikes=False, gridcolor=T.PANEL, autorange="reversed", type="category")
    fig.update_layout(hovermode="closest")
    return _base(fig, f"Mapa de calor · top {len(orden)} emisoras × últimos {len(fechas)} días", max(360, 22 * len(orden) + 110), leyenda=False)


def grafica_ranking_emisoras(agg: pd.DataFrame, metrica: str = "IMPORTE", top: int = 15) -> go.Figure:
    if agg is None or agg.empty:
        return _vacio()
    d = agg.sort_values(metrica).tail(top)
    fmt = T.fmt_mxn if metrica == "IMPORTE" else T.fmt_num
    fig = go.Figure(go.Bar(x=d[metrica], y=d["EMISORA"], orientation="h", marker_color=T.SERIE_1, **_barras_kw(),
                           text=[fmt(v) for v in d[metrica]], textposition="outside",
                           textfont=dict(color=T.TEXT_2, size=10),
                           hovertemplate="<b>%{y}</b> %{x:,.0f}<extra></extra>"))
    fig.update_xaxes(tickprefix="$" if metrica == "IMPORTE" else "", tickformat="~s", showspikes=False)
    fig.update_layout(hovermode="closest")
    return _base(fig, f"Ranking por {metrica.lower()}", max(320, 26 * len(d) + 80), leyenda=False)


def grafica_acumulado_emisoras(resumen: pd.DataFrame, emisoras: list[str]) -> go.Figure:
    if resumen is None or resumen.empty or not emisoras:
        return _vacio()
    fig = go.Figure()
    for i, emi in enumerate(emisoras[:8]):
        d = resumen[resumen["EMISORA"] == emi].sort_values("FECHA")
        fig.add_trace(go.Scatter(x=d["FECHA"], y=d["IMPORTE"].cumsum(), name=emi, mode="lines",
                                 line=dict(color=T.CATEGORICA[i], width=2),
                                 hovertemplate=f"{emi} $%{{y:,.0f}}<extra></extra>"))
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    return _sin_fines(_base(fig, "Importe acumulado por emisora", 420))


# ---------------------------------------------------------------------------
# Casas de bolsa · mercado completo (tabla de actividad del scanner)
# ---------------------------------------------------------------------------

def grafica_liga_casas(liga: pd.DataFrame, destacar: str = "PUNTO", top: int = 15) -> go.Figure:
    """Barras horizontales de participación; la casa destacada en morado, el resto en gris de marca."""
    if liga is None or liga.empty:
        return _vacio()
    d = liga.sort_values("IMPORTE").tail(top)
    colores = [T.PURPLE if c == destacar else T.GRAY_BRAND for c in d["CASA_BOLSA"]]
    fig = go.Figure(go.Bar(
        x=d["PART"], y=d["CASA_BOLSA"], orientation="h", marker_color=colores, **_barras_kw(),
        text=[f"{p:.1f}%  {T.fmt_mxn(v)}" for p, v in zip(d["PART"], d["IMPORTE"])], textposition="outside",
        textfont=dict(color=T.TEXT_2, size=11), customdata=d["EMISORAS"],
        hovertemplate="<b>%{y}</b><br>%{x:.1f}% del importe · %{customdata} emisoras<extra></extra>",
    ))
    fig.update_xaxes(ticksuffix="%", showspikes=False, range=[0, max(d["PART"].max() * 1.35, 5)])
    fig.update_layout(hovermode="closest")
    return _base(fig, f"Participación por casa de bolsa · {destacar} resaltada", max(340, 28 * len(d) + 90), leyenda=False)


def grafica_participacion_semanal(act: pd.DataFrame, casas: list[str]) -> go.Figure:
    """% del importe semanal ejecutado por cada casa (líneas, máximo 8 casas)."""
    if act is None or act.empty or not casas:
        return _vacio()
    d = act.copy()
    d["SEMANA"] = d["FECHA_OPERACION"] - pd.to_timedelta(d["FECHA_OPERACION"].dt.weekday, unit="D")
    tot = d.groupby("SEMANA")["IMPORTE"].sum()
    piv = d.pivot_table(index="SEMANA", columns="CASA_BOLSA", values="IMPORTE", aggfunc="sum").fillna(0)
    share = piv.div(tot, axis=0) * 100
    fig = go.Figure()
    for i, c in enumerate(casas[:8]):
        if c in share:
            fig.add_trace(go.Scatter(x=share.index, y=share[c], name=c, mode="lines+markers",
                                     line=dict(color=T.CATEGORICA[i], width=2.5 if i == 0 else 1.8), marker=dict(size=7),
                                     hovertemplate=f"{c} %{{y:.1f}}%<extra></extra>"))
    fig.update_yaxes(ticksuffix="%", rangemode="tozero")
    return _base(fig, "Participación semanal en el importe de recompras", 400)


def grafica_matriz_casas(act: pd.DataFrame, top_emisoras: int = 25, top_casas: int = 10) -> go.Figure:
    """Quién ejecuta para quién: importe por emisora x casa de bolsa."""
    if act is None or act.empty:
        return _vacio()
    em = act.groupby("EMISORA")["IMPORTE"].sum().sort_values(ascending=False).head(top_emisoras).index
    cs = act.groupby("CASA_BOLSA")["IMPORTE"].sum().sort_values(ascending=False).head(top_casas).index
    piv = (act[act["EMISORA"].isin(em) & act["CASA_BOLSA"].isin(cs)]
           .pivot_table(index="EMISORA", columns="CASA_BOLSA", values="IMPORTE", aggfunc="sum")
           .reindex(index=em, columns=cs)
           .astype("float64"))   # pd.NA de columnas Int64 rompe nanmin/log10
    texto = piv.map(lambda v: T.fmt_mxn(v) if pd.notna(v) else "")
    z = np.log10(piv.fillna(0) + 1).where(piv.notna())
    rel = (z - np.nanmin(z.values)) / max(np.nanmax(z.values) - np.nanmin(z.values), 1e-9)
    fig = go.Figure(go.Heatmap(
        z=z, x=list(piv.columns), y=list(piv.index),
        colorscale=T.SECUENCIAL, xgap=2, ygap=2, showscale=False, customdata=texto.values,
        hovertemplate="<b>%{y}</b> · %{x}<br>%{customdata}<extra></extra>",
    ))
    # Etiquetas con contraste según el tono de la celda
    for i, emi in enumerate(piv.index):
        for j, casa in enumerate(piv.columns):
            if pd.notna(piv.iat[i, j]):
                fig.add_annotation(x=casa, y=emi, text=texto.iat[i, j], showarrow=False,
                                   font=dict(size=9, color="#FFFFFF" if rel.iat[i, j] > 0.55 else T.TEXT))
    fig.update_xaxes(showspikes=False, side="top", type="category", gridcolor=T.PANEL)
    fig.update_yaxes(showspikes=False, autorange="reversed", type="category", gridcolor=T.PANEL)
    fig.update_layout(hovermode="closest")
    return _base(fig, "Matriz emisora x casa de bolsa (importe)", max(380, 22 * len(piv) + 120), leyenda=False)
