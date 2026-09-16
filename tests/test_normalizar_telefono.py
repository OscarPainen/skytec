"""Fase 1.5 / Fase 3: la web acepta teléfonos internacionales que pueden no
llevar +56 — normalizar_telefono() arma un número listo para wa.me."""
from __future__ import annotations

from core.firebase_sync import normalizar_telefono


def test_ya_viene_con_mas_y_codigo_de_pais():
    assert normalizar_telefono("+56 9 1234 5678") == "56912345678"


def test_movil_chileno_sin_prefijo():
    assert normalizar_telefono("912345678") == "56912345678"
    assert normalizar_telefono("9 1234 5678") == "56912345678"


def test_fijo_chileno_sin_prefijo():
    assert normalizar_telefono("22345678") == "56222345678"


def test_internacional_no_chileno():
    assert normalizar_telefono("+1 555 123 4567") == "15551234567"


def test_ya_viene_con_56_pero_sin_mas():
    assert normalizar_telefono("56912345678") == "56912345678"


def test_basura_no_lanza_excepcion():
    assert normalizar_telefono("abc") == ""
    assert normalizar_telefono("") == ""
    assert normalizar_telefono(None) == ""  # type: ignore[arg-type]
