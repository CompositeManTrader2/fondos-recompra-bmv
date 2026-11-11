"""
Emisoras × casas de bolsa: con quién opera cada fondo de recompra.

Fuente: los avisos de recompra de la BMV, que traen la casa de bolsa que
ejecutó cada operación. El contrato del fondo de recompra no es público; la
casa que ejecuta las operaciones es la evidencia pública de quién opera el
fondo (ver `casa_vigente`).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

# Claves que aparecen en los avisos → nombre comercial (sólo las inequívocas;
# las demás se muestran con la clave tal como la publica la BMV).
NOMBRES = {
    "ACTIN": "Actinver", "BANOR": "Banorte", "BCOMR": "BBVA", "BTGP": "BTG Pactual", "BXMAS": "Ve por Más",
    "CITI": "Citi", "CS": "Credit Suisse", "GBM": "GBM", "GS": "Goldman Sachs", "INBUR": "Inbursa",
    "INVEX": "Invex", "MNXCB": "Monex", "MS": "Morgan Stanley", "PUNTO": "Punto", "SANT": "Santander",
    "SCTIA": "Scotiabank", "ICAM": "Intercam", "FMX": "Finamex",
}
# Variantes de captura de una misma casa.
EQUIVALENTES = {"FINAMEX, S.A.B. DE C.V.": "FMX"}

MEDIDAS = {"IMPORTE": "Importe operado", "N_OPS": "Número de operaciones"}


def nombre(clave: str) -> str:
    return NOMBRES.get(clave, clave)


def _base(act: pd.DataFrame, ini: date, fin: date) -> pd.DataFrame:
    a = act.copy()
    a["FECHA_OPERACION"] = pd.to_datetime(a["FECHA_OPERACION"])
    a = a[(a["FECHA_OPERACION"].dt.date >= ini) & (a["FECHA_OPERACION"].dt.date <= fin)]
    a["CASA_BOLSA"] = a["CASA_BOLSA"].fillna("N/D").astype(str).str.strip().replace(EQUIVALENTES)
    for c in ("IMPORTE", "N_OPS", "ACCIONES"):
        a[c] = pd.to_numeric(a[c], errors="coerce").fillna(0.0)
    return a


def detalle(act: pd.DataFrame, ini: date, fin: date) -> pd.DataFrame:
    """Una fila por (emisora, casa): importe, operaciones, sesiones, primera/última fecha y ponderaciones."""
    a = _base(act, ini, fin)
    if a.empty:
        return pd.DataFrame()
    g = a.groupby(["EMISORA", "CASA_BOLSA"]).agg(
        IMPORTE=("IMPORTE", "sum"), N_OPS=("N_OPS", "sum"), ACCIONES=("ACCIONES", "sum"),
        SESIONES=("FECHA_OPERACION", "nunique"), PRIMERA=("FECHA_OPERACION", "min"),
        ULTIMA=("FECHA_OPERACION", "max")).reset_index()
    tot = g.groupby("EMISORA")[["IMPORTE", "N_OPS"]].transform("sum")
    g["PCT_IMPORTE"] = 100 * g["IMPORTE"] / tot["IMPORTE"].where(tot["IMPORTE"] > 0)
    g["PCT_OPS"] = 100 * g["N_OPS"] / tot["N_OPS"].where(tot["N_OPS"] > 0)
    g["NOMBRE"] = g["CASA_BOLSA"].map(nombre)
    return g.sort_values(["EMISORA", "IMPORTE"], ascending=[True, False]).reset_index(drop=True)


def casa_vigente(act: pd.DataFrame, fin: date) -> pd.DataFrame:
    """
    Casa con la que la emisora operó su fondo en el aviso más reciente (≤ fin),
    desde cuándo opera ininterrumpidamente con ella y cuál usaba antes.
    Es la mejor aproximación pública a "quién tiene el contrato del fondo".
    """
    a = _base(act, date(1900, 1, 1), fin)
    if a.empty:
        return pd.DataFrame()
    dia = (a.groupby(["EMISORA", "FECHA_OPERACION", "CASA_BOLSA"])["IMPORTE"].sum().reset_index()
           .sort_values(["EMISORA", "FECHA_OPERACION", "IMPORTE"]))
    # En días con varias casas, la de mayor importe representa el día.
    rep = dia.groupby(["EMISORA", "FECHA_OPERACION"]).tail(1).sort_values(["EMISORA", "FECHA_OPERACION"])
    filas = []
    for emi, g in rep.groupby("EMISORA"):
        casas = g["CASA_BOLSA"].tolist()
        fechas = g["FECHA_OPERACION"].tolist()
        actual = casas[-1]
        k = len(casas) - 1
        while k > 0 and casas[k - 1] == actual:
            k -= 1
        anterior = casas[k - 1] if k > 0 else None
        ult_dia = dia[(dia["EMISORA"] == emi) & (dia["FECHA_OPERACION"] == fechas[-1])]
        # Reparto de las últimas 4 semanas de actividad de la emisora (detecta mandatos compartidos).
        rec = dia[(dia["EMISORA"] == emi) & (dia["FECHA_OPERACION"] > fechas[-1] - pd.Timedelta(days=28))]
        rep30 = rec.groupby("CASA_BOLSA")["IMPORTE"].sum().sort_values(ascending=False)
        rep30 = 100 * rep30 / rep30.sum() if rep30.sum() > 0 else rep30
        reparto = " · ".join(f"{c} {v:.0f}%" for c, v in rep30.items())
        filas.append({"EMISORA": emi, "CASA_VIGENTE": actual, "DESDE": fechas[k].date(),
                      "ULTIMA_OPERACION": fechas[-1].date(), "CASA_ANTERIOR": anterior,
                      "CAMBIO": fechas[k].date() if anterior else None,
                      "CASAS_ULTIMO_DIA": ", ".join(ult_dia.sort_values("IMPORTE", ascending=False)["CASA_BOLSA"]),
                      "REPARTO_4S": reparto, "COMPARTIDO": len(rep30) > 1})
    out = pd.DataFrame(filas)
    out["NOMBRE_VIGENTE"] = out["CASA_VIGENTE"].map(nombre)
    return out


def matriz(act: pd.DataFrame, ini: date, fin: date, medida: str = "IMPORTE",
           max_casas: int = 12) -> tuple[pd.DataFrame, list[str]]:
    """
    Una fila por emisora: totales del periodo, casa principal, casa vigente y la
    ponderación (%) de cada casa según `medida` ('IMPORTE' o 'N_OPS'). Las casas
    fuera de las `max_casas` más grandes del periodo se agrupan en "OTRAS".
    Devuelve (tabla, columnas_de_casas).
    """
    det = detalle(act, ini, fin)
    if det.empty:
        return pd.DataFrame(), []
    pct = "PCT_IMPORTE" if medida == "IMPORTE" else "PCT_OPS"
    orden = det.groupby("CASA_BOLSA")[medida].sum().sort_values(ascending=False)
    top = list(orden.index[:max_casas])
    d = det.assign(COL=np.where(det["CASA_BOLSA"].isin(top), det["CASA_BOLSA"], "OTRAS"))
    piv = d.pivot_table(index="EMISORA", columns="COL", values=pct, aggfunc="sum")
    cols = top + (["OTRAS"] if "OTRAS" in piv.columns else [])
    piv = piv.reindex(columns=cols)

    tot = det.groupby("EMISORA").agg(IMPORTE=("IMPORTE", "sum"), N_OPS=("N_OPS", "sum"),
                                     N_CASAS=("CASA_BOLSA", "nunique"), ULTIMA=("ULTIMA", "max"))
    princ = det.sort_values(pct, ascending=False).groupby("EMISORA").head(1).set_index("EMISORA")
    tot["CASA_PRINCIPAL"] = princ["CASA_BOLSA"]
    tot["PCT_PRINCIPAL"] = princ[pct]
    vig = casa_vigente(act, fin).set_index("EMISORA")
    tot["CASA_VIGENTE"] = vig["CASA_VIGENTE"].reindex(tot.index)
    tot["DESDE"] = vig["DESDE"].reindex(tot.index)
    tot["REPARTO_4S"] = vig["REPARTO_4S"].reindex(tot.index)
    tab = tot.join(piv).sort_values(medida, ascending=False).reset_index()
    tab["IMPORTE"] = tab["IMPORTE"] / 1e6
    return tab, cols


def resumen_casas(act: pd.DataFrame, ini: date, fin: date) -> pd.DataFrame:
    """Por casa: emisoras atendidas, importe, operaciones y participación del periodo."""
    det = detalle(act, ini, fin)
    if det.empty:
        return pd.DataFrame()
    g = det.groupby("CASA_BOLSA").agg(EMISORAS=("EMISORA", "nunique"), IMPORTE=("IMPORTE", "sum"),
                                      N_OPS=("N_OPS", "sum")).sort_values("IMPORTE", ascending=False)
    g["PART_IMPORTE"] = 100 * g["IMPORTE"] / g["IMPORTE"].sum()
    g["PART_OPS"] = 100 * g["N_OPS"] / g["N_OPS"].sum()
    g["IMPORTE"] = g["IMPORTE"] / 1e6
    g["NOMBRE"] = g.index.map(nombre)
    return g.reset_index()


# ---------------------------------------------------------------------------
# Descargas
# ---------------------------------------------------------------------------

def excel_bytes(tab: pd.DataFrame, cols: list[str], det: pd.DataFrame, casas: pd.DataFrame,
                ini: date, fin: date, medida: str) -> bytes:
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        t = tab.rename(columns={"IMPORTE": "IMPORTE (MXN M)", "N_OPS": "OPERACIONES", "N_CASAS": "NO. CASAS",
                                "PCT_PRINCIPAL": "% PRINCIPAL"})
        t.to_excel(xw, sheet_name="Emisoras x casas", index=False, startrow=2)
        ws = xw.sheets["Emisoras x casas"]
        ws["A1"] = f"Emisoras y casas de bolsa · {ini:%d/%m/%Y} – {fin:%d/%m/%Y} · ponderación por {MEDIDAS[medida].lower()} (%)"
        det.to_excel(xw, sheet_name="Detalle emisora-casa", index=False)
        casas.to_excel(xw, sheet_name="Casas", index=False)
        vig = tab[["EMISORA", "CASA_VIGENTE", "DESDE"]]
        vig.to_excel(xw, sheet_name="Casa vigente", index=False)
    return buf.getvalue()


def pdf_bytes(tab: pd.DataFrame, cols: list[str], casas: pd.DataFrame, ini: date, fin: date,
              medida: str, filas_pag: int = 30) -> bytes:
    """PDF horizontal con la identidad de Punto: casas del periodo + matriz emisora × casa."""
    import io
    from datetime import datetime, timedelta, timezone

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                    TableStyle)

    from src import reporte_pdf as R

    R._registrar_fuentes()
    h = R._hex
    est_tit = ParagraphStyle("t", fontName=R._F["regular"], fontSize=22, leading=26, textColor=h(R.TEXT))
    est_sub = ParagraphStyle("s", fontName=R._F["regular"], fontSize=8.4, leading=11, textColor=h(R.MUTED))
    est_nota = ParagraphStyle("n", fontName=R._F["regular"], fontSize=6.8, leading=8.6, textColor=h(R.MUTED))
    est_h3 = ParagraphStyle("h", fontName=R._F["bold"], fontSize=10.5, leading=13, textColor=h(R.TEXT))

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=(R.PAGE_W, R.PAGE_H), leftMargin=R.M, rightMargin=R.M, topMargin=R.TOP,
                          bottomMargin=34, title="Emisoras y casas de bolsa", author="Punto Casa de Bolsa")
    hoy = datetime.now(timezone(timedelta(hours=-6))).date()
    marco = Frame(R.M, 34, R.PAGE_W - 2 * R.M, R.PAGE_H - R.TOP - 34, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate("n", frames=[marco],
                                       onPage=lambda c, d: R._marco(c, d, R._fecha_larga(hoy, "es"), "es"))])
    ancho = R.PAGE_W - 2 * R.M
    periodo = f"{ini:%d/%m/%Y} – {fin:%d/%m/%Y}"
    pond = MEDIDAS[medida].lower()
    s = [Paragraph("Emisoras y casas de bolsa", est_tit), Spacer(1, 2),
         Paragraph(f"Con quién operan los fondos de recompra · {periodo} · ponderación por {pond}", est_sub),
         Spacer(1, 10)]

    # Resumen por casa
    datos = [["Casa", "Nombre", "Emisoras", "Importe (MXN M)", "Part. importe", "Operaciones", "Part. operaciones"]]
    for r in casas.itertuples():
        datos.append([r.CASA_BOLSA, r.NOMBRE, f"{r.EMISORAS}", R._f_monto(r.IMPORTE), R._f_pct(r.PART_IMPORTE),
                      f"{r.N_OPS:,.0f}", R._f_pct(r.PART_OPS)])
    w = [70, 120, 70, 100, 90, 90, 100]
    t = Table(datos, colWidths=w, rowHeights=[16] + [14] * (len(datos) - 1), hAlign="LEFT")
    st = R._estilo_base(1, 7.6)
    st.add("BACKGROUND", (0, 0), (-1, 0), h(R.PURPLE)); st.add("TEXTCOLOR", (0, 0), (-1, 0), h("#FFFFFF"))
    st.add("ALIGN", (2, 1), (-1, -1), "RIGHT"); st.add("ALIGN", (0, 1), (1, -1), "LEFT")
    for rr in range(1, len(datos)):
        if rr % 2 == 0:
            st.add("BACKGROUND", (0, rr), (-1, rr), h(R.LAVENDER_SOFT))
    t.setStyle(st)
    s += [Paragraph("Casas de bolsa en el periodo", est_h3), Spacer(1, 4), t, Spacer(1, 8),
          Paragraph("Fuente: avisos de recompra publicados por la BMV (casa de bolsa que ejecutó cada operación). "
                    "El contrato del fondo de recompra no es público; la casa que ejecuta las operaciones es la "
                    "evidencia pública de quién opera el fondo.", est_nota), PageBreak()]

    # Matriz emisora × casa (intensidad de color = ponderación)
    cab = ["#", "Emisora", "Importe\n(MXN M)", "Casa\nvigente"] + cols
    cuerpo = []
    for i, r in enumerate(tab.itertuples(index=False), start=1):
        r = r._asdict()
        fila = [str(i), r["EMISORA"], R._f_monto(r["IMPORTE"]), r["CASA_VIGENTE"] or ""]
        fila += ["" if pd.isna(r.get(c)) or r[c] <= 0 else ("<1%" if r[c] < 1 else f"{r[c]:.0f}%") for c in cols]
        cuerpo.append((fila, [r.get(c) for c in cols]))
    w_fijos = [18, 58, 56, 50]
    w_casa = (ancho - sum(w_fijos)) / max(len(cols), 1)
    lav = np.array([int(R.LAVENDER_SOFT[k:k + 2], 16) for k in (1, 3, 5)])
    mor = np.array([int(R.PURPLE[k:k + 2], 16) for k in (1, 3, 5)])
    for p in range(0, len(cuerpo), filas_pag):
        bloque = cuerpo[p:p + filas_pag]
        datos = [cab] + [f for f, _ in bloque]
        t = Table(datos, colWidths=w_fijos + [w_casa] * len(cols), rowHeights=[24] + [13.2] * len(bloque),
                  repeatRows=1)
        st = TableStyle(R._estilo_base(1, 7.2).getCommands())
        st.add("BACKGROUND", (0, 0), (-1, 0), h(R.PURPLE)); st.add("TEXTCOLOR", (0, 0), (-1, 0), h("#FFFFFF"))
        st.add("ALIGN", (2, 1), (-1, -1), "RIGHT"); st.add("ALIGN", (4, 1), (-1, -1), "CENTER")
        st.add("FONT", (1, 1), (1, -1), R._F["bold"], 7.2)
        st.add("LINEBEFORE", (4, 0), (4, -1), 0.8, h(R.PURPLE))
        for rr, (_, vals) in enumerate(bloque, start=1):
            st.add("LINEBELOW", (0, rr), (-1, rr), 0.3, h(R.GRID))
            for cc, v in enumerate(vals, start=4):
                if v is None or pd.isna(v) or v <= 0:
                    continue
                k = min(max(v, 0), 100) / 100
                rgb = (lav + (mor - lav) * k).astype(int)
                st.add("BACKGROUND", (cc, rr), (cc, rr), h("#%02X%02X%02X" % tuple(rgb)))
                if k > 0.55:
                    st.add("TEXTCOLOR", (cc, rr), (cc, rr), h("#FFFFFF"))
        t.setStyle(st)
        s += [Paragraph("Ponderación de cada casa por emisora", est_tit if p == 0 else est_h3), Spacer(1, 2),
              Paragraph(f"% del {pond} de la emisora ejecutado con cada casa · {periodo} · ordenado por importe", est_sub),
              Spacer(1, 6), t, Spacer(1, 4),
              Paragraph("Casa vigente = casa del aviso más reciente de la emisora. Casas fuera de las principales "
                        "del periodo se agrupan en OTRAS.", est_nota), PageBreak()]
    s = s[:-1]
    doc.build(s)
    return buf.getvalue()
