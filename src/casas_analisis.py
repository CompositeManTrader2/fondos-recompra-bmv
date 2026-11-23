"""
Inteligencia de intermediación de fondos de recompra: quién opera cada fondo,
cómo se reparte el mercado entre casas de bolsa, qué tan bien ejecuta cada una,
qué mandatos cambiaron de manos y dónde hay oportunidades comerciales.

Fuente: avisos de recompra de la BMV (casa que ejecutó cada operación),
fondo remanente de los avisos y cierres de Yahoo Finance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src import emisoras_casas as ec
from src import reporte_datos as rd

UMBRAL_EXCLUSIVO = 90.0      # % del importe para considerar el mandato exclusivo
UMBRAL_PRINCIPAL = 60.0      # % para "principal + secundaria"; debajo = compartido
PRIMA_MAX = 0.05             # |precio/cierre − 1| > 5 % se descarta (series distintas, liquidaciones)
RUN_MIN = 3                  # tramos más cortos se consideran alternancia y se ignoran
PREVIA_MIN = 10              # el mandato anterior debió durar al menos esto para hablar de "cambio"
NUEVA_MIN = 5                # y el nuevo al menos esto (o ser el tramo vigente)
MIN_OPS_PRIMA = 3            # avisos con menos operaciones (bloques, liquidaciones de derivados) no cuentan


@dataclass
class AnalisisCasas:
    ini: date
    fin: date
    ini_prev: date
    destacada: str
    kpis: dict
    liga: pd.DataFrame
    mensual: pd.DataFrame
    matriz: pd.DataFrame
    cols: list
    mandatos: pd.DataFrame
    cambios: pd.DataFrame
    oportunidades: dict
    perfiles: dict
    hallazgos: list = field(default_factory=list)


def _primas(act: pd.DataFrame, mercado: pd.DataFrame) -> pd.DataFrame:
    """Compras con su prima vs cierre del día (fracción); vacío si no hay precios."""
    if mercado is None or mercado.empty:
        return pd.DataFrame(columns=["CASA_BOLSA", "EMISORA", "IMPORTE", "PRIMA"])
    m = mercado[["FECHA", "EMISORA", "CLOSE"]].copy()
    m["FECHA"] = pd.to_datetime(m["FECHA"])
    c = act[(act["TIPO"] == "COMPRA") & (act["N_OPS"] >= MIN_OPS_PRIMA)].merge(m, left_on=["FECHA_OPERACION", "EMISORA"], right_on=["FECHA", "EMISORA"])
    c["PRIMA"] = c["PRECIO_PROM"] / c["CLOSE"] - 1
    return c[c["PRIMA"].abs() <= PRIMA_MAX]


def _prima_bps(df: pd.DataFrame) -> float:
    if df.empty or df["IMPORTE"].sum() <= 0:
        return np.nan
    return float(1e4 * (df["PRIMA"] * df["IMPORTE"]).sum() / df["IMPORTE"].sum())


def _cambios(act: pd.DataFrame, ini: date, fin: date) -> pd.DataFrame:
    """
    Cambios de casa principal: la casa de mayor importe de cada sesión forma
    tramos; los de menos de RUN_MIN sesiones se ignoran (alternancia de un
    mandato compartido). Hay cambio cuando un tramo de PREVIA_MIN+ sesiones da
    paso a otra casa que dura NUEVA_MIN+ sesiones o que sigue vigente. Las
    emisoras que alternan casas sin un tramo dominante se reportan como rotación.
    """
    a = act[pd.to_datetime(act["FECHA_OPERACION"]).dt.date <= fin]
    dia = (a.groupby(["EMISORA", "FECHA_OPERACION", "CASA_BOLSA"])["IMPORTE"].sum().reset_index()
           .sort_values(["EMISORA", "FECHA_OPERACION", "IMPORTE"]))
    rep = dia.groupby(["EMISORA", "FECHA_OPERACION"]).tail(1).sort_values(["EMISORA", "FECHA_OPERACION"])
    filas = []
    for emi, g in rep.groupby("EMISORA"):
        casas, fechas = g["CASA_BOLSA"].tolist(), g["FECHA_OPERACION"].tolist()
        tramos = []                                    # [casa, inicio, fin, n]
        for c, f in zip(casas, fechas):
            if tramos and tramos[-1][0] == c:
                tramos[-1][2], tramos[-1][3] = f, tramos[-1][3] + 1
            else:
                tramos.append([c, f, f, 1])
        tramos = [t for t in tramos if t[3] >= RUN_MIN]
        fusion = []
        for t in tramos:
            if fusion and fusion[-1][0] == t[0]:
                fusion[-1][2], fusion[-1][3] = t[2], fusion[-1][3] + t[3]
            else:
                fusion.append(t)
        for j, (prev, nuevo) in enumerate(zip(fusion, fusion[1:]), start=1):
            vigente = j == len(fusion) - 1
            consolidado = prev[3] >= PREVIA_MIN and (nuevo[3] >= NUEVA_MIN or vigente)
            if not (consolidado or (vigente and nuevo[3] >= NUEVA_MIN)):
                continue
            if ini <= nuevo[1].date() <= fin:
                imp = dia[(dia["EMISORA"] == emi) & (dia["CASA_BOLSA"] == nuevo[0]) &
                          (dia["FECHA_OPERACION"] >= nuevo[1])]["IMPORTE"].sum()
                filas.append({"EMISORA": emi, "DE": prev[0], "A": nuevo[0], "FECHA": nuevo[1].date(),
                              "SESIONES_PREVIA": prev[3], "SESIONES_NUEVA": nuevo[3],
                              "IMPORTE_DESDE": imp / 1e6})
    out = pd.DataFrame(filas, columns=["EMISORA", "DE", "A", "FECHA", "SESIONES_PREVIA", "SESIONES_NUEVA",
                                       "IMPORTE_DESDE"])
    return out.sort_values("FECHA", ascending=False).reset_index(drop=True)


def analizar(actividad: pd.DataFrame, docs: pd.DataFrame, mercado: pd.DataFrame, ini: date, fin: date,
             destacada: str = "PUNTO") -> AnalisisCasas:
    act = actividad.copy()
    act["FECHA_OPERACION"] = pd.to_datetime(act["FECHA_OPERACION"])
    act["CASA_BOLSA"] = act["CASA_BOLSA"].fillna("N/D").astype(str).str.strip().replace(ec.EQUIVALENTES)
    for c in ("IMPORTE", "N_OPS", "ACCIONES"):
        act[c] = pd.to_numeric(act[c], errors="coerce").fillna(0.0)
    dur = (fin - ini).days + 1
    ini_prev, fin_prev = ini - timedelta(days=dur), ini - timedelta(days=1)
    per = act[(act["FECHA_OPERACION"].dt.date >= ini) & (act["FECHA_OPERACION"].dt.date <= fin)]
    prev = act[(act["FECHA_OPERACION"].dt.date >= ini_prev) & (act["FECHA_OPERACION"].dt.date <= fin_prev)]
    sectores = rd.sectores()

    # ---------------- Matriz y detalle ----------------
    det = ec.detalle(act, ini, fin)
    tab, cols = ec.matriz(act, ini, fin, "IMPORTE", incluir=(destacada,))
    if det.empty:
        vacio = pd.DataFrame()
        return AnalisisCasas(ini, fin, ini_prev, destacada, {}, vacio, vacio, vacio, [], vacio, vacio, {}, {}, [])
    principal = det.sort_values("PCT_IMPORTE", ascending=False).groupby("EMISORA").head(1).set_index("EMISORA")

    # ---------------- Liga de casas ----------------
    primas = _primas(per, mercado)
    liga = det.groupby("CASA_BOLSA").agg(IMPORTE=("IMPORTE", "sum"), N_OPS=("N_OPS", "sum"),
                                         EMISORAS=("EMISORA", "nunique"))
    liga["PART"] = 100 * liga["IMPORTE"] / liga["IMPORTE"].sum()
    pp = prev.groupby("CASA_BOLSA")["IMPORTE"].sum()
    part_prev = 100 * pp / pp.sum() if pp.sum() > 0 else pp
    liga["PART_PREV"] = part_prev.reindex(liga.index)
    liga["DELTA_PP"] = liga["PART"] - liga["PART_PREV"].fillna(0)
    liga["EXCLUSIVOS"] = principal[principal["PCT_IMPORTE"] >= UMBRAL_EXCLUSIVO].groupby("CASA_BOLSA").size() \
        .reindex(liga.index).fillna(0).astype(int)
    liga["PRINCIPAL_EN"] = principal.groupby("CASA_BOLSA").size().reindex(liga.index).fillna(0).astype(int)
    liga["COMPARTIDOS"] = liga["EMISORAS"] - liga["EXCLUSIVOS"]
    liga["TICKET"] = liga["IMPORTE"] / liga["N_OPS"].where(liga["N_OPS"] > 0)
    liga["PRIMA_BPS"] = pd.Series({c: _prima_bps(g) for c, g in primas.groupby("CASA_BOLSA")}).reindex(liga.index)
    top = det.sort_values("IMPORTE", ascending=False).groupby("CASA_BOLSA")["EMISORA"] \
        .apply(lambda s: ", ".join(s.head(4)))
    liga["TOP"] = top.reindex(liga.index)
    liga = liga.sort_values("IMPORTE", ascending=False)
    liga["RANK"] = range(1, len(liga) + 1)
    rk_prev = part_prev.rank(ascending=False, method="min")
    liga["RANK_PREV"] = rk_prev.reindex(liga.index)
    liga["NOMBRE"] = liga.index.map(ec.nombre)
    liga["IMPORTE"] = liga["IMPORTE"] / 1e6

    # ---------------- Participación mensual (top 6 + otras) ----------------
    per_m = per.assign(MES=per["FECHA_OPERACION"].dt.to_period("M"))
    top6 = list(liga.index[:6])
    if destacada in liga.index and destacada not in top6:
        top6 = top6[:5] + [destacada]
    per_m["COL"] = np.where(per_m["CASA_BOLSA"].isin(top6), per_m["CASA_BOLSA"], "OTRAS")
    mensual = per_m.pivot_table(index="MES", columns="COL", values="IMPORTE", aggfunc="sum").fillna(0)
    mensual = 100 * mensual.div(mensual.sum(axis=1), axis=0)
    mensual = mensual.reindex(columns=[c for c in top6 + ["OTRAS"] if c in mensual.columns])

    # ---------------- Mandatos por emisora ----------------
    vig = ec.casa_vigente(act, fin).set_index("EMISORA")
    sesiones_mercado = max(act[(act["FECHA_OPERACION"].dt.date >= ini) &
                               (act["FECHA_OPERACION"].dt.date <= fin)]["FECHA_OPERACION"].nunique(), 1)
    ses_emi = per.groupby("EMISORA")["FECHA_OPERACION"].nunique()
    signo = per["TIPO"].map({"COMPRA": 1.0, "VENTA": -1.0}).fillna(0)
    neto = (per["IMPORTE"] * signo).groupby(per["EMISORA"]).sum() / 1e6
    rem = rd.remanente(docs, fin) if docs is not None and not docs.empty else pd.Series(dtype=float)
    f_docs = pd.to_datetime(docs["FECHA_OPERACION"], errors="coerce").dt.date if docs is not None and not docs.empty else None
    vigentes = set(docs.loc[(f_docs > fin - timedelta(days=365)) & (f_docs <= fin), "EMISORA"]) if f_docs is not None else set()
    rem = rem[rem.index.isin(vigentes)]
    compras_3m = act[(act["TIPO"] == "COMPRA") & (act["FECHA_OPERACION"].dt.date > fin - timedelta(days=91)) &
                     (act["FECHA_OPERACION"].dt.date <= fin)].groupby("EMISORA")["IMPORTE"].sum() / 3

    man = tab[["EMISORA", "IMPORTE", "N_OPS", "N_CASAS", "CASA_PRINCIPAL", "PCT_PRINCIPAL"]].set_index("EMISORA")
    man["SECTOR"] = [sectores.get(e, "OTHERS") for e in man.index]
    man["NETO"] = neto.reindex(man.index)
    man["TIPO"] = np.select([man["PCT_PRINCIPAL"] >= UMBRAL_EXCLUSIVO, man["PCT_PRINCIPAL"] >= UMBRAL_PRINCIPAL],
                            ["Exclusivo", "Principal + secundaria"], "Compartido")
    man["CASA_VIGENTE"] = vig["CASA_VIGENTE"].reindex(man.index)
    man["DESDE"] = vig["DESDE"].reindex(man.index)
    man["ULTIMA"] = vig["ULTIMA_OPERACION"].reindex(man.index)
    man["REPARTO_4S"] = vig["REPARTO_4S"].reindex(man.index)
    dias = (pd.Timestamp(fin) - pd.to_datetime(man["ULTIMA"])).dt.days
    man["ESTATUS"] = np.select([dias <= 30, dias <= 120], ["Activo", "En pausa"], "Inactivo")
    man["SESIONES"] = ses_emi.reindex(man.index).fillna(0).astype(int)
    man["INTENSIDAD"] = 100 * man["SESIONES"] / sesiones_mercado
    man["REMANENTE"] = rem.reindex(man.index) / 1e6
    man["MESES_FONDO"] = rem.reindex(man.index) / compras_3m.reindex(man.index).where(compras_3m > 0)
    man["PRIMA_BPS"] = pd.Series({e: _prima_bps(g) for e, g in primas.groupby("EMISORA")}).reindex(man.index)
    man = man.reset_index()

    # ---------------- Cambios de mandato ----------------
    cambios = _cambios(act, ini, fin)

    # ---------------- Oportunidades para la casa destacada ----------------
    D = destacada
    con_d = set(det.loc[det["CASA_BOLSA"] == D, "EMISORA"])
    activos = man[man["ESTATUS"] == "Activo"]
    sin_d = activos[~activos["EMISORA"].isin(con_d)].copy()
    sin_d["ORDEN"] = sin_d["REMANENTE"].fillna(0) + sin_d["IMPORTE"]
    sin_d = sin_d.sort_values("ORDEN", ascending=False)
    en_mov = man[(man["TIPO"] != "Exclusivo") | man["EMISORA"].isin(cambios["EMISORA"])]
    en_mov = en_mov[en_mov["CASA_PRINCIPAL"] != D].sort_values("IMPORTE", ascending=False)
    # Fondos disponibles sin operar: remanente vigente y sin operaciones en 45+ días.
    ult_global = act[act["FECHA_OPERACION"].dt.date <= fin].groupby("EMISORA")["FECHA_OPERACION"].max().dt.date
    casa_ult = ec.casa_vigente(act, fin).set_index("EMISORA")["CASA_VIGENTE"]
    dorm = pd.DataFrame({"REMANENTE": rem / 1e6})
    dorm["ULTIMA"] = ult_global.reindex(dorm.index)
    dorm["DIAS_SIN"] = [(fin - u).days if pd.notna(u) else np.nan for u in dorm["ULTIMA"]]
    dorm["CASA_ULTIMA"] = casa_ult.reindex(dorm.index)
    dorm["SECTOR"] = [sectores.get(e, "OTHERS") for e in dorm.index]
    dorm = dorm[(dorm["DIAS_SIN"] >= 45) & (dorm["REMANENTE"] > 0)].sort_values("REMANENTE", ascending=False)
    clientes = det[det["CASA_BOLSA"] == D][["EMISORA", "IMPORTE", "N_OPS", "PCT_IMPORTE", "ULTIMA"]].copy()
    clientes["IMPORTE"] = clientes["IMPORTE"] / 1e6
    clientes = clientes.merge(man[["EMISORA", "TIPO", "CASA_VIGENTE", "REMANENTE"]], on="EMISORA", how="left") \
        .sort_values("IMPORTE", ascending=False)
    oportunidades = {"sin_destacada": sin_d.reset_index(drop=True), "en_movimiento": en_mov.reset_index(drop=True),
                     "fondos_sin_operar": dorm.reset_index().rename(columns={"index": "EMISORA"}),
                     "clientes": clientes.reset_index(drop=True)}

    # ---------------- Perfiles de las casas principales ----------------
    perfiles = {}
    casas_perfil = list(liga.index[:8])
    if destacada in liga.index and destacada not in casas_perfil:
        casas_perfil = casas_perfil[:7] + [destacada]
    for casa in casas_perfil:
        p = det[det["CASA_BOLSA"] == casa][["EMISORA", "IMPORTE", "N_OPS", "PCT_IMPORTE", "ULTIMA"]].copy()
        p["IMPORTE"] = p["IMPORTE"] / 1e6
        perfiles[casa] = p.sort_values("IMPORTE", ascending=False).reset_index(drop=True)

    # ---------------- KPIs ----------------
    cuota = liga["PART"] / 100
    rank_d = int(liga.loc[D, "RANK"]) if D in liga.index else None
    kpis = {
        "importe": liga["IMPORTE"].sum(), "emisoras": int(det["EMISORA"].nunique()), "casas": int(len(liga)),
        "exclusivos": int((man["TIPO"] == "Exclusivo").sum()), "compartidos": int((man["TIPO"] != "Exclusivo").sum()),
        "cambios": int(len(cambios)), "top3": float(liga["PART"].head(3).sum()), "hhi": float((cuota ** 2).sum() * 1e4),
        "lider": liga.index[0], "lider_part": float(liga["PART"].iat[0]), "lider_delta": float(liga["DELTA_PP"].iat[0]),
        "dest_part": float(liga.loc[D, "PART"]) if D in liga.index else 0.0,
        "dest_delta": float(liga.loc[D, "DELTA_PP"]) if D in liga.index else np.nan,
        "dest_rank": rank_d, "dest_emisoras": int(liga.loc[D, "EMISORAS"]) if D in liga.index else 0,
        "prima_mercado": _prima_bps(primas),
        "remanente_sin_d": float(sin_d["REMANENTE"].fillna(0).sum()),
    }
    an = AnalisisCasas(ini, fin, ini_prev, D, kpis, liga, mensual, tab, cols, man, cambios, oportunidades, perfiles)
    an.hallazgos = _hallazgos(an)
    return an


def _m(v) -> str:
    return "n.d." if v is None or pd.isna(v) else f"{v:,.0f}"


def _hallazgos(an: AnalisisCasas) -> list[str]:
    k, L, D = an.kpis, an.liga, an.destacada
    out = [
        f"En el periodo, {k['emisoras']} emisoras operaron sus fondos de recompra con {k['casas']} casas de bolsa, por un "
        f"importe de <b>${_m(k['importe'])} millones</b> (compras + ventas). Las 3 casas más grandes concentran el "
        f"{k['top3']:.0f}% (HHI {k['hhi']:,.0f}).",
        f"<b>{k['lider']}</b> lidera con {k['lider_part']:.1f}% del importe "
        f"({k['lider_delta']:+.1f} pp vs el periodo previo) y opera para {int(L['EMISORAS'].iat[0])} emisoras.",
        f"{k['exclusivos']} emisoras operan con una sola casa (≥{UMBRAL_EXCLUSIVO:.0f}% del importe) y "
        f"{k['compartidos']} reparten su fondo entre varias: esos mandatos compartidos son los más disputables.",
    ]
    ganan = L[L["DELTA_PP"] >= 1].sort_values("DELTA_PP", ascending=False)
    pierden = L[L["DELTA_PP"] <= -1].sort_values("DELTA_PP")
    if not ganan.empty or not pierden.empty:
        g = ", ".join(f"{c} ({v:+.1f} pp)" for c, v in ganan["DELTA_PP"].head(3).items()) or "ninguna"
        p = ", ".join(f"{c} ({v:+.1f} pp)" for c, v in pierden["DELTA_PP"].head(3).items()) or "ninguna"
        out.append(f"Ganan participación: {g}. Pierden: {p}.")
    if not an.cambios.empty:
        ej = "; ".join(f"{r.EMISORA} ({r.DE}→{r.A}, {r.FECHA:%d/%m/%Y})" for r in an.cambios.head(4).itertuples())
        out.append(f"Se detectaron {len(an.cambios)} cambios de casa principal. Más recientes: {ej}.")
    if k["dest_rank"]:
        out.append(f"{D} ocupa el lugar #{k['dest_rank']} con {k['dest_part']:.1f}% del importe "
                   f"({k['dest_delta']:+.1f} pp) y opera para {k['dest_emisoras']} emisoras.")
    else:
        out.append(f"{D} no ejecutó recompras en el periodo.")
    sin = an.oportunidades["sin_destacada"]
    if not sin.empty:
        nombres = ", ".join(sin["EMISORA"].head(5))
        out.append(f"Emisoras activas sin {D} con mayor fondo disponible: {nombres} "
                   f"(fondos remanentes por ${_m(k['remanente_sin_d'])} millones en total).")
    dorm = an.oportunidades["fondos_sin_operar"]
    if not dorm.empty:
        out.append(f"{len(dorm)} emisoras tienen fondo remanente vigente y llevan 45+ días sin operar "
                   f"(${_m(dorm['REMANENTE'].sum())} millones), p. ej. {', '.join(dorm['EMISORA'].head(4))}.")
    return out
