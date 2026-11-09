"""
Análisis profundo para el reporte Net Buybacks: KPIs, dinámica temporal,
concentración, ejecución de los programas, momentum, intermediarios y calidad
de datos. Todo se calcula a partir de las mismas tablas que `reporte_datos`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src import reporte_datos as rd


@dataclass
class Analisis:
    kpis: dict
    mensual: pd.DataFrame          # 36 meses: NETO, COMPRA, VENTA, N_COMPRADORAS, N_VENDEDORAS
    stats_mensual: dict
    acumulado: pd.DataFrame        # índice = día del año, columnas = años (MXN millones acumulados)
    concentracion: dict
    pareto: pd.DataFrame           # emisoras LTM ordenadas con % acumulado
    ejecucion: pd.DataFrame
    aceleran: pd.DataFrame
    desaceleran: pd.DataFrame
    inician: pd.DataFrame
    pausan: pd.DataFrame
    vendedoras: pd.DataFrame
    casas: pd.DataFrame
    calidad: dict
    hallazgos: dict = field(default_factory=dict)   # idioma → lista de frases


def _meses_completos(corte: date, n: int) -> pd.PeriodIndex:
    ult = pd.Timestamp(corte).to_period("M")
    if corte.day < 25:
        ult -= 1
    return pd.period_range(ult - (n - 1), ult, freq="M")


def analizar(actividad: pd.DataFrame, docs: pd.DataFrame, mercado: pd.DataFrame, corte: date,
             d: rd.Datos | None = None) -> Analisis:
    d = d or rd.preparar(actividad, docs, mercado, corte)
    a = rd._con_signo(actividad[pd.to_datetime(actividad["FECHA_OPERACION"]).dt.date <= corte])
    a["MES"] = a["FECHA_OPERACION"].dt.to_period("M")
    cob = d.cobertura
    per = d.periodos
    circ = rd.circulacion(docs, corte)
    precio = rd.cierre(mercado, corte)
    mcap = (circ * precio).dropna()
    # Remanente sólo de programas vigentes: emisoras con algún aviso en los últimos 12 meses.
    rem = rd.remanente(docs, corte)
    f_docs = pd.to_datetime(docs["FECHA_OPERACION"], errors="coerce").dt.date
    vigentes = set(docs.loc[(f_docs > corte - timedelta(days=365)) & (f_docs <= corte), "EMISORA"])
    rem = rem[rem.index.isin(vigentes)]

    # ---------------- Mensual 36M ----------------
    meses = _meses_completos(corte, 36)
    meses = meses[[rd.cubierto(m.start_time.date(), cob) for m in meses]]
    am = a[a["MES"].isin(meses)]
    pe = am.groupby(["MES", "EMISORA"])[["NETO_MXN", "C_MXN", "V_MXN"]].sum()
    men = pe.groupby(level="MES").agg(NETO=("NETO_MXN", "sum"), COMPRA=("C_MXN", "sum"), VENTA=("V_MXN", "sum"))
    men["N_COMPRADORAS"] = pe["NETO_MXN"].gt(0).groupby(level="MES").sum()
    men["N_VENDEDORAS"] = pe["NETO_MXN"].lt(0).groupby(level="MES").sum()
    men = men.reindex(meses).fillna(0)
    for c in ("NETO", "COMPRA", "VENTA"):
        men[c] = men[c] / 1e6
    men["PROM_12M"] = men["NETO"].rolling(12, min_periods=12).mean()

    ult12 = men["NETO"].iloc[-12:]
    ultimo = men["NETO"].iloc[-1] if len(men) else np.nan
    stats = {
        "mes_ultimo": meses[-1] if len(meses) else None,
        "ultimo": ultimo,
        "prom_12m": ult12.mean(),
        "mediana_12m": ult12.median(),
        "desv_12m": ult12.std(),
        "max_12m": ult12.max(), "mes_max": ult12.idxmax() if len(ult12) else None,
        "min_12m": ult12.min(), "mes_min": ult12.idxmin() if len(ult12) else None,
        "z_ultimo": (ultimo - ult12.mean()) / ult12.std() if len(ult12) > 2 and ult12.std() > 0 else np.nan,
        "prom_3m": men["NETO"].iloc[-3:].mean(),
        "compradoras_prom_12m": men["N_COMPRADORAS"].iloc[-12:].mean(),
        "compradoras_ultimo": men["N_COMPRADORAS"].iloc[-1] if len(men) else np.nan,
        "n_meses": len(men),
    }

    # ---------------- Acumulado en el año (por día del año) ----------------
    acum = {}
    for y in range(corte.year - 3, corte.year + 1):
        if not rd.cubierto(date(y, 1, 1), cob):
            continue
        fin = min(date(y, 12, 31), corte) if y == corte.year else date(y, 12, 31)
        sub = a[(a["FECHA_OPERACION"].dt.year == y) & (a["FECHA_OPERACION"].dt.date <= fin)]
        s = sub.groupby(sub["FECHA_OPERACION"].dt.dayofyear)["NETO_MXN"].sum().sort_index().cumsum() / 1e6
        dias = np.arange(1, (fin - date(y, 1, 1)).days + 2)
        acum[y] = s.reindex(dias).ffill().fillna(0)
    acumulado = pd.DataFrame(acum)

    # ---------------- Concentración LTM ----------------
    ltm = rd.neto(a, per["LTM"].ini, per["LTM"].fin)
    pos = ltm[ltm["NETO_MXN"] > 0]["NETO_MXN"].sort_values(ascending=False) / 1e6
    tot_pos = pos.sum()
    cuota = pos / tot_pos if tot_pos > 0 else pos
    yld = (100 * ltm["NETO_ACC"] / circ.reindex(ltm.index)).dropna()
    conc = {
        "n_compradoras": int((ltm["NETO_MXN"] > 0).sum()),
        "n_vendedoras": int((ltm["NETO_MXN"] < 0).sum()),
        "top1": cuota.iloc[:1].sum() * 100, "top1_emisora": cuota.index[0] if len(cuota) else "—",
        "top5": cuota.iloc[:5].sum() * 100, "top10": cuota.iloc[:10].sum() * 100,
        "hhi": float((cuota ** 2).sum() * 10000),
        "n_equivalente": float(1 / (cuota ** 2).sum()) if len(cuota) else np.nan,
        "yield_mediana": yld[yld > 0].median() if (yld > 0).any() else np.nan,
        "yield_p75": yld[yld > 0].quantile(0.75) if (yld > 0).any() else np.nan,
        "n_yield_1pct": int((yld >= 1).sum()),
    }
    pareto = pd.DataFrame({"MONTO": pos, "CUOTA": cuota * 100})
    pareto["ACUM"] = pareto["CUOTA"].cumsum()

    # Por año: número de emisoras y concentración (para la tabla de amplitud)
    filas_anio = []
    for y in range(corte.year - 4, corte.year + 1):
        ini, fin = date(y, 1, 1), min(date(y, 12, 31), corte)
        if not rd.cubierto(ini, cob):
            continue
        n = rd.neto(a, ini, fin)
        p = n[n["NETO_MXN"] > 0]["NETO_MXN"].sort_values(ascending=False)
        cu = p / p.sum() if p.sum() > 0 else p
        filas_anio.append({"ANIO": y, "NETO": n["NETO_MXN"].sum() / 1e6, "COMPRADORAS": int((n["NETO_MXN"] > 0).sum()),
                           "VENDEDORAS": int((n["NETO_MXN"] < 0).sum()), "TOP5": cu.iloc[:5].sum() * 100,
                           "HHI": float((cu ** 2).sum() * 10000)})
    conc["por_anio"] = pd.DataFrame(filas_anio)

    # ---------------- Ejecución (top 25 compradores LTM) ----------------
    ini_ltm, fin_ltm = per["LTM"].ini, per["LTM"].fin
    altm = a[(a["FECHA_OPERACION"].dt.date >= ini_ltm) & (a["FECHA_OPERACION"].dt.date <= fin_ltm)]
    dias_hab = max(altm["FECHA_OPERACION"].dt.normalize().nunique(), 1)
    dias_compra = altm[altm["C_MXN"] > 0].groupby("EMISORA")["FECHA_OPERACION"].apply(lambda s: s.dt.normalize().nunique())
    ini_3m = corte - timedelta(days=91)
    a3 = a[a["FECHA_OPERACION"].dt.date > ini_3m]
    compra_3m_mes = a3.groupby("EMISORA")["C_MXN"].sum() / 3
    m = mercado.copy() if mercado is not None and not mercado.empty else pd.DataFrame(columns=["FECHA", "EMISORA", "CLOSE"])
    m["FECHA"] = pd.to_datetime(m["FECHA"])
    m = m[(m["FECHA"].dt.date <= corte) & (m["FECHA"].dt.date > corte - timedelta(days=365))].dropna(subset=["CLOSE"])
    rango = m.groupby("EMISORA")["CLOSE"].agg(["min", "max"])
    ej = ltm.copy()
    ej = ej[ej["C_MXN"] > 0].sort_values("NETO_MXN", ascending=False).head(25)
    ej["NETO"] = ej["NETO_MXN"] / 1e6
    ej["YIELD"] = 100 * ej["NETO_ACC"] / circ.reindex(ej.index)
    ej["INTENSIDAD"] = 100 * dias_compra.reindex(ej.index).fillna(0) / dias_hab
    ej["PX_COMPRA"] = ej["C_MXN"] / ej["C_ACC"].where(ej["C_ACC"] > 0)
    ej["CIERRE"] = precio.reindex(ej.index)
    ej["REND"] = 100 * (ej["CIERRE"] / ej["PX_COMPRA"] - 1)
    lo, hi = rango["min"].reindex(ej.index), rango["max"].reindex(ej.index)
    ej["POS_RANGO"] = (100 * (ej["PX_COMPRA"] - lo) / (hi - lo).where(hi > lo)).clip(0, 100)
    ej["REMANENTE"] = rem.reindex(ej.index) / 1e6
    ej["REM_MCAP"] = 100 * rem.reindex(ej.index) / mcap.reindex(ej.index)
    ej["MESES_FONDO"] = rem.reindex(ej.index) / compra_3m_mes.reindex(ej.index).where(compra_3m_mes > 0)
    ejecucion = ej[["NETO", "YIELD", "INTENSIDAD", "PX_COMPRA", "CIERRE", "REND", "POS_RANGO", "REMANENTE",
                    "REM_MCAP", "MESES_FONDO"]]

    # ---------------- Momentum y señales ----------------
    ult3 = _meses_completos(corte, 3)
    ult12m = _meses_completos(corte, 12)
    pm = a.groupby(["EMISORA", "MES"])["NETO_MXN"].sum().unstack(fill_value=0) / 1e6
    p3 = pm.reindex(columns=ult3, fill_value=0).mean(axis=1)
    p12 = pm.reindex(columns=ult12m, fill_value=0).mean(axis=1)
    mom = pd.DataFrame({"PROM_3M": p3, "PROM_12M": p12})
    mom["DIF"] = mom["PROM_3M"] - mom["PROM_12M"]
    mom["YIELD_LTM"] = (100 * ltm["NETO_ACC"] / circ.reindex(ltm.index)).reindex(mom.index)
    sig = mom[(mom["PROM_12M"].abs() >= 1) | (mom["PROM_3M"].abs() >= 1)]
    aceleran = sig[sig["DIF"] > 0].sort_values("DIF", ascending=False).head(10)
    desaceleran = sig[sig["DIF"] < 0].sort_values("DIF").head(10)

    compras = a[a["C_MXN"] > 0]
    ultima_compra = compras.groupby("EMISORA")["FECHA_OPERACION"].max().dt.date
    primera_90 = compras[compras["FECHA_OPERACION"].dt.date > corte - timedelta(days=90)].groupby("EMISORA")["C_MXN"].sum() / 1e6
    previas = compras[(compras["FECHA_OPERACION"].dt.date <= corte - timedelta(days=90)) &
                      (compras["FECHA_OPERACION"].dt.date > corte - timedelta(days=455))]["EMISORA"].unique()
    inician = pd.DataFrame({"COMPRA_90D": primera_90[~primera_90.index.isin(previas)]})
    inician["PRIMERA"] = compras[compras["EMISORA"].isin(inician.index)].groupby("EMISORA")["FECHA_OPERACION"].min().dt.date
    inician = inician.sort_values("COMPRA_90D", ascending=False).head(10)
    if not rd.cubierto(corte - timedelta(days=455), cob):
        inician = inician.iloc[0:0]

    meses_activos = (pm.reindex(columns=ult12m, fill_value=0) > 0).sum(axis=1)
    pausa = pd.DataFrame({"MESES_ACTIVOS_12M": meses_activos, "ULTIMA": ultima_compra.reindex(meses_activos.index)})
    pausa["DIAS_SIN"] = [(corte - f).days if pd.notna(f) else np.nan for f in pausa["ULTIMA"]]
    pausa["REMANENTE"] = rem.reindex(pausa.index) / 1e6
    pausan = pausa[(pausa["MESES_ACTIVOS_12M"] >= 4) & (pausa["DIAS_SIN"] >= 45)].sort_values("MESES_ACTIVOS_12M", ascending=False).head(10)

    vend = ltm[ltm["NETO_MXN"] < 0].copy()
    vend["NETO"] = vend["NETO_MXN"] / 1e6
    vend["VENTA"] = vend["V_MXN"] / 1e6
    vend["PX_VENTA"] = vend["V_MXN"] / vend["V_ACC"].where(vend["V_ACC"] > 0)
    vendedoras = vend.sort_values("NETO")[["NETO", "VENTA", "PX_VENTA"]].head(10)

    # ---------------- Intermediarios (compras brutas LTM) ----------------
    cb = altm[altm["C_MXN"] > 0].groupby("CASA_BOLSA").agg(MONTO=("C_MXN", "sum"), EMISORAS=("EMISORA", "nunique"))
    cb = cb[cb.index.astype(str).str.upper() != "N/D"]
    cb["CUOTA"] = 100 * cb["MONTO"] / cb["MONTO"].sum() if cb["MONTO"].sum() > 0 else 0
    cb["MONTO"] = cb["MONTO"] / 1e6
    casas = cb.sort_values("MONTO", ascending=False)

    # ---------------- Calidad de datos ----------------
    est = docs["ESTADO"].value_counts() if "ESTADO" in docs else pd.Series(dtype=int)
    arch = docs["ARCHIVO"].astype(str) if "ARCHIVO" in docs else pd.Series(dtype=str)
    calidad = {
        "avisos": int(len(docs)),
        "avisos_ok": int(est.get("ok", 0)),
        "reemplazados": int(est.get("reemplazado", 0)),
        "sin_tabla": int(est.get("sin_tabla", 0)),
        "fibras": int(arch.str.startswith("recofib").sum()),
        "emisoras": int(a["EMISORA"].nunique()),
        "cobertura": cob,
        "ultimo_dato": a["FECHA_OPERACION"].max().date() if len(a) else None,
    }

    # ---------------- KPIs ----------------
    tot = d.sectores[d.sectores["SECTOR"] == "TOTAL"].iloc[0]
    kpis = {
        "ytd": tot["YTD_MONTO"], "ytd_yoy": tot.get("YTD_YOY", np.nan), "ytd1": tot["YTD1_MONTO"],
        "ltm": tot["LTM_MONTO"], "ltm_yield": tot["LTM_YIELD"], "y1": tot["Y1_MONTO"],
        "emis_ytd": tot["YTD_EMIS"], "emis_ytd1": tot["YTD1_EMIS"],
        "top5": conc["top5"], "run_rate": (tot["YTD_MONTO"] / max((corte - per["YTD"].ini).days + 1, 1) * 365)
        if pd.notna(tot["YTD_MONTO"]) else np.nan,
        "rem_total": rem[rem > 0].sum() / 1e6,
        "rem_mcap": 100 * rem.reindex(mcap.index).fillna(0).clip(lower=0).sum() / mcap.sum() if mcap.sum() > 0 else np.nan,
    }

    an = Analisis(kpis=kpis, mensual=men, stats_mensual=stats, acumulado=acumulado, concentracion=conc,
                  pareto=pareto, ejecucion=ejecucion, aceleran=aceleran, desaceleran=desaceleran, inician=inician,
                  pausan=pausan, vendedoras=vendedoras, casas=casas, calidad=calidad)
    an.hallazgos = {"es": _hallazgos(an, d, "es"), "en": _hallazgos(an, d, "en")}
    return an


# ---------------------------------------------------------------------------
# Hallazgos en texto (resumen ejecutivo)
# ---------------------------------------------------------------------------

def _m(v) -> str:
    return "n.d." if v is None or pd.isna(v) else f"{v:,.0f}"


def _p(v, dec=1) -> str:
    return "n.d." if v is None or pd.isna(v) else f"{v:.{dec}f}%"


def _hallazgos(an: Analisis, d: rd.Datos, idioma: str) -> list[str]:
    k, s, c = an.kpis, an.stats_mensual, an.concentracion
    es = idioma == "es"
    out = []
    y = d.corte.year
    if pd.notna(k["ytd"]):
        var = k["ytd_yoy"]
        if es:
            txt = f"La recompra neta acumulada en {y} suma <b>${_m(k['ytd'])} millones</b>"
            if pd.notna(var):
                txt += f", {'+' if var >= 0 else ''}{var:.0f}% contra el mismo periodo de {y - 1} (${_m(k['ytd1'])} millones)"
            txt += f"; a este ritmo el año cerraría cerca de ${_m(k['run_rate'])} millones (vs ${_m(k['y1'])} millones en {y - 1})."
        else:
            txt = f"Net buybacks in {y} YTD total <b>MXN {_m(k['ytd'])} million</b>"
            if pd.notna(var):
                txt += f", {'+' if var >= 0 else ''}{var:.0f}% vs. the same period of {y - 1} (MXN {_m(k['ytd1'])} million)"
            txt += f"; at this pace the year would close near MXN {_m(k['run_rate'])} million (vs MXN {_m(k['y1'])} million in {y - 1})."
        out.append(txt)
    sec = d.sectores[d.sectores["SECTOR"] != "TOTAL"].dropna(subset=["YTD_MONTO"])
    if not sec.empty and pd.notna(k["ytd"]) and k["ytd"]:
        top = sec.sort_values("YTD_MONTO", ascending=False).head(2)
        sh = 100 * top["YTD_MONTO"] / k["ytd"]
        nombres = [str(x).title() for x in top["SECTOR"]]
        out.append(
            f"Por sector, {nombres[0]} ({sh.iloc[0]:.0f}% del total) y {nombres[1]} ({sh.iloc[1]:.0f}%) concentran la recompra del año."
            if es else
            f"By sector, {nombres[0]} ({sh.iloc[0]:.0f}% of the total) and {nombres[1]} ({sh.iloc[1]:.0f}%) lead this year's buybacks.")
    if c["n_compradoras"]:
        out.append(
            f"En los últimos 12 meses, {c['n_compradoras']} emisoras fueron compradoras netas y {c['n_vendedoras']} vendedoras netas. "
            f"Las 5 mayores explican el {c['top5']:.0f}% del monto ({c['top1_emisora']} sola, {c['top1']:.0f}%); "
            f"la concentración equivale a {c['n_equivalente']:.0f} emisoras de igual tamaño."
            if es else
            f"Over the last 12 months, {c['n_compradoras']} issuers were net buyers and {c['n_vendedoras']} net sellers. "
            f"The top 5 account for {c['top5']:.0f}% of the amount ({c['top1_emisora']} alone, {c['top1']:.0f}%); "
            f"concentration is equivalent to {c['n_equivalente']:.0f} equal-sized issuers.")
    if s["mes_ultimo"] is not None and pd.notna(s["prom_12m"]):
        mes = s["mes_ultimo"]
        nom = (rd_mes(mes, idioma))
        z = s["z_ultimo"]
        tono_es = "por encima" if s["ultimo"] > s["prom_12m"] else "por debajo"
        tono_en = "above" if s["ultimo"] > s["prom_12m"] else "below"
        out.append(
            f"En {nom} la recompra neta fue de ${_m(s['ultimo'])} millones, {tono_es} del promedio mensual de 12 meses "
            f"(${_m(s['prom_12m'])} millones; {z:+.1f} desviaciones estándar). Emisoras compradoras en el mes: "
            f"{s['compradoras_ultimo']:.0f} (promedio 12M: {s['compradoras_prom_12m']:.0f})."
            if es else
            f"In {nom} net buybacks were MXN {_m(s['ultimo'])} million, {tono_en} the 12-month monthly average "
            f"(MXN {_m(s['prom_12m'])} million; {z:+.1f} standard deviations). Issuers buying in the month: "
            f"{s['compradoras_ultimo']:.0f} (12M average: {s['compradoras_prom_12m']:.0f}).")
    if not an.aceleran.empty:
        nombres = ", ".join(an.aceleran.index[:4])
        out.append(f"Aceleran su ritmo (promedio 3M vs 12M): {nombres}." if es
                   else f"Accelerating (3M vs 12M monthly average): {nombres}.")
    if not an.pausan.empty:
        nombres = ", ".join(an.pausan.index[:4])
        out.append(f"Recompradores habituales sin compras en 45+ días: {nombres}." if es
                   else f"Regular buyers with no purchases in 45+ days: {nombres}.")
    if pd.notna(k["rem_total"]) and k["rem_total"] > 0:
        out.append(
            f"Los fondos de recompra aún disponibles suman ${_m(k['rem_total'])} millones "
            f"({_p(k['rem_mcap'], 2)} del valor de mercado de las emisoras con precio)."
            if es else
            f"Remaining buyback funds total MXN {_m(k['rem_total'])} million "
            f"({_p(k['rem_mcap'], 2)} of the market value of issuers with prices).")
    return out


def rd_mes(mes: pd.Period, idioma: str) -> str:
    nombres = {"es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                      "octubre", "noviembre", "diciembre"],
               "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                      "October", "November", "December"]}
    return f"{nombres[idioma][mes.month - 1]} {mes.year}"
