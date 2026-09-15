"""Estructural (CLAUDE.md sección 7): el costo congelado en venta_items no
cambia cuando cambia productos.costo. Protege la decisión central de la
Fase 1 — si este test se rompe, el diseño está mal, no el test.
"""
from __future__ import annotations

from core import database
from modules.inventario import repo as inventario
from modules.pos import repo as pos


def test_cambiar_costo_del_producto_no_mueve_ventas_viejas(db_temporal):
    pid = inventario.crear_producto(
        "Repuesto", precio_venta=5000, costo=2000, stock_inicial=10,
        linea_negocio="tecnologia",
    )
    venta_id = pos.registrar_venta(
        [{"producto_id": pid, "cantidad": 1, "precio_unitario": 5000}], pos_origen="Tech",
    )

    inventario.registrar_entrada(pid, 1, 9999)  # sube el costo promedio ponderado

    conn = database.get_connection()
    try:
        costo_congelado = conn.execute(
            "SELECT costo_unitario FROM venta_items WHERE venta_id=?", (venta_id,)
        ).fetchone()[0]
        costo_actual_producto = conn.execute(
            "SELECT costo FROM productos WHERE id=?", (pid,)
        ).fetchone()[0]
    finally:
        conn.close()

    assert costo_congelado == 2000
    assert costo_actual_producto != costo_congelado, "el producto sí debía subir de costo"
