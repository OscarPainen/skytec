"""Vender un producto deja costo_unitario, linea_negocio y origen correctos."""
from __future__ import annotations

import pytest

from core import database
from modules.inventario import repo as inventario
from modules.pos import repo as pos


def test_venta_congela_costo_linea_y_origen(db_temporal):
    pid = inventario.crear_producto(
        "Cargador", precio_venta=1500, costo=1000, stock_inicial=10,
        linea_negocio="tecnologia",
    )
    venta_id = pos.registrar_venta(
        [{"producto_id": pid, "cantidad": 1, "precio_unitario": 1500}],
        pos_origen="Tech",
    )
    conn = database.get_connection()
    try:
        fila = conn.execute(
            "SELECT vi.costo_unitario, vi.linea_negocio, v.origen FROM venta_items vi "
            "JOIN ventas v ON v.id = vi.venta_id WHERE vi.venta_id=?", (venta_id,)
        ).fetchone()
    finally:
        conn.close()
    assert fila["costo_unitario"] == 1000
    assert fila["linea_negocio"] == "tecnologia"
    assert fila["origen"] == "pos"


def test_item_sin_producto_exige_linea_negocio(db_temporal):
    with pytest.raises(ValueError):
        pos.registrar_venta(
            [{"descripcion": "Servicio", "cantidad": 1, "precio_unitario": 1000}],
            pos_origen="Servicio Técnico",
        )


def test_item_sin_producto_con_linea_negocio_ok(db_temporal):
    venta_id = pos.registrar_venta(
        [{"descripcion": "Cambio pantalla", "cantidad": 1, "precio_unitario": 1000,
          "linea_negocio": "reparacion", "costo_unitario": 0}],
        pos_origen="Servicio Técnico", origen="agenda",
    )
    conn = database.get_connection()
    try:
        fila = conn.execute(
            "SELECT vi.linea_negocio, vi.costo_unitario, v.origen FROM venta_items vi "
            "JOIN ventas v ON v.id = vi.venta_id WHERE vi.venta_id=?", (venta_id,)
        ).fetchone()
    finally:
        conn.close()
    assert fila["linea_negocio"] == "reparacion"
    assert fila["costo_unitario"] == 0
    assert fila["origen"] == "agenda"


def test_movimiento_stock_guarda_costo_unitario(db_temporal):
    pid = inventario.crear_producto(
        "Funda", precio_venta=3000, costo=1000, stock_inicial=5, linea_negocio="tecnologia",
    )
    pos.registrar_venta(
        [{"producto_id": pid, "cantidad": 1, "precio_unitario": 3000}], pos_origen="Tech",
    )
    conn = database.get_connection()
    try:
        costo = conn.execute(
            "SELECT costo_unitario FROM movimientos_stock WHERE tipo='salida'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert costo == 1000, "antes de la Fase 1 quedaba NULL"
