"""
Reporte PDF "Casas de bolsa y fondos de recompra" (identidad Punto).

  1. Portada
  2. Resumen ejecutivo: KPIs, hallazgos y participación de mercado por casa
  3. Liga de casas: ranking, cambio vs periodo previo, mandatos, ticket, ejecución
  4. Participación mensual por casa y concentración
  5+ Matriz emisora × casa (ponderación del importe)
  6+ Mandatos por emisora: tipo, casa vigente, estatus, intensidad, fondo remanente
  7. Cambios de mandato
  8. Oportunidades comerciales para la casa destacada
  9. Perfiles de las principales casas
  último. Metodología
"""
from __future__ import annotations

import io
import math
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from src import casas_analisis as ca
from src import emisoras_casas as ec
from src import reporte_pdf as R
from src import reporte_pdf_secciones as S

CAT = S.CAT
GANA, PIERDE = S.COMPRA, S.VENTA
PIE = "CASAS DE BOLSA Y FONDOS DE RECOMPRA"


# ---------------------------------------------------------------------------
# Gráficas
# ---------------------------------------------------------------------------

def _g_participacion(liga: pd.DataFrame, destacada: str, w: float, h: float):
    plt = S._plt()
    d = liga.head(12)
    if destacada in liga.index and destacada not in d.index:
        d = pd.concat([d.iloc[:11], liga.loc[[destacada]]])
    d = d.iloc[::-1]
    fig, ax = plt.subplots(figsize=(w / 72, h / 72))
    fig.subplots_adjust(left=0.17, right=0.80, top=0.86, bottom=0.06)
    y = np.arange(len(d))
    colores = [CAT[0] if c != destacada else CAT[3] for c in d.index]
    ax.barh(y, d["PART"], color=colores, height=0.62, zorder=2)
    xmax = max(d["PART"].max(), 1) * 1.18
    ax.set_xlim(0, xmax)
    for i, (c, r) in enumerate(d.iterrows()):
        ax.text(r["PART"] + xmax * 0.01, i, f"{r['PART']:.1f}%", va="center", fontsize=7, color=R.TEXT)
        dpp = r["DELTA_PP"]
        if pd.notna(dpp) and abs(dpp) >= 0.05:
            ax.text(xmax * 1.02, i, f"{dpp:+.1f} pp", va="center", fontsize=6.8,
                    color=GANA if dpp > 0 else PIERDE, fontweight="bold", clip_on=False)
    ax.set_yticks(y, [f"{c}" for c in d.index], fontsize=7.2)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    R._estilo_ax(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=R.GRID, linewidth=0.8)
    fig.text(0.01, 0.985, "Participación por importe operado", fontsize=10.5, fontweight="bold", color=R.TEXT, va="top")
    fig.text(0.01, 0.935, "% del periodo · a la derecha: cambio vs periodo previo (pp)", fontsize=7.2, color=R.MUTED, va="top")
    return R._fig_png(fig)


def _g_mensual(mensual: pd.DataFrame, destacada: str, w: float, h: float):
    """Barras apiladas al 100 % por mes (una escala), casas en orden fijo de la paleta."""
    plt = S._plt()
    fig, ax = plt.subplots(figsize=(w / 72, h / 72))
    fig.subplots_adjust(left=0.06, right=0.99, top=0.76, bottom=0.12)
    x = np.arange(len(mensual))
    base = np.zeros(len(mensual))
    paleta = {c: CAT[i % len(CAT)] for i, c in enumerate([c for c in mensual.columns if c != "OTRAS"])}
    paleta["OTRAS"] = "#C9BFD3"
    for c in mensual.columns:
        v = mensual[c].values
        ax.bar(x, v, bottom=base, color=paleta[c], width=0.72, label=c, edgecolor="white", linewidth=0.8, zorder=2)
        for i, (b, val) in enumerate(zip(base, v)):
            if val >= 9:
                ax.text(i, b + val / 2, f"{val:.0f}", ha="center", va="center", fontsize=6.2,
                        color="white" if c != "OTRAS" else R.TEXT)
        base += v
    ax.set_ylim(0, 100)
    ax.set_xticks(x, [f"{R.MES_CORTO['es'][m.month - 1]}\n{m.year}" if (m.month == 1 or i == 0) else R.MES_CORTO["es"][m.month - 1]
                      for i, m in enumerate(mensual.index)], fontsize=6.8)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    R._estilo_ax(ax)
    S._leyenda(ax, ncol=len(mensual.columns))
    S._titulos(fig, "Participación mensual por casa", "% del importe operado cada mes · casas principales del periodo", dy=0.07)
    return R._fig_png(fig)


def _g_ejecucion(liga: pd.DataFrame, destacada: str, w: float, h: float):
    """Compra vs cierre (bps) por casa: debajo de 0 = compró por debajo del cierre."""
    plt = S._plt()
    d = liga.dropna(subset=["PRIMA_BPS"])
    d = d[d["N_OPS"] >= 200].sort_values("PRIMA_BPS")
    fig, ax = plt.subplots(figsize=(w / 72, h / 72))
    fig.subplots_adjust(left=0.05, right=0.99, top=0.74, bottom=0.17)
    x = np.arange(len(d))
    colores = [GANA if v < 0 else PIERDE for v in d["PRIMA_BPS"]]
    ax.bar(x, d["PRIMA_BPS"], color=colores, width=0.6, zorder=2)
    for i, v in enumerate(d["PRIMA_BPS"]):
        ax.annotate(f"{v:+.0f}", xy=(i, v), xytext=(0, 3 if v >= 0 else -9), textcoords="offset points",
                    ha="center", fontsize=6.8, color=R.TEXT)
    ax.axhline(0, color="#8C8496", lw=0.9)
    lo, hi = min(d["PRIMA_BPS"].min(), 0), max(d["PRIMA_BPS"].max(), 0)
    ax.set_ylim(lo - (hi - lo) * 0.18 if lo < 0 else 0, hi + (hi - lo) * 0.15)
    etiquetas = [f"{c}*" if c == destacada else c for c in d.index]
    ax.set_xticks(x, etiquetas, fontsize=7.2)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:+.0f}")
    R._estilo_ax(ax)
    S._titulos(fig, "Disciplina de precio: compra vs cierre del día",
               "bps, ponderado por importe · verde = compró por debajo del cierre · casas con 200+ operaciones", dy=0.09)
    return R._fig_png(fig)


def _g_tipos(man: pd.DataFrame, w: float, h: float):
    """Mandatos por tipo: número de emisoras (barras horizontales, una serie)."""
    plt = S._plt()
    orden = ["Exclusivo", "Principal + secundaria", "Compartido"]
    cnt = man["TIPO"].value_counts().reindex(orden).fillna(0)
    imp = man.groupby("TIPO")["IMPORTE"].sum().reindex(orden).fillna(0)
    fig, ax = plt.subplots(figsize=(w / 72, h / 72))
    fig.subplots_adjust(left=0.36, right=0.86, top=0.70, bottom=0.10)
    y = np.arange(len(orden))[::-1]
    ax.barh(y, cnt.values, color=CAT[0], height=0.55, zorder=2)
    for yy, n, m in zip(y, cnt.values, imp.values):
        ax.text(n + max(cnt.max(), 1) * 0.02, yy, f"{n:.0f}  ·  ${m:,.0f} M", va="center", fontsize=7, color=R.TEXT,
                clip_on=False)
    ax.set_yticks(y, orden, fontsize=7.2)
    ax.set_xlim(0, max(cnt.max(), 1) * 1.15)
    R._estilo_ax(ax)
    ax.grid(axis="y", visible=False)
    ax.set_xticks([])
    S._titulos(fig, "Mandatos por tipo", "emisoras · importe operado", dy=0.11)
    return R._fig_png(fig)


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------

def _tabla(datos, widths, fs=7.2, alto=14, cab=None, izq=(0,), negativos=(), positivos=(), resaltar_fila=None,
           alto_cab=None):
    from reportlab.platypus import Table
    t = Table(datos, colWidths=widths, rowHeights=[alto_cab] + [alto] * (len(datos) - 1), repeatRows=1, hAlign="LEFT")
    st = R._estilo_base(1, fs)
    st.add("BACKGROUND", (0, 0), (-1, 0), R._hex(cab or R.PURPLE))
    st.add("TEXTCOLOR", (0, 0), (-1, 0), R._hex("#FFFFFF"))
    st.add("FONT", (0, 0), (-1, 0), R._F["bold"], fs - 0.3)
    st.add("ALIGN", (0, 1), (-1, -1), "RIGHT")
    for c in izq:
        st.add("ALIGN", (c, 1), (c, -1), "LEFT")
    for rr in range(1, len(datos)):
        if rr % 2 == 0:
            st.add("BACKGROUND", (0, rr), (-1, rr), R._hex(R.LAVENDER_SOFT))
    for c, rr in negativos:
        st.add("TEXTCOLOR", (c, rr), (c, rr), R._hex(PIERDE))
    for c, rr in positivos:
        st.add("TEXTCOLOR", (c, rr), (c, rr), R._hex(GANA))
    if resaltar_fila:
        st.add("BACKGROUND", (0, resaltar_fila), (-1, resaltar_fila), R._hex("#FCEFD9"))
        st.add("FONT", (0, resaltar_fila), (-1, resaltar_fila), R._F["bold"], fs)
    t.setStyle(st)
    return t


def _f(v, dec=0, nd="") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v):
        return nd
    return f"{v:,.{dec}f}"


def _fd(d) -> str:
    return d.strftime("%d/%m/%Y") if d is not None and not pd.isna(d) else ""


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

def _portada(c, doc, titulo: str, periodo: str):
    c.saveState()
    c.setFillColor(R._hex(R.PURPLE)); c.rect(0, 0, R.PAGE_W, R.PAGE_H, stroke=0, fill=1)
    for (x, y, r, col, a) in [(700, 520, 260, "#8A4FB8", 0.55), (840, 140, 220, R.PURPLE_DARK, 0.55),
                              (520, 640, 160, "#9B66C7", 0.35), (620, 260, 90, R.LAVENDER, 0.18)]:
        c.setFillColor(R._hex(col)); c.setFillAlpha(a); c.circle(x, y, r, stroke=0, fill=1)
    c.setFillAlpha(1)
    R._logo(c, R.PAGE_W - 40, R.PAGE_H - 36, blanco=True)
    c.setFillColor(R._hex("#FFFFFF")); c.roundRect(40, 46, 420, 130, 16, stroke=0, fill=1)
    c.setFillColor(R._hex(R.TEXT)); c.setFont(R._F["regular"], 24); c.drawString(62, 136, titulo[0])
    c.drawString(62, 110, titulo[1])
    c.setStrokeColor(R._hex(R.TEXT)); c.setLineWidth(0.7); c.line(62, 96, 438, 96)
    c.setFont(R._F["regular"], 11); c.drawString(62, 72, periodo)
    c.setFillColor(R._hex("#FFFFFF")); c.setFont(R._F["regular"], 8.5)
    c.drawRightString(R.PAGE_W - 40, 30, "Inteligencia de intermediación · Bolsa Mexicana de Valores")
    c.restoreState()


def _marco(c, doc, fecha_pub: str):
    c.saveState()
    c.setFillColor(R._hex(R.MUTED)); c.setFont(R._F["regular"], 8.5)
    c.drawString(R.M, R.PAGE_H - 40, fecha_pub)
    R._logo(c, R.PAGE_W - R.M, R.PAGE_H - 24)
    c.setFont(R._F["regular"], 7.5)
    c.drawRightString(R.PAGE_W - R.M, 16, f"{PIE}  |  {doc.page}")
    c.setStrokeColor(R._hex(R.LAVENDER)); c.setLineWidth(2); c.line(R.M, 26, R.M + 60, 26)
    c.restoreState()


def _kpis(an: ca.AnalisisCasas, ancho: float):
    from reportlab.platypus import Paragraph, Table
    e = S._estilos()
    k, D = an.kpis, an.destacada
    dpp = k["dest_delta"]
    tiles = [
        ("Importe operado", f"${k['importe']:,.0f}", Paragraph("millones · compras + ventas", e["k_sub"])),
        ("Emisoras con fondo activo", f"{k['emisoras']}", Paragraph(f"{k['casas']} casas de bolsa", e["k_sub"])),
        ("Mandatos exclusivos", f"{k['exclusivos']}", Paragraph(f"{k['compartidos']} compartidos", e["k_sub"])),
        ("Concentración top 3", f"{k['top3']:.0f}%", Paragraph(f"HHI {k['hhi']:,.0f}", e["k_sub"])),
        ("Cambios de mandato", f"{k['cambios']}", Paragraph("en el periodo", e["k_sub"])),
        (f"Posición {D}", f"#{k['dest_rank']}" if k["dest_rank"] else "—",
         Paragraph(f"{k['dest_part']:.1f}% · {dpp:+.1f} pp" if pd.notna(dpp) else f"{k['dest_part']:.1f}%",
                   e["k_pos"] if pd.notna(dpp) and dpp >= 0 else e["k_neg"])),
    ]
    celdas = [[Paragraph(a, e["k_lab"]), Paragraph(b, e["k_val"]), c] for a, b, c in tiles]
    w = ancho / len(celdas)
    t = Table([[Table([[c[0]], [c[1]], [c[2]]], colWidths=[w - 14],
                      style=[("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])
                for c in celdas]], colWidths=[w] * len(celdas))
    st = [("BACKGROUND", (0, 0), (-1, -1), R._hex(R.LAVENDER_SOFT)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LINEABOVE", (0, 0), (-1, 0), 2, R._hex(R.PURPLE))]
    st += [("LINEBEFORE", (i, 0), (i, 0), 1.2, R._hex("#FFFFFF")) for i in range(1, len(celdas))]
    t.setStyle(st)
    return t


def _titulo(texto, sub, e):
    from reportlab.platypus import Paragraph, Spacer
    return [Paragraph(texto, e["tit"]), Spacer(1, 2), Paragraph(sub, e["sub"]), Spacer(1, 8)]


def pagina_resumen(an, ancho, e) -> list:
    from reportlab.platypus import Image, PageBreak, Paragraph, Spacer, Table
    izq_w, der_w = ancho * 0.52, ancho * 0.48
    bullets = [Paragraph("Hallazgos principales", e["h3"]), Spacer(1, 6)]
    bullets += [Paragraph(h, e["bul"], bulletText="•") for h in an.hallazgos]
    g = _g_participacion(an.liga, an.destacada, der_w, 330)
    return _titulo("Resumen ejecutivo", f"Periodo {an.ini:%d/%m/%Y} – {an.fin:%d/%m/%Y} · comparado contra "
                                        f"{an.ini_prev:%d/%m/%Y} – {an.ini - timedelta(days=1):%d/%m/%Y}", e) + [
        _kpis(an, ancho), Spacer(1, 12),
        Table([[bullets, Image(g, der_w, 330)]], colWidths=[izq_w, der_w], style=S._sin_pad()), PageBreak()]


def pagina_liga(an, ancho, e) -> list:
    from reportlab.platypus import Image, PageBreak, Paragraph, Spacer
    L, D = an.liga, an.destacada
    cab = ["#", "Casa", "Nombre", "Importe\n(MXN M)", "Part.", "Cambio\n(pp)", "Lugar\nprevio", "Emisoras",
           "Exclusivas", "Compar-\ntidas", "Operaciones", "Ticket prom.\n(MXN miles)", "Compra vs\ncierre (bps)",
           "Principales emisoras"]
    datos, neg, pos, fila_d = [cab], [], [], None
    for i, (c, r) in enumerate(L.iterrows(), start=1):
        dpp = r["DELTA_PP"]
        datos.append([str(int(r["RANK"])), c, r["NOMBRE"], _f(r["IMPORTE"]), f"{r['PART']:.1f}%",
                      f"{dpp:+.1f}" if pd.notna(dpp) else "", _f(r["RANK_PREV"]), str(int(r["EMISORAS"])),
                      str(int(r["EXCLUSIVOS"])), str(int(r["COMPARTIDOS"])), _f(r["N_OPS"]),
                      _f(r["TICKET"] / 1e3), _f(r["PRIMA_BPS"], 1), r["TOP"] or ""])
        if pd.notna(dpp) and dpp <= -0.05:
            neg.append((5, i))
        elif pd.notna(dpp) and dpp >= 0.05:
            pos.append((5, i))
        if c == D:
            fila_d = i
    w = [18, 40, 66, 52, 38, 40, 36, 42, 46, 42, 54, 58, 54]
    w.append(ancho - sum(w))
    t = _tabla(datos, w, fs=7.1, alto=14.5, izq=(1, 2, 13), negativos=neg, positivos=pos, resaltar_fila=fila_d, alto_cab=26)
    g = _g_ejecucion(L, D, ancho, 175)
    nota = Paragraph(
        "Exclusivas = emisoras en las que la casa ejecuta ≥90% del importe. Compartidas = emisoras donde participa con "
        "menos. Ticket = importe / operaciones. Compra vs cierre = precio promedio de compra contra el cierre del día, "
        "ponderado por importe (negativo = compró por debajo del cierre); excluye avisos de menos de 3 operaciones "
        "(bloques y liquidaciones de derivados).", e["nota"])
    return _titulo("Liga de casas de bolsa", "Ranking por importe operado de los fondos de recompra", e) + [
        t, Spacer(1, 4), nota, Spacer(1, 6), Image(g, ancho, 175), PageBreak()]


def pagina_mensual(an, ancho, e) -> list:
    from reportlab.platypus import Image, PageBreak, Paragraph, Spacer, Table
    g = _g_mensual(an.mensual, an.destacada, ancho, 250)
    gt = _g_tipos(an.mandatos, ancho * 0.42, 150)
    # Sectores × casa principal
    m = an.mandatos
    sec = m.groupby(["SECTOR", "CASA_PRINCIPAL"])["IMPORTE"].sum().reset_index()
    tot_sec = sec.groupby("SECTOR")["IMPORTE"].sum().sort_values(ascending=False)
    datos = [["Sector", "Importe\n(MXN M)", "Casa líder", "Part. líder", "Emisoras"]]
    for s_, imp in tot_sec.items():
        g_ = sec[sec["SECTOR"] == s_].sort_values("IMPORTE", ascending=False)
        lider = g_.iloc[0]
        datos.append([str(s_).title(), _f(imp), lider["CASA_PRINCIPAL"], f"{100 * lider['IMPORTE'] / imp:.0f}%",
                      str(int((m["SECTOR"] == s_).sum()))])
    w_t = ancho * 0.54
    t = _tabla(datos, [w_t * 0.34, w_t * 0.18, w_t * 0.18, w_t * 0.16, w_t * 0.14], fs=7, alto=12.5, alto_cab=22)
    abajo = Table([[Image(gt, ancho * 0.42, 150), [Paragraph("Casa líder por sector", e["h3"]), Spacer(1, 3), t]]],
                  colWidths=[ancho * 0.45, ancho * 0.55], style=S._sin_pad())
    return _titulo("Dinámica de la intermediación", "Cómo se reparte el mercado mes a mes, por tipo de mandato y por sector", e) + [
        Image(g, ancho, 250), Spacer(1, 6), abajo, PageBreak()]


def paginas_matriz(an, ancho, e, filas_pag: int = 30) -> list:
    from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle
    tab, cols = an.matriz, an.cols
    man = an.mandatos.set_index("EMISORA")
    cab = ["#", "Emisora", "Importe\n(MXN M)", "Tipo", "Casa\nvigente"] + cols
    cuerpo = []
    for i, r in enumerate(tab.itertuples(index=False), start=1):
        r = r._asdict()
        tipo = {"Exclusivo": "Excl.", "Principal + secundaria": "Princ.+sec.", "Compartido": "Compart."}.get(
            man["TIPO"].get(r["EMISORA"], ""), "")
        fila = [str(i), r["EMISORA"], _f(r["IMPORTE"]), tipo, r["CASA_VIGENTE"] or ""]
        fila += ["" if pd.isna(r.get(c)) or r[c] <= 0 else ("<1%" if r[c] < 1 else f"{r[c]:.0f}%") for c in cols]
        cuerpo.append((fila, [r.get(c) for c in cols]))
    w_fijos = [18, 56, 50, 52, 46]
    w_casa = (ancho - sum(w_fijos)) / max(len(cols), 1)
    lav = np.array([0xF7, 0xF2, 0xFB]); mor = np.array([0x70, 0x30, 0xA0])
    out = []
    for p in range(0, len(cuerpo), filas_pag):
        bloque = cuerpo[p:p + filas_pag]
        datos = [cab] + [f for f, _ in bloque]
        t = Table(datos, colWidths=w_fijos + [w_casa] * len(cols), rowHeights=[24] + [13.4] * len(bloque), repeatRows=1)
        st = TableStyle(R._estilo_base(1, 7.1).getCommands())
        st.add("BACKGROUND", (0, 0), (-1, 0), R._hex(R.PURPLE)); st.add("TEXTCOLOR", (0, 0), (-1, 0), R._hex("#FFFFFF"))
        st.add("ALIGN", (2, 1), (2, -1), "RIGHT"); st.add("ALIGN", (3, 1), (4, -1), "LEFT")
        st.add("ALIGN", (5, 1), (-1, -1), "CENTER"); st.add("FONT", (1, 1), (1, -1), R._F["bold"], 7.1)
        st.add("LINEBEFORE", (5, 0), (5, -1), 0.8, R._hex(R.PURPLE))
        if an.destacada in cols:
            k = 5 + cols.index(an.destacada)
            st.add("BOX", (k, 0), (k, -1), 1.2, R._hex(CAT[3]))
        for rr, (_, vals) in enumerate(bloque, start=1):
            st.add("LINEBELOW", (0, rr), (-1, rr), 0.3, R._hex(R.GRID))
            for cc, v in enumerate(vals, start=5):
                if v is None or pd.isna(v) or v <= 0:
                    continue
                kk = min(v, 100) / 100
                rgb = (lav + (mor - lav) * kk).astype(int)
                st.add("BACKGROUND", (cc, rr), (cc, rr), R._hex("#%02X%02X%02X" % tuple(rgb)))
                if kk > 0.55:
                    st.add("TEXTCOLOR", (cc, rr), (cc, rr), R._hex("#FFFFFF"))
        t.setStyle(st)
        out += _titulo("Quién opera cada fondo" + ("" if p == 0 else " (cont.)"),
                       "% del importe de cada emisora ejecutado con cada casa · ordenado por importe · "
                       "casa vigente = la del aviso más reciente", e) + [
            t, Spacer(1, 4), Paragraph("Casas fuera de las 12 principales del periodo se agrupan en OTRAS. "
                                       f"Recuadro: {an.destacada}.", e["nota"]), PageBreak()]
    return out


def paginas_mandatos(an, ancho, e, filas_pag: int = 28) -> list:
    from reportlab.platypus import PageBreak, Paragraph, Spacer
    m = an.mandatos
    cab = ["Emisora", "Sector", "Tipo de mandato", "Casa\nprincipal", "Part.", "Casa\nvigente", "Desde",
           "Estatus", "Última\noperación", "Intensidad\n(% sesiones)", "Importe\n(MXN M)", "Neto\n(MXN M)",
           "Fondo\nremanente (M)", "Meses de\nfondo", "Compra vs\ncierre (bps)"]
    filas = []
    for r in m.itertuples(index=False):
        meses = r.MESES_FONDO
        filas.append(([r.EMISORA, str(r.SECTOR).title()[:22], r.TIPO, r.CASA_PRINCIPAL, f"{r.PCT_PRINCIPAL:.0f}%",
                       r.CASA_VIGENTE or "", _fd(r.DESDE), r.ESTATUS, _fd(r.ULTIMA), _f(r.INTENSIDAD),
                       _f(r.IMPORTE), _f(r.NETO), _f(r.REMANENTE),
                       "" if pd.isna(meses) else (">60" if meses > 60 else f"{meses:.1f}"), _f(r.PRIMA_BPS, 1)],
                      r.ESTATUS, r.NETO))
    w = [50, 92, 84, 44, 34, 44, 50, 46, 50, 50, 50, 50, 56, 42]
    w.append(ancho - sum(w))
    out = []
    for p in range(0, len(filas), filas_pag):
        bloque = filas[p:p + filas_pag]
        datos = [cab] + [f for f, _, _ in bloque]
        neg = [(11, i) for i, (_, _, n) in enumerate(bloque, start=1) if pd.notna(n) and n < 0]
        neg += [(7, i) for i, (_, est, _) in enumerate(bloque, start=1) if est == "Inactivo"]
        pos = [(7, i) for i, (_, est, _) in enumerate(bloque, start=1) if est == "Activo"]
        t = _tabla(datos, w, fs=6.9, alto=14, izq=(0, 1, 2, 3, 5, 7), negativos=neg, positivos=pos, alto_cab=26)
        out += _titulo("Mandatos por emisora" + ("" if p == 0 else " (cont.)"),
                       "Tipo, casa vigente, actividad y fondo disponible de cada programa de recompra", e) + [
            t, Spacer(1, 4),
            Paragraph("Tipo: Exclusivo ≥90% del importe con una casa; Principal + secundaria 60–90%; Compartido <60%. "
                      "Estatus: Activo = operó en los últimos 30 días; En pausa 31–120; Inactivo >120. Intensidad = sesiones "
                      "con recompra / sesiones del periodo. Meses de fondo = remanente / compras mensuales promedio de "
                      "los últimos 3 meses.", e["nota"]), PageBreak()]
    return out


def pagina_cambios(an, ancho, e) -> list:
    from reportlab.platypus import PageBreak, Paragraph, Spacer
    c = an.cambios
    out = _titulo("Cambios de mandato", "Emisoras que cambiaron de casa principal en el periodo · más recientes primero", e)
    if c.empty:
        return out + [Paragraph("No se detectaron cambios de casa principal en el periodo.", e["bul"]), PageBreak()]
    cab = ["Fecha", "Emisora", "Sector", "De", "", "A", "Sesiones con\nla casa anterior", "Sesiones con\nla nueva",
           "Importe con la\nnueva (MXN M)", "Casa vigente hoy"]
    man = an.mandatos.set_index("EMISORA")
    datos, neg, pos = [cab], [], []
    for i, r in enumerate(c.itertuples(index=False), start=1):
        datos.append([_fd(r.FECHA), r.EMISORA, str(man["SECTOR"].get(r.EMISORA, "")).title(), r.DE, "→", r.A,
                      str(r.SESIONES_PREVIA), str(r.SESIONES_NUEVA), _f(r.IMPORTE_DESDE, 1),
                      man["CASA_VIGENTE"].get(r.EMISORA, "") or ""])
        if r.DE == an.destacada:
            neg.append((3, i))
        if r.A == an.destacada:
            pos.append((5, i))
    w = [62, 62, 130, 56, 18, 56, 90, 80, 92]
    w.append(ancho - sum(w))
    t = _tabla(datos, w, fs=7.4, alto=16, izq=(1, 2, 3, 5, 9), negativos=neg, positivos=pos, alto_cab=26)
    return out + [t, Spacer(1, 6), Paragraph(
        "Se considera cambio cuando la casa de mayor importe de cada sesión deja de ser la misma durante un tramo "
        f"consolidado (casa anterior ≥{ca.PREVIA_MIN} sesiones, nueva ≥{ca.NUEVA_MIN} sesiones o vigente). Las "
        f"alternancias cortas entre casas (mandatos compartidos) no cuentan como cambio. En rojo: mandatos que "
        f"perdió {an.destacada}; en verde: los que ganó.", e["nota"]), PageBreak()]


def pagina_oportunidades(an, ancho, e) -> list:
    from reportlab.platypus import PageBreak, Paragraph, Spacer, Table
    D, op = an.destacada, an.oportunidades
    col_w = (ancho - 14) / 2

    def bloque(titulo, df, columnas, color, n=10):
        if df is None or df.empty:
            return [Paragraph(titulo, e["h3"]), Spacer(1, 3), Paragraph("Ninguna en el periodo.", e["nota"]), Spacer(1, 10)]
        datos = [[c[0] for c in columnas]]
        for r in df.head(n).itertuples(index=False):  # columnas: (título, campo, formato[, ancho relativo])
            r = r._asdict()
            datos.append([c[2](r.get(c[1])) for c in columnas])
        anchos = [c[3] if len(c) > 3 else 1.0 for c in columnas[1:]]
        w = [col_w * 0.18] + [col_w * 0.82 * a / sum(anchos) for a in anchos]
        izq_cols = tuple(i for i, c in enumerate(columnas) if c[2] is txt)
        return [Paragraph(titulo, e["h3"]), Spacer(1, 3),
                _tabla(datos, w, fs=7, alto=13.2, cab=color, izq=izq_cols, alto_cab=22), Spacer(1, 10)]

    txt = lambda v: "" if v is None or pd.isna(v) else str(v)
    num = lambda v: _f(v)
    izq = bloque(f"Emisoras activas sin {D} · ordenadas por fondo disponible", op["sin_destacada"],
                 [("Emisora", "EMISORA", txt), ("Casa vigente", "CASA_VIGENTE", txt), ("Tipo", "TIPO", txt),
                  ("Importe (M)", "IMPORTE", num), ("Fondo rem. (M)", "REMANENTE", num)], CAT[0], n=12)
    izq += bloque("Mandatos en movimiento (compartidos o con cambio reciente)", op["en_movimiento"],
                  [("Emisora", "EMISORA", txt), ("Principal", "CASA_PRINCIPAL", txt, 0.8),
                   ("Part.", "PCT_PRINCIPAL", lambda v: f"{v:.0f}%", 0.6), ("Reparto últimas 4 semanas", "REPARTO_4S", txt, 2.6),
                   ("Importe (M)", "IMPORTE", num, 0.9)], CAT[1], n=10)
    der = bloque("Fondos disponibles sin operar (45+ días)", op["fondos_sin_operar"],
                 [("Emisora", "EMISORA", txt), ("Última casa", "CASA_ULTIMA", txt), ("Última op.", "ULTIMA", _fd),
                  ("Días sin", "DIAS_SIN", num), ("Fondo rem. (M)", "REMANENTE", num)], CAT[2], n=12)
    der += bloque(f"Clientes actuales de {D}", op["clientes"],
                  [("Emisora", "EMISORA", txt), (f"Part. {D}", "PCT_IMPORTE", lambda v: f"{v:.0f}%"),
                   ("Importe (M)", "IMPORTE", lambda v: _f(v, 1)), ("Casa vigente", "CASA_VIGENTE", txt),
                   ("Última op.", "ULTIMA", _fd)], CAT[3], n=10)
    cuerpo = Table([[izq, der]], colWidths=[col_w + 14, col_w], style=S._sin_pad())
    return _titulo(f"Oportunidades comerciales para {D}",
                   "Dónde hay fondo de recompra disponible y mandatos que se pueden disputar", e) + [cuerpo, PageBreak()]


def pagina_perfiles(an, ancho, e) -> list:
    from reportlab.platypus import PageBreak, Paragraph, Spacer, Table
    casas = list(an.perfiles)[:8]
    col_w = (ancho - 3 * 10) / 4
    celdas = []
    for c in casas:
        p, r = an.perfiles[c], an.liga.loc[c]
        datos = [["Emisora", "Importe (M)", "Peso casa"]]
        for x in p.head(7).itertuples(index=False):
            datos.append([x.EMISORA, _f(x.IMPORTE), f"{x.PCT_IMPORTE:.0f}%"])
        t = _tabla(datos, [col_w * 0.38, col_w * 0.34, col_w * 0.28], fs=6.8, alto=12, izq=(0,), alto_cab=15,
                   cab=CAT[3] if c == an.destacada else R.PURPLE)
        enc = Paragraph(f"<b>{c}</b> · {ec.nombre(c)}", e["h3"])
        sub = Paragraph(f"#{int(r['RANK'])} · {r['PART']:.1f}% ({r['DELTA_PP']:+.1f} pp) · {int(r['EMISORAS'])} emisoras · "
                        f"{int(r['EXCLUSIVOS'])} exclusivas", e["nota"])
        celdas.append([enc, sub, Spacer(1, 3), t])
    filas = [celdas[i:i + 4] for i in range(0, len(celdas), 4)]
    for f in filas:
        f += [""] * (4 - len(f))
    grid = Table(filas, colWidths=[col_w + 10] * 3 + [col_w],
                 style=S._sin_pad() + [("BOTTOMPADDING", (0, 0), (-1, -1), 12)])
    return _titulo("Perfiles de las principales casas", "Cartera de emisoras de cada casa · peso de la casa en el fondo de cada emisora", e) + [
        grid, PageBreak()]


def pagina_metodologia(an, ancho, e) -> list:
    from reportlab.platypus import Paragraph, Spacer
    puntos = [
        "Fuente: avisos de recompra publicados por la Bolsa Mexicana de Valores; cada aviso informa la casa de bolsa que "
        "ejecutó las operaciones del fondo. Fondo remanente: último aviso de cada emisora en los últimos 12 meses. "
        "Cierres: Yahoo Finance.",
        "El contrato del fondo de recompra entre emisora y casa de bolsa no es público. La casa que ejecuta las "
        "operaciones, reportada obligatoriamente en cada aviso, es la evidencia pública de quién opera el fondo.",
        "Importe operado = compras + ventas del fondo (actividad intermediada), no la recompra neta.",
        f"Mandatos: Exclusivo si una casa ejecuta ≥{ca.UMBRAL_EXCLUSIVO:.0f}% del importe de la emisora; Principal + "
        f"secundaria {ca.UMBRAL_PRINCIPAL:.0f}–{ca.UMBRAL_EXCLUSIVO:.0f}%; Compartido debajo de {ca.UMBRAL_PRINCIPAL:.0f}%.",
        "Compra vs cierre: precio promedio de compra de cada aviso contra el cierre del día, ponderado por importe. Mide "
        "la disciplina de precio de la ejecución; depende también de las instrucciones de cada emisora.",
        "Se aplican las correcciones y cancelaciones publicadas por las emisoras (avisos sustituidos y folios en cero).",
        "HHI = Σ (participación %)² de las casas; >2,500 muy concentrado, 1,500–2,500 moderado.",
    ]
    s = _titulo("Metodología", "Definiciones y fuentes", e)
    for p in puntos:
        s += [Paragraph("•  " + p, e["bul"]), Spacer(1, 3)]
    gen = datetime.now(timezone(timedelta(hours=-6))).strftime("%d/%m/%Y %H:%M")
    s += [Spacer(1, 10), Paragraph(f"Generado: {gen} CDMX · Datos al {an.fin:%d/%m/%Y}. Este documento es informativo "
                                   "y no constituye una recomendación.", e["nota"])]
    return s


def generar_pdf(an: ca.AnalisisCasas) -> bytes:
    from reportlab.platypus import BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate

    R._registrar_fuentes()
    e = S._estilos()
    hoy = datetime.now(timezone(timedelta(hours=-6))).date()
    periodo = f"{an.ini:%d/%m/%Y} – {an.fin:%d/%m/%Y}"
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=(R.PAGE_W, R.PAGE_H), leftMargin=R.M, rightMargin=R.M, topMargin=R.TOP,
                          bottomMargin=34, title="Casas de bolsa y fondos de recompra", author="Punto Casa de Bolsa")
    marco = Frame(R.M, 34, R.PAGE_W - 2 * R.M, R.PAGE_H - R.TOP - 34, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate("portada", frames=[Frame(0, 0, R.PAGE_W, R.PAGE_H)],
                     onPage=lambda c, d: _portada(c, d, ("Casas de bolsa y", "fondos de recompra"), periodo)),
        PageTemplate("normal", frames=[marco], onPage=lambda c, d: _marco(c, d, R._fecha_larga(hoy, "es"))),
    ])
    ancho = R.PAGE_W - 2 * R.M
    s = [NextPageTemplate("normal"), PageBreak()]
    s += pagina_resumen(an, ancho, e)
    s += pagina_liga(an, ancho, e)
    s += pagina_mensual(an, ancho, e)
    s += paginas_matriz(an, ancho, e)
    s += paginas_mandatos(an, ancho, e)
    s += pagina_cambios(an, ancho, e)
    s += pagina_oportunidades(an, ancho, e)
    s += pagina_perfiles(an, ancho, e)
    s += pagina_metodologia(an, ancho, e)
    doc.build(s)
    return buf.getvalue()


def excel_bytes(an: ca.AnalisisCasas) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame({"Hallazgos": [h.replace("<b>", "").replace("</b>", "") for h in an.hallazgos]}) \
            .to_excel(xw, sheet_name="Resumen", index=False)
        an.liga.reset_index().to_excel(xw, sheet_name="Liga de casas", index=False)
        an.matriz.to_excel(xw, sheet_name="Matriz emisora x casa", index=False)
        an.mandatos.to_excel(xw, sheet_name="Mandatos", index=False)
        an.cambios.to_excel(xw, sheet_name="Cambios de mandato", index=False)
        for k, nombre in (("sin_destacada", f"Sin {an.destacada}"), ("en_movimiento", "En movimiento"),
                          ("fondos_sin_operar", "Fondos sin operar"), ("clientes", f"Clientes {an.destacada}")):
            an.oportunidades[k].to_excel(xw, sheet_name=nombre[:31], index=False)
        an.mensual.reset_index().astype({"MES": str}).to_excel(xw, sheet_name="Participación mensual", index=False)
    return buf.getvalue()
