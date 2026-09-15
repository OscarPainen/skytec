"""Acceso a datos de Ajustes: CRUD de `categorias` y sus guardrails de borrado.

Antes de la migración v4 las categorías vivían en un JSON aparte
(core/config.py) y no tenían línea de negocio asociada. Ahora son una tabla:
cada categoría pertenece a exactamente una línea (reparacion/tecnologia/
suplemento), que es el eje fijo del Dashboard.
"""
from __future__ import annotations

from core import database

LINEAS_NEGOCIO = ("reparacion", "tecnologia", "suplemento")


def listar_categorias(linea: str | None = None, solo_activas: bool = True) -> list[dict]:
    sql = "SELECT id, nombre, linea_negocio, activa FROM categorias WHERE 1=1"
    params: list[object] = []
    if solo_activas:
        sql += " AND activa = 1"
    if linea:
        sql += " AND linea_negocio = ?"
        params.append(linea)
    sql += " ORDER BY nombre COLLATE NOCASE"
    conn = database.get_connection()
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def crear_categoria(nombre: str, linea_negocio: str) -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre de la categoría no puede estar vacío.")
    if linea_negocio not in LINEAS_NEGOCIO:
        raise ValueError(f"Línea de negocio inválida: {linea_negocio}")
    conn = database.get_connection()
    try:
        existe = conn.execute(
            "SELECT id FROM categorias WHERE nombre = ? COLLATE NOCASE", (nombre,)
        ).fetchone()
        if existe:
            raise ValueError(f"«{nombre}» ya existe.")
        cur = conn.execute(
            "INSERT INTO categorias (nombre, linea_negocio) VALUES (?,?)",
            (nombre, linea_negocio),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def tiene_ventas(nombre_categoria: str) -> bool:
    # Solo lectura: consulta la foto de categoría congelada en cada venta.
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM venta_items WHERE categoria=?", (nombre_categoria,)
        ).fetchone()
        return row[0] > 0
    finally:
        conn.close()


def tiene_productos(nombre_categoria: str) -> bool:
    # Solo lectura: productos de inventario (vendidos o no) en esa categoría.
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM productos WHERE categoria=?", (nombre_categoria,)
        ).fetchone()
        return row[0] > 0
    finally:
        conn.close()


def desactivar_categoria(categoria_id: int) -> None:
    """Deja de aparecer en los selectores, sin borrar el histórico que la usa."""
    conn = database.get_connection()
    try:
        conn.execute("UPDATE categorias SET activa=0 WHERE id=?", (categoria_id,))
        conn.commit()
    finally:
        conn.close()


def eliminar_categoria(categoria_id: int) -> None:
    """Borrado físico. Llamar solo si tiene_ventas/tiene_productos dan False."""
    conn = database.get_connection()
    try:
        conn.execute("DELETE FROM categorias WHERE id=?", (categoria_id,))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    import os
    import tempfile
    from core import database as db

    tmp = os.path.join(tempfile.mkdtemp(), "t.db")
    os.environ["SKYTEC_DB"] = tmp
    db.DB_PATH = __import__("pathlib").Path(tmp)
    db.init_db()

    # la migración v4 siembra 4 categorías activas
    assert len(listar_categorias()) == 4, listar_categorias()
    assert len(listar_categorias(linea="suplemento")) == 1

    cid = crear_categoria("Fundas", "tecnologia")
    assert len(listar_categorias()) == 5

    try:
        crear_categoria("fundas", "tecnologia")  # duplicado, sin distinguir mayúsculas
        raise AssertionError("debió rechazar el duplicado")
    except ValueError:
        pass

    try:
        crear_categoria("Inventada", "no_existe")
        raise AssertionError("debió rechazar línea inválida")
    except ValueError:
        pass

    assert not tiene_ventas("Fundas") and not tiene_productos("Fundas")

    desactivar_categoria(cid)
    assert len(listar_categorias()) == 4  # ya no aparece entre las activas
    assert len(listar_categorias(solo_activas=False)) == 5

    eliminar_categoria(cid)
    assert len(listar_categorias(solo_activas=False)) == 4

    print("OK ajustes/repo.py")
