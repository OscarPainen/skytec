"""Acceso a datos de Servicio Técnico.

Bandeja de solicitudes (web + manuales), servicio (fecha, precio, detalles) y la
integración con el PoS: al aceptar, el servicio genera una NOTA DE VENTA tipo
`servicio_tecnico` (punto de unión con venta directa). Los "vencidos" se derivan
de la fecha comprometida vs. hoy, sin job en segundo plano.
"""
from __future__ import annotations

from datetime import date

from core import database
from modules.pos import repo as pos

# Estados que siguen "vivos" (aún gestionables en agenda).
ACTIVOS = ("pendiente", "revisada", "aceptada", "en_reparacion")


def crear_solicitud_manual(
    modelo: str, nombre: str, email: str, telefono: str,
    tipo_servicio: str, fecha_entrega: str | None,
) -> int:
    conn = database.get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO solicitudes_reparacion (modelo_telefono, cliente_nombre, "
            "cliente_email, cliente_telefono, tipo_servicio, fecha_entrega_solicitada, "
            "estado, origen) VALUES (?,?,?,?,?,?, 'pendiente', 'manual')",
            (modelo, nombre, email, telefono, tipo_servicio, fecha_entrega or None),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _fila(row: dict) -> dict:
    d = dict(row)
    hoy = date.today().isoformat()
    d["vencido"] = bool(
        d.get("fecha_entrega_solicitada")
        and d["fecha_entrega_solicitada"] < hoy
        and d["estado"] not in ("completada", "no_retirada")
    )
    return d


_SELECT = (
    "SELECT s.*, t.fecha_reparacion, t.precio, t.detalles, t.venta_id "
    "FROM solicitudes_reparacion s "
    "LEFT JOIN servicios_tecnicos t ON t.solicitud_id = s.id "
)


def listar(estado: str | None = None) -> list[dict]:
    sql = _SELECT
    params: list[object] = []
    if estado:
        sql += "WHERE s.estado = ? "
        params.append(estado)
    sql += "ORDER BY s.creado_en DESC"
    conn = database.get_connection()
    try:
        return [_fila(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def obtener(solicitud_id: int) -> dict:
    conn = database.get_connection()
    try:
        row = conn.execute(_SELECT + "WHERE s.id = ?", (solicitud_id,)).fetchone()
        if row is None:
            raise ValueError("Solicitud inexistente.")
        return _fila(row)
    finally:
        conn.close()


def guardar_servicio(
    solicitud_id: int, fecha_reparacion: str | None, precio: int, detalles: str
) -> None:
    """Upsert de los datos del servicio. Marca la solicitud como 'revisada'."""
    conn = database.get_connection()
    try:
        existe = conn.execute(
            "SELECT id FROM servicios_tecnicos WHERE solicitud_id=?", (solicitud_id,)
        ).fetchone()
        if existe:
            conn.execute(
                "UPDATE servicios_tecnicos SET fecha_reparacion=?, precio=?, detalles=? "
                "WHERE solicitud_id=?",
                (fecha_reparacion or None, precio, detalles, solicitud_id),
            )
        else:
            conn.execute(
                "INSERT INTO servicios_tecnicos (solicitud_id, fecha_reparacion, "
                "precio, detalles) VALUES (?,?,?,?)",
                (solicitud_id, fecha_reparacion or None, precio, detalles),
            )
        # pendiente -> revisada (no piso estados más avanzados)
        conn.execute(
            "UPDATE solicitudes_reparacion SET estado='revisada' "
            "WHERE id=? AND estado='pendiente'",
            (solicitud_id,),
        )
        conn.commit()
    finally:
        conn.close()


def aceptar(solicitud_id: int, usuario_id: int | None = None) -> int:
    """El cliente aceptó: genera la nota de venta, agenda y cambia estado.

    Devuelve el N° de nota (venta). Requiere precio guardado (> 0).
    """
    s = obtener(solicitud_id)
    if not s.get("precio"):
        raise ValueError("Primero guarda el precio del servicio.")
    if s.get("venta_id"):
        raise ValueError("Este servicio ya fue aceptado y tiene nota de venta.")

    linea = f"Servicio técnico: {s.get('tipo_servicio') or 'Reparación'} " \
            f"{s.get('modelo_telefono') or ''}".strip()
    venta_id = pos.registrar_venta(
        [{"descripcion": linea, "cantidad": 1, "precio_unitario": int(s["precio"])}],
        pos_origen="Servicio Técnico", usuario_id=usuario_id, tipo="servicio_tecnico",
    )
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE servicios_tecnicos SET venta_id=?, estado='aceptada' WHERE solicitud_id=?",
            (venta_id, solicitud_id),
        )
        conn.execute(
            "UPDATE solicitudes_reparacion SET estado='aceptada' WHERE id=?",
            (solicitud_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return venta_id


def cambiar_estado(solicitud_id: int, estado: str) -> None:
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE solicitudes_reparacion SET estado=? WHERE id=?", (estado, solicitud_id)
        )
        conn.commit()
    finally:
        conn.close()


def eliminar(solicitud_id: int) -> None:
    """Elimina la solicitud y su servicio. La nota de venta (si existe) se conserva."""
    conn = database.get_connection()
    try:
        conn.execute("DELETE FROM servicios_tecnicos WHERE solicitud_id=?", (solicitud_id,))
        conn.execute("DELETE FROM solicitudes_reparacion WHERE id=?", (solicitud_id,))
        conn.commit()
    finally:
        conn.close()


# ── Vistas de agenda / excepciones ──────────────────────────────────────────
def agenda_activos() -> list[dict]:
    """Servicios vivos y al día (agendados o pendientes), no vencidos."""
    return [s for s in listar() if s["estado"] in ACTIVOS and not s["vencido"]]


def vencidos() -> list[dict]:
    """Pasó la fecha comprometida y aún no se entregó/retiró."""
    return [s for s in listar() if s["vencido"]]


def no_retiradas() -> list[dict]:
    return listar(estado="no_retirada")


def whatsapp_texto(solicitud_id: int) -> str:
    """Mensaje pre-diseñado con toda la info del servicio."""
    s = obtener(solicitud_id)
    negocio = database.get_config("negocio_nombre", "Skytec")
    precio = f"${int(s['precio']):,.0f}".replace(",", ".") if s.get("precio") else "por confirmar"
    return (
        f"Hola {s.get('cliente_nombre') or ''} 👋\n"
        f"Le escribimos de {negocio} por su equipo *{s.get('modelo_telefono') or ''}*.\n\n"
        f"Servicio: {s.get('tipo_servicio') or 'Reparación'}\n"
        f"Fecha de reparación: {s.get('fecha_reparacion') or 'por confirmar'}\n"
        f"Fecha de entrega: {s.get('fecha_entrega_solicitada') or 'por confirmar'}\n"
        f"Valor: {precio}\n"
        f"{('Detalles: ' + s['detalles']) if s.get('detalles') else ''}\n\n"
        f"¿Confirma que avancemos con el servicio?"
    ).strip()


if __name__ == "__main__":
    import os
    import tempfile

    os.environ["SKYTEC_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
    database.DB_PATH = __import__("pathlib").Path(os.environ["SKYTEC_DB"])
    database.init_db()

    sid = crear_solicitud_manual("iPhone 13", "Ana", "a@x.cl", "56911112222",
                                 "Cambio de pantalla", "2020-01-01")  # entrega pasada
    assert listar()[0]["estado"] == "pendiente"

    # aceptar sin precio -> error
    try:
        aceptar(sid); raise AssertionError("debió exigir precio")
    except ValueError:
        pass

    guardar_servicio(sid, "2020-01-01", 45000, "Pantalla OLED")
    assert obtener(sid)["estado"] == "revisada" and obtener(sid)["precio"] == 45000

    vid = aceptar(sid)
    s = obtener(sid)
    assert s["estado"] == "aceptada" and s["venta_id"] == vid
    # la nota de venta unificada existe y es de tipo servicio_tecnico
    venta, items = pos.obtener_venta(vid)
    assert venta.tipo == "servicio_tecnico" and "Servicio técnico" in items[0]["nombre"]
    assert venta.total == 45000

    # doble aceptación bloqueada
    try:
        aceptar(sid); raise AssertionError("no debe re-aceptar")
    except ValueError:
        pass

    # vencido: entrega 2020 < hoy y no completada
    assert len(vencidos()) == 1 and len(agenda_activos()) == 0
    cambiar_estado(sid, "completada")
    assert len(vencidos()) == 0
    assert "iPhone 13" in whatsapp_texto(sid)
    print("OK servicio_tecnico/repo.py")
