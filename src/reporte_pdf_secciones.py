"""
Secciones de análisis del reporte Net Buybacks (gráficas y tablas):
resumen ejecutivo, dinámica del mercado, concentración, ejecución de los
programas, momentum y señales, intermediarios y calidad de datos.

Reglas de visualización: una sola escala por gráfica, colores categóricos en
orden fijo (paleta validada de Punto), compras en verde / ventas en rojo,
etiquetas directas selectivas y leyenda cuando hay 2+ series.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src import reporte_analisis as ra
from src import reporte_datos as rd
from src import reporte_pdf as R

CAT = ["#7030A0", "#0E9A94", "#2063B0", "#C5770F", "#AB3276", "#599234"]
COMPRA = "#2E9E52"
VENTA = "#A9131F"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _plt():
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = R._MPL_FAMILIA
    return plt


def _titulos(fig, titulo: str, sub: str, y0: float = 0.985, dy: float = 0.075):
    fig.text(0.01, y0, titulo, fontsize=10.5, fontweight="bold", color=R.TEXT, va="top")
    fig.text(0.01, y0 - dy, sub, fontsize=7.3, color=R.MUTED, va="top")


def _leyenda(ax, ncol: int = 4, **kw):
    """Leyenda arriba del área de datos, alineada a la izquierda (nunca encima de las marcas)."""
    return ax.legend(frameon=False, fontsize=7, labelcolor=R.TEXT, handlelength=1.4, ncol=ncol,
                     loc="lower left", bbox_to_anchor=(0, 1.0), borderaxespad=0.2, columnspacing=1.4)


def _etiquetas_mes(indice, idioma: str) -> list[str]:
    """Etiqueta trimestral (Ene/Abr/Jul/Oct) con el año en enero o en el primer mes."""
    out = []
    for i, m in enumerate(indice):
        if (m.month - 1) % 3 == 0:
            out.append(R.MES_CORTO[idioma][m.month - 1] + (f"\n{m.year}" if m.month == 1 or i < 3 else ""))
        else:
            out.append("")
    return out


def _sin_pad():
    return [("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP")]


def _estilos():
    from reportlab.lib.styles import ParagraphStyle
    h = R._hex
    return {
        "tit": ParagraphStyle("tit", fontName=R._F["regular"], fontSize=24, leading=27, textColor=h(R.TEXT)),
        "sub": ParagraphStyle("sub", fontName=R._F["regular"], fontSize=8.2, leading=10.5, textColor=h(R.MUTED)),
        "h3": ParagraphStyle("h3", fontName=R._F["bold"], fontSize=10.5, leading=13, textColor=h(R.TEXT)),
        "nota": ParagraphStyle("nota", fontName=R._F["regular"], fontSize=6.8, leading=8.6, textColor=h(R.MUTED)),
        "bul": ParagraphStyle("bul", fontName=R._F["regular"], fontSize=8.8, leading=12.2, textColor=h(R.TEXT),
                              leftIndent=10, bulletIndent=0, spaceAfter=5),
        "k_lab": ParagraphStyle("kl", fontName=R._F["regular"], fontSize=7.2, leading=9, textColor=h(R.MUTED)),
        "k_val": ParagraphStyle("kv", fontName=R._F["bold"], fontSize=17, leading=20, textColor=h(R.PURPLE_DARK)),
        "k_sub": ParagraphStyle("ks", fontName=R._F["regular"], fontSize=7, leading=8.8, textColor=h(R.MUTED)),
        "k_pos": ParagraphStyle("kp", fontName=R._F["bold"], fontSize=7, leading=8.8, textColor=h(COMPRA)),
        "k_neg": ParagraphStyle("kn", fontName=R._F["bold"], fontSize=7, leading=8.8, textColor=h(VENTA)),
    }


def _tabla_simple(datos, widths, fs=7.2, alto=12.5, cab_color=None, alinear_izq=(0,), negativos=(), total=False):
    """Tabla compacta con encabezado morado y filas alternadas."""
    from reportlab.platypus import Table
    t = Table(datos, colWidths=widths, rowHeights=[None] + [alto] * (len(datos) - 1), repeatRows=1)
    st = R._estilo_base(1, fs, total_fila=len(datos) - 1 if total else None)
    st.add("BACKGROUND", (0, 0), (-1, 0), R._hex(cab_color or R.PURPLE))
    st.add("TEXTCOLOR", (0, 0), (-1, 0), R._hex("#FFFFFF"))
    st.add("FONT", (0, 0), (-1, 0), R._F["bold"], fs - 0.4)
    st.add("ALIGN", (0, 1), (-1, -1), "RIGHT")
    for c in alinear_izq:
        st.add("ALIGN", (c, 1), (c, -1), "LEFT")
    for rr in range(1, len(datos)):
        if rr % 2 == 0:
            st.add("BACKGROUND", (0, rr), (-1, rr), R._hex(R.LAVENDER_SOFT))
    for c, rr in negativos:
        st.add("TEXTCOLOR", (c, rr), (c, rr), R._hex(R.RED))
    t.setStyle(st)
    return t


# ---------------------------------------------------------------------------
# Gráficas
# ---------------------------------------------------------------------------

def g_acumulado(acum: pd.DataFrame, titulo: str, sub: str, idioma: str, w: float, h: float):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(w / 72, h / 72))
    fig.subplots_adjust(left=0.11, right=0.85, top=0.78, bottom=0.08)
    anios = list(acum.columns)
    actual = anios[-1] if anios else None
    previos = anios[:-1][::-1]                         # el más reciente primero → color fijo por antigüedad
    colores = {actual: CAT[0], **{y: CAT[i + 1] for i, y in enumerate(previos)}}
    for y in anios:
        s = acum[y].dropna()
        ax.plot(s.index, s.values, color=colores[y], lw=2.2 if y == actual else 1.4, label=str(y), zorder=3 if y == actual else 2)
        if y == actual or (previos and y == previos[0]):
            dy = 7 if y == actual else -7
            ax.annotate(f"{s.iloc[-1]:,.0f}", xy=(s.index[-1], s.iloc[-1]), xytext=(4, dy), textcoords="offset points",
                        fontsize=7, color=R.TEXT, va="center", annotation_clip=False,
                        fontweight="bold" if y == actual else "normal")
    inicio_mes = [pd.Timestamp(2001, m, 1).dayofyear for m in range(1, 13)]
    ax.set_xticks(inicio_mes, R.MES_CORTO[idioma], fontsize=6.8)
    ax.set_xlim(1, 366)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    R._estilo_ax(ax)
    _leyenda(ax, ncol=len(anios))
    _titulos(fig, titulo, sub, dy=0.06)
    return R._fig_png(fig)


def g_mensual36(men: pd.DataFrame, t: dict, idioma: str, w: float, h: float):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(w / 72, h / 72))
    fig.subplots_adjust(left=0.07, right=0.995, top=0.74, bottom=0.14)
    x = np.arange(len(men))
    ax.bar(x, men["NETO"], color=CAT[0], width=0.66, zorder=2, label="Net buybacks" if idioma == "en" else "Recompra neta")
    ax.plot(x, men["PROM_12M"], color=CAT[1], lw=2, zorder=3, label=t["prom12"])
    ult = len(men) - 1
    ax.annotate(f"{men['NETO'].iat[ult]:,.0f}", xy=(ult, men["NETO"].iat[ult]), xytext=(0, 3), textcoords="offset points",
                ha="center", fontsize=6.6, color=R.TEXT)
    ax.set_xticks(x, _etiquetas_mes(men.index, idioma), fontsize=6.6)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.axhline(0, color="#C9BFD3", lw=0.8)
    R._estilo_ax(ax)
    _leyenda(ax, ncol=2)
    _titulos(fig, t["g_men"], t["g_men_sub"], dy=0.085)
    return R._fig_png(fig)


def g_amplitud(men: pd.DataFrame, t: dict, idioma: str, w: float, h: float):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(w / 72, h / 72))
    fig.subplots_adjust(left=0.07, right=0.995, top=0.70, bottom=0.17)
    x = np.arange(len(men))
    ax.bar(x, men["N_COMPRADORAS"], color=COMPRA, width=0.66, zorder=2, label=t["compradoras"])
    ax.bar(x, -men["N_VENDEDORAS"], color=VENTA, width=0.66, zorder=2, label=t["vendedoras"])
    ax.axhline(0, color="#C9BFD3", lw=0.8)
    ax.set_xticks(x, _etiquetas_mes(men.index, idioma), fontsize=6.6)
    ax.yaxis.set_major_formatter(lambda v, _: f"{abs(v):.0f}")
    R._estilo_ax(ax)
    _leyenda(ax, ncol=2)
    _titulos(fig, t["g_amp"], t["g_amp_sub"], dy=0.09)
    return R._fig_png(fig)


def g_pareto(par: pd.DataFrame, t: dict, w: float, h: float, n: int = 20):
    plt = _plt()
    p = par.head(n)
    fig, ax = plt.subplots(figsize=(w / 72, h / 72))
    fig.subplots_adjust(left=0.07, right=0.99, top=0.74, bottom=0.21)
    x = np.arange(len(p))
    ax.bar(x, p["CUOTA"], color=CAT[0], width=0.62, zorder=2, label=t["cb_cuota"])
    ax.plot(x, p["ACUM"], color=CAT[1], lw=2, marker="o", ms=3.2, zorder=3, label=t["acumulada"])
    for i in range(min(3, len(p))):
        ax.annotate(f"{p['CUOTA'].iat[i]:.0f}%", xy=(i, p["CUOTA"].iat[i]), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=6.6, color=R.TEXT)
    for i in (4, 9):
        if i < len(p):
            ax.annotate(f"{p['ACUM'].iat[i]:.0f}%", xy=(i, p["ACUM"].iat[i]), xytext=(0, 5), textcoords="offset points",
                        ha="center", fontsize=6.6, color=R.TEXT)
    ax.set_ylim(0, 105)
    ax.set_xticks(x, p.index, rotation=90, fontsize=6.8)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    R._estilo_ax(ax)
    _leyenda(ax, ncol=2)
    _titulos(fig, t["g_pareto"], t["g_pareto_sub"], dy=0.07)
    return R._fig_png(fig)


def g_casas(casas: pd.DataFrame, t: dict, w: float, h: float, n: int = 12):
    plt = _plt()
    c = casas.head(n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(w / 72, h / 72))
    fig.subplots_adjust(left=0.13, right=0.95, top=0.86, bottom=0.06)
    y = np.arange(len(c))
    ax.barh(y, c["CUOTA"], color=CAT[0], height=0.62, zorder=2)
    xmax = max(c["CUOTA"].max(), 1) * 1.15
    ax.set_xlim(0, xmax)
    for i, v in enumerate(c["CUOTA"]):
        ax.text(v + xmax * 0.01, i, f"{v:.1f}%", va="center", fontsize=6.8, color=R.TEXT)
    ax.set_yticks(y, c.index, fontsize=7)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    R._estilo_ax(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=R.GRID, linewidth=0.8)
    _titulos(fig, t["g_casas"], t["g_casas_sub"], dy=0.05)
    return R._fig_png(fig)


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

def _kpis(an: ra.Analisis, d: rd.Datos, t: dict, ancho: float):
    from reportlab.platypus import Paragraph, Table
    e = _estilos()
    k = an.kpis
    y = d.corte.year
    yoy = k["ytd_yoy"]
    yoy_txt = (f"{'+' if yoy >= 0 else ''}{yoy:.0f}% {t['k_yoy'].format(y1=y - 1)}") if pd.notna(yoy) else ""
    tiles = [
        (t["k_ytd"].format(y=y), R._f_monto(k["ytd"]), Paragraph(yoy_txt, e["k_pos"] if pd.notna(yoy) and yoy >= 0 else e["k_neg"])),
        (t["k_ltm"], R._f_monto(k["ltm"]), Paragraph(t["k_mxn"], e["k_sub"])),
        (t["k_yield"], R._f_pct(k["ltm_yield"], 2), Paragraph("", e["k_sub"])),
        (t["k_emis"], R._f_monto(k["emis_ytd"]), Paragraph(f"{R._f_monto(k['emis_ytd1'])} {t['k_yoy'].format(y1=y - 1)}", e["k_sub"])),
        (t["k_top5"], R._f_pct(k["top5"], 0), Paragraph("", e["k_sub"])),
        (t["k_rem"], R._f_monto(k["rem_total"]), Paragraph(t["k_rem_sub"].format(p=R._f_pct(k["rem_mcap"], 1)), e["k_sub"])),
    ]
    celdas = [[Paragraph(lab, e["k_lab"]), Paragraph(val, e["k_val"]), sub] for lab, val, sub in tiles]
    w = ancho / len(celdas)
    tabla = Table([[Table([[c[0]], [c[1]], [c[2]]], colWidths=[w - 14],
                          style=[("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])
                    for c in celdas]], colWidths=[w] * len(celdas))
    st = [("BACKGROUND", (0, 0), (-1, -1), R._hex(R.LAVENDER_SOFT)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]
    for i in range(1, len(celdas)):
        st.append(("LINEBEFORE", (i, 0), (i, 0), 1.2, R._hex("#FFFFFF")))
    st.append(("LINEABOVE", (0, 0), (-1, 0), 2, R._hex(R.PURPLE)))
    tabla.setStyle(st)
    return tabla


def pagina_resumen(an: ra.Analisis, d: rd.Datos, idioma: str, ancho: float) -> list:
    from reportlab.platypus import Image, PageBreak, Paragraph, Spacer, Table
    t, e = R.L[idioma], _estilos()
    izq_w, der_w = ancho * 0.47, ancho * 0.53
    bullets = [Paragraph(t["hallazgos"], e["h3"]), Spacer(1, 6)]
    bullets += [Paragraph(h, e["bul"], bulletText="•") for h in an.hallazgos[idioma]]
    g = g_acumulado(an.acumulado, t["acum"], t["acum_sub"], idioma, der_w, 345)
    cuerpo = Table([[bullets, Image(g, der_w, 345)]], colWidths=[izq_w - 12, der_w + 12], style=_sin_pad())
    return [Paragraph(t["resumen"], e["tit"]), Spacer(1, 2),
            Paragraph(t["resumen_sub"].format(corte=d.corte.strftime("%d/%m/%Y")), e["sub"]), Spacer(1, 10),
            _kpis(an, d, t, ancho), Spacer(1, 14), cuerpo, PageBreak()]


def pagina_dinamica(an: ra.Analisis, d: rd.Datos, idioma: str, ancho: float) -> list:
    from reportlab.platypus import Image, PageBreak, Paragraph, Spacer, Table
    t, e = R.L[idioma], _estilos()
    s = an.stats_mensual
    g_w, s_w = ancho * 0.72, ancho * 0.26
    g1 = g_mensual36(an.mensual, t, idioma, g_w, 232)
    g2 = g_amplitud(an.mensual, t, idioma, g_w, 175)
    mes = lambda p: ra.rd_mes(p, idioma) if p is not None else "—"
    filas = [[t["st_tit"], ""],
             [t["st_ult"].format(m=mes(s["mes_ultimo"])), R._f_monto(s["ultimo"])],
             [t["st_prom"], R._f_monto(s["prom_12m"])],
             [t["st_med"], R._f_monto(s["mediana_12m"])],
             [t["st_desv"], R._f_monto(s["desv_12m"])],
             [t["st_z"], f"{s['z_ultimo']:+.2f}" if pd.notna(s["z_ultimo"]) else "n.d."],
             [t["st_3m"], R._f_monto(s["prom_3m"])],
             [t["st_max"], f"{R._f_monto(s['max_12m'])}  ({mes(s['mes_max'])})"],
             [t["st_min"], f"{R._f_monto(s['min_12m'])}  ({mes(s['mes_min'])})"],
             [t["st_comp"], f"{s['compradoras_ultimo']:.0f} / {s['compradoras_prom_12m']:.0f}"]]
    from reportlab.platypus import Table as T
    stats = T(filas, colWidths=[s_w * 0.52, s_w * 0.48], rowHeights=[18] + [21] * (len(filas) - 1))
    st = R._estilo_base(1, 7.2)
    st.add("SPAN", (0, 0), (1, 0))
    st.add("BACKGROUND", (0, 0), (-1, 0), R._hex(R.PURPLE))
    st.add("TEXTCOLOR", (0, 0), (-1, 0), R._hex("#FFFFFF"))
    st.add("ALIGN", (0, 1), (0, -1), "LEFT")
    st.add("ALIGN", (1, 1), (1, -1), "RIGHT")
    st.add("FONT", (1, 1), (1, -1), R._F["bold"], 7.4)
    for rr in range(1, len(filas)):
        st.add("LINEBELOW", (0, rr), (-1, rr), 0.4, R._hex(R.GRID))
    stats.setStyle(st)
    nota = Paragraph(("Millones de pesos." if idioma == "es" else "MXN Million.") +
                     (" Z-score = (último mes − promedio) / desviación estándar." if idioma == "es"
                      else " Z-score = (last month − average) / standard deviation."), e["nota"])
    cuerpo = Table([[[Image(g1, g_w, 232), Spacer(1, 4), Image(g2, g_w, 175)], [Spacer(1, 22), stats, Spacer(1, 6), nota]]],
                   colWidths=[g_w + ancho * 0.02, s_w], style=_sin_pad())
    return [Paragraph(t["dinamica"], e["tit"]), Spacer(1, 2), Paragraph(t["dinamica_sub"], e["sub"]), Spacer(1, 6),
            cuerpo, PageBreak()]


def pagina_concentracion(an: ra.Analisis, d: rd.Datos, idioma: str, ancho: float) -> list:
    from reportlab.platypus import Image, PageBreak, Paragraph, Spacer, Table
    t, e = R.L[idioma], _estilos()
    c = an.concentracion
    g = g_pareto(an.pareto, t, ancho, 225)
    met = [[t["c_top5"], R._f_pct(c["top5"], 0)], [t["c_top10"], R._f_pct(c["top10"], 0)],
           [t["c_hhi"], R._f_monto(c["hhi"])], [t["c_neq"], f"{c['n_equivalente']:.1f}"],
           [t["c_med"], R._f_pct(c["yield_mediana"], 2)], [t["c_1pct"], f"{c['n_yield_1pct']}"],
           [t["compradoras"], f"{c['n_compradoras']}"], [t["vendedoras"], f"{c['n_vendedoras']}"]]
    w_m = ancho * 0.36
    tm = Table(met, colWidths=[w_m * 0.64, w_m * 0.36], rowHeights=[19] * len(met))
    st = R._estilo_base(0, 7.6)
    st.add("ALIGN", (0, 0), (0, -1), "LEFT")
    st.add("ALIGN", (1, 0), (1, -1), "RIGHT")
    st.add("FONT", (1, 0), (1, -1), R._F["bold"], 8)
    for rr in range(len(met)):
        st.add("LINEBELOW", (0, rr), (-1, rr), 0.4, R._hex(R.GRID))
    tm.setStyle(st)
    pa = c["por_anio"]
    datos = [[t["a_anio"], t["a_neto"], t["a_comp"], t["a_vend"], t["a_top5"], t["a_hhi"]]]
    for r in pa.itertuples():
        anio = f"{r.ANIO} YTD" if r.ANIO == d.corte.year else str(r.ANIO)
        datos.append([anio, R._f_monto(r.NETO), str(r.COMPRADORAS), str(r.VENDEDORAS), R._f_pct(r.TOP5, 0), R._f_monto(r.HHI)])
    w_a = ancho * 0.58
    ta = _tabla_simple(datos, [w_a * 0.16] + [w_a * 0.168] * 5, fs=7.6, alto=19)
    nota = Paragraph("HHI = Σ (participación %)² sobre compradoras netas; > 2,500 = muy concentrado, 1,500–2,500 = moderado. "
                     "No. equivalente = 10,000 / HHI." if idioma == "es" else
                     "HHI = Σ (share %)² across net buyers; > 2,500 = highly concentrated, 1,500–2,500 = moderate. "
                     "Equivalent number = 10,000 / HHI.", e["nota"])
    abajo = Table([[[Paragraph(t["conc"] + " · 12M", e["h3"]), Spacer(1, 4), tm],
                    [Paragraph(t["anual"], e["h3"]), Spacer(1, 4), ta, Spacer(1, 6), nota]]],
                  colWidths=[ancho * 0.40, ancho * 0.60], style=_sin_pad())
    return [Paragraph(t["conc"], e["tit"]), Spacer(1, 2), Paragraph(t["conc_sub"], e["sub"]), Spacer(1, 6),
            Image(g, ancho, 225), Spacer(1, 8), abajo, PageBreak()]


def pagina_ejecucion(an: ra.Analisis, d: rd.Datos, idioma: str, ancho: float) -> list:
    from reportlab.platypus import PageBreak, Paragraph, Spacer
    t, e = R.L[idioma], _estilos()
    ej = an.ejecucion
    cab = ["#", "Emisora" if idioma == "es" else "Company", t["e_neto"], t["e_yield"], t["e_int"], t["e_px"], t["e_cierre"],
           t["e_rend"], t["e_pos"], t["e_rem"], t["e_remcap"], t["e_meses"]]
    datos, neg = [cab], []
    for i, (emi, r) in enumerate(ej.iterrows(), start=1):
        meses = r["MESES_FONDO"]
        meses_txt = "" if pd.isna(meses) else (">60" if meses > 60 else f"{meses:.1f}")
        fila = [str(i), emi, R._f_monto(r["NETO"]), R._f_pct(r["YIELD"], 2), R._f_pct(r["INTENSIDAD"], 0),
                R._f_num(r["PX_COMPRA"], 2, nd=""), R._f_num(r["CIERRE"], 2, nd=""),
                (f"{r['REND']:+.1f}%" if pd.notna(r["REND"]) else ""), R._f_pct(r["POS_RANGO"], 0, nd=""),
                R._f_monto(r["REMANENTE"], nd=""), R._f_pct(r["REM_MCAP"], 1, nd=""), meses_txt]
        if pd.notna(r["REND"]) and r["REND"] < 0:
            neg.append((7, i))
        datos.append(fila)
    w0 = [18, 62]
    resto = (ancho - sum(w0)) / 10
    tabla = _tabla_simple(datos, w0 + [resto] * 10, fs=7.4, alto=15.2, alinear_izq=(1,), negativos=neg)
    tabla.setStyle([("ALIGN", (0, 1), (0, -1), "CENTER"), ("FONT", (1, 1), (1, -1), R._F["bold"], 7.4),
                    ("LINEBEFORE", (5, 0), (5, -1), 0.8, R._hex(R.PURPLE_MID)),
                    ("LINEBEFORE", (9, 0), (9, -1), 0.8, R._hex(R.PURPLE_MID))])
    return [Paragraph(t["ejec"], e["tit"]), Spacer(1, 2), Paragraph(t["ejec_sub"], e["sub"]), Spacer(1, 8),
            tabla, Spacer(1, 6), Paragraph(t["ejec_nota"], e["nota"]), PageBreak()]


def pagina_momentum(an: ra.Analisis, d: rd.Datos, idioma: str, ancho: float) -> list:
    from reportlab.platypus import PageBreak, Paragraph, Spacer, Table
    t, e = R.L[idioma], _estilos()
    col_w = (ancho - 16) / 2
    emp = "Emisora" if idioma == "es" else "Company"

    def bloque(titulo, df, columnas, color=None):
        if df is None or df.empty:
            return [Paragraph(titulo, e["h3"]), Spacer(1, 3), Paragraph(t["ninguna"], e["nota"]), Spacer(1, 10)]
        datos, neg = [[emp] + [c[0] for c in columnas]], []
        for i, (emi, r) in enumerate(df.iterrows(), start=1):
            fila = [emi]
            for j, (_, col, fmt) in enumerate(columnas, start=1):
                v = r[col]
                fila.append(fmt(v))
                if isinstance(v, (int, float, np.floating)) and pd.notna(v) and v < 0:
                    neg.append((j, i))
            datos.append(fila)
        w = [col_w * 0.24] + [col_w * 0.76 / len(columnas)] * len(columnas)
        return [Paragraph(titulo, e["h3"]), Spacer(1, 3),
                _tabla_simple(datos, w, fs=7.4, alto=15, cab_color=color, negativos=neg), Spacer(1, 14)]

    fm = lambda v: R._f_monto(v, nd="")
    fp = lambda v: R._f_pct(v, 2, nd="")
    ff = lambda v: v.strftime("%d/%m/%Y") if pd.notna(v) else ""
    izq = bloque(t["m_acel"], an.aceleran.head(8), [(t["m_3m"], "PROM_3M", fm), (t["m_12m"], "PROM_12M", fm),
                                                    (t["m_dif"], "DIF", fm), (t["m_yld"], "YIELD_LTM", fp)], CAT[0])
    izq += bloque(t["m_desacel"], an.desaceleran.head(8), [(t["m_3m"], "PROM_3M", fm), (t["m_12m"], "PROM_12M", fm),
                                                           (t["m_dif"], "DIF", fm), (t["m_yld"], "YIELD_LTM", fp)], R.PURPLE_DARK)
    der = bloque(t["m_pausa"], an.pausan.head(8), [(t["m_meses"], "MESES_ACTIVOS_12M", lambda v: f"{v:.0f}"),
                                                   (t["m_ult"], "ULTIMA", ff), (t["m_dias"], "DIAS_SIN", lambda v: f"{v:.0f}"),
                                                   (t["m_rem"], "REMANENTE", fm)], CAT[1])
    der += bloque(t["m_vend"], an.vendedoras.head(6), [(t["m_neto"], "NETO", fm), (t["m_venta"], "VENTA", fm),
                                                       (t["m_pxv"], "PX_VENTA", lambda v: R._f_num(v, 2, nd=""))], VENTA)
    if not an.inician.empty:
        der += bloque(t["m_inic"], an.inician.head(5), [(t["m_comp90"], "COMPRA_90D", fm), (t["m_prim"], "PRIMERA", ff)], COMPRA)
    cuerpo = Table([[izq, der]], colWidths=[col_w + 16, col_w], style=_sin_pad())
    return [Paragraph(t["momentum"], e["tit"]), Spacer(1, 2), Paragraph(t["momentum_sub"], e["sub"]), Spacer(1, 8),
            cuerpo, PageBreak()]


def pagina_casas(an: ra.Analisis, d: rd.Datos, idioma: str, ancho: float) -> list:
    from reportlab.platypus import Image, PageBreak, Paragraph, Spacer, Table
    t, e = R.L[idioma], _estilos()
    g_w, t_w = ancho * 0.56, ancho * 0.40
    g = g_casas(an.casas, t, g_w, 380)
    cs = an.casas.head(20)
    datos = [[t["cb_casa"], t["cb_monto"], t["cb_cuota"], t["cb_emis"]]]
    for casa, r in cs.iterrows():
        datos.append([casa, R._f_monto(r["MONTO"]), R._f_pct(r["CUOTA"], 1), f"{r['EMISORAS']:.0f}"])
    tabla = _tabla_simple(datos, [t_w * 0.34, t_w * 0.24, t_w * 0.22, t_w * 0.20], fs=7.2, alto=15, alinear_izq=(0,))
    cuerpo = Table([[Image(g, g_w, 380), tabla]], colWidths=[g_w + ancho * 0.04, t_w], style=_sin_pad())
    return [Paragraph(t["casas"], e["tit"]), Spacer(1, 2), Paragraph(t["casas_sub"], e["sub"]), Spacer(1, 8),
            cuerpo, PageBreak()]


def bloque_calidad(an: ra.Analisis, idioma: str, ancho: float) -> list:
    from reportlab.platypus import Paragraph, Spacer, Table
    t, e = R.L[idioma], _estilos()
    q = an.calidad
    filas = [[t["q_avisos"], f"{q['avisos']:,}"], [t["q_corr"], f"{q['reemplazados']:,}"],
             [t["q_fibras"], f"{q['fibras']:,}"], [t["q_emis"], f"{q['emisoras']:,}"],
             [t["q_cob"], q["cobertura"].strftime("%d/%m/%Y") if q["cobertura"] else "—"],
             [t["q_ult"], q["ultimo_dato"].strftime("%d/%m/%Y") if q["ultimo_dato"] else "—"]]
    tb = Table(filas, colWidths=[ancho * 0.30, ancho * 0.12], rowHeights=[15] * len(filas), hAlign="LEFT")
    st = R._estilo_base(0, 7.8)
    st.add("ALIGN", (0, 0), (0, -1), "LEFT")
    st.add("ALIGN", (1, 0), (1, -1), "RIGHT")
    st.add("FONT", (1, 0), (1, -1), R._F["bold"], 7.8)
    for rr in range(len(filas)):
        st.add("LINEBELOW", (0, rr), (-1, rr), 0.4, R._hex(R.GRID))
    tb.setStyle(st)
    return [Paragraph(t["calidad"], e["h3"]), Spacer(1, 4), tb, Spacer(1, 10)]
