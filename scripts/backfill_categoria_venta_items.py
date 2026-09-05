"""Backfill de una sola vez: llena venta_items.categoria en ventas ya registradas
antes de la migración v3 (donde la columna quedó NULL).

Dos casos:
  1. Ítems con producto_id: la categoría se copia desde productos.categoria.
  2. Ítems de servicio técnico (sin producto_id, venta.tipo='servicio_tecnico'):
     se fija 'reparacion', igual que hace aceptar() para las ventas nuevas.

Por defecto corre en modo dry-run: solo muestra el SQL exacto y cuántas filas
afectaría, sin escribir nada. Recién con --apply ejecuta los UPDATE.

Uso:
    python scripts/backfill_categoria_venta_items.py            # dry-run
    python scripts/backfill_categoria_venta_items.py --apply    # aplica de verdad
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import database  # noqa: E402

UPDATE_PRODUCTOS = """
UPDATE venta_items
SET categoria = (SELECT p.categoria FROM productos p WHERE p.id = venta_items.producto_id)
WHERE categoria IS NULL AND producto_id IS NOT NULL
"""

COUNT_PRODUCTOS = """
SELECT COUNT(*) FROM venta_items
WHERE categoria IS NULL AND producto_id IS NOT NULL
"""

UPDATE_SERVICIO_TECNICO = """
UPDATE venta_items
SET categoria = 'reparacion'
WHERE categoria IS NULL
  AND producto_id IS NULL
  AND venta_id IN (SELECT id FROM ventas WHERE tipo = 'servicio_tecnico')
"""

COUNT_SERVICIO_TECNICO = """
SELECT COUNT(*) FROM venta_items
WHERE categoria IS NULL
  AND producto_id IS NULL
  AND venta_id IN (SELECT id FROM ventas WHERE tipo = 'servicio_tecnico')
"""

# No debería haber filas así (todo ítem sin producto_id hoy es servicio técnico),
# pero se reportan sin tocarlas por si aparece algún caso no contemplado.
COUNT_ANOMALIAS = """
SELECT COUNT(*) FROM venta_items
WHERE categoria IS NULL
  AND producto_id IS NULL
  AND venta_id IN (SELECT id FROM ventas WHERE tipo != 'servicio_tecnico')
"""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # consola Windows (cp1252) no imprime tildes/─
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Ejecuta los UPDATE de verdad. Sin este flag solo se muestra el plan.",
    )
    args = parser.parse_args()

    conn = database.get_connection()
    try:
        n_productos = conn.execute(COUNT_PRODUCTOS).fetchone()[0]
        n_servicio = conn.execute(COUNT_SERVICIO_TECNICO).fetchone()[0]
        n_anomalias = conn.execute(COUNT_ANOMALIAS).fetchone()[0]

        print(f"Base de datos: {database.DB_PATH}")
        print()
        print("── UPDATE 1: ítems con producto_id (copia productos.categoria) ──")
        print(UPDATE_PRODUCTOS.strip())
        print(f"Filas afectadas: {n_productos}")
        print()
        print("── UPDATE 2: ítems de servicio técnico (fija 'reparacion') ──")
        print(UPDATE_SERVICIO_TECNICO.strip())
        print(f"Filas afectadas: {n_servicio}")
        print()
        if n_anomalias:
            print(f"⚠ {n_anomalias} fila(s) con categoria NULL y producto_id NULL "
                  f"en ventas que NO son 'servicio_tecnico'. No se tocan — revísalas a mano.")
            print()

        if not args.apply:
            print("Modo dry-run: no se ejecutó ningún UPDATE. Corre con --apply para aplicar.")
            return

        conn.execute(UPDATE_PRODUCTOS)
        conn.execute(UPDATE_SERVICIO_TECNICO)
        conn.commit()
        print(f"Aplicado: {n_productos + n_servicio} fila(s) actualizadas.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
