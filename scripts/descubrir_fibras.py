"""
Descubre el historial de recompras de CBFIs de FIBRAs y lo agenda para el scanner.

Las FIBRAs publican sus recompras como "Recompras Fibras" (ruta /docs-pub/recofib/),
que el barrido por ID sólo cubre desde que el scanner prueba esa ruta. Este script
consulta la API de búsqueda de BMV por FIBRA, extrae los IDs de sus avisos y los
deja en data/daily/_state.json → "reprocesar_ids"; la siguiente corrida del
scanner los descarga y procesa como cualquier otro aviso.

    python scripts/descubrir_fibras.py            # lista por defecto
    python scripts/descubrir_fibras.py FUNO FMTY  # sólo esas
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import bmv_scraper, daily_scanner  # noqa: E402

FIBRAS = [
    "FUNO", "FMTY", "FIBRAUP", "FSHOP", "FPLUS", "FNOVA", "FINN", "STORAGE", "TERRA", "FIBRAHD",
    "FIBRAMQ", "FIBRAPL", "DANHOS", "FIHO", "FHIPO", "EDUCA", "FVIA", "FCFE", "NEXT", "FEXI",
    "FIBRAMTY", "FMX", "FSITES", "HOTEL",
]


def main(claves: list[str]) -> None:
    estado = daily_scanner.leer_estado()
    docs = daily_scanner.leer_documentos()
    conocidos = set(docs["ID"].astype(int)) if not docs.empty else set()
    ids: set[int] = set()
    for clave in claves:
        try:
            encontrados = bmv_scraper.descubrir_pdfs(clave, max_documentos=5000, auto_resolver=False)
        except Exception as e:  # emisora inexistente o sin documentos
            print(f"  {clave:<9} sin resultados ({str(e)[:60]})")
            continue
        fib = [d for d in encontrados if "/recofib/" in d["url"]]
        nuevos = {int(m.group(1)) for d in fib if (m := re.search(r"recofib_(\d+)_", d["url"]))} - conocidos
        ids |= nuevos
        print(f"  {clave:<9} {len(fib):>4} avisos recofib · {len(nuevos):>4} nuevos")
    previos = set(int(i) for i in estado.get("reprocesar_ids", []))
    estado["reprocesar_ids"] = sorted(previos | ids)
    daily_scanner.guardar_estado(estado)
    print(f"Agendados {len(ids):,} avisos de FIBRAs (total en cola: {len(estado['reprocesar_ids']):,}).")


if __name__ == "__main__":
    main([a.upper() for a in sys.argv[1:]] or FIBRAS)
