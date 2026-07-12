"""Acceso a datos del Punto de Venta.

La confirmación de una venta es una unidad transaccional: crea la venta y sus
ítems, descuenta el stock y registra la salida en movimientos_stock, todo en una
sola transacción (o se hace completo, o no se hace nada). Montos en CLP enteros.
"""
from __future__ import annotations

from core import database
from core.models import Venta


def _clp(valor: int) -> str:
    # Qt-free (esta capa no depende de la UI); la UI tiene su propio formateador.
    return f"${valor:,.0f}".replace(",", ".")


def registrar_venta(
    items: list[dict],
    pos_origen: str,
    usuario_id: int | None = None,
    boleta_sii: str | None = None,
    tipo: str = "directa",
) -> int:
    """Confirma la venta. items: [{producto_id, cantidad, precio_unitario}].

    Valida stock de todos los ítems antes de tocar nada. Devuelve el N° de nota
    (id de la venta). Lanza ValueError con mensaje humano si algo no cuadra.
    """
    if not items:
        raise ValueError("El carrito está vacío.")
    conn = database.get_connection()
    try:
        total = 0
        for it in items:
            if it["cantidad"] <= 0:
                raise ValueError("Las cantidades deben ser mayores a 0.")
            pid = it.get("producto_id")
            if pid is not None:  # línea de producto: valida stock
                row = conn.execute(
                    "SELECT stock_actual, nombre FROM productos WHERE id=?", (pid,)
                ).fetchone()
                if row is None:
                    raise ValueError("Uno de los productos ya no existe.")
                if it["cantidad"] > row["stock_actual"]:
                    raise ValueError(
                        f"Stock insuficiente de «{row['nombre']}» "
                        f"(disponible: {row['stock_actual']})."
                    )
            total += it["cantidad"] * it["precio_unitario"]

        cur = conn.execute(
            "INSERT INTO ventas (tipo, total, usuario_id, pos_origen, boleta_sii) "
            "VALUES (?,?,?,?,?)",
            (tipo, total, usuario_id, pos_origen, boleta_sii),
        )
        venta_id = cur.lastrowid
        for it in items:
            pid = it.get("producto_id")
            subtotal = it["cantidad"] * it["precio_unitario"]
            conn.execute(
                "INSERT INTO venta_items (venta_id, producto_id, cantidad, "
                "precio_unitario, subtotal, descripcion) VALUES (?,?,?,?,?,?)",
                (venta_id, pid, it["cantidad"], it["precio_unitario"],
                 subtotal, it.get("descripcion")),
            )
            if pid is not None:  # solo los productos mueven stock
                conn.execute(
                    "UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?",
                    (it["cantidad"], pid),
                )
                conn.execute(
                    "INSERT INTO movimientos_stock (producto_id, tipo, cantidad, "
                    "motivo, usuario_id) VALUES (?,?,?,?,?)",
                    (pid, "salida", it["cantidad"], f"Venta #{venta_id}", usuario_id),
                )
        conn.commit()
        return venta_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def obtener_venta(venta_id: int) -> tuple[Venta, list[dict]]:
    conn = database.get_connection()
    try:
        v = conn.execute("SELECT * FROM ventas WHERE id=?", (venta_id,)).fetchone()
        if v is None:
            raise ValueError("Venta inexistente.")
        items = conn.execute(
            "SELECT vi.cantidad, vi.precio_unitario, vi.subtotal, "
            "COALESCE(p.nombre, vi.descripcion, 'Ítem') AS nombre "
            "FROM venta_items vi LEFT JOIN productos p ON p.id = vi.producto_id "
            "WHERE vi.venta_id=?",
            (venta_id,),
        ).fetchall()
        return Venta.from_row(v), [dict(i) for i in items]
    finally:
        conn.close()


def nota_texto(venta_id: int, ancho: int = 40) -> str:
    """Nota de venta en texto plano. La Fase 4 la reusa para la impresión ESC/POS."""
    venta, items = obtener_venta(venta_id)
    negocio = database.get_config("negocio_nombre", "Skytec")
    tipo = "Servicio técnico" if venta.tipo == "servicio_tecnico" else "Venta directa"
    sep = "-" * ancho
    lineas = [
        negocio.center(ancho),
        f"Nota N° {venta.id}".center(ancho),
        sep,
        f"Fecha: {venta.fecha}",
        f"Tipo:  {tipo}",
        f"Caja:  {venta.pos_origen or '-'}",
    ]
    if venta.boleta_sii:
        lineas.append(f"Boleta SII: {venta.boleta_sii}")
    lineas.append(sep)
    for it in items:
        lineas.append(f"{it['cantidad']} x {it['nombre']}")
        monto = _clp(it["subtotal"]).rjust(ancho)
        lineas.append(monto)
    lineas.append(sep)
    lineas.append(f"TOTAL: {_clp(venta.total)}".rjust(ancho))
    return "\n".join(lineas)


if __name__ == "__main__":
    import os
    import tempfile
    from core import database as db
    from modules.inventario import repo as inv

    tmp = os.path.join(tempfile.mkdtemp(), "t.db")
    os.environ["SKYTEC_DB"] = tmp
    db.DB_PATH = __import__("pathlib").Path(tmp)
    db.init_db()

    a = inv.crear_producto("Cargador", 5000, 2000, stock_inicial=10)
    b = inv.crear_producto("Funda", 3000, 1000, stock_inicial=5)

    vid = registrar_venta(
        [{"producto_id": a, "cantidad": 2, "precio_unitario": 5000},
         {"producto_id": b, "cantidad": 1, "precio_unitario": 3000}],
        pos_origen="Tech", usuario_id=1, boleta_sii="B-123",
    )
    venta, items = obtener_venta(vid)
    assert venta.total == 13000 and len(items) == 2, venta.total
    assert inv.listar_productos(busqueda="Cargador")[0].stock_actual == 8
    # movimiento salida registrado
    conn = db.get_connection()
    n = conn.execute("SELECT COUNT(*) FROM movimientos_stock WHERE tipo='salida'").fetchone()[0]
    conn.close()
    assert n == 2, n

    # stock insuficiente -> rollback, nada cambia
    try:
        registrar_venta([{"producto_id": b, "cantidad": 99, "precio_unitario": 3000}], "Fit")
        raise AssertionError("debió fallar por stock")
    except ValueError:
        pass
    assert inv.listar_productos(busqueda="Funda")[0].stock_actual == 4  # sigue en 4

    assert "TOTAL" in nota_texto(vid) and "Cargador" in nota_texto(vid)
    print("OK pos/repo.py")
