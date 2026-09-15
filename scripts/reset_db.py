"""Reset destructivo de la base: borra ventas, productos, movimientos y
solicitudes de servicio técnico. Conserva usuarios, config y categorias.

Pensado para dejar la base limpia antes de cargar el catálogo real, al
preparar la entrega (ver docs/plan-ejecucion.md, Fase 4).

Pide escribir la palabra RESET para confirmar (no un simple y/n: un borrado
de toda la base no puede ser un Enter apurado) y hace un respaldo ANTES de
tocar nada — si el respaldo falla, el script se detiene sin borrar.

Uso:
    python scripts/reset_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import backup, database  # noqa: E402

# Orden obligatorio por las FK (con foreign_keys=ON): hijos antes que padres.
# movimientos_stock -> productos; servicios_tecnicos -> solicitudes_reparacion
# y ventas; venta_items -> ventas y productos.
TABLAS_A_BORRAR = [
    "movimientos_stock",
    "servicios_tecnicos",
    "venta_items",
    "ventas",
    "solicitudes_reparacion",
    "productos",
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # consola Windows (cp1252)
    database.init_db()

    print(f"Base de datos: {database.DB_PATH}")
    print()
    print("Esto borra TODAS las ventas, productos, movimientos de stock y")
    print("solicitudes de servicio técnico. Se conservan usuarios, config y")
    print("categorias. Se hace un respaldo antes de borrar.")
    print()
    respuesta = input("Escribe RESET (en mayúsculas) para confirmar: ")
    if respuesta != "RESET":
        print("Cancelado. No se tocó nada.")
        return

    try:
        destino = backup.respaldar_ahora("antes-reset")
    except Exception as e:
        print(f"No se pudo hacer el respaldo previo: {e}")
        print("Reset cancelado: no se borra nada sin respaldo.")
        return
    print(f"Respaldo creado: {destino}")

    conn = database.get_connection()
    try:
        for tabla in TABLAS_A_BORRAR:
            conn.execute(f"DELETE FROM {tabla}")
        for tabla in TABLAS_A_BORRAR:
            conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (tabla,))
        conn.commit()
    finally:
        conn.close()

    print("Listo: ventas, productos, solicitudes y movimientos borrados.")
    print("Se conservaron usuarios, config y categorias.")


if __name__ == "__main__":
    main()
