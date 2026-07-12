"""Ventana principal: navegación lateral + área de contenido por módulos.

Fase 1 entrega el esqueleto: cada módulo es un estado vacío con nota de la
fase que lo implementará. Las páginas reales se enchufan en fases siguientes
reemplazando el placeholder en `self.paginas`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core import database
from core.models import Usuario
from ui import styles

try:  # qtawesome es opcional: sin él la UI funciona igual, solo sin íconos.
    import qtawesome as qta
except Exception:  # pragma: no cover
    qta = None


def _icon(nombre: str):
    return qta.icon(nombre, color=styles.TEXT_ON_DARK) if qta else None


# (etiqueta, ícono, texto de la fase que lo implementa)
MODULOS = [
    ("Servicio Técnico", "fa5s.tools", "Se implementa en la Fase 5."),
    ("Punto de Venta", "fa5s.cash-register", "Se implementa en la Fase 3."),
    ("Inventario", "fa5s.boxes", "Se implementa en la Fase 2."),
    ("Agenda", "fa5s.calendar-alt", "Se implementa en la Fase 5."),
    ("Ajustes", "fa5s.cog", "Configuración del negocio, PoS e impresora."),
]


class _Placeholder(QWidget):
    """Estado vacío amable para un módulo aún no implementado."""

    def __init__(self, titulo: str, nota: str) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(styles.S4, styles.S4, styles.S4, styles.S4)
        lay.setSpacing(styles.S1)

        t = QLabel(titulo)
        t.setObjectName("Title")
        lay.addWidget(t)

        lay.addStretch()
        vacio = QLabel(nota)
        vacio.setObjectName("EmptyState")
        vacio.setAlignment(Qt.AlignCenter)
        lay.addWidget(vacio)
        lay.addStretch()


class MainWindow(QMainWindow):
    def __init__(self, usuario: Usuario) -> None:
        super().__init__()
        self.usuario = usuario
        nombre_negocio = database.get_config("negocio_nombre", "Skytec")
        self.setWindowTitle(f"{nombre_negocio} — {usuario.nombre} ({usuario.rol})")
        self.resize(1100, 720)
        self.setStyleSheet(styles.build_stylesheet())

        raiz = QWidget()
        raiz_lay = QHBoxLayout(raiz)
        raiz_lay.setContentsMargins(0, 0, 0, 0)
        raiz_lay.setSpacing(0)
        raiz_lay.addWidget(self._construir_sidebar(nombre_negocio))

        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")
        raiz_lay.addWidget(self.stack, 1)
        self.setCentralWidget(raiz)

        # paginas: dict etiqueta -> widget, para reemplazar en fases futuras
        self.paginas: dict[str, QWidget] = {}
        for etiqueta, _icono, nota in MODULOS:
            pagina = self._construir_pagina(etiqueta, nota)
            self.paginas[etiqueta] = pagina
            self.stack.addWidget(pagina)

        self.botones.buttons()[0].setChecked(True)
        self.stack.setCurrentIndex(0)

    def _construir_pagina(self, etiqueta: str, nota: str) -> QWidget:
        """Página real si el módulo ya está implementado; si no, estado vacío."""
        if etiqueta == "Servicio Técnico":
            from modules.servicio_tecnico.page import ServicioTecnicoPage

            return ServicioTecnicoPage(self.usuario)
        if etiqueta == "Agenda":
            from modules.agenda.page import AgendaPage

            return AgendaPage(self.usuario)
        if etiqueta == "Inventario":
            from modules.inventario.page import InventarioPage

            return InventarioPage(self.usuario)
        if etiqueta == "Punto de Venta":
            from modules.pos.page import PosPage

            return PosPage(self.usuario)
        if etiqueta == "Ajustes":
            from modules.ajustes.page import AjustesPage

            return AjustesPage(self.usuario)
        return _Placeholder(etiqueta, nota)

    def _construir_sidebar(self, nombre_negocio: str) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(230)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 0, 0, styles.S2)
        lay.setSpacing(0)

        brand = QLabel(nombre_negocio)
        brand.setObjectName("Brand")
        lay.addWidget(brand)

        self.botones = QButtonGroup(self)
        self.botones.setExclusive(True)
        for i, (etiqueta, icono, _nota) in enumerate(MODULOS):
            btn = QPushButton(etiqueta)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            ico = _icon(icono)
            if ico:
                btn.setIcon(ico)
            btn.clicked.connect(lambda _=False, idx=i: self.stack.setCurrentIndex(idx))
            self.botones.addButton(btn, i)
            lay.addWidget(btn)

        lay.addStretch()
        self.status = QLabel("Sin conexión")
        self.status.setObjectName("StatusOffline")
        self.status.setContentsMargins(styles.S2, 0, styles.S2, 0)
        lay.addWidget(self.status)
        return side

    def set_estado_conexion(self, online: bool) -> None:
        """La sincronización (Fase 6) llamará esto para el indicador discreto."""
        self.status.setText("Conectado" if online else "Sin conexión")
        self.status.setObjectName("StatusOnline" if online else "StatusOffline")
        self.status.setStyleSheet(self.styleSheet())  # re-aplica el objectName
