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
    origen: str = "pos",
) -> int:
    """Confirma la venta. items: [{producto_id, cantidad, precio_unitario}].

    La categoría, línea de negocio y costo de cada ítem se congelan al momento
    de la venta (igual que el precio): para ítems con producto_id se copian de
    productos; para ítems sin producto_id (ej. servicio técnico) hay que pasar
    linea_negocio explícita (sin default silencioso — el Dashboard no puede
    adivinar la línea de un ítem que no viene de inventario) y opcionalmente
    categoria/costo_unitario. Así el Dashboard no depende de cómo esté
    categorizado el producto *hoy*, sino de cómo estaba el día de esa venta.

    origen distingue de dónde nace la venta: 'pos' (mostrador), 'web' o
    'agenda' (servicio técnico, según el origen de la solicitud).

    Valida stock de todos los ítems antes de tocar nada. Devuelve el N° de nota
    (id de la venta). Lanza ValueError con mensaje humano si algo no cuadra.
    """
    if not items:
        raise ValueError("El carrito está vacío.")
    conn = database.get_connection()
    try:
        total = 0
        datos_por_pid: dict[int, dict] = {}
        for it in items:
            if it["cantidad"] <= 0:
                raise ValueError("Las cantidades deben ser mayores a 0.")
            pid = it.get("producto_id")
            if pid is not None:  # línea de producto: valida stock y trae su foto
                row = conn.execute(
                    "SELECT stock_actual, nombre, categoria, linea_negocio, costo "
                    "FROM productos WHERE id=?",
                    (pid,),
                ).fetchone()
                if row is None:
                    raise ValueError("Uno de los productos ya no existe.")
                if it["cantidad"] > row["stock_actual"]:
                    raise ValueError(
                        f"Stock insuficiente de «{row['nombre']}» "
                        f"(disponible: {row['stock_actual']})."
                    )
                datos_por_pid[pid] = dict(row)
            elif not it.get("linea_negocio"):
                raise ValueError("Falta linea_negocio para un ítem sin producto.")
            total += it["cantidad"] * it["precio_unitario"]

        cur = conn.execute(
            "INSERT INTO ventas (tipo, total, usuario_id, pos_origen, boleta_sii, origen) "
            "VALUES (?,?,?,?,?,?)",
            (tipo, total, usuario_id, pos_origen, boleta_sii, origen),
        )
        venta_id = cur.lastrowid
        for it in items:
            pid = it.get("producto_id")
            subtotal = it["cantidad"] * it["precio_unitario"]
            if pid is not None:
                datos = datos_por_pid[pid]
                categoria = datos["categoria"]
                linea_negocio = datos["linea_negocio"]
                costo_unitario = datos["costo"]
            else:
                categoria = it.get("categoria")
                linea_negocio = it["linea_negocio"]
                costo_unitario = it.get("costo_unitario", 0)
            conn.execute(
                "INSERT INTO venta_items (venta_id, producto_id, cantidad, "
                "precio_unitario, subtotal, descripcion, categoria, linea_negocio, "
                "costo_unitario) VALUES (?,?,?,?,?,?,?,?,?)",
                (venta_id, pid, it["cantidad"], it["precio_unitario"], subtotal,
                 it.get("descripcion"), categoria, linea_negocio, costo_unitario),
            )
            if pid is not None:  # solo los productos mueven stock
                conn.execute(
                    "UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?",
                    (it["cantidad"], pid),
                )
                conn.execute(
                    "INSERT INTO movimientos_stock (producto_id, tipo, cantidad, "
                    "costo_unitario, motivo, usuario_id) VALUES (?,?,?,?,?,?)",
                    (pid, "salida", it["cantidad"], datos_por_pid[pid]["costo"],
                     f"Venta #{venta_id}", usuario_id),
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

    a = inv.crear_producto("Cargador", 5000, 2000, stock_inicial=10, linea_negocio="tecnologia")
    b = inv.crear_producto("Funda", 3000, 1000, stock_inicial=5, linea_negocio="tecnologia")

    vid = registrar_venta(
        [{"producto_id": a, "cantidad": 2, "precio_unitario": 5000},
         {"producto_id": b, "cantidad": 1, "precio_unitario": 3000}],
        pos_origen="Tech", usuario_id=1, boleta_sii="B-123",
    )
    venta, items = obtener_venta(vid)
    assert venta.total == 13000 and len(items) == 2, venta.total
    assert inv.listar_productos(busqueda="Cargador")[0].stock_actual == 8
    # movimiento salida registrado, CON costo_unitario (antes quedaba NULL)
    conn = db.get_connection()
    n = conn.execute(
        "SELECT COUNT(*) FROM movimientos_stock WHERE tipo='salida' AND costo_unitario IS NOT NULL"
    ).fetchone()[0]
    conn.close()
    assert n == 2, n

    # costo_unitario, linea_negocio y origen quedan congelados en venta_items/ventas
    conn = db.get_connection()
    fila = conn.execute(
        "SELECT vi.costo_unitario, vi.linea_negocio, v.origen FROM venta_items vi "
        "JOIN ventas v ON v.id = vi.venta_id WHERE vi.producto_id=?", (a,)
    ).fetchone()
    conn.close()
    assert fila["costo_unitario"] == 2000 and fila["linea_negocio"] == "tecnologia", dict(fila)
    assert fila["origen"] == "pos", "origen por defecto debe ser 'pos'"

    # margen protegido: cambiar el costo del producto DESPUÉS de vender no
    # debe mover lo ya congelado en la venta.
    inv.registrar_entrada(a, 1, 9999)  # sube el costo promedio ponderado
    conn = db.get_connection()
    costo_venta_vieja = conn.execute(
        "SELECT costo_unitario FROM venta_items WHERE producto_id=? LIMIT 1", (a,)
    ).fetchone()[0]
    conn.close()
    assert costo_venta_vieja == 2000, "el costo congelado no puede cambiar"

    # ítem sin producto_id (servicio técnico) sin linea_negocio -> error, sin default silencioso
    try:
        registrar_venta(
            [{"descripcion": "Cambio pantalla", "cantidad": 1, "precio_unitario": 1000}],
            "Servicio Técnico",
        )
        raise AssertionError("debió exigir linea_negocio")
    except ValueError:
        pass

    # stock insuficiente -> rollback, nada cambia
    try:
        registrar_venta([{"producto_id": b, "cantidad": 99, "precio_unitario": 3000}], "Fit")
        raise AssertionError("debió fallar por stock")
    except ValueError:
        pass
    assert inv.listar_productos(busqueda="Funda")[0].stock_actual == 4  # sigue en 4

    assert "TOTAL" in nota_texto(vid) and "Cargador" in nota_texto(vid)
    print("OK pos/repo.py")
