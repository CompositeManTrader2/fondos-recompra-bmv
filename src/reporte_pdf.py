"""
Reporte mensual "Net Buybacks" en PDF (todas las emisoras de la BMV), con la
identidad de Punto Casa de Bolsa.

Páginas
  1. Portada (morada; usa assets/portada.jpg si existe)
  2. Resumen ejecutivo: KPIs, hallazgos automáticos y acumulado del año vs años previos
  3. Recompra neta por sector: 12M de los dos años previos, últimos 12M, YTD previo y YTD
  4. Dinámica del mercado: flujo mensual 36M, amplitud (compradoras/vendedoras) y estadísticos
  5. Top 20 buyback yield y compradores netos 12M, recompra neta mensual con top 3
  6. Concentración y amplitud: Pareto, HHI y comparativo por año
  7. Ejecución de los programas: intensidad, precio de compra vs cierre y rango 52s, fondo remanente
  8. Momentum y señales: aceleran / desaceleran / en pausa / vendedoras netas / nuevas
  9. Intermediarios: participación de casas de bolsa
  10. Ranking YTD · 11. Ranking 5 años · 12+ Detalle por emisora
  último. Metodología, calidad de datos y aviso legal (assets/aviso_legal.txt si existe)

Uso:
    pdf_bytes = generar_pdf(actividad, documentos, mercado, corte=date(2026, 11, 3))
"""
from __future__ import annotations

import io
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src import reporte_datos as rd

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "assets"
REPORTES = REPO / "reportes"

# Identidad Punto
PURPLE = "#7030A0"
PURPLE_DARK = "#4E1F72"
PURPLE_MID = "#E4D2F0"
LAVENDER = "#ECDEF5"
LAVENDER_SOFT = "#F7F2FB"
TEAL = "#0E9A94"
GRAY = "#949BA1"
TEXT = "#1F1A26"
MUTED = "#6B6475"
RED = "#A9131F"
GRID = "#EEE8F3"

PAGE_W, PAGE_H = 880, 612
M = 30
TOP = 64          # deja libre la franja de fecha y logotipo

MESES = {"en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                "October", "November", "December"],
         "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                "octubre", "noviembre", "diciembre"]}
MES_CORTO = {"en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
             "es": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]}

L = {
    "en": dict(
        portada="Buybacks", sub_portada="Bolsa Mexicana de Valores · all issuers",
        net="Net Buybacks", cifras="–Figures in MXN Million", pie="NET BUYBACKS",
        monto="Amount", yoy="YOY%", by="Buyback\nYield", emis="Issuers", total="TOTAL",
        nota_sec="Buyback yield = net buybacks / market value (outstanding shares × close as of {corte}). "
                 "Issuers = companies buying back in the period. n.d. = before full-market data coverage ({cob}).",
        top_yield="{y} Last 12M Top 20 · Buyback Yield", top_yield_sub="Buyback Yield = Net shares bought back / Outstanding shares · Box: LTM average buy price",
        top_comp="{y} Last 12M Top 20 Net Buyers", top_comp_sub="Figures in MXN Million",
        mensual="Net buybacks month over month", mensual_sub="MXN Million · top 3 issuers by monthly buyback yield",
        rk_ytd="Net Buybacks - year to date ranking", rk_5y="Net Buybacks - 5 year ranking",
        rk_monto="Amount (MXN Million)", rk_yield="Buyback Yield %", empresa="Company", yld="Yield %",
        periodo="–Period: {ini} – {fin}", det_sub="–Order by 5 year Buyback Yield%",
        g_yield="Buyback Yield", g_monto="Amount (MXN Million)", g_acc="Shares (Million)",
        g_precio="Price per Share {y} YTD", compra="Buy Avg.", venta="Sell Avg.", g_rem="Remaining\nfund", rem2="(MXN Million)",
        tot="Total", ytd="YTD", cobertura_parcial="*Data coverage starts {cob}; earlier periods shown as n.d.",
        metodo="Methodology & Disclosures", pendiente="Pending data", nd="n.d.",
        resumen='Executive summary',
        resumen_sub='Key figures and findings · data as of {corte}',
        k_ytd='{y} YTD net buybacks',
        k_yoy='vs {y1} YTD',
        k_ltm='Last 12M net buybacks',
        k_yield='LTM buyback yield',
        k_emis='Issuers buying YTD',
        k_top5='Top-5 share (LTM)',
        k_rem='Remaining buyback funds',
        k_rem_sub='{p} of market value',
        k_mxn='MXN million',
        hallazgos='Key findings',
        acum='Cumulative net buybacks by year',
        acum_sub='MXN Million · by calendar day',
        dinamica='Market dynamics',
        dinamica_sub='Monthly flows, breadth and statistics · last 36 months',
        g_men='Net buybacks per month',
        g_men_sub='MXN Million · line: 12-month moving average',
        g_amp='Breadth: net buyers vs net sellers per month',
        g_amp_sub='Number of issuers',
        compradoras='Net buyers',
        vendedoras='Net sellers',
        prom12='12M average',
        st_tit='Monthly statistics (last 12M)',
        st_ult='Last month ({m})',
        st_prom='Average',
        st_med='Median',
        st_desv='Std. deviation',
        st_z='Last month z-score',
        st_max='Highest month',
        st_min='Lowest month',
        st_3m='3M average',
        st_comp='Buyers last month / 12M avg.',
        conc='Concentration & breadth',
        conc_sub='Who drives the flow · last 12 months',
        g_pareto='Share of LTM net buybacks',
        g_pareto_sub='% of total · bars: issuer share · line: cumulative share',
        acumulada='Cumulative',
        c_hhi='HHI (0–10,000)',
        c_neq='Equivalent # of issuers',
        c_med='Median buyback yield',
        c_1pct='Issuers with yield ≥ 1%',
        c_top10='Top-10 share',
        c_top5='Top-5 share',
        anual='Breadth and concentration by year',
        a_anio='Year',
        a_neto='Net amount',
        a_comp='Buyers',
        a_vend='Sellers',
        a_top5='Top-5 %',
        a_hhi='HHI',
        ejec='Program execution',
        ejec_sub='Top 25 net buyers, last 12 months · how often, at what price and how much fund is left',
        e_neto='Net LTM\n(MXN M)',
        e_yield='Yield\nLTM',
        e_int='Intensity\n(% days)',
        e_px='Avg. buy\nprice',
        e_cierre='Last\nclose',
        e_rend='Close vs\navg. buy',
        e_pos='Buy price in\n52w range',
        e_rem='Remaining\nfund (M)',
        e_remcap='Fund /\nmkt cap',
        e_meses='Months\nof fund*',
        ejec_nota='Intensity = days with purchases / trading days. Buy price in 52-week range: 0% = bought at the low, 100% = at the high. Months of fund* = remaining fund / average monthly purchases of the last 3 months. Close vs avg. buy = gain/loss on the shares repurchased at the current price. Remaining fund: last filing in the past 12 months.',
        momentum='Momentum & signals',
        momentum_sub='Changes in behavior · MXN Million per month',
        m_acel='Accelerating (3M vs 12M avg.)',
        m_desacel='Decelerating (3M vs 12M avg.)',
        m_pausa='Regular buyers on pause (45+ days without buying)',
        m_vend='Net sellers, last 12M (treasury resales)',
        m_inic='New buyers (first purchases in 15 months)',
        m_3m='3M avg.',
        m_12m='12M avg.',
        m_dif='Change',
        m_yld='Yield LTM',
        m_meses='Active months',
        m_ult='Last buy',
        m_dias='Days idle',
        m_rem='Fund (M)',
        m_neto='Net LTM',
        m_venta='Sold',
        m_pxv='Avg. sell',
        m_comp90='Bought 90d',
        m_prim='First buy',
        ninguna='None in the period',
        casas='Intermediaries',
        casas_sub='Broker-dealers executing buyback purchases · last 12 months (gross purchases)',
        g_casas='Share of gross buyback purchases',
        g_casas_sub='% of MXN amount · top 12 brokers',
        cb_casa='Broker',
        cb_monto='Purchases\n(MXN M)',
        cb_cuota='Share',
        cb_emis='Issuers',
        calidad='Data quality',
        q_avisos='Filings processed',
        q_corr='Filings superseded by a later correction',
        q_fibras='REIT (FIBRA) filings',
        q_emis='Issuers with activity',
        q_cob='Full-market coverage from',
        q_ult='Last trade date',
    ),
    "es": dict(
        portada="Recompras", sub_portada="Bolsa Mexicana de Valores · todas las emisoras",
        net="Recompra neta", cifras="–Cifras en millones de pesos", pie="RECOMPRA NETA",
        monto="Monto", yoy="Var. %", by="Buyback\nYield", emis="Emisoras", total="TOTAL",
        nota_sec="Buyback yield = recompra neta / valor de mercado (acciones en circulación × cierre al {corte}). "
                 "Emisoras = emisoras recomprando en el periodo. n.d. = antes del inicio de la cobertura de todo el mercado ({cob}).",
        top_yield="Top 20 últimos 12M {y} · Buyback Yield", top_yield_sub="Buyback Yield = acciones netas recompradas / acciones en circulación · Recuadro: precio promedio de compra 12M",
        top_comp="Top 20 compradores netos últimos 12M {y}", top_comp_sub="Cifras en millones de pesos",
        mensual="Recompra neta mes a mes", mensual_sub="Millones de pesos · top 3 emisoras por buyback yield del mes",
        rk_ytd="Recompra neta - ranking en el año", rk_5y="Recompra neta - ranking 5 años",
        rk_monto="Monto (millones de pesos)", rk_yield="Buyback Yield %", empresa="Emisora", yld="Yield %",
        periodo="–Periodo: {ini} – {fin}", det_sub="–Ordenado por buyback yield a 5 años",
        g_yield="Buyback Yield", g_monto="Monto (millones de pesos)", g_acc="Acciones (millones)",
        g_precio="Precio por acción {y} YTD", compra="Compra prom.", venta="Venta prom.", g_rem="Remanente\nfondo", rem2="(millones)",
        tot="Total", ytd="YTD", cobertura_parcial="*La cobertura de datos inicia el {cob}; periodos anteriores aparecen como n.d.",
        metodo="Metodología y aviso legal", pendiente="Sin datos", nd="n.d.",
        resumen='Resumen ejecutivo',
        resumen_sub='Cifras clave y hallazgos · datos al {corte}',
        k_ytd='Recompra neta {y} YTD',
        k_yoy='vs {y1} YTD',
        k_ltm='Recompra neta 12M',
        k_yield='Buyback yield 12M',
        k_emis='Emisoras comprando YTD',
        k_top5='Peso top 5 (12M)',
        k_rem='Fondos de recompra remanentes',
        k_rem_sub='{p} del valor de mercado',
        k_mxn='millones de pesos',
        hallazgos='Hallazgos principales',
        acum='Recompra neta acumulada por año',
        acum_sub='Millones de pesos · por día natural',
        dinamica='Dinámica del mercado',
        dinamica_sub='Flujos mensuales, amplitud y estadísticos · últimos 36 meses',
        g_men='Recompra neta por mes',
        g_men_sub='Millones de pesos · línea: promedio móvil de 12 meses',
        g_amp='Amplitud: compradoras vs vendedoras netas por mes',
        g_amp_sub='Número de emisoras',
        compradoras='Compradoras netas',
        vendedoras='Vendedoras netas',
        prom12='Promedio 12M',
        st_tit='Estadísticos mensuales (últimos 12M)',
        st_ult='Último mes ({m})',
        st_prom='Promedio',
        st_med='Mediana',
        st_desv='Desviación estándar',
        st_z='Z-score del último mes',
        st_max='Mes más alto',
        st_min='Mes más bajo',
        st_3m='Promedio 3M',
        st_comp='Compradoras último mes / prom. 12M',
        conc='Concentración y amplitud',
        conc_sub='Quién mueve el flujo · últimos 12 meses',
        g_pareto='Participación en la recompra neta 12M',
        g_pareto_sub='% del total · barras: peso de la emisora · línea: acumulado',
        acumulada='Acumulado',
        c_hhi='HHI (0–10,000)',
        c_neq='No. equivalente de emisoras',
        c_med='Buyback yield mediano',
        c_1pct='Emisoras con yield ≥ 1%',
        c_top10='Peso top 10',
        c_top5='Peso top 5',
        anual='Amplitud y concentración por año',
        a_anio='Año',
        a_neto='Monto neto',
        a_comp='Compradoras',
        a_vend='Vendedoras',
        a_top5='Top 5 %',
        a_hhi='HHI',
        ejec='Ejecución de los programas',
        ejec_sub='Top 25 compradores netos, últimos 12 meses · con qué frecuencia, a qué precio y cuánto fondo les queda',
        e_neto='Neto 12M\n(millones)',
        e_yield='Yield\n12M',
        e_int='Intensidad\n(% días)',
        e_px='Precio prom.\ncompra',
        e_cierre='Último\ncierre',
        e_rend='Cierre vs\nprom. compra',
        e_pos='Compra en\nrango 52s',
        e_rem='Fondo\nremanente (M)',
        e_remcap='Fondo /\nvalor merc.',
        e_meses='Meses\nde fondo*',
        ejec_nota='Intensidad = días con compra / días hábiles. Compra en rango de 52 semanas: 0% = compró en el mínimo, 100% = en el máximo. Meses de fondo* = fondo remanente / compras mensuales promedio de los últimos 3 meses. Cierre vs prom. compra = ganancia/pérdida de las acciones recompradas al precio actual. Fondo remanente: último aviso de los últimos 12 meses.',
        momentum='Momentum y señales',
        momentum_sub='Cambios de comportamiento · millones de pesos por mes',
        m_acel='Aceleran (promedio 3M vs 12M)',
        m_desacel='Desaceleran (promedio 3M vs 12M)',
        m_pausa='Recompradores habituales en pausa (45+ días sin comprar)',
        m_vend='Vendedoras netas 12M (recolocación de tesorería)',
        m_inic='Nuevas compradoras (primeras compras en 15 meses)',
        m_3m='Prom. 3M',
        m_12m='Prom. 12M',
        m_dif='Cambio',
        m_yld='Yield 12M',
        m_meses='Meses activos',
        m_ult='Última compra',
        m_dias='Días sin',
        m_rem='Fondo (M)',
        m_neto='Neto 12M',
        m_venta='Vendido',
        m_pxv='Precio venta',
        m_comp90='Compra 90d',
        m_prim='Primera compra',
        ninguna='Ninguna en el periodo',
        casas='Intermediarios',
        casas_sub='Casas de bolsa que ejecutan las recompras · últimos 12 meses (compras brutas)',
        g_casas='Participación en las compras de recompra',
        g_casas_sub='% del monto en pesos · top 12 casas',
        cb_casa='Casa de bolsa',
        cb_monto='Compras\n(millones)',
        cb_cuota='Participación',
        cb_emis='Emisoras',
        calidad='Calidad de datos',
        q_avisos='Avisos procesados',
        q_corr='Avisos sustituidos por una corrección posterior',
        q_fibras='Avisos de FIBRAs',
        q_emis='Emisoras con actividad',
        q_cob='Cobertura de todo el mercado desde',
        q_ult='Última operación',
    ),
}

METODOLOGIA = {
    "en": [
        "Source: public buyback filings (\"Información de recompra\") published by Bolsa Mexicana de Valores for every issuer, "
        "collected automatically each business day. Closing prices: Yahoo Finance.",
        "Net buybacks = amount bought − amount sold by each issuer's buyback fund, in MXN, by trade date.",
        "Buyback yield = net shares bought back / outstanding shares reported in the issuer's latest filing. "
        "Sector yield = sector net buybacks / sector market value (outstanding shares × close at the cut-off date).",
        "Sector classification: data/sectores.csv (editable). Periods that start before the full-market data coverage "
        "are shown as n.d. rather than as partial figures.",
        "Includes REIT (FIBRA) CBFI buybacks, which the exchange publishes under a separate filing type.",
        "Corrections: when an issuer files again for the same trade date starting from the same remaining-fund balance "
        "(broker change, typing error, resend), the later filing replaces the earlier one; operations re-filed with the "
        "same folio and zero shares are treated as cancellations. Former tickers are merged into the current one "
        "(e.g. ALFA → SIGMAF).",
        "Momentum compares the average monthly net amount of the last 3 complete months with the last 12. "
        "Concentration uses the Herfindahl-Hirschman index over net buyers.",
    ],
    "es": [
        "Fuente: avisos públicos de recompra (\"Información de recompra\") que publica la Bolsa Mexicana de Valores para cada "
        "emisora, recolectados automáticamente cada día hábil. Precios de cierre: Yahoo Finance.",
        "Recompra neta = importe comprado − importe vendido por el fondo de recompra de cada emisora, en pesos, por fecha de operación.",
        "Buyback yield = acciones netas recompradas / acciones en circulación del último aviso de la emisora. "
        "Yield sectorial = recompra neta del sector / valor de mercado del sector (circulación × cierre a la fecha de corte).",
        "Clasificación sectorial: data/sectores.csv (editable). Los periodos que inician antes de la cobertura de todo el "
        "mercado aparecen como n.d. en lugar de cifras parciales.",
        "Incluye las recompras de CBFIs de FIBRAs, que la Bolsa publica como un tipo de aviso distinto.",
        "Correcciones: cuando una emisora vuelve a publicar para la misma fecha de operación partiendo del mismo remanente "
        "(cambio de casa de bolsa, error de captura, reenvío), el aviso posterior sustituye al anterior; las operaciones "
        "republicadas con el mismo folio y 0 acciones se tratan como cancelaciones. Las claves anteriores se unen a la "
        "vigente (p. ej. ALFA → SIGMAF).",
        "El momentum compara el monto neto mensual promedio de los últimos 3 meses completos contra el de 12 meses. "
        "La concentración usa el índice Herfindahl-Hirschman sobre las compradoras netas.",
    ],
}

AVISO_GENERICO = {
    "en": "This document is for informational purposes only and does not constitute an offer, recommendation or "
          "solicitation to buy or sell any security. Figures are compiled from public filings and third-party prices "
          "that may contain errors or omissions; no guarantee is given as to their accuracy or completeness.",
    "es": "Este documento tiene fines exclusivamente informativos y no constituye una oferta, recomendación ni "
          "solicitud de compra o venta de valores. Las cifras se integran de avisos públicos y precios de terceros que "
          "pueden contener errores u omisiones; no se garantiza su exactitud ni su integridad.",
}


# ---------------------------------------------------------------------------
# Fuentes
# ---------------------------------------------------------------------------

_FUENTES = {
    "regular": ["C:/Windows/Fonts/calibri.ttf", "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "bold": ["C:/Windows/Fonts/calibrib.ttf", "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "light": ["C:/Windows/Fonts/calibril.ttf", "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}
_F = {"regular": "Helvetica", "bold": "Helvetica-Bold", "light": "Helvetica"}
_MPL_FAMILIA = None


def _registrar_fuentes() -> None:
    global _MPL_FAMILIA
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for peso, rutas in _FUENTES.items():
        ruta = next((r for r in rutas if Path(r).exists()), None)
        if ruta:
            nombre = f"PT-{peso}"
            if nombre not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(nombre, ruta))
            _F[peso] = nombre
    if _MPL_FAMILIA is None:
        from matplotlib import font_manager
        for peso in ("regular", "bold"):
            ruta = next((r for r in _FUENTES[peso] if Path(r).exists()), None)
            if ruta:
                font_manager.fontManager.addfont(ruta)
                if peso == "regular":
                    _MPL_FAMILIA = font_manager.FontProperties(fname=ruta).get_name()
        _MPL_FAMILIA = _MPL_FAMILIA or "DejaVu Sans"


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------

def _f_monto(v, nd="n.d.") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return nd
    r = round(v)
    if r == 0 and v != 0:
        return "0"
    return f"({abs(r):,.0f})" if r < 0 else f"{r:,.0f}"


def _f_pct(v, dec=1, nd="n.d.") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return nd
    return f"{v:.{dec}f}%"


def _f_yoy(v, nd="n.d.") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return nd
    if v > 300:
        return ">300%"
    if v < -300:
        return "<-300%"
    return f"{v:.0f}%"


def _f_num(v, dec=1, nd="n.d.") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return nd
    return f"{v:,.{dec}f}"


def _neg(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v)) and v < 0


def _fecha_larga(d: date, idioma: str) -> str:
    if idioma == "es":
        return f"{d.day} de {MESES['es'][d.month - 1]} de {d.year}"
    return f"{MESES['en'][d.month - 1]} {d.day}, {d.year}"


def _mes_anio(d: date, idioma: str) -> str:
    m = MESES[idioma][d.month - 1]
    return f"{m.capitalize()} {d.year}"


def _hex(c: str):
    from reportlab.lib import colors
    return colors.HexColor(c)


# ---------------------------------------------------------------------------
# Gráficas (matplotlib → PNG)
# ---------------------------------------------------------------------------

def _fig_png(fig) -> io.BytesIO:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=220, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def _estilo_ax(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#C9BFD3")
    ax.tick_params(colors=TEXT, labelsize=7, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _g_top_yield(df: pd.DataFrame, titulo: str, sub: str, ancho_pt: float, alto_pt: float) -> io.BytesIO:
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = _MPL_FAMILIA
    fig, ax = plt.subplots(figsize=(ancho_pt / 72, alto_pt / 72))
    fig.subplots_adjust(left=0.05, right=0.995, top=0.70, bottom=0.22)
    x = np.arange(len(df))
    ax.bar(x, df["YIELD"], color=PURPLE, width=0.62, zorder=2)
    ymax = max(df["YIELD"].max() * 1.15, 1)
    ax.set_ylim(0, ymax)
    for i, v in enumerate(df["YIELD"]):
        ax.text(i, v + ymax * 0.02, f"{v:.1f}%", ha="center", va="bottom", fontsize=7, color=PURPLE_DARK)
        px = df["PRECIO_PROM"].iat[i]
        ax.annotate(f"P${px:,.0f}" if pd.notna(px) else "—", xy=(i, 1.06), xycoords=("data", "axes fraction"),
                    ha="center", va="bottom", fontsize=6.5, color="white",
                    bbox=dict(boxstyle="round,pad=0.35", fc=PURPLE_DARK, ec="none"))
    ax.set_xticks(x, df.index, rotation=90, fontsize=7)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    _estilo_ax(ax)
    fig.text(0.005, 0.97, titulo, fontsize=11, fontweight="bold", color=TEXT, va="top")
    fig.text(0.005, 0.89, sub, fontsize=7.5, color=MUTED, va="top")
    return _fig_png(fig)


def _g_top_compradores(df: pd.DataFrame, titulo: str, sub: str, ancho_pt: float, alto_pt: float) -> io.BytesIO:
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = _MPL_FAMILIA
    fig, ax = plt.subplots(figsize=(ancho_pt / 72, alto_pt / 72))
    fig.subplots_adjust(left=0.15, right=0.97, top=0.84, bottom=0.07)
    d = df.iloc[::-1]
    vals = d["NETO_MXN"] / 1e6
    y = np.arange(len(d))
    ax.barh(y, vals, color=PURPLE, height=0.62, zorder=2)
    xmax = max(vals.max(), 1) * 1.16
    ax.set_xlim(min(0, vals.min() * 1.1), xmax)
    for i, v in enumerate(vals):
        ax.text(v + xmax * 0.01, i, f"{v:,.0f}", va="center", fontsize=6.8, color=PURPLE_DARK)
    ax.set_yticks(y, d.index, fontsize=7)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    _estilo_ax(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    fig.text(0.01, 0.985, titulo, fontsize=11, fontweight="bold", color=TEXT, va="top")
    fig.text(0.01, 0.925, sub, fontsize=7.5, color=MUTED, va="top")
    return _fig_png(fig)


def _g_mensual(df: pd.DataFrame, titulo: str, sub: str, idioma: str, ancho_pt: float, alto_pt: float) -> io.BytesIO:
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = _MPL_FAMILIA
    fig, ax = plt.subplots(figsize=(ancho_pt / 72, alto_pt / 72))
    fig.subplots_adjust(left=0.09, right=0.99, top=0.84, bottom=0.08)
    x = np.arange(len(df))
    vals = df["NETO_MXN"].astype(float)
    ax.bar(x, vals.fillna(0), color=PURPLE, width=0.55, zorder=2)
    ymax = max(np.nanmax(vals.values) if vals.notna().any() else 1, 1) * 1.55
    ax.set_ylim(min(0, np.nanmin(vals.values) * 1.2 if vals.notna().any() else 0), ymax)
    for i, (v, top) in enumerate(zip(vals, df["TOP"])):
        if pd.isna(v):
            ax.text(i, ymax * 0.02, L[idioma]["nd"], ha="center", va="bottom", fontsize=6.5, color=MUTED)
            continue
        etiqueta = "\n".join(f"{e} {y:.1f}%" for e, y in top)
        ax.text(i, max(v, 0) + ymax * 0.015, etiqueta, ha="center", va="bottom", fontsize=5.6,
                color=PURPLE_DARK, linespacing=1.15)
    ax.set_xticks(x, [MES_CORTO[idioma][m.month - 1] + ("\n" + str(m.year) if m.month == 1 or i == 0 else "")
                      for i, m in enumerate(df["MES"])], fontsize=7)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}" if v else "–")
    _estilo_ax(ax)
    fig.text(0.01, 0.985, titulo, fontsize=11, fontweight="bold", color=TEXT, va="top")
    fig.text(0.01, 0.925, sub, fontsize=7.5, color=MUTED, va="top")
    return _fig_png(fig)


# ---------------------------------------------------------------------------
# Tablas (reportlab)
# ---------------------------------------------------------------------------

def _estilo_base(n_cab: int, fs: float, total_fila: int | None = None):
    from reportlab.platypus import TableStyle
    st = [
        ("FONT", (0, 0), (-1, -1), _F["regular"], fs),
        ("FONT", (0, 0), (-1, n_cab - 1), _F["bold"], fs),
        ("TEXTCOLOR", (0, 0), (-1, -1), _hex(TEXT)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, n_cab - 1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    if total_fila is not None:
        st += [("BACKGROUND", (0, total_fila), (-1, total_fila), _hex(LAVENDER)),
               ("FONT", (0, total_fila), (-1, total_fila), _F["bold"], fs)]
    return TableStyle(st)


def _tabla_sectores(d: rd.Datos, idioma: str):
    from reportlab.platypus import Table
    t = L[idioma]
    per = d.periodos
    grupos = [("Y2", False), ("Y1", True), ("LTM", False), ("YTD1", False), ("YTD", True)]
    fila0, fila1, spans = [""], [""], []
    col = 1
    for k, con_yoy in grupos:
        sub = [t["monto"]] + ([t["yoy"]] if con_yoy else []) + [t["by"], t["emis"]]
        fila0 += [per[k].etiqueta] + [""] * (len(sub) - 1)
        spans.append((col, col + len(sub) - 1))
        fila1 += sub
        col += len(sub)
    datos, negativos = [fila0, fila1], []
    for i, r in enumerate(d.sectores.itertuples(index=False), start=2):
        r = r._asdict()
        fila = [r["SECTOR"] if r["SECTOR"] != "TOTAL" else t["total"]]
        for k, con_yoy in grupos:
            vals = [(_f_monto(r[f"{k}_MONTO"]), r[f"{k}_MONTO"])]
            if con_yoy:
                vals.append((_f_yoy(r[f"{k}_YOY"]), r[f"{k}_YOY"]))
            vals += [(_f_pct(r[f"{k}_YIELD"]), r[f"{k}_YIELD"]),
                     (_f_monto(r[f"{k}_EMIS"]), None)]
            for txt, v in vals:
                if _neg(v):
                    negativos.append((len(fila), i))
                fila.append(txt)
        datos.append(fila)
    ancho_sector = 118
    resto = (PAGE_W - 2 * M - ancho_sector) / (len(fila0) - 1)
    tabla = Table(datos, colWidths=[ancho_sector] + [resto] * (len(fila0) - 1), repeatRows=2,
                  rowHeights=[16, 24] + [22] * (len(datos) - 2))
    st = _estilo_base(2, 7.6, total_fila=len(datos) - 1)
    st.add("BACKGROUND", (1, 0), (-1, 0), _hex(PURPLE))
    st.add("TEXTCOLOR", (1, 0), (-1, 0), _hex("#FFFFFF"))
    st.add("BACKGROUND", (1, 1), (-1, 1), _hex(PURPLE_MID))
    st.add("FONT", (1, 1), (-1, 1), _F["regular"], 6.8)
    st.add("ALIGN", (1, 2), (-1, -1), "RIGHT")
    st.add("FONT", (0, 2), (0, -1), _F["bold"], 7)
    for a, b in spans:
        st.add("SPAN", (a, 0), (b, 0))
        st.add("LINEBEFORE", (a, 0), (a, -1), 0.8, _hex(PURPLE))
    # Sombrea el bloque YTD (como el reporte de referencia)
    ytd_ini = spans[-1][0]
    st.add("BACKGROUND", (ytd_ini, 2), (-1, len(datos) - 2), _hex(LAVENDER_SOFT))
    for c, rr in negativos:
        st.add("TEXTCOLOR", (c, rr), (c, rr), _hex(RED))
    for rr in range(2, len(datos) - 1):
        st.add("LINEBELOW", (0, rr), (-1, rr), 0.3, _hex(GRID))
    tabla.setStyle(st)
    return tabla


def _tabla_ranking(rk: pd.DataFrame, idioma: str, filas_max: int = 30):
    from reportlab.platypus import Table
    t = L[idioma]
    monto = rk.sort_values("MONTO", ascending=False)
    yld = rk.dropna(subset=["YIELD"]).sort_values("YIELD", ascending=False)
    n = max(len(monto), len(yld), 1)
    g = max(2, math.ceil(n / filas_max))           # grupos de columnas por lado
    filas = math.ceil(n / g)

    def bloques(df, col, fmt):
        out = []
        for k in range(g):
            parte = df.iloc[k * filas:(k + 1) * filas]
            out.append([(str(k * filas + i + 1), e, fmt(v), v) for i, (e, v) in enumerate(zip(parte.index, parte[col]))])
        return out
    izq, der = bloques(monto, "MONTO", _f_monto), bloques(yld, "YIELD", lambda v: _f_pct(v))
    cab0 = [t["rk_monto"]] + [""] * (3 * g - 1) + [""] + [t["rk_yield"]] + [""] * (3 * g - 1)
    cab1 = (["#", t["empresa"], t["monto"]] * g) + [""] + (["#", t["empresa"], t["yld"]] * g)
    datos, negativos = [cab0, cab1], []
    for i in range(filas):
        fila = []
        for lado_i, lado in enumerate((izq, der)):
            if lado_i == 1:
                fila.append("")
            for b in lado:
                if i < len(b):
                    num, emi, txt, v = b[i]
                    if _neg(v):
                        negativos.append((len(fila) + 2, i + 2))
                    fila += [num, emi, txt]
                else:
                    fila += ["", "", ""]
        datos.append(fila)
    ancho_util = PAGE_W - 2 * M
    gap = 14
    w_num, w_val = 16, 44 if g <= 2 else 38
    w_emp = (ancho_util - gap - 2 * g * (w_num + w_val)) / (2 * g)
    w_emp = min(w_emp, 70)
    widths = ([w_num, w_emp, w_val] * g) + [gap] + ([w_num, w_emp, w_val] * g)
    alto = min(14, 430 / (filas + 2))
    fs = min(7.4, alto * 0.56)
    tabla = Table(datos, colWidths=widths, rowHeights=[15, 15] + [alto] * filas)
    st = _estilo_base(2, fs)
    izq_fin = 3 * g - 1
    der_ini = izq_fin + 2
    st.add("SPAN", (0, 0), (izq_fin, 0))
    st.add("SPAN", (der_ini, 0), (-1, 0))
    st.add("BACKGROUND", (0, 0), (izq_fin, 0), _hex(PURPLE))
    st.add("BACKGROUND", (der_ini, 0), (-1, 0), _hex(TEAL))
    st.add("BACKGROUND", (0, 1), (izq_fin, 1), _hex(PURPLE_DARK))
    st.add("BACKGROUND", (der_ini, 1), (-1, 1), _hex("#0A6F6B"))
    st.add("TEXTCOLOR", (0, 0), (-1, 1), _hex("#FFFFFF"))
    for k in range(2 * g):
        c0 = 3 * k + (1 if k >= g else 0)
        st.add("ALIGN", (c0, 2), (c0, -1), "CENTER")
        st.add("ALIGN", (c0 + 2, 2), (c0 + 2, -1), "RIGHT")
        st.add("BOX", (c0, 1), (c0 + 2, -1), 0.5, _hex(PURPLE_MID))
    for rr in range(2, len(datos)):
        if rr % 2 == 1:
            st.add("BACKGROUND", (0, rr), (izq_fin, rr), _hex(LAVENDER_SOFT))
            st.add("BACKGROUND", (der_ini, rr), (-1, rr), _hex(LAVENDER_SOFT))
    for c, rr in negativos:
        st.add("TEXTCOLOR", (c, rr), (c, rr), _hex(RED))
    tabla.setStyle(st)
    return tabla


def _tablas_detalle(d: rd.Datos, idioma: str, filas_pag: int = 38):
    from reportlab.platypus import Table
    t = L[idioma]
    anios = d.anios
    etiq_anio = [str(y) for y in anios[:-1]] + [f"{anios[-1]} {t['ytd']}"]
    cab0 = ["#", t["empresa"], t["g_yield"]] + [""] * 5 + [t["g_monto"]] + [""] * 5 + [t["g_acc"]] + [""] * 5 + \
           [t["g_precio"].format(y=anios[-1]), "", t["g_rem"]]
    cab1 = ["", ""] + ([t["tot"]] + etiq_anio) * 3 + [t["compra"], t["venta"], t["rem2"]]
    filas = []
    for i, (emi, r) in enumerate(d.detalle.iterrows(), start=1):
        vals = [(_f_pct(r["YTOT"]), r["YTOT"])] + [(_f_pct(r[f"Y{y}"]), r[f"Y{y}"]) for y in anios] + \
               [(_f_monto(r["MTOT"]), r["MTOT"])] + [(_f_monto(r[f"M{y}"]), r[f"M{y}"]) for y in anios] + \
               [(_f_num(r["ATOT"]), r["ATOT"])] + [(_f_num(r[f"A{y}"]), r[f"A{y}"]) for y in anios] + \
               [(_f_num(r["PX_COMPRA"], nd=""), None), (_f_num(r["PX_VENTA"], nd=""), None),
                (_f_monto(r["REMANENTE"], nd=""), None)]
        filas.append((str(i), emi, vals))
    widths_fijos = [18, 52]
    resto = (PAGE_W - 2 * M - sum(widths_fijos) - 46) / 20
    widths = widths_fijos + [resto] * 20 + [46]
    tablas = []
    for p in range(0, max(len(filas), 1), filas_pag):
        bloque = filas[p:p + filas_pag]
        datos, negativos = [cab0, cab1], []
        for ri, (num, emi, vals) in enumerate(bloque, start=2):
            fila = [num, emi]
            for txt, v in vals:
                if _neg(v):
                    negativos.append((len(fila), ri))
                fila.append(txt)
            datos.append(fila)
        tabla = Table(datos, colWidths=widths, rowHeights=[22, 15] + [11] * len(bloque), repeatRows=2)
        st = _estilo_base(2, 6.4)
        for a, b in ((2, 7), (8, 13), (14, 19), (20, 21)):
            st.add("SPAN", (a, 0), (b, 0))
            st.add("LINEBEFORE", (a, 0), (a, -1), 0.8, _hex(PURPLE))
        st.add("LINEBEFORE", (22, 0), (22, -1), 0.8, _hex(PURPLE))
        st.add("BACKGROUND", (0, 0), (-1, 0), _hex(PURPLE))
        st.add("TEXTCOLOR", (0, 0), (-1, 0), _hex("#FFFFFF"))
        st.add("BACKGROUND", (0, 1), (-1, 1), _hex(PURPLE_MID))
        st.add("ALIGN", (2, 2), (-1, -1), "RIGHT")
        st.add("ALIGN", (0, 2), (0, -1), "CENTER")
        st.add("FONT", (1, 2), (1, -1), _F["bold"], 6.4)
        for rr in range(2, len(datos)):
            if rr % 2 == 1:
                st.add("BACKGROUND", (0, rr), (-1, rr), _hex(LAVENDER_SOFT))
        for c, rr in negativos:
            st.add("TEXTCOLOR", (c, rr), (c, rr), _hex(RED))
        tabla.setStyle(st)
        tablas.append(tabla)
    return tablas


# ---------------------------------------------------------------------------
# Páginas (canvas)
# ---------------------------------------------------------------------------

def _logo(c, x_der: float, y_top: float, blanco: bool = False):
    """Logotipo arriba a la derecha: archivo oficial si existe, si no wordmark de texto."""
    for nombre in ("logo_punto_blanco.png" if blanco else "logo_punto.png", "logo_punto.png"):
        p = ASSETS / nombre
        if p.exists():
            from reportlab.lib.utils import ImageReader
            img = ImageReader(str(p))
            iw, ih = img.getSize()
            h = 34
            w = iw * h / ih
            c.drawImage(img, x_der - w, y_top - h, w, h, mask="auto")
            return
    gris, morado = ("#FFFFFF", "#FFFFFF") if blanco else (GRAY, PURPLE)
    from reportlab.pdfbase.pdfmetrics import stringWidth
    f = _F["bold"]
    w_punt, w_o = stringWidth("punt", f, 26), stringWidth("o", f, 26)
    x0 = x_der - w_punt - w_o
    c.setFont(f, 26)
    c.setFillColor(_hex(gris)); c.drawString(x0, y_top - 22, "punt")
    c.setFillColor(_hex(morado)); c.drawString(x0 + w_punt, y_top - 22, "o")
    c.setFont(_F["regular"], 8.5)
    c.setFillColor(_hex(gris)); c.drawRightString(x_der, y_top - 33, "casa de bolsa")


def _portada(c, doc, edicion: str, idioma: str):
    t = L[idioma]
    foto = ASSETS / "portada.jpg"
    c.saveState()
    if foto.exists():
        c.drawImage(str(foto), 0, 0, PAGE_W, PAGE_H, preserveAspectRatio=False)
        c.setFillColor(_hex(PURPLE)); c.setFillAlpha(0.25); c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    else:
        c.setFillColor(_hex(PURPLE)); c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        # Composición geométrica en tonos de la marca
        for (x, y, r, col, a) in [(700, 520, 260, "#8A4FB8", 0.55), (840, 140, 220, PURPLE_DARK, 0.55),
                                  (520, 640, 160, "#9B66C7", 0.35), (160, 610, 120, "#8A4FB8", 0.30),
                                  (620, 260, 90, LAVENDER, 0.18)]:
            c.setFillColor(_hex(col)); c.setFillAlpha(a); c.circle(x, y, r, stroke=0, fill=1)
        c.setFillAlpha(1)
        c.setStrokeColor(_hex(LAVENDER)); c.setStrokeAlpha(0.35); c.setLineWidth(0.8)
        for k in range(9):
            c.line(430 + k * 38, 0, 880, 330 - k * 38)
        c.setStrokeAlpha(1)
    c.setFillAlpha(1)
    _logo(c, PAGE_W - 40, PAGE_H - 36, blanco=True)
    # Tarjeta blanca con título y edición
    c.setFillColor(_hex("#FFFFFF"))
    c.roundRect(40, 46, 300, 110, 16, stroke=0, fill=1)
    c.setFillColor(_hex(TEXT)); c.setFont(_F["regular"], 26); c.drawString(62, 112, t["portada"])
    c.setStrokeColor(_hex(TEXT)); c.setLineWidth(0.7); c.line(62, 96, 318, 96)
    c.setFont(_F["regular"], 11); c.drawString(62, 72, edicion)
    c.setFillColor(_hex("#FFFFFF")); c.setFont(_F["regular"], 8.5)
    c.drawRightString(PAGE_W - 40, 30, t["sub_portada"])
    c.restoreState()


def _marco(c, doc, fecha_pub: str, idioma: str):
    c.saveState()
    c.setFillColor(_hex(MUTED)); c.setFont(_F["regular"], 8.5)
    c.drawString(M, PAGE_H - 40, fecha_pub)
    _logo(c, PAGE_W - M, PAGE_H - 24)
    c.setFont(_F["regular"], 7.5)
    c.drawRightString(PAGE_W - M, 16, f"{L[idioma]['pie']}  |  {doc.page}")
    c.setStrokeColor(_hex(LAVENDER)); c.setLineWidth(2); c.line(M, 26, M + 60, 26)
    c.restoreState()


# ---------------------------------------------------------------------------
# Ensamble
# ---------------------------------------------------------------------------

def generar_pdf(actividad: pd.DataFrame, documentos: pd.DataFrame, mercado: pd.DataFrame, corte: date,
                idioma: str = "en", fecha_publicacion: date | None = None, edicion: date | None = None) -> bytes:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (BaseDocTemplate, Frame, Image, NextPageTemplate, PageBreak, PageTemplate,
                                    Paragraph, Spacer, Table)

    from src import reporte_analisis as ra
    from src import reporte_pdf_secciones as sec

    _registrar_fuentes()
    t = L[idioma]
    d = rd.preparar(actividad, documentos, mercado, corte)
    an = ra.analizar(actividad, documentos, mercado, corte, d=d)
    fecha_pub = _fecha_larga(fecha_publicacion or corte, idioma)
    edicion_txt = _mes_anio(edicion or (fecha_publicacion or corte), idioma)
    cob_txt = d.cobertura.strftime("%d/%m/%Y") if d.cobertura else "—"

    est_tit = ParagraphStyle("tit", fontName=_F["regular"], fontSize=24, leading=27, textColor=_hex(TEXT))
    est_sub = ParagraphStyle("sub", fontName=_F["regular"], fontSize=8.2, leading=10.5, textColor=_hex(MUTED))
    est_nota = ParagraphStyle("nota", fontName=_F["regular"], fontSize=7, leading=9, textColor=_hex(MUTED))
    est_txt = ParagraphStyle("txt", fontName=_F["regular"], fontSize=9.5, leading=13.5, textColor=_hex(TEXT))
    est_h2 = ParagraphStyle("h2", fontName=_F["bold"], fontSize=12, leading=16, textColor=_hex(PURPLE))

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=(PAGE_W, PAGE_H), leftMargin=M, rightMargin=M, topMargin=TOP,
                          bottomMargin=34, title=f"{t['portada']} · {edicion_txt}", author="Punto Casa de Bolsa")
    marco = Frame(M, 34, PAGE_W - 2 * M, PAGE_H - TOP - 34, id="f", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate("portada", frames=[Frame(0, 0, PAGE_W, PAGE_H, id="p")],
                     onPage=lambda c, dd: _portada(c, dd, edicion_txt, idioma)),
        PageTemplate("normal", frames=[marco], onPage=lambda c, dd: _marco(c, dd, fecha_pub, idioma)),
    ])
    ancho = PAGE_W - 2 * M
    parcial = d.cobertura and d.cobertura > d.periodos["Y2"].ini

    s = [NextPageTemplate("normal"), PageBreak()]

    # 2. Resumen ejecutivo
    s += sec.pagina_resumen(an, d, idioma, ancho)

    # 3. Sectores
    s += [Paragraph(t["net"], est_tit), Spacer(1, 2), Paragraph(t["cifras"], est_sub), Spacer(1, 8),
          _tabla_sectores(d, idioma), Spacer(1, 6),
          Paragraph(t["nota_sec"].format(corte=d.corte.strftime("%d/%m/%Y"), cob=cob_txt), est_nota), PageBreak()]

    # 4. Dinámica del mercado
    s += sec.pagina_dinamica(an, d, idioma, ancho)

    # 5. Gráficas top 20
    y = d.corte.year
    ltm_nota = "" if rd.cubierto(d.periodos["LTM"].ini, d.cobertura) else f"  ·  {t['cobertura_parcial'].format(cob=cob_txt)}"
    h1, h2 = 190, 262
    g1 = _g_top_yield(d.top_yield_ltm, t["top_yield"].format(y=y), t["top_yield_sub"] + ltm_nota, ancho, h1)
    g2 = _g_top_compradores(d.top_compradores_ltm, t["top_comp"].format(y=y), t["top_comp_sub"] + ltm_nota, ancho * 0.44, h2)
    g3 = _g_mensual(d.mensual, t["mensual"], t["mensual_sub"], idioma, ancho * 0.555, h2)
    s += [Paragraph(t["net"], est_tit), Spacer(1, 4), Image(g1, ancho, h1), Spacer(1, 2),
          Table([[Image(g2, ancho * 0.44, h2), Image(g3, ancho * 0.555, h2)]], colWidths=[ancho * 0.445, ancho * 0.555],
                style=[("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
          PageBreak()]

    # 6–9. Concentración, ejecución, momentum, intermediarios
    s += sec.pagina_concentracion(an, d, idioma, ancho)
    s += sec.pagina_ejecucion(an, d, idioma, ancho)
    s += sec.pagina_momentum(an, d, idioma, ancho)
    s += sec.pagina_casas(an, d, idioma, ancho)

    # 10. Ranking YTD
    fmt_f = lambda f: f"{MES_CORTO[idioma][f.month - 1]} {f.year}"
    s += [Paragraph(t["rk_ytd"], est_tit), Spacer(1, 2), Paragraph(t["cifras"], est_sub),
          Paragraph(t["periodo"].format(ini=fmt_f(d.periodos["YTD"].ini), fin=d.corte.strftime("%d/%m/%Y")), est_sub),
          Spacer(1, 8), _tabla_ranking(d.ranking_ytd, idioma), PageBreak()]

    # 5. Ranking 5 años
    s += [Paragraph(t["rk_5y"], est_tit), Spacer(1, 2), Paragraph(t["cifras"], est_sub),
          Paragraph(t["periodo"].format(ini=fmt_f(d.ini_5y), fin=d.corte.strftime("%d/%m/%Y")) +
                    (f"  {t['cobertura_parcial'].format(cob=cob_txt)}" if parcial else ""), est_sub),
          Spacer(1, 8), _tabla_ranking(d.ranking_5y, idioma, filas_max=30), PageBreak()]

    # 6+. Detalle
    for i, tabla in enumerate(_tablas_detalle(d, idioma)):
        s += [Paragraph(t["net"], est_tit), Spacer(1, 2), Paragraph(t["cifras"], est_sub),
              Paragraph(t["det_sub"] + (f"  ·  {t['cobertura_parcial'].format(cob=cob_txt)}" if parcial else ""), est_sub),
              Spacer(1, 6), tabla, PageBreak()]

    # Último: metodología y aviso legal
    archivo_aviso = ASSETS / "aviso_legal.txt"
    aviso = archivo_aviso.read_text(encoding="utf-8").strip() if archivo_aviso.exists() else AVISO_GENERICO[idioma]
    s += [Paragraph(t["metodo"], est_tit), Spacer(1, 14)]
    for p in METODOLOGIA[idioma]:
        s += [Paragraph("•  " + p, est_txt), Spacer(1, 5)]
    s += [Spacer(1, 6)] + sec.bloque_calidad(an, idioma, ancho)
    s += [Spacer(1, 10), Paragraph("Aviso legal" if idioma == "es" else "Disclosures", est_h2), Spacer(1, 4)]
    for parrafo in aviso.split("\n\n"):
        s += [Paragraph(parrafo.replace("\n", " "), est_txt), Spacer(1, 6)]
    if not archivo_aviso.exists():
        s += [Spacer(1, 8), Paragraph(
            "Texto genérico. Coloque el aviso legal oficial de la casa de bolsa en assets/aviso_legal.txt "
            "antes de distribuir este documento.", est_nota)]
    gen = datetime.now(timezone(timedelta(hours=-6))).strftime("%d/%m/%Y %H:%M")
    s += [Spacer(1, 14), Paragraph(f"{'Generado' if idioma == 'es' else 'Generated'}: {gen} CDMX · "
                                   f"{'Datos al' if idioma == 'es' else 'Data as of'} {d.corte:%d/%m/%Y}", est_nota)]

    doc.build(s)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Automatización mensual (scanner)
# ---------------------------------------------------------------------------

def generar_mensual_si_corresponde(idioma: str = "en") -> Path | None:
    """
    En la primera corrida de cada mes, genera la edición del mes con datos al
    cierre del mes anterior: reportes/Buybacks_AAAA-MM.pdf. Devuelve la ruta o None.
    """
    import json
    hoy = datetime.now(timezone(timedelta(hours=-6))).date()
    edicion = f"{hoy:%Y-%m}"
    destino = REPORTES / f"Buybacks_{edicion}.pdf"
    estado_f = REPO / "data" / "daily" / "_state.json"
    estado = json.loads(estado_f.read_text(encoding="utf-8")) if estado_f.exists() else {}
    if estado.get("ultimo_reporte_mensual") == edicion and destino.exists():
        return None
    actividad, docs, mercado = rd.cargar_locales()
    if actividad.empty:
        return None
    fin_mes_ant = hoy.replace(day=1) - timedelta(days=1)
    fechas = pd.to_datetime(actividad["FECHA_OPERACION"]).dt.date
    previas = fechas[fechas <= fin_mes_ant]
    if previas.empty:
        return None
    corte = previas.max()
    pdf = generar_pdf(actividad, docs, mercado, corte, idioma=idioma, fecha_publicacion=hoy, edicion=hoy)
    REPORTES.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(pdf)
    estado["ultimo_reporte_mensual"] = edicion
    estado_f.write_text(json.dumps(estado, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return destino
