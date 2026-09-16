"""Acceso a datos de Servicio Técnico.

Bandeja de solicitudes (web + manuales), servicio (fecha, precio, detalles) y la
integración con el PoS. La NOTA DE VENTA (tipo `servicio_tecnico`, punto de
unión con venta directa) se genera al COMPLETAR el servicio (completar()), no
al aceptar. Antes se generaba al aceptar: una reparación aceptada y nunca
retirada quedaba contada como ingreso para siempre (Fase 1.5,
docs/flujo-venta.md, hallazgo 1). Los "vencidos" se derivan de la fecha
comprometida vs. hoy, sin job en segundo plano.
"""
from __future__ import annotations

from datetime import date

from core import database
from modules.pos import repo as pos

# Estados que siguen "vivos" (aún gestionables en agenda).
ACTIVOS = ("pendiente", "revisada", "aceptada", "en_reparacion")

# Un "pedido" es una solicitud que todavía vive en la bandeja de Servicio Técnico
# (aún no se acepta/agenda). Al aceptar, pasa a Agenda y sale de esta bandeja.
PEDIDOS = ("pendiente", "revisada")

# Un servicio "agendado" ya pasó por "Cliente aceptó" y vive en Agenda. Recorre
# estos estados SIN salirse de la lista de Agenda: cambiar de estado NO lo borra,
# queda visible hasta que se elimine a mano. Agenda es el "PoS del servicio".
AGENDADOS = ("aceptada", "en_reparacion", "completada", "no_retirada")

# Dentro de AGENDADOS: "activos" es trabajo todavía abierto (nadie puede
# perderlo de vista, por eso agenda_agendados() nunca los recorta);
# "terminales" ya se cerró y solo importa como historial reciente (por eso
# ahí sí se aplica el límite).
ESTADOS_ACTIVOS_AGENDA = ("aceptada", "en_reparacion")
ESTADOS_TERMINALES_AGENDA = ("completada", "no_retirada")


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


def aceptar(solicitud_id: int, usuario_id: int | None = None) -> None:
    """El cliente aceptó: agenda el servicio. YA NO genera la venta — el
    ingreso se reconoce al completar() (ver más abajo), no acá. Requiere
    precio guardado (> 0): sin precio no tiene sentido agendar un trabajo que
    después no se sabría cuánto cobrar.
    """
    s = obtener(solicitud_id)
    if not s.get("precio"):
        raise ValueError("Primero guarda el precio del servicio.")
    if s["estado"] not in PEDIDOS:
        raise ValueError("Esta solicitud ya fue aceptada.")

    conn = database.get_connection()
    try:
        # servicios_tecnicos.estado: columna vestigial (Fase 1.5,
        # docs/flujo-venta.md, hallazgo 4). Nada en el código la lee — el
        # estado real que manda es solicitudes_reparacion.estado, abajo. Se
        # sigue escribiendo por si algún día se retoma, pero no confíes en
        # ella para nada nuevo.
        conn.execute(
            "UPDATE servicios_tecnicos SET estado='aceptada' WHERE solicitud_id=?",
            (solicitud_id,),
        )
        conn.execute(
            "UPDATE solicitudes_reparacion SET estado='aceptada' WHERE id=?",
            (solicitud_id,),
        )
        conn.commit()
    finally:
        conn.close()


def completar(solicitud_id: int, usuario_id: int | None = None) -> int:
    """Cierra el trabajo: ACÁ se genera la nota de venta (acá se reconoce el
    ingreso, no al aceptar) y se marca 'completada'. Devuelve el N° de nota.
    Bloquea completar dos veces (ya tiene venta_id) — mismo guardrail contra
    doble cobro que antes vivía en aceptar().
    """
    s = obtener(solicitud_id)
    if s.get("venta_id"):
        raise ValueError("Este servicio ya tiene nota de venta.")
    if s["estado"] not in AGENDADOS:
        raise ValueError("Solo se puede completar un servicio ya agendado.")

    linea = f"Servicio técnico: {s.get('tipo_servicio') or 'Reparación'} " \
            f"{s.get('modelo_telefono') or ''}".strip()
    # costo_unitario=0: el servicio técnico no tiene costo de repuestos
    # modelado todavía. TODO: cuando exista catálogo de tipos de servicio con
    # costo, reemplazar este 0 (backlog post-entrega, ver docs/plan-ejecucion.md).
    # categoria="Reparaciones" (no "reparacion"): coincide con el nombre
    # exacto que sembró la migración v4 en la tabla categorias, para que el
    # desglose por categoría del Dashboard no muestre un valor huérfano que
    # no está en la lista que gestiona Ajustes.
    venta_id = pos.registrar_venta(
        [{"descripcion": linea, "cantidad": 1, "precio_unitario": int(s["precio"]),
          "categoria": "Reparaciones", "linea_negocio": "reparacion", "costo_unitario": 0}],
        pos_origen="Servicio Técnico", usuario_id=usuario_id, tipo="servicio_tecnico",
        origen="web" if s.get("origen") == "web" else "agenda",
    )
    conn = database.get_connection()
    try:
        # estado='completada' acá también es vestigial, igual que en
        # aceptar() (ver comentario ahí). venta_id SÍ importa: es lo que lee
        # obtener()/_SELECT para saber si el servicio ya tiene nota de venta.
        conn.execute(
            "UPDATE servicios_tecnicos SET venta_id=?, estado='completada' WHERE solicitud_id=?",
            (venta_id, solicitud_id),
        )
        conn.execute(
            "UPDATE solicitudes_reparacion SET estado='completada' WHERE id=?",
            (solicitud_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return venta_id


def cambiar_estado(solicitud_id: int, estado: str) -> None:
    """Transición de estado SIN efectos de negocio. Para 'completada' no se
    usa esta función desde la UI — hay que llamar a completar(), que es la
    que genera la venta. Esta queda para 'en_reparacion' y 'no_retirada',
    que son cambios de estado puros."""
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
def pedidos() -> list[dict]:
    """Bandeja de Servicio Técnico: solo las solicitudes que todavía son 'pedidos'
    (pendiente/revisada). En cuanto se aceptan, pasan a Agenda y salen de aquí, así
    Servicio Técnico queda limpio con las solicitudes por atender."""
    return [s for s in listar() if s["estado"] in PEDIDOS]


def agenda_agendados(limite: int = 15) -> list[dict]:
    """Vista principal de Agenda: TODOS los servicios activos (aceptada,
    en_reparacion — trabajo todavía abierto, sin límite) más los últimos
    `limite` servicios terminales (completada, no_retirada) como historial
    reciente.

    Antes recortaba a los últimos `limite` AGENDADOS mezclando activos y
    terminales: con 15+ servicios cerrados más nuevos, un trabajo activo sin
    terminar podía quedar invisible en TODA la UI (Fase 1.5,
    docs/flujo-venta.md, hallazgo 2). `listar()` ya ordena por más reciente,
    así que un solo recorrido preserva ese orden: cada activo se conserva
    siempre, cada terminal se conserva solo hasta completar `limite`.

    Clave (sin cambios): cambiar el estado de un servicio NO lo saca de esta
    lista por sí solo (antes, marcar 'Completada' o 'No retirada' lo hacía
    desaparecer y parecía que se eliminaba). El servicio queda guardado y
    visible hasta que se elimine a mano o el cupo de terminales lo desplace."""
    resultado: list[dict] = []
    vistos_terminales = 0
    for s in listar():
        if s["estado"] in ESTADOS_ACTIVOS_AGENDA:
            resultado.append(s)
        elif s["estado"] in ESTADOS_TERMINALES_AGENDA:
            if vistos_terminales < limite:
                resultado.append(s)
                vistos_terminales += 1
    return resultado


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

    # aceptar() YA NO genera venta (Fase 1.5, hallazgo 1)
    aceptar(sid)
    s = obtener(sid)
    assert s["estado"] == "aceptada" and s["venta_id"] is None, s["venta_id"]

    # doble aceptación bloqueada (ahora por estado, no por venta_id)
    try:
        aceptar(sid); raise AssertionError("no debe re-aceptar")
    except ValueError:
        pass

    # completar sin haber aceptado -> error (usa una 2da solicitud aparte)
    sid_sin_aceptar = crear_solicitud_manual("Xiaomi", "Beto", "b@x.cl", "56933334444",
                                             "Bateria", "2027-01-01")  # entrega futura: no debe contar como vencido
    guardar_servicio(sid_sin_aceptar, "2027-01-01", 20000, "x")
    try:
        completar(sid_sin_aceptar); raise AssertionError("no debe completar sin aceptar")
    except ValueError:
        pass

    # vencido: entrega 2020 < hoy y estado 'aceptada' (no completada/no_retirada)
    assert len(vencidos()) == 1
    # ya está agendada: aparece en Agenda y ya NO en la bandeja de pedidos
    assert len(agenda_agendados()) == 1 and len(pedidos()) == 1  # el pedido de Beto sigue pendiente

    # --- EL FIX CENTRAL: agendar y marcar no_retirada SIN completar nunca
    # no debe generar ninguna venta. Antes, aceptar() ya la había creado. ---
    cambiar_estado(sid, "no_retirada")
    assert len(agenda_agendados()) == 1, "no_retirada no debe sacar la fila de Agenda"
    assert len(no_retiradas()) == 1
    conn = database.get_connection()
    n_ventas = conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
    conn.close()
    assert n_ventas == 0, "no_retirada sin completar NUNCA debe generar venta"
    assert obtener(sid)["venta_id"] is None

    # ahora sí: completar() genera la venta con el precio correcto
    vid = completar(sid)
    s = obtener(sid)
    assert s["estado"] == "completada" and s["venta_id"] == vid
    venta, items = pos.obtener_venta(vid)
    assert venta.tipo == "servicio_tecnico" and "Servicio técnico" in items[0]["nombre"]
    assert venta.total == 45000
    conn = database.get_connection()
    origen = conn.execute("SELECT origen FROM ventas WHERE id=?", (vid,)).fetchone()[0]
    conn.close()
    assert origen == "agenda", origen  # la solicitud es 'manual'
    assert len(agenda_agendados()) == 1, "completada NO debe desaparecer de Agenda"

    # doble completar bloqueado (ya tiene venta_id)
    try:
        completar(sid); raise AssertionError("no debe completar dos veces")
    except ValueError:
        pass
    conn = database.get_connection()
    n_ventas = conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
    conn.close()
    assert n_ventas == 1, "doble completar no debe duplicar la venta"

    assert "iPhone 13" in whatsapp_texto(sid)
    print("OK servicio_tecnico/repo.py")
