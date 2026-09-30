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
        "ID", "URL", "ARCHIVO", "EMISORA", "FECHA_OPERACION", "CASA_BOLSA",
        "N_OPS", "ACCIONES", "IMPORTE", "REMANENTE_PRESENTE", "ESTADO", "ERROR", "PROCESADO_EN",
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

def reconstruir_resumen(docs: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Recalcula resumen_diario desde TODOS los parquets de emisoras."""
    if docs is None:
        docs = leer_documentos()
    filas = []
    for p in sorted((REPO_ROOT / "data" / "activos").glob("*/operations.parquet")):
        emisora = p.parent.name
        try:
            df = data_processor.consolidar_operaciones(pd.read_parquet(p))
        except Exception:
            continue
        if df.empty:
            continue
        diarios = data_processor.estadisticos_por_periodo(df, "FECHA")
        extra = df.groupby("FECHA").agg(
            N_CASAS=("CASA_BOLSA", "nunique"),
            N_DOCS=("ARCHIVO_ORIGEN", "nunique"),
        ).reset_index()
        diarios = diarios.merge(extra, on="FECHA", how="left")
        diarios.insert(1, "EMISORA", emisora)
        filas.append(diarios)
    if not filas:
        return pd.DataFrame()
    res = pd.concat(filas, ignore_index=True)

    # Remanente de recursos del fondo: el del documento más reciente del día.
    if not docs.empty and "REMANENTE_PRESENTE" in docs.columns:
        rem = docs.dropna(subset=["REMANENTE_PRESENTE", "FECHA_OPERACION"]).copy()
        if not rem.empty:
            rem["FECHA"] = pd.to_datetime(rem["FECHA_OPERACION"]).dt.normalize()
            rem = rem.sort_values("ID").groupby(["FECHA", "EMISORA"])["REMANENTE_PRESENTE"].last().reset_index()
            res = res.merge(rem, on=["FECHA", "EMISORA"], how="left")
    if "REMANENTE_PRESENTE" not in res.columns:
        res["REMANENTE_PRESENTE"] = pd.NA

    res = res[pd.to_datetime(res["FECHA"]).dt.weekday < 5]
    return res.sort_values(["FECHA", "IMPORTE"], ascending=[True, False]).reset_index(drop=True)


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
    max_ids: int = 60000,
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

    n_proc = max(1, min(4, os.cpu_count() or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool, ProcessPoolExecutor(max_workers=n_proc) as ppool:
        while True:
            if time.time() - t0 > max_minutos * 60:
                res.abortado = f"presupuesto de tiempo ({max_minutos} min) agotado"
                break
            if res.ids_revisados >= max_ids:
                res.abortado = f"límite de IDs ({max_ids:,}) alcanzado"
                break

            ids = [i for i in range(next_id, next_id + CHUNK) if i not in conocidos]
            resultados = list(pool.map(lambda i: _fetch(sess, i), ids))
            errores = [r for r in resultados if r[1] == "error"]

            if ids and len(errores) > 0.5 * len(ids):
                log(f"  ⚠ {len(errores)}/{len(ids)} errores de red en {next_id:,}; reintento en 20 s")
                time.sleep(20)
                resultados = list(pool.map(lambda i: _fetch(sess, i), ids))
                errores = [r for r in resultados if r[1] == "error"]
                if len(errores) > 0.5 * len(ids):
                    res.abortado = f"BMV no responde (≥50 % errores en IDs {next_id:,}+)"
                    res.errores_red += len(errores)
                    break

            res.errores_red += len(errores)
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
                    "FECHA_OPERACION": parsed.fecha_operacion,
                    "CASA_BOLSA": parsed.casa_bolsa,
                    "N_OPS": int(len(ops)),
                    "ACCIONES": float(acc or 0),
                    "IMPORTE": float(imp or 0),
                    "REMANENTE_PRESENTE": parsed.remanente_presente,
                    "ESTADO": estado_doc,
                    "ERROR": parsed.error,
                    "PROCESADO_EN": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
                conocidos.add(doc_id)
                res.docs_nuevos += 1
                hits_esta_corrida += 1
                ultimo_hit_corrida = max(ultimo_hit_corrida, doc_id)

            if pdfs:
                log(f"  · IDs {next_id:,}–{next_id + CHUNK - 1:,}: {len(pdfs)} PDFs ({', '.join(sorted(emisoras_chunk))})")

            if len(docs_nuevos) >= FLUSH_EVERY_DOCS:
                _flush(pendientes_ops, docs_nuevos, dry_run)
                estado["last_hit_id"] = ultimo_hit_corrida
                if not dry_run:
                    guardar_estado(estado)

            next_id += CHUNK
            res.fin_id = next_id - 1
            if next_id - ultimo_hit_corrida > frontier_gap:
                break

    _flush(pendientes_ops, docs_nuevos, dry_run)

    # Ventana de frontera adaptativa: si no hubo hits nuevos, la duplicamos
    # para cruzar huecos largos (feriados); con hits, vuelve a la base.
    estado["frontier_gap"] = FRONTIER_GAP_BASE if hits_esta_corrida else min(frontier_gap * 2, FRONTIER_GAP_MAX)
    estado["last_hit_id"] = ultimo_hit_corrida
    res.duracion_s = round(time.time() - t0, 1)

    if not dry_run:
        docs_all = leer_documentos()
        resumen = reconstruir_resumen(docs_all)
        if not resumen.empty:
            resumen.to_parquet(RESUMEN_FILE, index=False)
        storage.reconstruir_metadatos_indice()
        corrida = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **res.to_dict()}
        estado["last_run_utc"] = corrida["utc"]
        estado["runs"] = ([corrida] + list(estado.get("runs", [])))[:60]
        guardar_estado(estado)

    log(f"■ Fin · {res.ids_revisados:,} IDs · {res.docs_nuevos} docs nuevos · {res.ops_nuevas:,} ops · "
        f"{len(res.emisoras)} emisoras · {res.errores_red} errores · {res.duracion_s}s"
        + (f" · DETENIDO: {res.abortado}" if res.abortado else ""))
    return res
