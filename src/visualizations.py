"""
Gráficas Plotly para el dashboard.

Convenciones:
  - Todas las gráficas con eje temporal eliminan fines de semana
    (`xaxis.rangebreaks`) para que no aparezcan huecos en el eje.
  - Devuelven un `go.Figure` listo para `st.plotly_chart(fig, use_container_width=True)`.
  - Paleta morada coherente con el branding original.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Paleta y helpers
# ---------------------------------------------------------------------------

COLOR_BARRA = "#7D3C98"
COLOR_BARRA_LIGHT = "#BB8FCE"
COLOR_VWAP = "#5B2C6F"
COLOR_VWAP_5 = "#27AE60"
COLOR_VWAP_20 = "#D35400"
COLOR_COMPRA = "#27AE60"
COLOR_VENTA = "#C0392B"
COLOR_MERCADO = "#2C3E50"
COLOR_ACUM = "#2980B9"
PALETA = [
    "#2E0854", "#4B0082", "#5D3A9B", "#800080", "#9370DB", "#8A2BE2",
    "#9932CC", "#9400D3", "#A020F0", "#B03060", "#BF40BF", "#D891EF",
    "#DA70D6", "#E6E6FA", "#EE82EE", "#FF00FF",
]


def _aplicar_rangebreaks(fig: go.Figure) -> go.Figure:
    """Quita sábados y domingos del eje X (y feriados conocidos si los hubiera).

    Se aplica a todos los xaxes del figure (también en subplots).
    """
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),
            # Si quisieras agregar feriados puntuales:
            # dict(values=["2025-12-25", "2026-01-01"]),
        ]
    )
    return fig


def _layout_base(fig: go.Figure, titulo: str, alto: int = 480) -> go.Figure:
    fig.update_layout(
        title=dict(text=f"<b>{titulo}</b>", x=0.02, xanchor="left"),
        template="plotly_white",
        margin=dict(l=40, r=40, t=70, b=40),
        height=alto,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# Operaciones / Acciones / Importes con VWAP overlay (mejorada)
# ---------------------------------------------------------------------------

def grafica_actividad_diaria(
    diarios: pd.DataFrame,
    metrica: str = "OPERACIONES",
    incluir_vwap_lados: bool = True,
) -> go.Figure:
    """metrica ∈ {'OPERACIONES', 'ACCIONES', 'IMPORTE'}."""
    if diarios is None or diarios.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)

    d = diarios.sort_values("FECHA").copy()
    fechas = pd.to_datetime(d["FECHA"])

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=fechas, y=d[metrica],
            name=metrica.title(),
            marker_color=COLOR_BARRA,
            opacity=0.85,
            hovertemplate="%{x|%a %d-%b-%Y}<br>" + metrica.title() + ": %{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )

    if "VWAP" in d.columns:
        fig.add_trace(
            go.Scatter(
                x=fechas, y=d["VWAP"], name="VWAP",
                mode="lines+markers",
                line=dict(color=COLOR_VWAP, width=2.5),
                marker=dict(size=7),
                hovertemplate="VWAP: $%{y:,.4f}<extra></extra>",
            ),
            secondary_y=True,
        )
    if incluir_vwap_lados:
        if "VWAP_COMPRA" in d.columns and d["VWAP_COMPRA"].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=fechas, y=d["VWAP_COMPRA"], name="VWAP Compra",
                    mode="lines+markers", line=dict(color=COLOR_COMPRA, dash="dot", width=1.5),
                    marker=dict(symbol="triangle-up", size=8),
                    hovertemplate="VWAP Compra: $%{y:,.4f}<extra></extra>",
                ),
                secondary_y=True,
            )
        if "VWAP_VENTA" in d.columns and d["VWAP_VENTA"].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=fechas, y=d["VWAP_VENTA"], name="VWAP Venta",
                    mode="lines+markers", line=dict(color=COLOR_VENTA, dash="dot", width=1.5),
                    marker=dict(symbol="triangle-down", size=8),
                    hovertemplate="VWAP Venta: $%{y:,.4f}<extra></extra>",
                ),
                secondary_y=True,
            )

    eje_y_format = {"OPERACIONES": ",d", "ACCIONES": ",d", "IMPORTE": "$,.0f"}.get(metrica, ",.0f")
    fig.update_yaxes(title_text=metrica.title(), tickformat=eje_y_format, secondary_y=False)
    fig.update_yaxes(title_text="VWAP (MXN)", tickprefix="$", tickformat=",.4f", secondary_y=True)
    fig.update_xaxes(title_text="Fecha")

    titulo = {
        "OPERACIONES": "Ejecuciones diarias y VWAP",
        "ACCIONES": "Acciones operadas y VWAP",
        "IMPORTE": "Importe operado y VWAP",
    }.get(metrica, metrica)
    return _aplicar_rangebreaks(_layout_base(fig, titulo))


def grafica_actividad_mensual(mensuales: pd.DataFrame) -> go.Figure:
    if mensuales is None or mensuales.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)
    m = mensuales.sort_values("MES").copy()
    fechas = pd.to_datetime(m["MES"])

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=fechas, y=m["IMPORTE"], name="Importe",
        marker_color=COLOR_BARRA, opacity=0.85,
        hovertemplate="%{x|%b-%Y}<br>Importe: $%{y:,.0f}<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=fechas, y=m["VWAP"], name="VWAP",
        mode="lines+markers", line=dict(color=COLOR_VWAP, width=2.5),
        hovertemplate="VWAP: $%{y:,.4f}<extra></extra>",
    ), secondary_y=True)
    fig.update_yaxes(title_text="Importe (MXN)", tickprefix="$", tickformat=",.0f", secondary_y=False)
    fig.update_yaxes(title_text="VWAP (MXN)", tickprefix="$", tickformat=",.4f", secondary_y=True)
    return _layout_base(fig, "Importe operado y VWAP por mes")


# ---------------------------------------------------------------------------
# 🆕 Acumulados (acciones recompradas e importe gastado)
# ---------------------------------------------------------------------------

def grafica_acumulado(diarios: pd.DataFrame) -> go.Figure:
    """Muestra el acumulado (running sum) de acciones e importe a lo largo del tiempo."""
    if diarios is None or diarios.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)

    d = diarios.sort_values("FECHA").copy()
    d["ACC_ACCIONES_NETO"] = (
        d.get("ACCIONES_COMPRA", d["ACCIONES"]).fillna(0)
        - d.get("ACCIONES_VENTA", pd.Series(0, index=d.index)).fillna(0)
    ).cumsum()
    d["ACC_IMPORTE"] = d["IMPORTE"].fillna(0).cumsum()

    fechas = pd.to_datetime(d["FECHA"])
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=fechas, y=d["ACC_ACCIONES_NETO"], name="Acciones netas (acumuladas)",
        mode="lines", fill="tozeroy",
        line=dict(color=COLOR_ACUM, width=2),
        fillcolor="rgba(41, 128, 185, 0.2)",
        hovertemplate="%{x|%a %d-%b-%Y}<br>Netas: %{y:,.0f}<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=fechas, y=d["ACC_IMPORTE"], name="Importe gastado (acumulado)",
        mode="lines", line=dict(color=COLOR_BARRA, width=2.5, dash="dash"),
        hovertemplate="%{x|%a %d-%b-%Y}<br>Importe: $%{y:,.0f}<extra></extra>",
    ), secondary_y=True)
    fig.update_yaxes(title_text="Acciones netas acumuladas", tickformat=",d", secondary_y=False)
    fig.update_yaxes(title_text="Importe acumulado (MXN)", tickprefix="$", tickformat=",.0f", secondary_y=True)
    return _aplicar_rangebreaks(_layout_base(fig, "Posición acumulada del fondo de recompra"))


# ---------------------------------------------------------------------------
# 🆕 VWAP rolling
# ---------------------------------------------------------------------------

def grafica_vwap_rolling(diarios: pd.DataFrame, ventanas: tuple[int, ...] = (5, 10, 20)) -> go.Figure:
    """VWAP diario con medias móviles ponderadas por acciones."""
    if diarios is None or diarios.empty or "VWAP" not in diarios.columns:
        return _layout_base(go.Figure(), "Sin datos", 300)
    d = diarios.sort_values("FECHA").copy()
    fechas = pd.to_datetime(d["FECHA"])

    # VWAP rolling = Σ(precio * acciones) / Σ(acciones) en ventana móvil
    pv = (d["VWAP"] * d["ACCIONES"].fillna(0))
    acc = d["ACCIONES"].fillna(0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fechas, y=d["VWAP"], name="VWAP diario",
        mode="lines+markers", line=dict(color=COLOR_VWAP, width=1.8),
        marker=dict(size=5),
        hovertemplate="%{x|%a %d-%b-%Y}<br>VWAP: $%{y:,.4f}<extra></extra>",
    ))
    colors_rolling = [COLOR_VWAP_5, COLOR_BARRA_LIGHT, COLOR_VWAP_20]
    for i, w in enumerate(ventanas):
        if len(d) >= w:
            roll = (pv.rolling(w).sum() / acc.rolling(w).sum().replace(0, np.nan))
            fig.add_trace(go.Scatter(
                x=fechas, y=roll, name=f"VWAP móvil {w}d",
                mode="lines", line=dict(color=colors_rolling[i % len(colors_rolling)], width=2.2),
                hovertemplate=f"VWAP {w}d: $%{{y:,.4f}}<extra></extra>",
            ))
    fig.update_yaxes(title_text="Precio (MXN)", tickprefix="$", tickformat=",.4f")
    return _aplicar_rangebreaks(_layout_base(fig, "VWAP diario y medias móviles"))


# ---------------------------------------------------------------------------
# 🆕 Box plot diario / dispersión intradía
# ---------------------------------------------------------------------------

def grafica_dispersion_intradia(df_ops: pd.DataFrame, max_dias: int = 60) -> go.Figure:
    """Box plot de precios por día — muestra rango y mediana intradía."""
    if df_ops is None or df_ops.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)
    d = df_ops.sort_values("FECHA_OPERACION").copy()
    d["FECHA"] = pd.to_datetime(d["FECHA_OPERACION"]).dt.normalize()
    # Limitar a últimos N días para no saturar
    fechas_unicas = sorted(d["FECHA"].unique())
    if len(fechas_unicas) > max_dias:
        ultimas = fechas_unicas[-max_dias:]
        d = d[d["FECHA"].isin(ultimas)]

    fig = go.Figure()
    fig.add_trace(go.Box(
        x=d["FECHA"], y=d["PRECIO_UNITARIO"],
        name="Precio", marker_color=COLOR_BARRA,
        boxpoints="outliers", line=dict(width=1.4),
        hovertemplate="%{x|%a %d-%b-%Y}<br>Precio: $%{y:,.4f}<extra></extra>",
    ))
    fig.update_yaxes(title_text="Precio ejecutado (MXN)", tickprefix="$", tickformat=",.4f")
    fig.update_xaxes(title_text="Fecha")
    return _aplicar_rangebreaks(_layout_base(fig, f"Dispersión intradía de precios (últimos {min(max_dias, len(fechas_unicas))} días con operaciones)"))


# ---------------------------------------------------------------------------
# 🆕 Compra vs Venta apilado por día
# ---------------------------------------------------------------------------

def grafica_compra_vs_venta(diarios: pd.DataFrame) -> go.Figure:
    """Barras apiladas mostrando acciones compradas vs vendidas por día."""
    if diarios is None or diarios.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)
    d = diarios.sort_values("FECHA").copy()
    fechas = pd.to_datetime(d["FECHA"])
    fig = go.Figure()
    if "ACCIONES_COMPRA" in d.columns:
        fig.add_trace(go.Bar(
            x=fechas, y=d["ACCIONES_COMPRA"].fillna(0),
            name="Compra", marker_color=COLOR_COMPRA,
            hovertemplate="%{x|%a %d-%b-%Y}<br>Compra: %{y:,.0f}<extra></extra>",
        ))
    if "ACCIONES_VENTA" in d.columns:
        # Las ventas se grafican como negativas para visualizarlas debajo del eje
        fig.add_trace(go.Bar(
            x=fechas, y=-d["ACCIONES_VENTA"].fillna(0),
            name="Venta", marker_color=COLOR_VENTA,
            hovertemplate="%{x|%a %d-%b-%Y}<br>Venta: %{customdata:,.0f}<extra></extra>",
            customdata=d["ACCIONES_VENTA"].fillna(0),
        ))
    fig.update_layout(barmode="relative")
    fig.update_yaxes(title_text="Acciones (compra ↑ / venta ↓)", tickformat=",d")
    fig.update_xaxes(title_text="Fecha")
    return _aplicar_rangebreaks(_layout_base(fig, "Compra vs Venta de acciones por día"))


# ---------------------------------------------------------------------------
# 🆕 Heatmap calendario tipo GitHub
# ---------------------------------------------------------------------------

def grafica_heatmap_calendario(diarios: pd.DataFrame, metrica: str = "ACCIONES") -> go.Figure:
    """Heatmap día-de-semana × semana con la métrica indicada (estilo GitHub)."""
    if diarios is None or diarios.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)

    d = diarios.copy()
    d["FECHA"] = pd.to_datetime(d["FECHA"])
    fechas_full = pd.date_range(d["FECHA"].min(), d["FECHA"].max(), freq="D")
    base = pd.DataFrame({"FECHA": fechas_full})
    base = base.merge(d[["FECHA", metrica]], on="FECHA", how="left").fillna(0)
    # Sólo días hábiles (lun-vie)
    base = base[base["FECHA"].dt.weekday < 5].copy()
    base["dow"] = base["FECHA"].dt.day_name(locale=None).str[:3]
    base["semana"] = base["FECHA"].dt.strftime("%Y-W%U")

    # Map para ordenar días
    dias_orden = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    base["dow"] = base["dow"].astype("category").cat.set_categories(dias_orden, ordered=True)

    pivot = base.pivot_table(index="dow", columns="semana", values=metrica, aggfunc="sum", observed=True).fillna(0)
    pivot = pivot.reindex(dias_orden)

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns,
        y=pivot.index,
        colorscale="Purples",
        hovertemplate="Semana: %{x}<br>%{y}<br>" + metrica.title() + ": %{z:,.0f}<extra></extra>",
        colorbar=dict(title=metrica.title()),
    ))
    fig.update_layout(template="plotly_white", height=320,
                      margin=dict(l=40, r=40, t=60, b=40),
                      title=dict(text=f"<b>Calendario de {metrica.lower()} por día</b>", x=0.02))
    fig.update_xaxes(title_text="Semana ISO", tickangle=-45)
    fig.update_yaxes(title_text="")
    return fig


# ---------------------------------------------------------------------------
# 🆕 Histograma de precios ejecutados
# ---------------------------------------------------------------------------

def grafica_histograma_precios(df_ops: pd.DataFrame, bins: int = 40) -> go.Figure:
    """Distribución de los precios ejecutados (con líneas de min/max/VWAP)."""
    if df_ops is None or df_ops.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)
    precios = pd.to_numeric(df_ops["PRECIO_UNITARIO"], errors="coerce").dropna()
    acc = pd.to_numeric(df_ops["NUMERO_DE_ACCIONES"], errors="coerce").fillna(0)
    vwap = (precios * acc).sum() / acc.sum() if acc.sum() else precios.mean()

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=precios, nbinsx=bins, marker_color=COLOR_BARRA, opacity=0.85,
        hovertemplate="Precio ~ $%{x:,.4f}<br># operaciones: %{y}<extra></extra>",
        name="Operaciones",
    ))
    fig.add_vline(x=vwap, line=dict(color=COLOR_VWAP, width=2, dash="dash"),
                  annotation_text=f"VWAP ${vwap:,.4f}", annotation_position="top right")
    fig.add_vline(x=precios.min(), line=dict(color="#888", width=1, dash="dot"),
                  annotation_text=f"Mín ${precios.min():,.4f}", annotation_position="top left")
    fig.add_vline(x=precios.max(), line=dict(color="#888", width=1, dash="dot"),
                  annotation_text=f"Máx ${precios.max():,.4f}", annotation_position="top right")
    fig.update_xaxes(title_text="Precio (MXN)", tickprefix="$", tickformat=",.4f")
    fig.update_yaxes(title_text="# operaciones")
    return _layout_base(fig, "Distribución de precios ejecutados")


# ---------------------------------------------------------------------------
# 🆕 Tamaño promedio de operación por día
# ---------------------------------------------------------------------------

def grafica_tamano_operacion(diarios: pd.DataFrame) -> go.Figure:
    if diarios is None or diarios.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)
    d = diarios.sort_values("FECHA").copy()
    d["TAMANO_PROM_ACC"] = d["ACCIONES"] / d["OPERACIONES"].replace(0, np.nan)
    d["TAMANO_PROM_IMP"] = d["IMPORTE"] / d["OPERACIONES"].replace(0, np.nan)
    fechas = pd.to_datetime(d["FECHA"])

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=fechas, y=d["TAMANO_PROM_ACC"], name="Acciones / operación",
        marker_color=COLOR_BARRA, opacity=0.85,
        hovertemplate="%{x|%a %d-%b-%Y}<br>Acciones/op: %{y:,.0f}<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=fechas, y=d["TAMANO_PROM_IMP"], name="MXN / operación",
        mode="lines+markers", line=dict(color=COLOR_VWAP, width=2),
        hovertemplate="%{x|%a %d-%b-%Y}<br>MXN/op: $%{y:,.0f}<extra></extra>",
    ), secondary_y=True)
    fig.update_yaxes(title_text="Acciones por operación", tickformat=",d", secondary_y=False)
    fig.update_yaxes(title_text="MXN por operación", tickprefix="$", tickformat=",.0f", secondary_y=True)
    return _aplicar_rangebreaks(_layout_base(fig, "Tamaño promedio de operación"))


# ---------------------------------------------------------------------------
# Casas de bolsa (mejoradas)
# ---------------------------------------------------------------------------

def grafica_monto_por_casa(por_casa: pd.DataFrame, top_n: int = 15) -> go.Figure:
    if por_casa is None or por_casa.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)
    df = por_casa.sort_values("IMPORTE", ascending=True).tail(top_n)
    fig = go.Figure(go.Bar(
        x=df["IMPORTE"], y=df["CASA_BOLSA"], orientation="h",
        marker_color=COLOR_BARRA,
        text=[f"${v:,.0f}" for v in df["IMPORTE"]], textposition="outside",
        hovertemplate="<b>%{y}</b><br>Importe: $%{x:,.0f}<extra></extra>",
    ))
    fig.update_xaxes(title="Importe operado (MXN)", tickprefix="$", tickformat=",.0f")
    return _layout_base(fig, f"Top {top_n} casas de bolsa por importe", alto=500)


def grafica_pastel_casas(por_casa: pd.DataFrame, metrica: str = "IMPORTE") -> go.Figure:
    if por_casa is None or por_casa.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)
    valores = por_casa[metrica]
    etiquetas = por_casa["CASA_BOLSA"]
    fig = go.Figure(go.Pie(
        labels=etiquetas, values=valores, hole=0.45,
        marker=dict(colors=PALETA[:len(etiquetas)], line=dict(color="white", width=1)),
        textinfo="percent",
        hovertemplate="<b>%{label}</b><br>" + metrica.title() + ": %{value:,.0f}<br>%{percent}<extra></extra>",
    ))
    titulo = "Participación por importe" if metrica == "IMPORTE" else "Participación por # operaciones"
    return _layout_base(fig, titulo, alto=500)


# ---------------------------------------------------------------------------
# 🆕 Casas de bolsa por día (heatmap stacked)
# ---------------------------------------------------------------------------

def grafica_actividad_casas_temporal(df_ops: pd.DataFrame, top_n: int = 8) -> go.Figure:
    """Stacked area chart de las top N casas a lo largo del tiempo."""
    if df_ops is None or df_ops.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)
    d = df_ops.copy()
    d["FECHA"] = pd.to_datetime(d["FECHA_OPERACION"]).dt.normalize()
    top = (d.groupby("CASA_BOLSA")["IMPORTE_OPERACION"].sum()
             .sort_values(ascending=False).head(top_n).index.tolist())
    d["CASA_GRP"] = d["CASA_BOLSA"].where(d["CASA_BOLSA"].isin(top), other="OTRAS")
    pivot = (d.pivot_table(index="FECHA", columns="CASA_GRP",
                           values="IMPORTE_OPERACION", aggfunc="sum")
              .fillna(0).sort_index())
    fig = go.Figure()
    casas_orden = top + (["OTRAS"] if "OTRAS" in pivot.columns else [])
    for i, casa in enumerate(casas_orden):
        if casa in pivot.columns:
            fig.add_trace(go.Scatter(
                x=pivot.index, y=pivot[casa], name=casa,
                mode="lines", stackgroup="one",
                line=dict(width=0.5, color=PALETA[i % len(PALETA)]),
                hovertemplate=f"<b>{casa}</b><br>%{{x|%a %d-%b-%Y}}<br>$%{{y:,.0f}}<extra></extra>",
            ))
    fig.update_yaxes(title_text="Importe (MXN)", tickprefix="$", tickformat=",.0f")
    return _aplicar_rangebreaks(_layout_base(fig, f"Actividad por casa de bolsa (top {top_n})"))


# ---------------------------------------------------------------------------
# Comparativo VWAP vs Mercado (mejorado)
# ---------------------------------------------------------------------------

def grafica_vwap_vs_mercado(comparativo: pd.DataFrame) -> go.Figure:
    if comparativo is None or comparativo.empty:
        return _layout_base(go.Figure(), "Sin datos de mercado", 300)
    df = comparativo.sort_values("FECHA").copy()
    fechas = pd.to_datetime(df["FECHA"])
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Scatter(
        x=fechas, y=df["VWAP"], name="VWAP fondo",
        mode="lines+markers", line=dict(color=COLOR_VWAP, width=2.5),
        hovertemplate="VWAP: $%{y:,.4f}<extra></extra>",
    ), secondary_y=False)
    if "PRECIO_MERCADO" in df.columns:
        fig.add_trace(go.Scatter(
            x=fechas, y=df["PRECIO_MERCADO"], name="Precio mercado",
            mode="lines", line=dict(color=COLOR_MERCADO, width=2),
            hovertemplate="Mercado: $%{y:,.4f}<extra></extra>",
        ), secondary_y=False)

    if "VWAP_VS_MERCADO_%" in df.columns:
        colors = ["#27AE60" if v <= 0 else "#C0392B" for v in df["VWAP_VS_MERCADO_%"].fillna(0)]
        fig.add_trace(go.Bar(
            x=fechas, y=df["VWAP_VS_MERCADO_%"],
            name="Sobreprecio (%)", marker_color=colors, opacity=0.45,
            hovertemplate="Sobreprecio: %{y:.2f}%<extra></extra>",
        ), secondary_y=True)

    fig.update_yaxes(title="Precio (MXN)", tickprefix="$", tickformat=",.4f", secondary_y=False)
    fig.update_yaxes(title="Sobreprecio (%)", ticksuffix="%", secondary_y=True)
    return _aplicar_rangebreaks(_layout_base(fig, "VWAP del fondo vs precio de mercado"))


# ---------------------------------------------------------------------------
# Comparativa Multi-Activo (mejorada)
# ---------------------------------------------------------------------------

def grafica_multi_activo(
    series_por_ticker: dict[str, pd.DataFrame],
    metrica: str = "IMPORTE",
) -> go.Figure:
    fig = go.Figure()
    if not series_por_ticker:
        return _layout_base(fig, "Sin datos", 300)
    for i, (ticker, diarios) in enumerate(series_por_ticker.items()):
        if diarios is None or diarios.empty:
            continue
        d = diarios.sort_values("FECHA")
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(d["FECHA"]), y=d[metrica],
            name=ticker, mode="lines+markers",
            line=dict(color=PALETA[i % len(PALETA)], width=2),
        ))
    fmt = {"IMPORTE": "$,.0f", "ACCIONES": ",d", "OPERACIONES": ",d", "VWAP": "$,.4f"}.get(metrica, ",.0f")
    fig.update_yaxes(title=metrica.title(), tickformat=fmt,
                     tickprefix="$" if metrica in ("IMPORTE", "VWAP") else "")
    fig.update_xaxes(title="Fecha")
    return _aplicar_rangebreaks(_layout_base(fig, f"Comparativo multi-activo · {metrica.title()} diario"))
