"""Acceso a datos de inventario.

Todo el stock se mueve por aquí para que quede registro en `movimientos_stock`
(nunca se toca `productos.stock_actual` a mano). Montos en CLP como enteros.
"""
from __future__ import annotations

from core import database
from core.models import Producto


def listar_productos(
    busqueda: str = "",
    categoria: str | None = None,
    incluir_no_disponibles: bool = False,
) -> list[Producto]:
    sql = "SELECT * FROM productos WHERE 1=1"
    params: list[object] = []
    if not incluir_no_disponibles:
        sql += " AND disponible = 1"
    if busqueda:
        sql += " AND nombre LIKE ?"
        params.append(f"%{busqueda}%")
    if categoria:
        sql += " AND categoria = ?"
        params.append(categoria)
    sql += " ORDER BY nombre COLLATE NOCASE"
    conn = database.get_connection()
    try:
        return [Producto.from_row(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def categorias() -> list[str]:
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT categoria FROM productos "
            "WHERE categoria IS NOT NULL AND categoria <> '' ORDER BY categoria"
        )
        return [r[0] for r in rows]
    finally:
        conn.close()


def valor_inventario() -> tuple[int, int]:
    """Devuelve (unidades_totales, valor_en_CLP) de productos disponibles."""
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(stock_actual),0), "
            "COALESCE(SUM(stock_actual * costo),0) "
            "FROM productos WHERE disponible = 1"
        ).fetchone()
        return int(row[0]), int(row[1])
    finally:
        conn.close()


def crear_producto(
    nombre: str,
    precio_venta: int,
    costo: int,
    stock_inicial: int = 0,
    categoria: str = "",
    descripcion: str = "",
    imagen_path: str = "",
    usuario_id: int | None = None,
) -> int:
    conn = database.get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO productos (nombre, descripcion, imagen_path, precio_venta, "
            "costo, stock_actual, categoria) VALUES (?,?,?,?,?,?,?)",
            (nombre, descripcion, imagen_path, precio_venta, costo, 0, categoria),
        )
        pid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    if stock_inicial > 0:
        registrar_entrada(pid, stock_inicial, costo, usuario_id, motivo="Stock inicial")
    return pid


def registrar_entrada(
    producto_id: int,
    cantidad: int,
    costo_unitario: int,
    usuario_id: int | None = None,
    motivo: str = "Llegada de mercadería",
) -> None:
    """Suma stock y actualiza el costo por promedio ponderado."""
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a 0")
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT stock_actual, costo FROM productos WHERE id=?", (producto_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Producto inexistente")
        stock, costo = row["stock_actual"], row["costo"]
        # ponytail: promedio ponderado móvil. Cambiar a FIFO solo si contabilidad
        # lo exige; para retail chico el promedio es el estándar razonable.
        nuevo_stock = stock + cantidad
        nuevo_costo = round((stock * costo + cantidad * costo_unitario) / nuevo_stock)
        conn.execute(
            "UPDATE productos SET stock_actual=?, costo=? WHERE id=?",
            (nuevo_stock, nuevo_costo, producto_id),
        )
        conn.execute(
            "INSERT INTO movimientos_stock (producto_id, tipo, cantidad, "
            "costo_unitario, motivo, usuario_id) VALUES (?,?,?,?,?,?)",
            (producto_id, "entrada", cantidad, costo_unitario, motivo, usuario_id),
        )
        conn.commit()
    finally:
        conn.close()


def registrar_merma(
    producto_id: int, cantidad: int, motivo: str, usuario_id: int | None = None
) -> None:
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a 0")
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT stock_actual FROM productos WHERE id=?", (producto_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Producto inexistente")
        if cantidad > row["stock_actual"]:
            raise ValueError("No puedes dar de baja más stock del disponible")
        conn.execute(
            "UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?",
            (cantidad, producto_id),
        )
        conn.execute(
            "INSERT INTO movimientos_stock (producto_id, tipo, cantidad, motivo, "
            "usuario_id) VALUES (?,?,?,?,?)",
            (producto_id, "merma", cantidad, motivo, usuario_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_disponible(producto_id: int, disponible: bool) -> None:
    """Baja/alta lógica: no borra histórico."""
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE productos SET disponible=? WHERE id=?",
            (1 if disponible else 0, producto_id),
        )
        conn.commit()
    finally:
        conn.close()


def eliminar_producto(producto_id: int) -> None:
    """Borrado físico. Bloqueado si el producto tiene histórico (usar baja lógica)."""
    conn = database.get_connection()
    try:
        usado = conn.execute(
            "SELECT (SELECT COUNT(*) FROM movimientos_stock WHERE producto_id=?) + "
            "(SELECT COUNT(*) FROM venta_items WHERE producto_id=?)",
            (producto_id, producto_id),
        ).fetchone()[0]
        if usado:
            raise ValueError(
                "Este producto tiene movimientos o ventas registradas. "
                "Márcalo como no disponible en lugar de eliminarlo."
            )
        conn.execute("DELETE FROM productos WHERE id=?", (producto_id,))
        conn.commit()
    finally:
        conn.close()


def mapa_nombres() -> dict[str, int]:
    """nombre (minúsculas, sin espacios extremos) -> id. Para detectar duplicados."""
    conn = database.get_connection()
    try:
        rows = conn.execute("SELECT id, nombre FROM productos")
        return {r["nombre"].strip().lower(): r["id"] for r in rows}
    finally:
        conn.close()


def umbral_stock_bajo() -> int:
    try:
        return int(database.get_config("stock_bajo_umbral", "5") or 5)
    except ValueError:
        return 5


if __name__ == "__main__":
    # Auto-check del núcleo: crear, entrada (promedio ponderado), merma, guardas.
    import os
    import tempfile

    tmp = os.path.join(tempfile.mkdtemp(), "t.db")
    os.environ["SKYTEC_DB"] = tmp
    database.DB_PATH = __import__("pathlib").Path(tmp)
    database.init_db()

    pid = crear_producto("Cargador", precio_venta=5000, costo=2000, stock_inicial=10)
    p = listar_productos()[0]
    assert p.stock_actual == 10 and p.costo == 2000, (p.stock_actual, p.costo)

    registrar_entrada(pid, 10, 4000)  # promedio: (10*2000 + 10*4000)/20 = 3000
    p = listar_productos()[0]
    assert p.stock_actual == 20 and p.costo == 3000, (p.stock_actual, p.costo)
    assert p.valor_inventario == 60000

    registrar_merma(pid, 5, "roto")
    assert listar_productos()[0].stock_actual == 15

    for bad in (lambda: registrar_merma(pid, 999, "x"),
                lambda: registrar_entrada(pid, 0, 1),
                lambda: eliminar_producto(pid)):
        try:
            bad(); raise AssertionError("debio fallar")
        except ValueError:
            pass

    set_disponible(pid, False)
    assert listar_productos() == [] and len(listar_productos(incluir_no_disponibles=True)) == 1
    print("OK inventario/repo.py")
