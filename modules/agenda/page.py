"""Módulo Agenda — el "PoS del servicio": historial de servicios agendados.

Tres vistas:
- "Agendados": los últimos servicios que pasaron por "Cliente aceptó", en cualquier
  estado (aceptada / en reparación / completada / no retirada). Cambiar el estado NO
  saca la fila de la lista; el servicio queda guardado hasta que se elimine a mano.
- "Vencidos": pasó la fecha comprometida y aún no se entregó (se resaltan en rojo).
- "No retirados": equipos marcados como no retirados.

Al abrir una fila se reutiliza el detalle de Servicio Técnico (donde se cambia de
estado, se ve la nota de venta o se elimina para corregir un error).
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
        self.filtro.addItem("Agendados", "agendados")
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

    def showEvent(self, event) -> None:
        """AgendaPage se crea una sola vez y queda oculta al cambiar de pestaña
        (QStackedWidget), así que sin esto la tabla quedaba desactualizada si
        una solicitud se aceptaba desde Servicio Técnico. showEvent se dispara
        cada vez que la pestaña vuelve a mostrarse, así que refrescamos aquí."""
        super().showEvent(event)
        self.recargar()

    def _fuente(self) -> list[dict]:
        return {
            "agendados": lambda: repo.agenda_agendados(15),
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
            "agendados": "No hay servicios agendados todavía.",
            "vencidos": "No hay trabajos vencidos. 👌",
            "no_retirados": "No hay equipos sin retirar.",
        }[self.filtro.currentData()])

    def _abrir_fila(self, row: int, _col: int) -> None:
        sid = self.tabla.item(row, 0).data(Qt.UserRole)
        # mostrar_nota=True: desde Agenda sí se puede ver/generar la nota de
        # venta (ya no se genera sola al aceptar en Servicio Técnico).
        SolicitudDialog(sid, self.usuario, self, mostrar_nota=True).exec()
        self.recargar()
