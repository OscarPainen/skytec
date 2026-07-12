"""Hilo de impresión: manda el ticket a la impresora sin congelar la UI.

Una impresora de red que no responde puede tardar segundos en dar timeout; por
eso la impresión va en un QThread. Reutilizable desde la nota de venta y desde
la prueba de impresión en Ajustes.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from core import printing


class PrintWorker(QThread):
    ok = Signal()
    error = Signal(str)  # mensaje humano

    def __init__(self, texto: str, logo: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.texto = texto
        self.logo = logo

    def run(self) -> None:
        try:
            printing.imprimir_texto(self.texto, self.logo)
            self.ok.emit()
        except printing.PrintingError as e:
            self.error.emit(str(e))
        except Exception:
            self.error.emit("Error inesperado al imprimir.")
