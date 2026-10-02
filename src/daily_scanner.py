"""
Scanner diario de recompras de TODA la BMV.

Cómo descubre los documentos
----------------------------
Cada PDF de recompra vive en una URL pública con un ID global y secuencial
de BMV (compartido con todos los tipos de documento):

    https://www.bmv.com.mx/docs-pub/recompra/recompra_{ID}_1.pdf

Hay ~320 IDs por día hábil y ~10 % son recompras. En lugar de consultar
emisora por emisora, el scanner recorre los IDs hacia adelante desde el
último documento conocido: si la URL responde un PDF, es una recompra
(de la emisora que sea); si responde 404, era otro tipo de documento.
El PDF trae la *Clave de cotización*, así que la emisora sale del parser.

Estado y archivos (todo bajo data/daily/):
    _state.json            → último ID encontrado, ventana de frontera, historial de corridas
    documentos.parquet     → registro de cada PDF procesado (idempotencia)
    resumen_diario.parquet → una fila por (FECHA, EMISORA) — alimenta el monitor

Además cada operación se agrega al parquet de su emisora en
data/activos/{EMISORA}/operations.parquet, así que todas las emisoras
quedan disponibles en el Dashboard individual.
"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

# El scanner siempre escribe al filesystem (el workflow hace un solo commit).
os.environ.setdefault("STORAGE_BACKEND", "local")

from src import data_processor, pdf_parser, storage  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DAILY_ROOT = REPO_ROOT / "data" / "daily"
STATE_FILE = DAILY_ROOT / "_state.json"
DOCS_FILE = DAILY_ROOT / "documentos.parquet"
RESUMEN_FILE = DAILY_ROOT / "resumen_diario.parquet"

URL_TEMPLATE = "https://www.bmv.com.mx/docs-pub/recompra/recompra_{id}_1.pdf"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Último ID conocido al construir el scanner (24-sep-2026). Sólo se usa si no
# hay estado previo ni datos cargados de los que inferir la semilla.
DEFAULT_SEED_ID = 1591442
LOOKBACK_IDS = 800          # re-revisa esta ventana antes del último hit (PDFs publicados tarde)
FRONTIER_GAP_BASE = 1500    # IDs seguidos sin recompra para declarar "frontera"
FRONTIER_GAP_MAX = 24000
CHUNK = 200
FLUSH_EVERY_DOCS = 150
MAX_REPARSE = 4000
MERCADO_FILE_NAME = "mercado.parquet"
ACTIVIDAD_FILE_NAME = "actividad.parquet"


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

def leer_estado() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def guardar_estado(estado: dict) -> None:
    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(estado, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def leer_documentos() -> pd.DataFrame:
    if DOCS_FILE.exists():
        try:
            return pd.read_parquet(DOCS_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=[
        "ID", "URL", "ARCHIVO", "EMISORA", "SERIE", "FECHA_REPORTE", "FECHA_OPERACION", "CASA_BOLSA",
        "N_OPS", "ACCIONES", "IMPORTE", "REMANENTE_PRESENTE", "TESORERIA", "CIRCULACION",
        "ESTADO", "ERROR", "PARSER_VERSION", "PROCESADO_EN",
    ])


def _id_de_archivo(nombre) -> Optional[int]:
    m = re.search(r"recompra_(\d+)_", str(nombre))
    return int(m.group(1)) if m else None


def inferir_semilla() -> int:
    """Máximo ID visto en los datos ya cargados (UI manual) o la constante."""
    ids = []
    for p in (REPO_ROOT / "data" / "activos").glob("*/operations.parquet"):
        try:
            col = pd.read_parquet(p, columns=["ARCHIVO_ORIGEN"])["ARCHIVO_ORIGEN"]
            ids.extend(i for i in col.map(_id_de_archivo).dropna().astype(int).tolist())
        except Exception:
            continue
    return max(ids) if ids else DEFAULT_SEED_ID


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------

def _session(workers: int) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/pdf,*/*"})
    adapter = HTTPAdapter(pool_connections=workers, pool_maxsize=workers, max_retries=1)
    s.mount("https://", adapter)
    return s


def _fetch(sess: requests.Session, doc_id: int, timeout: int = 25) -> tuple[int, str, Optional[bytes]]:
    """Devuelve (id, estado, bytes). estado ∈ {'pdf','miss','error'}."""
    url = URL_TEMPLATE.format(id=doc_id)
    try:
        r = sess.get(url, timeout=timeout)
    except requests.RequestException:
        return doc_id, "error", None
    if r.status_code == 404:
        return doc_id, "miss", None
    if r.status_code == 200:
        # Algunos CDNs responden 200 con HTML de error: validar firma PDF.
        return (doc_id, "pdf", r.content) if r.content[:5] == b"%PDF-" else (doc_id, "miss", None)
    if r.status_code in (403, 429) or r.status_code >= 500:
        return doc_id, "error", None
    return doc_id, "miss", None


def _parse_worker(item: tuple[int, bytes]) -> tuple[int, pdf_parser.ResultadoPDF]:
    doc_id, contenido = item
    return doc_id, pdf_parser.parsear_pdf(contenido, nombre_archivo=f"recompra_{doc_id}_1.pdf")


# ---------------------------------------------------------------------------
# Resumen de mercado
# ---------------------------------------------------------------------------

def _operaciones_todas() -> list[tuple[str, pd.DataFrame]]:
    out = []
    for p in sorted((REPO_ROOT / "data" / "activos").glob("*/operations.parquet")):
        try:
            df = data_processor.consolidar_operaciones(pd.read_parquet(p))
        except Exception:
            continue
        if not df.empty:
            out.append((p.parent.name, df))
    return out


def _serie_por_emisora(docs: pd.DataFrame) -> dict[str, str]:
    """Serie más reciente reportada por cada emisora (del registro)."""
    if docs.empty or "SERIE" not in docs:
        return {}
    s = docs.dropna(subset=["SERIE"]).sort_values("ID")
    return s.groupby("EMISORA")["SERIE"].last().to_dict()


def simbolo_yahoo(emisora: str, serie: Optional[str]) -> str:
    """AMX+B → AMXB.MX · WALMEX+* → WALMEX.MX · GCARSO+A1 → GCARSOA1.MX · FEXI+21 → FEXI21.MX"""
    from src import market_data
    if serie:
        return f"{emisora}{str(serie).replace('*', '')}.MX"
    return market_data.MAPEO_MANUAL.get(emisora, f"{emisora}.MX")


def actualizar_mercado(docs: pd.DataFrame, emisoras: list[str], log=print) -> pd.DataFrame:
    """
    Cierre y volumen diario de Yahoo Finance para cada emisora (una sola
    descarga en lote). Si Yahoo falla, conserva el archivo anterior.
    """
    destino = DAILY_ROOT / MERCADO_FILE_NAME
    previo = pd.read_parquet(destino) if destino.exists() else pd.DataFrame()
    try:
        import yfinance as yf
    except Exception:
        log("  · yfinance no instalado: se omiten datos de mercado")
        return previo
    series = _serie_por_emisora(docs)
    mapa = {simbolo_yahoo(e, series.get(e)): e for e in emisoras}
    if not mapa:
        return previo
    inicio = (datetime.now() - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    try:
        raw = yf.download(list(mapa), start=inicio, group_by="ticker", auto_adjust=False,
                          progress=False, threads=True)
    except Exception as e:
        log(f"  ⚠ Yahoo Finance falló ({e}); se conserva el archivo anterior")
        return previo
    filas = []
    for sym, emi in mapa.items():
        try:
            sub = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
            sub = sub[["Close", "Volume"]].dropna(how="all")
        except KeyError:
            continue
        if sub.empty:
            continue
        sub = sub.reset_index().rename(columns={"Date": "FECHA", "Close": "CLOSE", "Volume": "VOLUMEN"})
        sub["FECHA"] = pd.to_datetime(sub["FECHA"]).dt.tz_localize(None).dt.normalize()
        sub["EMISORA"], sub["SIMBOLO"] = emi, sym
        filas.append(sub[["FECHA", "EMISORA", "SIMBOLO", "CLOSE", "VOLUMEN"]])
    if not filas:
        log("  ⚠ Yahoo no devolvió precios; se conserva el archivo anterior")
        return previo
    mercado = pd.concat(filas, ignore_index=True)
    log(f"  · Mercado: {mercado['EMISORA'].nunique()}/{len(mapa)} emisoras con precio (Yahoo)")
    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    mercado.to_parquet(destino, index=False)
    return mercado


def reconstruir_resumen(docs: Optional[pd.DataFrame] = None, mercado: Optional[pd.DataFrame] = None,
                        ops_todas: Optional[list] = None) -> pd.DataFrame:
    """Recalcula resumen_diario desde TODOS los parquets de emisoras (+ mercado)."""
    if docs is None:
        docs = leer_documentos()
    if ops_todas is None:
        ops_todas = _operaciones_todas()
    filas = []
    for emisora, df in ops_todas:
        diarios = data_processor.estadisticos_por_periodo(df, "FECHA")
        extra = df.groupby("FECHA").agg(
            N_CASAS=("CASA_BOLSA", "nunique"),
            N_DOCS=("ARCHIVO_ORIGEN", "nunique"),
            CASA_PRINCIPAL=("CASA_BOLSA", lambda s: s.mode().iat[0] if not s.mode().empty else None),
        ).reset_index()
        diarios = diarios.merge(extra, on="FECHA", how="left")
        diarios.insert(1, "EMISORA", emisora)
        filas.append(diarios)
    if not filas:
        return pd.DataFrame()
    res = pd.concat(filas, ignore_index=True)

    # Del registro: remanente del fondo, serie y acciones en circulación (doc más reciente del día).
    if not docs.empty:
        reg = docs.dropna(subset=["FECHA_OPERACION"]).copy()
        reg["FECHA"] = pd.to_datetime(reg["FECHA_OPERACION"]).dt.normalize()
        cols = [c for c in ["REMANENTE_PRESENTE", "SERIE", "CIRCULACION"] if c in reg]
        if cols:
            ult = reg.sort_values("ID").groupby(["FECHA", "EMISORA"])[cols].last().reset_index()
            res = res.merge(ult, on=["FECHA", "EMISORA"], how="left")
    for c in ["REMANENTE_PRESENTE", "SERIE", "CIRCULACION"]:
        if c not in res:
            res[c] = pd.NA

    # Mercado: cierre y volumen → % del volumen operado y prima/descuento vs cierre.
    if mercado is not None and not mercado.empty:
        res = res.merge(mercado[["FECHA", "EMISORA", "CLOSE", "VOLUMEN"]], on=["FECHA", "EMISORA"], how="left")
        vol = pd.to_numeric(res["VOLUMEN"], errors="coerce").where(lambda v: v > 0)
        res["PCT_VOLUMEN"] = 100 * pd.to_numeric(res["ACCIONES_COMPRA"], errors="coerce") / vol
        ref = pd.to_numeric(res["VWAP_COMPRA"], errors="coerce").fillna(pd.to_numeric(res["VWAP"], errors="coerce"))
        res["PRIMA_PCT"] = 100 * (ref / pd.to_numeric(res["CLOSE"], errors="coerce") - 1)
    else:
        res["CLOSE"] = res["VOLUMEN"] = res["PCT_VOLUMEN"] = res["PRIMA_PCT"] = pd.NA
    circ = pd.to_numeric(res["CIRCULACION"], errors="coerce").where(lambda v: v > 0)
    res["PCT_CIRC"] = 100 * pd.to_numeric(res["ACCIONES_COMPRA"], errors="coerce") / circ

    res = res[pd.to_datetime(res["FECHA"]).dt.weekday < 5]
    return res.sort_values(["FECHA", "IMPORTE"], ascending=[True, False]).reset_index(drop=True)


def reconstruir_actividad(docs: pd.DataFrame, ops_todas: list) -> pd.DataFrame:
    """
    Tabla 'Buyback Activity': una fila por (fecha de reporte, fecha de
    operación, emisora, serie, casa, lado) con acciones, importe y precio
    promedio ponderado.
    """
    series = _serie_por_emisora(docs)
    reg = docs[["ARCHIVO", "FECHA_REPORTE", "SERIE"]].rename(
        columns={"ARCHIVO": "ARCHIVO_ORIGEN", "FECHA_REPORTE": "_FR", "SERIE": "_SR"}) if not docs.empty and "FECHA_REPORTE" in docs else None
    partes = []
    for emisora, df in ops_todas:
        d = df.copy()
        for c in ["FECHA_REPORTE", "SERIE"]:
            if c not in d:
                d[c] = pd.NA
        if reg is not None:
            # Operaciones cargadas antes del parser v2: completar desde el registro.
            d = d.merge(reg, on="ARCHIVO_ORIGEN", how="left")
            d["FECHA_REPORTE"] = pd.to_datetime(d["FECHA_REPORTE"], errors="coerce").fillna(
                pd.to_datetime(d["_FR"], errors="coerce"))
            d["SERIE"] = d["SERIE"].fillna(d["_SR"])
        d["FECHA_REPORTE"] = pd.to_datetime(d["FECHA_REPORTE"], errors="coerce").fillna(d["FECHA"]).dt.normalize()
        d["SERIE"] = d["SERIE"].fillna(series.get(emisora) or "")
        d["EMISORA"] = emisora
        partes.append(d)
    if not partes:
        return pd.DataFrame()
    todo = pd.concat(partes, ignore_index=True)
    todo["CASA_BOLSA"] = todo["CASA_BOLSA"].fillna("N/D")
    g = todo.groupby(["FECHA_REPORTE", "FECHA", "EMISORA", "SERIE", "CASA_BOLSA", "TIPO"], dropna=False).agg(
        ACCIONES=("NUMERO_DE_ACCIONES", "sum"), IMPORTE=("IMPORTE_OPERACION", "sum"), N_OPS=("PRECIO_UNITARIO", "size"),
    ).reset_index().rename(columns={"FECHA": "FECHA_OPERACION"})
    # float64 puro: los Int64 nullable (pd.NA) rompen operaciones de NumPy en la app.
    for c in ["ACCIONES", "IMPORTE", "N_OPS"]:
        g[c] = pd.to_numeric(g[c], errors="coerce").astype("float64")
    g["PRECIO_PROM"] = g["IMPORTE"] / g["ACCIONES"].where(g["ACCIONES"] > 0)
    return g.sort_values(["FECHA_REPORTE", "EMISORA", "FECHA_OPERACION", "TIPO"]).reset_index(drop=True)


def reconstruir_todo(docs: Optional[pd.DataFrame] = None, con_mercado: bool = True, log=print) -> dict:
    """Recalcula mercado, resumen, actividad e índice. Devuelve conteos."""
    docs = leer_documentos() if docs is None else docs
    ops_todas = _operaciones_todas()
    emisoras = [e for e, _ in ops_todas]
    destino_m = DAILY_ROOT / MERCADO_FILE_NAME
    if con_mercado:
        mercado = actualizar_mercado(docs, emisoras, log=log)
    else:
        mercado = pd.read_parquet(destino_m) if destino_m.exists() else pd.DataFrame()
    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    resumen = reconstruir_resumen(docs, mercado, ops_todas)
    if not resumen.empty:
        resumen.to_parquet(RESUMEN_FILE, index=False)
    actividad = reconstruir_actividad(docs, ops_todas)
    if not actividad.empty:
        actividad.to_parquet(DAILY_ROOT / ACTIVIDAD_FILE_NAME, index=False)
    n_idx = storage.reconstruir_metadatos_indice()
    return {"resumen": len(resumen), "actividad": len(actividad), "mercado": len(mercado), "indice": n_idx}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

@dataclass
class Resumen:
    inicio_id: int = 0
    fin_id: int = 0
    ids_revisados: int = 0
    pdfs_encontrados: int = 0
    docs_nuevos: int = 0
    ops_nuevas: int = 0
    errores_red: int = 0
    sin_tabla: int = 0
    emisoras: set = field(default_factory=set)
    abortado: Optional[str] = None
    duracion_s: float = 0.0

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["emisoras"] = sorted(self.emisoras)
        return d


def _flush(pendientes_ops: dict[str, list[pd.DataFrame]], docs_nuevos: list[dict], dry_run: bool) -> None:
    if dry_run:
        pendientes_ops.clear(); docs_nuevos.clear()
        return
    for emisora, dfs in pendientes_ops.items():
        df = data_processor.consolidar_operaciones(pd.concat(dfs, ignore_index=True))
        if not df.empty:
            df["EMISORA"] = emisora
            storage.guardar_operaciones(emisora, df, modo="append")
    pendientes_ops.clear()
    if docs_nuevos:
        docs = pd.concat([leer_documentos(), pd.DataFrame(docs_nuevos)], ignore_index=True)
        docs = docs.drop_duplicates(subset=["ID"], keep="last").sort_values("ID")
        DAILY_ROOT.mkdir(parents=True, exist_ok=True)
        docs.to_parquet(DOCS_FILE, index=False)
        docs_nuevos.clear()


def escanear(
    seed_id: Optional[int] = None,
    max_ids: int = 200000,
    max_minutos: float = 45,
    workers: int = 6,
    dry_run: bool = False,
    log=print,
) -> Resumen:
    t0 = time.time()
    estado = leer_estado()
    docs = leer_documentos()
    conocidos = set(pd.to_numeric(docs["ID"], errors="coerce").dropna().astype(int)) if not docs.empty else set()

    last_hit = int(estado.get("last_hit_id") or 0)
    if seed_id:
        inicio = int(seed_id)
    elif last_hit:
        inicio = max(1, last_hit - LOOKBACK_IDS + 1)
    else:
        semilla = inferir_semilla()
        inicio = max(1, semilla - 3000)   # primera corrida: ~2 semanas atrás
        last_hit = semilla
    frontier_gap = int(estado.get("frontier_gap") or FRONTIER_GAP_BASE)

    res = Resumen(inicio_id=inicio)
    log(f"▶ Scanner BMV · inicio ID {inicio:,} · último hit {last_hit:,} · frontera {frontier_gap:,} · workers {workers}")

    sess = _session(workers)
    pendientes_ops: dict[str, list[pd.DataFrame]] = {}
    docs_nuevos: list[dict] = []
    hits_esta_corrida = 0
    ultimo_hit_corrida = last_hit
    next_id = inicio

    # IDs que dieron error de red en corridas previas: se reintentan primero,
    # así un timeout puntual nunca deja un documento fuera del historial.
    reintentar = {int(i) for i in estado.get("ids_error", [])} - conocidos
    # Documentos leídos con un parser anterior se re-procesan (acotado por corrida).
    if not docs.empty:
        pv = pd.to_numeric(docs["PARSER_VERSION"] if "PARSER_VERSION" in docs else pd.Series(1, index=docs.index),
                           errors="coerce").fillna(1)
        viejos = pd.to_numeric(docs.loc[pv < pdf_parser.PARSER_VERSION, "ID"], errors="coerce").dropna().astype(int)
        if len(viejos):
            log(f"  ↻ {len(viejos):,} documentos con parser v<{pdf_parser.PARSER_VERSION}; se re-procesan hasta {MAX_REPARSE:,}")
        reintentar |= set(viejos.tolist()[:MAX_REPARSE])
    reintentar = sorted(reintentar)
    errores_run: set[int] = set()

    n_proc = max(1, min(4, os.cpu_count() or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool, ProcessPoolExecutor(max_workers=n_proc) as ppool:

        def _descargar(ids: list[int]) -> list:
            resultados = list(pool.map(lambda i: _fetch(sess, i), ids))
            errores = [r for r in resultados if r[1] == "error"]
            if ids and len(errores) > 0.5 * len(ids):
                log(f"  ⚠ {len(errores)}/{len(ids)} errores de red desde ID {ids[0]:,}; reintento en 20 s")
                time.sleep(20)
                resultados = list(pool.map(lambda i: _fetch(sess, i), ids))
            return resultados

        def _procesar(ids: list[int], etiqueta: str) -> list:
            nonlocal hits_esta_corrida, ultimo_hit_corrida
            resultados = _descargar(ids)
            err_ids = [i for i, est, _ in resultados if est == "error"]
            errores_run.update(err_ids)
            errores_run.difference_update(i for i, est, _ in resultados if est != "error")
            res.errores_red += len(err_ids)
            res.ids_revisados += len(ids)
            pdfs = [(i, c) for i, est, c in resultados if est == "pdf"]
            res.pdfs_encontrados += len(pdfs)
            emisoras_chunk: set[str] = set()
            for doc_id, parsed in ppool.map(_parse_worker, pdfs):
                emisora = (parsed.emisora or "DESCONOCIDA").upper().strip()
                emisoras_chunk.add(emisora)
                ops = parsed.operaciones
                estado_doc = "error" if parsed.error else ("ok" if not ops.empty else "sin_tabla")
                if estado_doc == "sin_tabla":
                    res.sin_tabla += 1
                if not ops.empty:
                    ops = ops.copy()
                    ops["EMISORA"] = emisora
                    pendientes_ops.setdefault(emisora, []).append(ops)
                    res.ops_nuevas += len(ops)
                    res.emisoras.add(emisora)
                acc = pd.to_numeric(ops.get("NUMERO_DE_ACCIONES"), errors="coerce").sum() if not ops.empty else 0
                imp = pd.to_numeric(ops.get("IMPORTE_OPERACION"), errors="coerce").sum() if not ops.empty else 0
                docs_nuevos.append({
                    "ID": doc_id,
                    "URL": URL_TEMPLATE.format(id=doc_id),
                    "ARCHIVO": f"recompra_{doc_id}_1.pdf",
                    "EMISORA": emisora,
                    "SERIE": parsed.serie,
                    "FECHA_REPORTE": parsed.fecha_reporte,
                    "FECHA_OPERACION": parsed.fecha_operacion,
                    "CASA_BOLSA": parsed.casa_bolsa,
                    "N_OPS": int(len(ops)),
                    "ACCIONES": float(acc or 0),
                    "IMPORTE": float(imp or 0),
                    "REMANENTE_PRESENTE": parsed.remanente_presente,
                    "TESORERIA": parsed.acciones_tesoreria,
                    "CIRCULACION": parsed.acciones_circulacion,
                    "ESTADO": estado_doc,
                    "ERROR": parsed.error,
                    "PARSER_VERSION": pdf_parser.PARSER_VERSION,
                    "PROCESADO_EN": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
                conocidos.add(doc_id)
                res.docs_nuevos += 1
                hits_esta_corrida += 1
                ultimo_hit_corrida = max(ultimo_hit_corrida, doc_id)

            if pdfs:
                log(f"  · {etiqueta}: {len(pdfs)} PDFs ({', '.join(sorted(emisoras_chunk))})")
            if len(docs_nuevos) >= FLUSH_EVERY_DOCS:
                _flush(pendientes_ops, docs_nuevos, dry_run)
                estado["last_hit_id"] = ultimo_hit_corrida
                if not dry_run:
                    guardar_estado(estado)
            return err_ids

        # 1) Reintentos de errores de red previos + re-proceso de parser viejo
        for k in range(0, len(reintentar), CHUNK):
            _procesar(reintentar[k:k + CHUNK], f"reproceso {k + 1:,}–{min(k + CHUNK, len(reintentar)):,} de {len(reintentar):,}")

        # 2) Barrido secuencial hasta la frontera
        while True:
            if time.time() - t0 > max_minutos * 60:
                res.abortado = f"presupuesto de tiempo ({max_minutos} min) agotado"
                break
            if res.ids_revisados >= max_ids:
                res.abortado = f"límite de IDs ({max_ids:,}) alcanzado"
                break
            ids = [i for i in range(next_id, next_id + CHUNK) if i not in conocidos]
            err_ids = _procesar(ids, f"IDs {next_id:,}–{next_id + CHUNK - 1:,}")
            if ids and len(err_ids) > 0.5 * len(ids):
                res.abortado = f"BMV no responde (≥50 % errores en IDs {next_id:,}+)"
                break
            next_id += CHUNK
            res.fin_id = next_id - 1
            if next_id - ultimo_hit_corrida > frontier_gap:
                break

    _flush(pendientes_ops, docs_nuevos, dry_run)

    # Ventana de frontera adaptativa: si no hubo hits nuevos, la duplicamos
    # para cruzar huecos largos (feriados); con hits, vuelve a la base.
    estado["frontier_gap"] = FRONTIER_GAP_BASE if hits_esta_corrida else min(frontier_gap * 2, FRONTIER_GAP_MAX)
    estado["last_hit_id"] = ultimo_hit_corrida
    # IDs que siguen fallando (y no son ya documentos conocidos) → siguiente corrida
    estado["ids_error"] = sorted(errores_run - conocidos)[-5000:]
    res.duracion_s = round(time.time() - t0, 1)

    if not dry_run:
        conteos = reconstruir_todo(leer_documentos(), con_mercado=True, log=log)
        log(f"  · Derivados: {conteos}")
        corrida = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **res.to_dict()}
        estado["last_run_utc"] = corrida["utc"]
        estado["runs"] = ([corrida] + list(estado.get("runs", [])))[:60]
        guardar_estado(estado)

    log(f"■ Fin · {res.ids_revisados:,} IDs · {res.docs_nuevos} docs nuevos · {res.ops_nuevas:,} ops · "
        f"{len(res.emisoras)} emisoras · {res.errores_red} errores · {res.duracion_s}s"
        + (f" · DETENIDO: {res.abortado}" if res.abortado else ""))
    return res
