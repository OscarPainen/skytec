"""Hilo para pedir la recuperación de contraseña sin congelar la UI (llamada
de red a Resend). Mismo patrón que workers/printing.py y workers/sync.py.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from core import email_resend


class RecuperacionWorker(QThread):
    ok = Signal(str)     # correo al que se mandó la clave temporal
    error = Signal(str)  # mensaje humano

    def __init__(self, nombre_usuario: str, parent=None) -> None:
        super().__init__(parent)
        self.nombre_usuario = nombre_usuario

    def run(self) -> None:
        try:
            email = email_resend.solicitar_recuperacion(self.nombre_usuario)
            self.ok.emit(email)
        except Exception as e:
            self.error.emit(str(e))
