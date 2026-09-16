"""Hilo de sincronización con Firebase: baja solicitudes nuevas cada cierto
intervalo sin congelar la UI (mismo patrón que workers/printing.py:
core/firebase_sync.py hace el trabajo real, este archivo solo lo agenda en
un QThread).

Si no hay credenciales configuradas, el hilo termina de inmediato sin
error: la sincronización es opcional, nunca puede impedir vender
(CLAUDE.md sección 6, regla de seguridad #3).
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from core import firebase_sync

INTERVALO_MINIMO = 60      # segundos
BACKOFF_TECHO = 15 * 60    # 15 min, tope del backoff ante errores de red


class SyncWorker(QThread):
    conexion_cambiada = Signal(bool)     # True = ciclo exitoso, False = error de red
    solicitudes_recibidas = Signal(int)  # cuántas eran realmente nuevas
    error_sync = Signal(str)             # mensaje humano, para log/estado

    def __init__(self, intervalo_segundos: int = INTERVALO_MINIMO, parent=None) -> None:
        super().__init__(parent)
        self._intervalo = max(INTERVALO_MINIMO, intervalo_segundos)
        self._detener = False
        self._conectado = False

    def solicitar_detencion(self) -> None:
        """Pide que el hilo termine en el próximo tramo de espera (hasta 1s
        de latencia, no hasta 15 min — ver _dormir)."""
        self._detener = True

    def run(self) -> None:
        if not firebase_sync.credenciales_disponibles():
            return  # sincronización apagada, sin error: es una condición normal

        backoff = self._intervalo
        while not self._detener:
            try:
                n = firebase_sync.sincronizar_una_vez()
                if not self._conectado:
                    self._conectado = True
                    self.conexion_cambiada.emit(True)
                if n:
                    self.solicitudes_recibidas.emit(n)
                backoff = self._intervalo  # se recupera al primer ciclo OK
            except Exception as e:
                if self._conectado:
                    self._conectado = False
                    self.conexion_cambiada.emit(False)
                self.error_sync.emit(str(e))
                backoff = min(backoff * 2, BACKOFF_TECHO)
            self._dormir(backoff)

    def _dormir(self, segundos: float) -> None:
        # En pasos de 1s (no un solo sleep largo) para que solicitar_detencion()
        # no tarde hasta 15 minutos en hacer efecto al cerrar la app.
        restante = segundos
        while restante > 0 and not self._detener:
            self.msleep(1000)
            restante -= 1


class SincronizarAhoraWorker(QThread):
    """Un solo ciclo de sincronización, disparado a mano — el botón
    "Actualización rápida" en Servicio Técnico. No reutiliza el SyncWorker
    de fondo (que corre cada 1 hora): ese hilo puede haber terminado si no
    hay credenciales, así que esto corre su propio ciclo, una vez, y
    termina. Mismo patrón que workers/printing.py."""

    ok = Signal(int)     # cuántas solicitudes nuevas trajo
    error = Signal(str)  # mensaje humano

    def run(self) -> None:
        if not firebase_sync.credenciales_disponibles():
            self.error.emit(
                "No hay credenciales de Firebase configuradas todavía."
            )
            return
        try:
            n = firebase_sync.sincronizar_una_vez()
            self.ok.emit(n)
        except Exception as e:
            self.error.emit(str(e))
