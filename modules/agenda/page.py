"""Módulo Agenda — calendario de servicios y gestión de excepciones.

Tres vistas: servicios activos y al día, vencidos (pasó la fecha comprometida) y
equipos no retirados. Los vencidos se resaltan. Al abrir una fila se reutiliza el
detalle de Servicio Técnico (donde se marca completado tardío o se elimina).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Usuario
from modules.servicio_tecnico import repo
from modules.servicio_tecnico.page import ESTADOS, SolicitudDialog
from ui import styles


class AgendaPage(QWidget):
    def __init__(self, usuario: Usuario) -> None:
        super().__init__()
        self.usuario = usuario

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(styles.S4, styles.S4, styles.S4, styles.S4)
        raiz.setSpacing(styles.S3)

        cab = QHBoxLayout()
        cab.setSpacing(styles.S1)
        titulo = QLabel("Agenda")
        titulo.setObjectName("Title")
        cab.addWidget(titulo)
        cab.addStretch()
        self.filtro = QComboBox()
        self.filtro.addItem("Activos / al día", "activos")
        self.filtro.addItem("Vencidos", "vencidos")
        self.filtro.addItem("No retirados", "no_retirados")
        self.filtro.currentIndexChanged.connect(self.recargar)
        cab.addWidget(self.filtro)
        raiz.addLayout(cab)

        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(
            ["Cliente", "Equipo", "Reparación", "Entrega", "Estado"]
        )
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(44)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.cellDoubleClicked.connect(self._abrir_fila)
        raiz.addWidget(self.tabla, 1)

        self.vacio = QLabel("")
        self.vacio.setObjectName("EmptyState")
        self.vacio.setAlignment(Qt.AlignCenter)
        raiz.addWidget(self.vacio)

        self.recargar()

    def _fuente(self) -> list[dict]:
        return {
            "activos": repo.agenda_activos,
            "vencidos": repo.vencidos,
            "no_retirados": repo.no_retiradas,
        }[self.filtro.currentData()]()

    def recargar(self) -> None:
        filas = self._fuente()
        self.tabla.setRowCount(0)
        for s in filas:
            r = self.tabla.rowCount()
            self.tabla.insertRow(r)
            estado = "Vencida" if s["vencido"] else ESTADOS.get(s["estado"], s["estado"])
            celdas = [
                s.get("cliente_nombre") or "—",
                s.get("modelo_telefono") or "—",
                s.get("fecha_reparacion") or "—",
                s.get("fecha_entrega_solicitada") or "—",
                estado,
            ]
            for c, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                if s["vencido"]:
                    item.setForeground(Qt.GlobalColor.red)
                self.tabla.setItem(r, c, item)
            self.tabla.item(r, 0).setData(Qt.UserRole, s["id"])
        self.tabla.setVisible(bool(filas))
        self.vacio.setVisible(not filas)
        self.vacio.setText({
            "activos": "No hay servicios agendados.",
            "vencidos": "No hay trabajos vencidos. 👌",
            "no_retirados": "No hay equipos sin retirar.",
        }[self.filtro.currentData()])

    def _abrir_fila(self, row: int, _col: int) -> None:
        sid = self.tabla.item(row, 0).data(Qt.UserRole)
        SolicitudDialog(sid, self.usuario, self).exec()
        self.recargar()
