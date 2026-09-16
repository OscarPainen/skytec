"""Estructural (CLAUDE.md sección 7): insertar dos veces el mismo
firebase_id deja una sola fila. No se toca sin hablarlo con Oscar."""
from __future__ import annotations

from core import database
from core.firebase_sync import mapear_solicitud_firestore
from modules.servicio_tecnico import repo as st


def test_doble_insercion_mismo_firebase_id_deja_una_sola_fila(db_temporal):
    mapeado = mapear_solicitud_firestore("mismo-id", {
        "cliente_nombre": "Ana", "modelo_telefono": "iPhone 12",
    })

    id1 = st.insertar_desde_firestore(mapeado)
    assert id1 is not None

    id2 = st.insertar_desde_firestore(mapeado)  # mismo firebase_id, de nuevo
    assert id2 is None, "la segunda vez debe ser ignorada, no crear otra fila"

    conn = database.get_connection()
    n = conn.execute(
        "SELECT COUNT(*) FROM solicitudes_reparacion WHERE firebase_id='mismo-id'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_insertar_desde_firestore_guarda_los_campos_mapeados(db_temporal):
    mapeado = mapear_solicitud_firestore("otro-id", {
        "cliente_nombre": "Beto", "modelo_telefono": "Galaxy A32",
        "cliente_telefono": "912345678", "tipo_servicio": "Cambio de batería",
    })
    sid = st.insertar_desde_firestore(mapeado)
    solicitud = st.obtener(sid)
    assert solicitud["cliente_nombre"] == "Beto"
    assert solicitud["cliente_telefono"] == "56912345678"
    assert solicitud["origen"] == "web"
    assert solicitud["estado"] == "pendiente"
    assert solicitud["firebase_id"] == "otro-id"
