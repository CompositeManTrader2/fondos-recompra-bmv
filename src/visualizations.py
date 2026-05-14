"""
Gráficas Plotly para el dashboard. Todas las funciones devuelven un go.Figure
listo para `st.plotly_chart(fig, use_container_width=True)`.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Paleta morada coherente con el branding original
COLOR_BARRA = "#7D3C98"
COLOR_BARRA_LIGHT = "#BB8FCE"
COLOR_VWAP = "#5B2C6F"
COLOR_COMPRA = "#27AE60"
COLOR_VENTA = "#C0392B"
COLOR_MERCADO = "#2C3E50"
PALETA = [
    "#2E0854", "#4B0082", "#5D3A9B", "#800080", "#9370DB", "#8A2BE2",
    "#9932CC", "#9400D3", "#A020F0", "#B03060", "#BF40BF", "#D891EF",
    "#DA70D6", "#E6E6FA", "#EE82EE", "#FF00FF",
]


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
# Operaciones / Acciones / Importes con VWAP overlay
# ---------------------------------------------------------------------------

def grafica_actividad_diaria(
    diarios: pd.DataFrame,
    metrica: str = "OPERACIONES",
    incluir_vwap_lados: bool = True,
) -> go.Figure:
    """
    metrica ∈ {'OPERACIONES', 'ACCIONES', 'IMPORTE'}.
    Eje izq: barras con la métrica; eje der: VWAP (y opcionalmente compra/venta).
    """
    if diarios is None or diarios.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)

    diarios = diarios.sort_values("FECHA").copy()
    fechas = pd.to_datetime(diarios["FECHA"])

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=fechas, y=diarios[metrica],
            name=metrica.title(),
            marker_color=COLOR_BARRA,
            hovertemplate="%{x|%d-%b-%Y}<br>"+metrica.title()+": %{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )

    if "VWAP" in diarios.columns:
        fig.add_trace(
            go.Scatter(
                x=fechas, y=diarios["VWAP"], name="VWAP",
                mode="lines+markers", line=dict(color=COLOR_VWAP, width=2.5),
                hovertemplate="VWAP: %{y:,.4f}<extra></extra>",
            ),
            secondary_y=True,
        )
    if incluir_vwap_lados:
        if "VWAP_COMPRA" in diarios.columns and diarios["VWAP_COMPRA"].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=fechas, y=diarios["VWAP_COMPRA"], name="VWAP Compra",
                    mode="lines+markers", line=dict(color=COLOR_COMPRA, dash="dash"),
                    marker_symbol="triangle-up",
                    hovertemplate="VWAP Compra: %{y:,.4f}<extra></extra>",
                ),
                secondary_y=True,
            )
        if "VWAP_VENTA" in diarios.columns and diarios["VWAP_VENTA"].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=fechas, y=diarios["VWAP_VENTA"], name="VWAP Venta",
                    mode="lines+markers", line=dict(color=COLOR_VENTA, dash="dash"),
                    marker_symbol="triangle-down",
                    hovertemplate="VWAP Venta: %{y:,.4f}<extra></extra>",
                ),
                secondary_y=True,
            )

    fig.update_yaxes(title_text=metrica.title(), secondary_y=False)
    fig.update_yaxes(title_text="VWAP (MXN)", secondary_y=True)
    fig.update_xaxes(title_text="Fecha")

    titulo = {
        "OPERACIONES": "Ejecuciones diarias y VWAP",
        "ACCIONES": "Acciones operadas y VWAP",
        "IMPORTE": "Importe operado y VWAP",
    }.get(metrica, metrica)
    return _layout_base(fig, titulo)


def grafica_actividad_mensual(mensuales: pd.DataFrame) -> go.Figure:
    if mensuales is None or mensuales.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)
    mensuales = mensuales.sort_values("MES").copy()
    fechas = pd.to_datetime(mensuales["MES"])

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=fechas, y=mensuales["IMPORTE"], name="Importe",
        marker_color=COLOR_BARRA,
        hovertemplate="%{x|%b-%Y}<br>Importe: $%{y:,.0f}<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=fechas, y=mensuales["VWAP"], name="VWAP",
        mode="lines+markers", line=dict(color=COLOR_VWAP, width=2.5),
        hovertemplate="VWAP: %{y:,.4f}<extra></extra>",
    ), secondary_y=True)
    fig.update_yaxes(title_text="Importe (MXN)", tickprefix="$", secondary_y=False)
    fig.update_yaxes(title_text="VWAP (MXN)", secondary_y=True)
    return _layout_base(fig, "Importe operado y VWAP por mes")


# ---------------------------------------------------------------------------
# Casas de bolsa
# ---------------------------------------------------------------------------

def grafica_monto_por_casa(por_casa: pd.DataFrame, top_n: int = 15) -> go.Figure:
    if por_casa is None or por_casa.empty:
        return _layout_base(go.Figure(), "Sin datos", 300)
    df = por_casa.sort_values("IMPORTE", ascending=True).tail(top_n)
    fig = go.Figure(go.Bar(
        x=df["IMPORTE"], y=df["CASA_BOLSA"], orientation="h",
        marker_color=COLOR_BARRA,
        text=[f"${v:,.0f}" for v in df["IMPORTE"]], textposition="outside",
        hovertemplate="%{y}<br>Importe: $%{x:,.0f}<extra></extra>",
    ))
    fig.update_xaxes(title="Importe operado (MXN)", tickprefix="$")
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
        hovertemplate="<b>%{label}</b><br>"+metrica.title()+": %{value:,.0f}<br>%{percent}<extra></extra>",
    ))
    titulo = "Participación por importe" if metrica == "IMPORTE" else "Participación por # operaciones"
    return _layout_base(fig, titulo, alto=500)


# ---------------------------------------------------------------------------
# Comparativo VWAP vs Mercado
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
    ), secondary_y=False)
    if "PRECIO_MERCADO" in df.columns:
        fig.add_trace(go.Scatter(
            x=fechas, y=df["PRECIO_MERCADO"], name="Precio mercado",
            mode="lines", line=dict(color=COLOR_MERCADO, width=2),
        ), secondary_y=False)

    if "VWAP_VS_MERCADO_%" in df.columns:
        fig.add_trace(go.Bar(
            x=fechas, y=df["VWAP_VS_MERCADO_%"],
            name="Sobreprecio (%)", marker_color=COLOR_BARRA_LIGHT, opacity=0.5,
            hovertemplate="Sobreprecio: %{y:.2f}%<extra></extra>",
        ), secondary_y=True)

    fig.update_yaxes(title="Precio (MXN)", secondary_y=False)
    fig.update_yaxes(title="Sobreprecio (%)", ticksuffix="%", secondary_y=True)
    return _layout_base(fig, "VWAP del fondo vs precio de mercado")


# ---------------------------------------------------------------------------
# Comparativa Multi-Activo
# ---------------------------------------------------------------------------

def grafica_multi_activo(
    series_por_ticker: dict[str, pd.DataFrame],
    metrica: str = "IMPORTE",
) -> go.Figure:
    """series_por_ticker: {'AMXL': diarios_df, 'GFNORTEO': diarios_df, ...}"""
    fig = go.Figure()
    if not series_por_ticker:
        return _layout_base(fig, "Sin datos", 300)
    for i, (ticker, diarios) in enumerate(series_por_ticker.items()):
        if diarios is None or diarios.empty:
            continue
        df = diarios.sort_values("FECHA")
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(df["FECHA"]), y=df[metrica],
            name=ticker, mode="lines+markers",
            line=dict(color=PALETA[i % len(PALETA)], width=2),
        ))
    fig.update_yaxes(title=metrica.title())
    fig.update_xaxes(title="Fecha")
    return _layout_base(fig, f"Comparativo multi-activo · {metrica.title()} diario")
