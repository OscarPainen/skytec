"""Módulo Servicio Técnico — bandeja de solicitudes y gestión de cada servicio.

La sincronización con Firebase (solicitudes web) llega en la Fase 6; aquí se
crean manualmente y se gestionan. "Cliente aceptó" desemboca en la nota de venta
unificada (reutiliza NotaVentaDialog del PoS).
"""
from __future__ import annotations

from urllib.parse import quote

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models import Usuario
from modules.inventario.page import clp
from modules.pos.page import NotaVentaDialog
from modules.servicio_tecnico import repo
from ui import styles

ESTADOS = {
    "pendiente": "Pendiente",
    "revisada": "Revisada",
    "aceptada": "Aceptada / agendada",
    "en_reparacion": "En reparación",
    "completada": "Completada",
    "no_retirada": "No retirada",
    "vencida": "Vencida",
}


def _spin_clp() -> QSpinBox:
    sp = QSpinBox()
    sp.setMaximum(100_000_000)
    sp.setPrefix("$ ")
    sp.setGroupSeparatorShown(True)
    return sp


class ServicioTecnicoPage(QWidget):
    def __init__(self, usuario: Usuario) -> None:
        super().__init__()
        self.usuario = usuario

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(styles.S4, styles.S4, styles.S4, styles.S4)
        raiz.setSpacing(styles.S3)

        cab = QHBoxLayout()
        cab.setSpacing(styles.S1)
        titulo = QLabel("Servicio Técnico")
        titulo.setObjectName("Title")
        cab.addWidget(titulo)
        cab.addStretch()
        self.filtro = QComboBox()
        self.filtro.addItem("Todas las solicitudes", None)
        for clave, texto in ESTADOS.items():
            self.filtro.addItem(texto, clave)
        self.filtro.currentIndexChanged.connect(self.recargar)
        cab.addWidget(self.filtro)
        nueva = QPushButton("Nueva solicitud")
        styles.style_button(nueva, "primary", "fa5s.plus")
        nueva.clicked.connect(self._nueva)
        cab.addWidget(nueva)
        raiz.addLayout(cab)

        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(
            ["Cliente", "Equipo", "Servicio", "Entrega", "Estado"]
        )
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(44)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.cellDoubleClicked.connect(self._abrir_fila)
        raiz.addWidget(self.tabla, 1)

        self.vacio = QLabel("No hay solicitudes. Crea una con «Nueva solicitud».")
        self.vacio.setObjectName("EmptyState")
        self.vacio.setAlignment(Qt.AlignCenter)
        raiz.addWidget(self.vacio)

        self.recargar()

    def recargar(self) -> None:
        filas = repo.listar(estado=self.filtro.currentData())
        self.tabla.setRowCount(0)
        for s in filas:
            r = self.tabla.rowCount()
            self.tabla.insertRow(r)
            estado = "Vencida" if s["vencido"] else ESTADOS.get(s["estado"], s["estado"])
            celdas = [
                s.get("cliente_nombre") or "—",
                s.get("modelo_telefono") or "—",
                s.get("tipo_servicio") or "—",
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

    def _abrir_fila(self, row: int, _col: int) -> None:
        sid = self.tabla.item(row, 0).data(Qt.UserRole)
        SolicitudDialog(sid, self.usuario, self).exec()
        self.recargar()

    def _nueva(self) -> None:
        if NuevaSolicitudDialog(self).exec() == QDialog.Accepted:
            self.recargar()


class NuevaSolicitudDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nueva solicitud")
        self.setMinimumWidth(440)
        self.setStyleSheet(styles.build_stylesheet())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(styles.S3, styles.S3, styles.S3, styles.S3)
        lay.setSpacing(styles.S2)
        lay.addWidget(QLabel("Nueva solicitud", objectName="Title"))

        self.modelo = QLineEdit()
        self.nombre = QLineEdit()
        self.email = QLineEdit()
        self.telefono = QLineEdit()
        self.telefono.setPlaceholderText("Ej: 56912345678")
        self.tipo = QLineEdit()
        self.tipo.setPlaceholderText("Ej: Cambio de pantalla")
        self.entrega = QDateEdit(QDate.currentDate())
        self.entrega.setCalendarPopup(True)
        self.entrega.setDisplayFormat("yyyy-MM-dd")

        for etiqueta, w in [
            ("Equipo / modelo *", self.modelo), ("Nombre del cliente *", self.nombre),
            ("Correo", self.email), ("Teléfono", self.telefono),
            ("Tipo de servicio", self.tipo), ("Fecha de entrega deseada", self.entrega),
        ]:
            lbl = QLabel(etiqueta)
            lbl.setObjectName("FieldLabel")
            lay.addWidget(lbl)
            lay.addWidget(w)

        acciones = QHBoxLayout()
        acciones.setSpacing(styles.S1)
        acciones.addStretch()
        cancelar = QPushButton("Cancelar")
        styles.style_button(cancelar, "secondary", "fa5s.times")
        cancelar.clicked.connect(self.reject)
        guardar = QPushButton("Guardar")
        styles.style_button(guardar, "primary", "fa5s.check")
        guardar.clicked.connect(self._guardar)
        acciones.addWidget(cancelar)
        acciones.addWidget(guardar)
        lay.addLayout(acciones)

    def _guardar(self) -> None:
        if not self.modelo.text().strip() or not self.nombre.text().strip():
            QMessageBox.warning(self, "Faltan datos", "Equipo y nombre son obligatorios.")
            return
        repo.crear_solicitud_manual(
            self.modelo.text().strip(), self.nombre.text().strip(),
            self.email.text().strip(), self.telefono.text().strip(),
            self.tipo.text().strip(), self.entrega.date().toString("yyyy-MM-dd"),
        )
        self.accept()


class SolicitudDialog(QDialog):
    """Detalle: datos del servicio, WhatsApp, aceptar y transiciones de estado."""

    def __init__(self, solicitud_id: int, usuario: Usuario, parent=None) -> None:
        super().__init__(parent)
        self.solicitud_id = solicitud_id
        self.usuario = usuario
        self.s = repo.obtener(solicitud_id)
        self.setWindowTitle(f"Solicitud — {self.s.get('cliente_nombre') or ''}")
        self.setMinimumWidth(480)
        self.setStyleSheet(styles.build_stylesheet())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(styles.S3, styles.S3, styles.S3, styles.S3)
        lay.setSpacing(styles.S2)

        lay.addWidget(QLabel(self.s.get("modelo_telefono") or "Equipo", objectName="Title"))
        info = QLabel(
            f"Cliente: {self.s.get('cliente_nombre') or '—'}   ·   "
            f"Tel: {self.s.get('cliente_telefono') or '—'}\n"
            f"Servicio: {self.s.get('tipo_servicio') or '—'}   ·   "
            f"Entrega comprometida: {self.s.get('fecha_entrega_solicitada') or '—'}\n"
            f"Estado: {ESTADOS.get(self.s['estado'], self.s['estado'])}"
            f"{'  ·  VENCIDO' if self.s['vencido'] else ''}"
        )
        info.setStyleSheet(f"color:{styles.TEXT_MUTED};")
        lay.addWidget(info)

        # Datos editables del servicio
        self.fecha_rep = QDateEdit(
            QDate.fromString(self.s["fecha_reparacion"], "yyyy-MM-dd")
            if self.s.get("fecha_reparacion") else QDate.currentDate()
        )
        self.fecha_rep.setCalendarPopup(True)
        self.fecha_rep.setDisplayFormat("yyyy-MM-dd")
        self.precio = _spin_clp()
        if self.s.get("precio"):
            self.precio.setValue(int(self.s["precio"]))
        self.detalles = QTextEdit(self.s.get("detalles") or "")
        self.detalles.setFixedHeight(72)

        for etiqueta, w in [
            ("Fecha de reparación", self.fecha_rep),
            ("Precio del servicio", self.precio),
            ("Detalles", self.detalles),
        ]:
            lbl = QLabel(etiqueta)
            lbl.setObjectName("FieldLabel")
            lay.addWidget(lbl)
            lay.addWidget(w)

        # Acciones principales
        f1 = QHBoxLayout()
        f1.setSpacing(styles.S1)
        guardar = QPushButton("Guardar datos")
        styles.style_button(guardar, "secondary", "fa5s.save")
        guardar.clicked.connect(self._guardar)
        f1.addWidget(guardar)
        wa = QPushButton("Generar mensaje WhatsApp")
        styles.style_button(wa, "secondary", "fa5b.whatsapp")
        wa.clicked.connect(self._whatsapp)
        f1.addWidget(wa)
        f1.addStretch()
        self.btn_aceptar = QPushButton("Cliente aceptó")
        styles.style_button(self.btn_aceptar, "primary", "fa5s.check-circle")
        self.btn_aceptar.clicked.connect(self._aceptar)
        self.btn_aceptar.setEnabled(not self.s.get("venta_id"))
        f1.addWidget(self.btn_aceptar)
        lay.addLayout(f1)

        # Transiciones de estado + eliminar
        f2 = QHBoxLayout()
        f2.setSpacing(styles.S1)
        for texto, estado in [
            ("En reparación", "en_reparacion"), ("Completada", "completada"),
            ("No retirada", "no_retirada"),
        ]:
            b = QPushButton(texto)
            styles.style_button(b, "secondary")
            b.clicked.connect(lambda _=False, e=estado: self._estado(e))
            f2.addWidget(b)
        f2.addStretch()
        eliminar = QPushButton("Eliminar")
        styles.style_button(eliminar, "danger", "fa5s.trash")
        eliminar.clicked.connect(self._eliminar)
        f2.addWidget(eliminar)
        lay.addLayout(f2)

    def _datos_servicio(self) -> None:
        repo.guardar_servicio(
            self.solicitud_id,
            self.fecha_rep.date().toString("yyyy-MM-dd"),
            self.precio.value(),
            self.detalles.toPlainText().strip(),
        )

    def _guardar(self) -> None:
        self._datos_servicio()
        QMessageBox.information(self, "Guardado", "Datos del servicio guardados.")
        self.accept()

    def _whatsapp(self) -> None:
        self._datos_servicio()  # guarda antes para que el mensaje esté completo
        texto = repo.whatsapp_texto(self.solicitud_id)
        QApplication.clipboard().setText(texto)
        digits = "".join(filter(str.isdigit, self.s.get("cliente_telefono") or ""))
        QDesktopServices.openUrl(QUrl(f"https://wa.me/{digits}?text={quote(texto)}"))
        QMessageBox.information(
            self, "WhatsApp",
            "Mensaje copiado al portapapeles y abriendo WhatsApp.",
        )

    def _aceptar(self) -> None:
        self._datos_servicio()
        try:
            venta_id = repo.aceptar(self.solicitud_id, self.usuario.id)
        except ValueError as e:
            QMessageBox.warning(self, "No se pudo aceptar", str(e))
            return
        NotaVentaDialog(venta_id, self).exec()
        self.accept()

    def _estado(self, estado: str) -> None:
        repo.cambiar_estado(self.solicitud_id, estado)
        self.accept()

    def _eliminar(self) -> None:
        if QMessageBox.question(
            self, "Eliminar solicitud", "¿Eliminar esta solicitud definitivamente?"
        ) == QMessageBox.Yes:
            repo.eliminar(self.solicitud_id)
            self.accept()
