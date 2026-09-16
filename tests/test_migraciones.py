"""Estructural (CLAUDE.md sección 7): init_db() corrido dos veces no falla."""
from __future__ import annotations

from core import database


def test_base_nueva_llega_a_v5(db_temporal):
    conn = database.get_connection()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 5, version

        columnas_productos = {r[1] for r in conn.execute("PRAGMA table_info(productos)")}
        assert "linea_negocio" in columnas_productos

        columnas_venta_items = {r[1] for r in conn.execute("PRAGMA table_info(venta_items)")}
        assert {"linea_negocio", "costo_unitario"} <= columnas_venta_items

        columnas_ventas = {r[1] for r in conn.execute("PRAGMA table_info(ventas)")}
        assert "origen" in columnas_ventas

        tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "categorias" in tablas

        vistas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}
        assert "v_operaciones" in vistas
        conn.execute("SELECT * FROM v_operaciones")  # no debe fallar, vacía o no
    finally:
        conn.close()


def test_categorias_semilla_una_por_linea(db_temporal):
    conn = database.get_connection()
    try:
        lineas = {r[0] for r in conn.execute("SELECT DISTINCT linea_negocio FROM categorias")}
    finally:
        conn.close()
    assert lineas == {"reparacion", "tecnologia", "suplemento"}


def test_init_db_dos_veces_no_falla(db_temporal):
    # Estructural: no se toca sin hablarlo con Oscar (CLAUDE.md sección 7).
    database.init_db()
    database.init_db()
    conn = database.get_connection()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        n_admins = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    finally:
        conn.close()
    assert version == 5
    assert n_admins == 1, "init_db() repetido no debe duplicar el admin"
