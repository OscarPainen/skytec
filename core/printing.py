"""Impresión térmica ESC/POS (python-escpos).

Robusto por diseño: si la impresora no responde o falta la librería, lanza
`PrintingError` con un mensaje humano — nunca crashea. La nota ya quedó guardada
en la base al confirmarse la venta, así que "guardar igual" = simplemente no
imprimir. Este módulo es Qt-free; el hilo de impresión vive en workers/printing.py.
"""
from __future__ import annotations

from pathlib import Path

from core.database import get_config

# Caracteres por línea según ancho de papel (Fuente A ESC/POS).
ANCHOS = {"58": 32, "80": 48}


class PrintingError(Exception):
    """Fallo de impresión ya traducido a lenguaje humano."""


def ancho_caracteres() -> int:
    return ANCHOS.get(str(get_config("impresora_ancho", "80")), 48)


def _abrir_impresora():
    try:
        from escpos import printer as escpos_printer
    except Exception:
        raise PrintingError(
            "Falta la librería de impresión (python-escpos). "
            "Instálala para poder imprimir."
        )

    conexion = (get_config("impresora_conexion", "usb") or "usb").lower()
    try:
        if conexion == "network":
            host = get_config("impresora_host", "192.168.0.100")
            puerto = int(get_config("impresora_puerto", "9100") or 9100)
            return escpos_printer.Network(host, puerto, timeout=5)
        if conexion == "serial":
            return escpos_printer.Serial(get_config("impresora_serial", "COM1") or "COM1")
        vendor = int(str(get_config("impresora_usb_vendor", "0x0416")), 16)
        product = int(str(get_config("impresora_usb_product", "0x5011")), 16)
        return escpos_printer.Usb(vendor, product)
    except PrintingError:
        raise
    except Exception as e:
        raise PrintingError(
            "No se pudo conectar con la impresora. Revisa que esté encendida y "
            f"conectada, y la configuración en Ajustes.\n\nDetalle: {e}"
        )


def imprimir_texto(texto: str, logo_path: str | None = None) -> None:
    """Imprime el ticket (texto ya formateado al ancho) y corta el papel."""
    p = _abrir_impresora()
    try:
        if logo_path and Path(logo_path).exists():
            try:
                p.image(logo_path)
            except Exception:
                pass  # el logo es opcional: nunca bloquea la impresión de la nota
        p.text(texto + "\n")
        p.cut()
    except Exception as e:
        raise PrintingError(f"Ocurrió un error al imprimir la nota.\n\nDetalle: {e}")
    finally:
        try:
            p.close()
        except Exception:
            pass


if __name__ == "__main__":
    import os
    import tempfile
    from core import database

    os.environ["SKYTEC_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
    database.DB_PATH = Path(os.environ["SKYTEC_DB"])
    database.init_db()

    assert ancho_caracteres() == 48  # default 80mm
    database.set_config("impresora_ancho", "58")
    assert ancho_caracteres() == 32

    # Sin impresora real conectada, debe lanzar PrintingError (no crashear).
    try:
        imprimir_texto("Prueba")
        print("OK printing.py (había una impresora y aceptó el ticket)")
    except PrintingError:
        print("OK printing.py (sin impresora: PrintingError controlado)")
