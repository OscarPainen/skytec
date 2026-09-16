"""Fase 3: mapear_solicitud_firestore es pura (sin I/O, sin credenciales) —
estos tests no necesitan conexión a Firebase."""
from __future__ import annotations

import datetime as dt

from core.firebase_sync import mapear_solicitud_firestore


def _ts(y, m, d, h=12, mi=0):
    return dt.datetime(y, m, d, h, mi, 0, tzinfo=dt.timezone.utc)


def test_documento_completo():
    doc = {
        "modelo_telefono": "iPhone 12",
        "cliente_nombre": "Ana Soto",
        "cliente_email": "ana@x.cl",
        "cliente_telefono": "+56 9 1234 5678",
        "tipo_servicio": "Cambio de pantalla",
        "tipo_servicio_detalle": "",
        "fecha_entrega_solicitada": _ts(2026, 9, 20),
        "estado": "nueva",
        "creado_en": _ts(2026, 9, 15, 10, 30),
    }
    m = mapear_solicitud_firestore("abc123", doc)
    assert m["modelo_telefono"] == "iPhone 12"
    assert m["cliente_nombre"] == "Ana Soto"
    assert m["cliente_telefono"] == "56912345678"
    assert m["tipo_servicio"] == "Cambio de pantalla"
    assert m["tipo_servicio_detalle"] == ""
    assert m["fecha_entrega_solicitada"] == "2026-09-20"
    assert m["estado"] == "pendiente"  # "nueva" (Firestore) -> "pendiente" (local)
    assert m["origen"] == "web"
    assert m["firebase_id"] == "abc123"
    assert m["creado_en"].startswith("2026-09-15")


def test_campos_faltantes_no_rompen_nada():
    m = mapear_solicitud_firestore("solo-nombre", {"cliente_nombre": "Beto"})
    assert m["cliente_nombre"] == "Beto"
    assert m["modelo_telefono"] == ""
    assert m["cliente_email"] == ""
    assert m["cliente_telefono"] == ""
    assert m["tipo_servicio"] == ""
    assert m["tipo_servicio_detalle"] == ""
    assert m["fecha_entrega_solicitada"] is None  # nullable en el esquema
    assert m["creado_en"] != ""  # sin creado_en real, cae en "ahora" -- nunca vacío
    assert m["origen"] == "web"


def test_documento_vacio_no_rompe_nada():
    m = mapear_solicitud_firestore("vacio", {})
    assert m["firebase_id"] == "vacio"
    assert m["estado"] == "pendiente"


def test_otro_a_evaluar_con_detalle():
    m = mapear_solicitud_firestore("ghi789", {
        "cliente_nombre": "Cata",
        "tipo_servicio": "Otro / a evaluar",
        "tipo_servicio_detalle": "Se moja seguido, revisar puerto de carga",
    })
    assert m["tipo_servicio"] == "Otro / a evaluar"
    assert m["tipo_servicio_detalle"] == "Se moja seguido, revisar puerto de carga"


def test_campos_inesperados_se_ignoran():
    m = mapear_solicitud_firestore("con-basura", {
        "cliente_nombre": "Dan",
        "campo_que_no_deberia_existir": "loquesea",
        "otro_mas": 12345,
    })
    assert m["cliente_nombre"] == "Dan"
    assert "campo_que_no_deberia_existir" not in m
    assert "otro_mas" not in m


def test_conversion_de_timestamp_con_zona_horaria():
    # Un timestamp en UTC a las 23:30 puede caer en el día siguiente en
    # horas locales adelantadas — se convierte a la hora LOCAL del sistema,
    # no se usa la fecha en UTC tal cual.
    ts_utc = dt.datetime(2026, 9, 15, 23, 30, 0, tzinfo=dt.timezone.utc)
    m = mapear_solicitud_firestore("x", {"creado_en": ts_utc})
    esperado_local = ts_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    assert m["creado_en"] == esperado_local
