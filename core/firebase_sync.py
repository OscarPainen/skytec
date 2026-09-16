"""Sincronización con las solicitudes que llegan desde skytec-web.

Contrato de datos verificado contra el código real de skytec-web
(src/types/index.ts, src/services/solicitudes.ts), colección
`solicitudes/{autoId}`:
  modelo_telefono, cliente_nombre, cliente_email, cliente_telefono,
  tipo_servicio, tipo_servicio_detalle, fecha_entrega_solicitada (Timestamp),
  estado (siempre "nueva" al crear), creado_en (serverTimestamp()).

Enfoque ya decidido (CLAUDE.md sección 5): Admin SDK con cuenta de servicio.
La web escribe con auth anónima + SDK cliente; acá se lee/actualiza con
Admin SDK, que ignora las reglas de Firestore.

Funciones puras (mapear_solicitud_firestore, normalizar_telefono) primero,
sin I/O — son las que se testean sin necesitar credenciales reales. Las que
hacen I/O están claramente separadas más abajo.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

from core.paths import app_data_dir

NOMBRE_ARCHIVO_CREDENCIAL = "serviceAccount.json"

# Mismos 6 valores que TIPOS_SERVICIO en skytec-web/src/types/index.ts — no
# se valida acá (si la web agrega uno nuevo, mejor guardarlo tal cual que
# rechazar la solicitud), es solo referencia para quien lea este archivo.
# ["Cambio de pantalla", "Cambio de batería", "Reparación de puerto de
#  carga", "Problema de software", "Daño por líquido", "Otro / a evaluar"]


# ── Funciones puras ──────────────────────────────────────────────────────────
def normalizar_telefono(raw: str) -> str:
    """Dígitos sin '+', con código de país, listos para un link wa.me.

    La web acepta teléfonos internacionales que pueden no llevar +56: un
    número chileno local sin prefijo rompía el link de WhatsApp antes de
    esto (Fase 1.5, docs/flujo-venta.md).

      - Ya viene con "+": se conservan los dígitos tal cual (ya trae su
        propio código de país, sea cual sea).
      - 9 dígitos empezando con 9 (móvil chileno sin prefijo): se antepone 56.
      - 8 dígitos (fijo chileno sin prefijo): se antepone 562.
      - No reconocido: se devuelven los dígitos tal cual y se avisa por
        consola — nunca se lanza una excepción por esto.
    """
    raw = raw or ""
    digitos = "".join(c for c in raw if c.isdigit())
    if raw.strip().startswith("+"):
        return digitos
    if len(digitos) == 9 and digitos.startswith("9"):
        return "56" + digitos
    if len(digitos) == 8:
        return "562" + digitos
    if digitos.startswith("56") and len(digitos) in (10, 11):
        return digitos
    if digitos:
        print(f"Advertencia: no se pudo normalizar el teléfono «{raw}», se usa tal cual.")
    return digitos


def _dt_a_texto(valor, con_hora: bool) -> str:
    """Timestamp de Firestore (llega como datetime con tz) -> TEXT local.
    None o vacío -> "" (nunca None, para no romper el resto del mapeo)."""
    if not isinstance(valor, _dt.datetime):
        return ""
    local = valor.astimezone()
    return local.strftime("%Y-%m-%d %H:%M:%S") if con_hora else local.strftime("%Y-%m-%d")


def mapear_solicitud_firestore(doc_id: str, data: dict) -> dict:
    """Documento de Firestore (dict, tal como lo da el SDK) -> columnas de
    solicitudes_reparacion. Pura: sin I/O, sin conexión a la base.

    Campos faltantes o de tipo inesperado -> "" (nunca None: rompería
    columnas que no son NOT NULL en el esquema pero sí lo son en el
    contrato de datos — mejor un string vacío consistente). Campos del
    documento que no están en este mapeo se ignoran sin fallar.
    """
    data = data or {}
    creado_en = _dt_a_texto(data.get("creado_en"), con_hora=True)
    return {
        "modelo_telefono": str(data.get("modelo_telefono") or ""),
        "cliente_nombre": str(data.get("cliente_nombre") or ""),
        "cliente_email": str(data.get("cliente_email") or ""),
        "cliente_telefono": normalizar_telefono(str(data.get("cliente_telefono") or "")),
        "tipo_servicio": str(data.get("tipo_servicio") or ""),
        "tipo_servicio_detalle": str(data.get("tipo_servicio_detalle") or ""),
        # nullable en el esquema: None (no "") para calzar con
        # crear_solicitud_manual, que también guarda None si no hay fecha.
        "fecha_entrega_solicitada": _dt_a_texto(data.get("fecha_entrega_solicitada"),
                                                 con_hora=False) or None,
        "estado": "pendiente",  # "nueva" (Firestore) -> "pendiente" (local)
        "origen": "web",
        "firebase_id": doc_id,
        # Si Firestore no trae creado_en (no debería pasar: lo pone el
        # servidor), cae en "ahora" -- nunca vacío, es NOT NULL en la base.
        "creado_en": creado_en or _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── Credenciales ──────────────────────────────────────────────────────────
def ruta_credenciales() -> Path:
    return Path(os.environ.get(
        "SKYTEC_FIREBASE_CREDENTIALS", str(app_data_dir() / NOMBRE_ARCHIVO_CREDENCIAL)
    ))


def credenciales_disponibles() -> bool:
    return ruta_credenciales().exists()


# ── I/O contra Firestore (Admin SDK) ────────────────────────────────────────
_db = None  # cliente de Firestore, singleton perezoso


def _cliente():
    """Cliente de Firestore, inicializado una sola vez. Import de
    firebase_admin adentro de la función a propósito: así los mapeos puros
    de arriba se pueden testear sin tener el paquete instalado si hiciera
    falta, y el error de "no hay credenciales" es explícito, no un import
    roto al cargar el módulo."""
    global _db
    if _db is None:
        import firebase_admin
        from firebase_admin import credentials, firestore

        ruta = ruta_credenciales()
        if not ruta.exists():
            raise RuntimeError(f"No se encontró la credencial de Firebase en {ruta}.")
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(str(ruta)))
        _db = firestore.client()
    return _db


def descargar_solicitudes_nuevas(limite: int = 50) -> list[tuple[str, dict]]:
    """[(doc_id, data)] de las solicitudes con estado "nueva", más viejas
    primero. No marca nada — eso es responsabilidad de marcar_sincronizada,
    llamada solo después de guardar localmente (ver sincronizar_una_vez).

    Sin order_by en la consulta a propósito: combinar un filtro de
    igualdad ("estado"=="nueva") con un order_by en OTRO campo
    ("creado_en") exige un índice compuesto en Firestore que no existe por
    defecto — hay que crearlo a mano en la consola (se confirmó probando
    contra el proyecto real: Firestore lo rechaza con
    FailedPrecondition/"query requires an index"). Con el volumen de un
    local de reparaciones no vale la pena ese paso manual extra: se baja
    sin ordenar y se ordena acá, en Python.
    """
    from google.cloud.firestore_v1.base_query import FieldFilter

    db = _cliente()
    docs = (
        db.collection("solicitudes")
        .where(filter=FieldFilter("estado", "==", "nueva"))
        .limit(limite)
        .stream()
    )
    resultado = [(d.id, d.to_dict()) for d in docs]
    epoca = _dt.datetime.min.replace(tzinfo=_dt.timezone.utc)
    resultado.sort(key=lambda par: par[1].get("creado_en") or epoca)
    return resultado


def marcar_sincronizada(doc_id: str) -> None:
    from firebase_admin import firestore

    db = _cliente()
    db.collection("solicitudes").document(doc_id).update({
        "estado": "sincronizada",
        "sincronizado_en": firestore.SERVER_TIMESTAMP,
    })


def sincronizar_una_vez() -> int:
    """Un ciclo completo: baja las solicitudes "nueva", las inserta
    localmente y recién ahí marca cada documento remoto como
    "sincronizada". Devuelve cuántas eran realmente nuevas (no cuenta las
    que ya estaban, aunque a esas igual se les corrige el estado remoto si
    por algo había quedado pegado en "nueva").

    ORDEN CRÍTICO: local primero, remoto después. Si el proceso muere entre
    medio, el próximo ciclo relee el documento (sigue en "nueva") y el
    UNIQUE de firebase_id descarta el duplicado sin generar uno nuevo. Al
    revés —marcar remoto antes— se perdería la solicitud para siempre si el
    proceso muere justo ahí.
    """
    from modules.servicio_tecnico import repo as st_repo

    nuevas = descargar_solicitudes_nuevas()
    recibidas = 0
    for doc_id, data in nuevas:
        mapeado = mapear_solicitud_firestore(doc_id, data)
        if st_repo.insertar_desde_firestore(mapeado):
            recibidas += 1
        marcar_sincronizada(doc_id)
    return recibidas


if __name__ == "__main__":
    # Auto-check: solo la parte pura (sin credenciales, sin red).
    doc_completo = {
        "modelo_telefono": "iPhone 12",
        "cliente_nombre": "Ana Soto",
        "cliente_email": "ana@x.cl",
        "cliente_telefono": "+56 9 1234 5678",
        "tipo_servicio": "Cambio de pantalla",
        "tipo_servicio_detalle": "",
        "fecha_entrega_solicitada": _dt.datetime(2026, 9, 20, 12, 0, 0, tzinfo=_dt.timezone.utc),
        "estado": "nueva",
        "creado_en": _dt.datetime(2026, 9, 15, 10, 30, 0, tzinfo=_dt.timezone.utc),
    }
    m = mapear_solicitud_firestore("abc123", doc_completo)
    assert m["modelo_telefono"] == "iPhone 12"
    assert m["cliente_telefono"] == "56912345678"
    assert m["estado"] == "pendiente" and m["origen"] == "web" and m["firebase_id"] == "abc123"
    assert m["fecha_entrega_solicitada"] == "2026-09-20"
    assert m["creado_en"] != ""

    # campos faltantes -> "" o None, nunca una excepción
    m2 = mapear_solicitud_firestore("def456", {"cliente_nombre": "Beto"})
    assert m2["modelo_telefono"] == "" and m2["fecha_entrega_solicitada"] is None
    assert m2["creado_en"] != ""  # cae en "ahora", nunca vacío

    # "Otro / a evaluar" con detalle
    m3 = mapear_solicitud_firestore("ghi789", {
        "cliente_nombre": "Cata", "tipo_servicio": "Otro / a evaluar",
        "tipo_servicio_detalle": "Se moja seguido, revisar puerto",
    })
    assert m3["tipo_servicio_detalle"] == "Se moja seguido, revisar puerto"

    # normalizar_telefono
    assert normalizar_telefono("+56 9 1234 5678") == "56912345678"
    assert normalizar_telefono("912345678") == "56912345678"
    assert normalizar_telefono("9 1234 5678") == "56912345678"  # 9 dígitos igual
    assert normalizar_telefono("22345678") == "56222345678"
    assert normalizar_telefono("+1 555 123 4567") == "15551234567"
    assert normalizar_telefono("") == ""
    assert normalizar_telefono("abc") == ""  # basura -> sin dígitos, sin excepción

    print("OK firebase_sync.py (solo funciones puras — sin credenciales)")
