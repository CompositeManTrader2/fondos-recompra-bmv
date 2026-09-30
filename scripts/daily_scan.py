"""
CLI del scanner diario de recompras BMV.

Uso:
    python scripts/daily_scan.py                       # corrida normal (incremental)
    python scripts/daily_scan.py --seed-id 1540000     # backfill desde un ID
    python scripts/daily_scan.py --rebuild-only        # sólo recalcula resumen + índice
    python scripts/daily_scan.py --dry-run --max-ids 400
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STORAGE_BACKEND"] = "local"

from src import daily_scanner, storage  # noqa: E402


def _step_summary(res: daily_scanner.Resumen) -> None:
    """Escribe una tabla en el resumen del job de GitHub Actions."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lineas = [
        "## 📊 Scanner diario de recompras BMV",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Rango de IDs | {res.inicio_id:,} → {res.fin_id:,} |",
        f"| IDs revisados | {res.ids_revisados:,} |",
        f"| PDFs de recompra nuevos | {res.docs_nuevos:,} |",
        f"| Operaciones nuevas | {res.ops_nuevas:,} |",
        f"| Emisoras con actividad | {len(res.emisoras)} |",
        f"| PDFs sin tabla | {res.sin_tabla} |",
        f"| Errores de red | {res.errores_red} |",
        f"| Duración | {res.duracion_s:,.0f} s |",
    ]
    if res.emisoras:
        lineas += ["", "**Emisoras:** " + ", ".join(sorted(res.emisoras))]
    if res.abortado:
        lineas += ["", f"> ⚠️ Corrida detenida: {res.abortado}. La siguiente corrida continúa desde aquí."]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed-id", type=int, default=None, help="ID inicial (backfill). Por defecto: incremental.")
    ap.add_argument("--max-ids", type=int, default=60000)
    ap.add_argument("--max-minutos", type=float, default=45)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild-only", action="store_true")
    args = ap.parse_args()

    if args.rebuild_only:
        res = daily_scanner.reconstruir_resumen()
        if not res.empty:
            daily_scanner.DAILY_ROOT.mkdir(parents=True, exist_ok=True)
            res.to_parquet(daily_scanner.RESUMEN_FILE, index=False)
        n = storage.reconstruir_metadatos_indice()
        print(f"Resumen: {len(res):,} filas · índice: {n} emisoras")
        return 0

    res = daily_scanner.escanear(
        seed_id=args.seed_id,
        max_ids=args.max_ids,
        max_minutos=args.max_minutos,
        workers=args.workers,
        dry_run=args.dry_run,
    )
    _step_summary(res)
    # Falla el job sólo si BMV no respondió en absoluto (útil para alertas).
    return 2 if (res.abortado and res.ids_revisados == 0) else 0


if __name__ == "__main__":
    sys.exit(main())
