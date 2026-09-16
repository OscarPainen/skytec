"""Login inicial forzado + recuperación de contraseña (core/database.py y
core/email_resend.py). El envío real a Resend no se testea acá (necesita
credenciales reales) — solo la lógica que no depende de la red.
"""
from __future__ import annotations

import os

import pytest

from core import database, email_resend


def test_admin_sembrado_fuerza_cambio_de_clave(db_temporal):
    fila = database.autenticar("admin", "1234")
    assert fila is not None
    assert fila["debe_cambiar_password"] == 1


def test_autenticar_rechaza_clave_o_usuario_incorrecto(db_temporal):
    assert database.autenticar("admin", "clave_mala") is None
    assert database.autenticar("no_existe", "1234") is None


def test_completar_primer_ingreso_cambia_clave_y_guarda_email(db_temporal):
    fila = database.autenticar("admin", "1234")
    database.completar_primer_ingreso(fila["id"], "clave_nueva_123", "admin@skytec.cl")

    assert database.autenticar("admin", "1234") is None, "la clave vieja no debe seguir sirviendo"
    fila2 = database.autenticar("admin", "clave_nueva_123")
    assert fila2 is not None
    assert fila2["debe_cambiar_password"] == 0
    assert database.obtener_email_usuario("admin") == "admin@skytec.cl"


def test_password_temporal_fuerza_cambio_de_nuevo(db_temporal):
    fila = database.autenticar("admin", "1234")
    database.completar_primer_ingreso(fila["id"], "clave_nueva_123", "admin@skytec.cl")

    database.aplicar_password_temporal("admin", "temporal999")
    assert database.autenticar("admin", "clave_nueva_123") is None
    fila2 = database.autenticar("admin", "temporal999")
    assert fila2 is not None and fila2["debe_cambiar_password"] == 1


def test_obtener_email_usuario_sin_email_devuelve_none(db_temporal):
    assert database.obtener_email_usuario("admin") is None
    assert database.obtener_email_usuario("no_existe") is None


# ── email_resend: solo lo que no necesita la API key real ──────────────────
def test_generar_password_temporal_evita_caracteres_confusos():
    clave = email_resend.generar_password_temporal(300)
    for c in "0O1lI":
        assert c not in clave


def test_generar_password_temporal_largo_configurable():
    assert len(email_resend.generar_password_temporal()) == 10
    assert len(email_resend.generar_password_temporal(6)) == 6


def test_configurado_false_sin_variables_de_entorno(monkeypatch):
    monkeypatch.delenv("SKYTEC_RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SKYTEC_RESEND_FROM", raising=False)
    assert not email_resend.configurado()


def test_configurado_true_con_ambas_variables(monkeypatch):
    monkeypatch.setenv("SKYTEC_RESEND_API_KEY", "re_test")
    monkeypatch.setenv("SKYTEC_RESEND_FROM", "Skytec <noreply@test.cl>")
    assert email_resend.configurado()


def test_enviar_sin_configurar_lanza_error_humano(monkeypatch):
    monkeypatch.delenv("SKYTEC_RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SKYTEC_RESEND_FROM", raising=False)
    with pytest.raises(RuntimeError, match="no está configurada"):
        email_resend.enviar_password_temporal("x@x.cl", "Ana", "abc123")


def test_solicitar_recuperacion_sin_email_configurado(db_temporal, monkeypatch):
    monkeypatch.setenv("SKYTEC_RESEND_API_KEY", "re_test")
    monkeypatch.setenv("SKYTEC_RESEND_FROM", "Skytec <noreply@test.cl>")
    with pytest.raises(RuntimeError, match="no tiene un correo configurado"):
        email_resend.solicitar_recuperacion("admin")


def test_solicitar_recuperacion_no_cambia_nada_si_falla_el_envio(db_temporal, monkeypatch):
    """El orden crítico: si Resend falla, la clave en la base NO debe tocarse."""
    fila = database.autenticar("admin", "1234")
    database.completar_primer_ingreso(fila["id"], "clave_original", "admin@skytec.cl")

    monkeypatch.delenv("SKYTEC_RESEND_API_KEY", raising=False)  # fuerza que falle el envío
    monkeypatch.delenv("SKYTEC_RESEND_FROM", raising=False)
    with pytest.raises(RuntimeError):
        email_resend.solicitar_recuperacion("admin")

    # la clave original debe seguir sirviendo -- no se aplicó ningún cambio
    assert database.autenticar("admin", "clave_original") is not None
