"""
Depuración de avisos de recompra: correcciones, reenvíos y cancelaciones.

Las emisoras corrigen sus avisos a la BMV de tres formas, y si no se aplican
el mismo dinero se cuenta dos veces (o se cuentan operaciones anuladas):

1. **Reemplazo de aviso.** Publican otro aviso para la misma emisora, serie y
   fecha de operación, que parte del mismo "remanente al último reporte" que
   el original (cambio de casa de bolsa, error de captura, reenvío). El aviso
   posterior (ID mayor) sustituye al anterior.
2. **Cancelación por folio.** Vuelven a publicar los mismos folios con 0
   acciones y precio 0: esas operaciones quedan anuladas.
3. **Corrección por folio.** Vuelven a publicar un folio con otros datos
   (p. ej. otra fecha): gana la versión del aviso más reciente.

`avisos_reemplazados` decide (1) con el registro de documentos; las reglas (2)
y (3) se aplican sobre las operaciones en `depurar_por_folio`.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# Un mismo folio sólo se considera la misma operación si los avisos están a
# menos de este número de días (los folios no se reinician en la práctica,
# pero así una eventual reutilización años después no borra operaciones).
VENTANA_FOLIO_DIAS = 120


def id_de_archivo(nombre) -> float:
    m = re.search(r"_(\d+)_\d+\.pdf$", str(nombre))
    return float(m.group(1)) if m else np.nan


def avisos_reemplazados(docs: pd.DataFrame) -> set[str]:
    """
    Nombres de archivo de avisos sustituidos por uno posterior.

    Un aviso B (posterior) sustituye a un aviso A de la misma emisora, serie y
    fecha de operación cuando:
      - ambos parten del mismo remanente "al último reporte" y además B se
        declara modificación, o tienen la misma casa de bolsa, o el mismo
        número de acciones (reenvío); o
      - B se declara modificación y no hay otro aviso con su mismo remanente
        inicial (corrige el aviso del día aunque cambie el saldo).
    Dos avisos del mismo día de casas distintas, con montos distintos y sin
    nota de modificación, se consideran complementarios y se conservan.
    """
    if docs is None or docs.empty:
        return set()
    d = docs[docs["ESTADO"].isin(["ok", "sin_tabla", "reemplazado"])].copy()
    if d.empty:
        return set()
    for c in ("REMANENTE_ULTIMO", "MODIFICACION"):
        if c not in d:
            d[c] = np.nan
    d["MODIFICACION"] = d["MODIFICACION"].fillna(False).astype(bool)
    d["SERIE"] = d["SERIE"].fillna("")
    d["_F"] = pd.to_datetime(d["FECHA_OPERACION"], errors="coerce").dt.normalize()
    d = d.dropna(subset=["_F"])
    clave = ["EMISORA", "SERIE", "_F"]
    d = d[d.groupby(clave)["ID"].transform("size") > 1].sort_values("ID")

    fuera: set[str] = set()
    for _, g in d.groupby(clave):
        filas = g.to_dict("records")
        for j, b in enumerate(filas):
            previos = [a for a in filas[:j] if a["ARCHIVO"] not in fuera]
            if not previos:
                continue
            rem_b = b.get("REMANENTE_ULTIMO")
            mismos = [a for a in previos
                      if pd.notna(rem_b) and pd.notna(a.get("REMANENTE_ULTIMO"))
                      and abs(float(a["REMANENTE_ULTIMO"]) - float(rem_b)) < 0.5]
            for a in mismos:
                if (b["MODIFICACION"] or a.get("CASA_BOLSA") == b.get("CASA_BOLSA")
                        or float(a.get("ACCIONES") or 0) == float(b.get("ACCIONES") or 0)):
                    fuera.add(a["ARCHIVO"])
            if b["MODIFICACION"] and not mismos:
                fuera.update(a["ARCHIVO"] for a in previos)
    return fuera


def depurar_por_folio(ops: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica cancelaciones y correcciones por folio y quita las filas en cero.

    Para cada (EMISORA, FOLIO) se conserva sólo la versión del aviso más
    reciente si los avisos están a menos de VENTANA_FOLIO_DIAS días.
    """
    if ops is None or ops.empty or "FOLIO" not in ops or "ARCHIVO_ORIGEN" not in ops:
        return ops
    o = ops.copy()
    o["_ID"] = o["ARCHIVO_ORIGEN"].map(id_de_archivo)
    o["_F"] = pd.to_datetime(o["FECHA_OPERACION"], errors="coerce")
    con_folio = o["FOLIO"].notna() & o["_ID"].notna()
    if con_folio.any():
        f = o[con_folio].sort_values("_ID")
        clave = ["EMISORA", "FOLIO"] if "EMISORA" in f else ["FOLIO"]
        ultimo_id = f.groupby(clave)["_ID"].transform("max")
        ultima_f = f.groupby(clave)["_F"].transform("last")
        superada = (f["_ID"] < ultimo_id) & ((ultima_f - f["_F"]).abs().dt.days <= VENTANA_FOLIO_DIAS)
        o = o.drop(index=f.index[superada])
    acc = pd.to_numeric(o.get("NUMERO_DE_ACCIONES"), errors="coerce").fillna(0)
    precio = pd.to_numeric(o.get("PRECIO_UNITARIO"), errors="coerce").fillna(0)
    o = o[(acc != 0) | (precio > 0)]
    o = o[pd.to_numeric(o["PRECIO_UNITARIO"], errors="coerce") > 0]
    return o.drop(columns=["_ID", "_F"])
