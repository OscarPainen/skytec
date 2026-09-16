"""Recuperación de contraseña por correo, vía Resend (resend.com).

Sin servidor de correo propio: Resend es un servicio de terceros que manda
el mail por su API. La API key y el remitente viven en variables de
entorno (.env), nunca en el código ni en la base — mismo criterio que
core/firebase_sync.py con la cuenta de servicio de Firebase.

Orden crítico, igual que en core/firebase_sync.py: primero se manda el
correo, y SOLO SI eso funciona se guarda la clave temporal en la base
(aplicar_password_temporal). Al revés, un envío que falla dejaría a
alguien afuera del sistema sin ninguna forma de entrar.
"""
from __future__ import annotations

import os
import random

API_KEY_ENV = "SKYTEC_RESEND_API_KEY"
FROM_ENV = "SKYTEC_RESEND_FROM"

# Sin 0/O/1/l/I: se confunden fácil si alguien la tiene que teclear a mano
# desde el celular mirando el correo.
_ALFABETO_CLAVE = "23456789ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"


def configurado() -> bool:
    return bool(os.environ.get(API_KEY_ENV)) and bool(os.environ.get(FROM_ENV))


def generar_password_temporal(largo: int = 10) -> str:
    return "".join(random.SystemRandom().choice(_ALFABETO_CLAVE) for _ in range(largo))


def enviar_password_temporal(destinatario: str, nombre_usuario: str, password_temporal: str) -> None:
    """Lanza RuntimeError con mensaje humano si Resend no está configurado
    o si el envío falla. No guarda nada en la base — eso es
    responsabilidad de quien llama, y solo debe pasar si esto NO lanza."""
    if not configurado():
        raise RuntimeError(
            "La recuperación por correo no está configurada todavía "
            "(faltan SKYTEC_RESEND_API_KEY / SKYTEC_RESEND_FROM en el .env)."
        )
    try:
        import resend
    except ImportError:
        raise RuntimeError(
            "Falta la librería de correo (resend). Instálala para poder "
            "mandar la contraseña temporal."
        )

    resend.api_key = os.environ[API_KEY_ENV]
    html = f"""
        <p>Hola {nombre_usuario},</p>
        <p>Se generó una contraseña temporal para tu cuenta de Skytec:</p>
        <p style="font-size:22px; font-weight:bold; letter-spacing:2px;">{password_temporal}</p>
        <p>Iniciá sesión con esta clave. El sistema te va a pedir que la
        cambies por una tuya antes de dejarte entrar.</p>
        <p>Si no pediste este cambio, avisale a un administrador.</p>
    """
    try:
        resend.Emails.send({
            "from": os.environ[FROM_ENV],
            "to": destinatario,
            "subject": "Skytec — contraseña temporal",
            "html": html,
        })
    except Exception as e:
        raise RuntimeError(f"No se pudo enviar el correo: {e}")


def solicitar_recuperacion(nombre_usuario: str) -> str:
    """Flujo completo: busca el correo del usuario, genera una clave
    temporal, la manda, y RECIÉN SI eso funciona la guarda en la base.
    Devuelve el correo al que se mandó (para mostrarlo, parcialmente
    tapado, en la UI). Lanza RuntimeError con mensaje humano en cualquier
    punto de falla — nunca deja la base en un estado a medias."""
    from core import database

    email = database.obtener_email_usuario(nombre_usuario)
    if not email:
        raise RuntimeError(
            "Este usuario no tiene un correo configurado. Pedile a otro "
            "administrador que te ayude a recuperar el acceso."
        )
    temporal = generar_password_temporal()
    enviar_password_temporal(email, nombre_usuario, temporal)  # lanza si falla
    database.aplicar_password_temporal(nombre_usuario, temporal)
    return email


if __name__ == "__main__":
    # Auto-check: solo lo que no necesita la API key real de Resend.
    assert len(generar_password_temporal()) == 10
    assert len(generar_password_temporal(6)) == 6
    for c in "0O1lI":
        assert c not in generar_password_temporal(200), f"'{c}' no debería poder salir"

    os.environ.pop(API_KEY_ENV, None)
    os.environ.pop(FROM_ENV, None)
    assert not configurado()
    try:
        enviar_password_temporal("x@x.cl", "Ana", "abc123")
        raise AssertionError("debió fallar sin configurar")
    except RuntimeError as e:
        assert "no está configurada" in str(e)

    print("OK email_resend.py (solo lo que no necesita la API key real)")
