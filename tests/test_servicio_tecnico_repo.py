"""Fase 1.5, hallazgo 1: el ingreso se reconoce al completar, no al aceptar.

Antes de este fix, aceptar() ya creaba la venta: una reparación aceptada y
nunca retirada quedaba contada como ingreso para siempre. Ver docs/flujo-venta.md.
"""
from __future__ import annotations

import pytest

from core import database
from modules.servicio_tecnico import repo as st


def _solicitud_con_precio(precio=45000, entrega="2027-01-01"):
    sid = st.crear_solicitud_manual(
        "iPhone 13", "Ana", "a@x.cl", "56911112222", "Cambio de pantalla", entrega,
    )
    st.guardar_servicio(sid, entrega, precio, "Pantalla OLED")
    return sid


def test_aceptar_no_genera_venta(db_temporal):
    sid = _solicitud_con_precio()
    st.aceptar(sid)
    conn = database.get_connection()
    n_ventas = conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
    conn.close()
    assert n_ventas == 0
    assert st.obtener(sid)["venta_id"] is None


def test_no_retirada_sin_completar_nunca_genera_venta(db_temporal):
    """El caso central del hallazgo 1: agendar y no retirar, sin completar
    nunca, no puede dejar plata contada que nunca entró a caja."""
    sid = _solicitud_con_precio()
    st.aceptar(sid)
    st.cambiar_estado(sid, "no_retirada")
    conn = database.get_connection()
    n_ventas = conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
    conn.close()
    assert n_ventas == 0
    assert st.obtener(sid)["venta_id"] is None


def test_completar_genera_la_venta_con_el_precio_guardado(db_temporal):
    sid = _solicitud_con_precio(precio=45000)
    st.aceptar(sid)
    venta_id = st.completar(sid)
    conn = database.get_connection()
    total = conn.execute("SELECT total FROM ventas WHERE id=?", (venta_id,)).fetchone()[0]
    conn.close()
    assert total == 45000
    assert st.obtener(sid)["estado"] == "completada"


def test_completar_sin_haber_aceptado_falla(db_temporal):
    sid = _solicitud_con_precio()
    with pytest.raises(ValueError):
        st.completar(sid)


def test_doble_completar_no_duplica_la_venta(db_temporal):
    sid = _solicitud_con_precio()
    st.aceptar(sid)
    st.completar(sid)
    with pytest.raises(ValueError):
        st.completar(sid)
    conn = database.get_connection()
    n_ventas = conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
    conn.close()
    assert n_ventas == 1


def test_doble_aceptar_bloqueado_por_estado(db_temporal):
    sid = _solicitud_con_precio()
    st.aceptar(sid)
    with pytest.raises(ValueError):
        st.aceptar(sid)


def _forzar_creado_en(sid: int, fecha: str) -> None:
    conn = database.get_connection()
    conn.execute("UPDATE solicitudes_reparacion SET creado_en=? WHERE id=?", (fecha, sid))
    conn.commit()
    conn.close()


def test_agenda_agendados_nunca_recorta_un_activo(db_temporal):
    """Fase 1.5, hallazgo 2: un trabajo 'en_reparacion' (sin terminar) no
    puede desaparecer de la Agenda solo porque hay 15+ servicios terminados
    más nuevos. Antes sí desaparecía (LIMIT 15 sobre la mezcla)."""
    sid_activo = _solicitud_con_precio(entrega="2027-01-01")
    st.aceptar(sid_activo)
    st.cambiar_estado(sid_activo, "en_reparacion")
    _forzar_creado_en(sid_activo, "2026-01-01 00:00:00")  # el más viejo de todos

    for i in range(16):
        sid = _solicitud_con_precio(entrega="2027-01-01")
        st.aceptar(sid)
        st.completar(sid)  # queda 'completada' (terminal)
        _forzar_creado_en(sid, f"2026-09-{10 + i:02d} 00:00:00")

    agendados = st.agenda_agendados(15)
    ids = [a["id"] for a in agendados]
    assert sid_activo in ids, "el activo no puede desaparecer"
    assert len(agendados) == 16, "1 activo (sin límite) + 15 terminales (el límite)"
    terminales_visibles = [a for a in agendados if a["estado"] == "completada"]
    assert len(terminales_visibles) == 15
