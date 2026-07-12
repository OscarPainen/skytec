"""Módulo Punto de Venta — buscador de productos, carrito y confirmación.

Dos PoS independientes (Tech/Fit, configurables): cada venta registra su
`pos_origen`. Al confirmar se descuenta stock y se genera la nota de venta.
La impresión térmica se conecta en la Fase 4 (aquí se muestra la vista previa).
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import database, printing
from core.models import Usuario
from modules.inventario import repo as inv
from modules.inventario.page import clp  # formateador CLP compartido (capa UI)
from modules.pos import repo
from ui import styles
from workers.printing import PrintWorker


def _centrar(widget: QWidget) -> QWidget:
    """Envuelve un widget para centrarlo dentro de su celda de tabla."""
    cont = QWidget()
    lay = QHBoxLayout(cont)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addStretch()
    lay.addWidget(widget)
    lay.addStretch()
    return cont


class PosPage(QWidget):
    def __init__(self, usuario: Usuario) -> None:
        super().__init__()
        self.usuario = usuario
        self.carrito: dict[int, dict] = {}   # producto_id -> {nombre, precio, cantidad, stock}
        self._productos: dict[int, object] = {}

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(styles.S4, styles.S4, styles.S4, styles.S4)
        raiz.setSpacing(styles.S3)

        # Encabezado + selector de PoS
        cab = QHBoxLayout()
        cab.setSpacing(styles.S1)
        titulo = QLabel("Punto de Venta")
        titulo.setObjectName("Title")
        cab.addWidget(titulo)
        cab.addStretch()
        etiqueta_caja = QLabel("Caja:")
        etiqueta_caja.setObjectName("Subtitle")
        cab.addWidget(etiqueta_caja)
        self.selector_pos = QComboBox()
        self.selector_pos.addItem(database.get_config("pos_1_nombre", "Tech"))
        self.selector_pos.addItem(database.get_config("pos_2_nombre", "Fit"))
        cab.addWidget(self.selector_pos)
        raiz.addLayout(cab)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(styles.S3)
        cuerpo.addWidget(self._panel_productos(), 2)
        cuerpo.addWidget(self._panel_carrito(), 3)
        raiz.addLayout(cuerpo, 1)

        self._cargar_productos()
        self._rebuild_carrito()

    # ── Panel izquierdo: productos ──────────────────────────────────────────
    def _panel_productos(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(styles.S1)
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText("Buscar producto…")
        self.buscar.textChanged.connect(self._cargar_productos)
        lay.addWidget(self.buscar)
        self.lista = QListWidget()
        self.lista.viewport().setCursor(Qt.PointingHandCursor)
        self.lista.itemActivated.connect(self._al_activar_item)
        self.lista.itemDoubleClicked.connect(self._al_activar_item)
        lay.addWidget(self.lista, 1)
        ayuda = QLabel("Doble clic o Enter para agregar al carrito")
        ayuda.setObjectName("Subtitle")
        lay.addWidget(ayuda)
        return panel

    def _cargar_productos(self) -> None:
        self.lista.clear()
        productos = [
            p for p in inv.listar_productos(busqueda=self.buscar.text().strip())
            if p.stock_actual > 0
        ]
        self._productos = {p.id: p for p in productos}
        if not productos:
            item = QListWidgetItem("No hay productos con stock disponible.")
            item.setFlags(Qt.NoItemFlags)
            self.lista.addItem(item)
            return
        for p in productos:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, p.id)
            item.setSizeHint(QSize(0, 48))
            self.lista.addItem(item)
            self.lista.setItemWidget(item, self._fila_producto(p))

    def _fila_producto(self, p) -> QWidget:
        """Fila: nombre (peso 500) a la izquierda, precio y stock a la derecha."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(4, 0, 4, 0)
        h.setSpacing(styles.S1)
        nombre = QLabel(p.nombre)
        nombre.setStyleSheet("font-weight:500; background:transparent;")
        meta = QLabel(f"{clp(p.precio_venta)}   ·   stock {p.stock_actual}")
        meta.setStyleSheet(f"color:{styles.TEXT_MUTED}; background:transparent;")
        h.addWidget(nombre)
        h.addStretch()
        h.addWidget(meta)
        return w

    def _al_activar_item(self, item: QListWidgetItem) -> None:
        pid = item.data(Qt.UserRole)
        if pid is not None:
            self._agregar(pid)

    def _agregar(self, pid: int) -> None:
        p = self._productos.get(pid)
        if p is None:
            return
        en_carrito = self.carrito.get(pid)
        if en_carrito:
            if en_carrito["cantidad"] >= p.stock_actual:
                return  # no superar el stock
            en_carrito["cantidad"] += 1
        else:
            self.carrito[pid] = {
                "nombre": p.nombre, "precio": p.precio_venta,
                "cantidad": 1, "stock": p.stock_actual,
            }
        self._rebuild_carrito()

    # ── Panel derecho: carrito ──────────────────────────────────────────────
    def _panel_carrito(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(styles.S1)

        lay.addWidget(QLabel("Venta actual", objectName="Title"))
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["PRODUCTO", "CANT.", "PRECIO", "SUBTOTAL", ""])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(52)  # filas cómodas
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setSelectionMode(QTableWidget.NoSelection)
        self.tabla.setShowGrid(False)
        # Headers en mayúsculas pequeñas con tracking (QSS no soporta letter-spacing)
        hf = self.tabla.horizontalHeader().font()
        hf.setLetterSpacing(QFont.PercentageSpacing, 108)
        hf.setPointSizeF(hf.pointSizeF() * 0.9)
        self.tabla.horizontalHeader().setFont(hf)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        lay.addWidget(self.tabla, 1)

        # Estado vacío diseñado: ícono sutil + texto centrado
        self.vacio = QWidget()
        vlay = QVBoxLayout(self.vacio)
        vlay.setAlignment(Qt.AlignCenter)
        vlay.setSpacing(styles.S1)
        icono = QLabel()
        icono.setAlignment(Qt.AlignCenter)
        if styles.qta is not None:
            icono.setPixmap(styles.qta.icon("fa5s.shopping-cart", color=styles.BORDER).pixmap(48, 48))
        vlay.addWidget(icono)
        txt = QLabel("Aún no hay productos en la venta.\nBusca y agrega desde la izquierda.")
        txt.setObjectName("EmptyState")
        txt.setAlignment(Qt.AlignCenter)
        vlay.addWidget(txt)
        lay.addWidget(self.vacio, 1)

        # Boleta SII (preparado, no bloqueante)
        fila_sii = QHBoxLayout()
        self.chk_boleta = QCheckBox("Emitir boleta SII")
        self.chk_boleta.toggled.connect(lambda on: self.boleta_num.setEnabled(on))
        fila_sii.addWidget(self.chk_boleta)
        self.boleta_num = QLineEdit()
        self.boleta_num.setPlaceholderText("N° de boleta (opcional)")
        self.boleta_num.setEnabled(False)
        fila_sii.addWidget(self.boleta_num, 1)
        lay.addLayout(fila_sii)
        nota_sii = QLabel("Integración SII pendiente de validar con el cliente.")
        nota_sii.setObjectName("Subtitle")
        lay.addWidget(nota_sii)

        # Total + acciones
        fila_total = QHBoxLayout()
        self.total = QLabel("Total: $0")
        self.total.setStyleSheet("font-size:20px; font-weight:700;")
        fila_total.addWidget(self.total)
        fila_total.addStretch()
        limpiar = QPushButton("Limpiar")
        styles.style_button(limpiar, "secondary", "fa5s.trash")
        limpiar.clicked.connect(self._limpiar)
        fila_total.addWidget(limpiar)
        self.btn_confirmar = QPushButton("Confirmar venta")
        styles.style_button(self.btn_confirmar, "primary", "fa5s.cash-register")
        self.btn_confirmar.clicked.connect(self._confirmar)
        fila_total.addWidget(self.btn_confirmar)
        lay.addLayout(fila_total)
        return panel

    def _rebuild_carrito(self) -> None:
        self.tabla.setRowCount(0)
        for pid, it in self.carrito.items():
            r = self.tabla.rowCount()
            self.tabla.insertRow(r)

            nombre = QTableWidgetItem(it["nombre"])
            nombre.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.tabla.setItem(r, 0, nombre)

            stepper = styles.QuantityStepper(value=it["cantidad"], minimum=1, maximum=it["stock"])
            sub_item = QTableWidgetItem(clp(it["precio"] * it["cantidad"]))
            sub_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            fb = sub_item.font(); fb.setBold(True); sub_item.setFont(fb)  # subtotal peso 600
            stepper.valueChanged.connect(
                lambda v, p=pid, si=sub_item: self._cambiar_cantidad(p, v, si)
            )
            self.tabla.setCellWidget(r, 1, _centrar(stepper))

            precio = QTableWidgetItem(clp(it["precio"]))
            precio.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla.setItem(r, 2, precio)
            self.tabla.setItem(r, 3, sub_item)

            quitar = QPushButton()
            styles.style_button(quitar, "icon_danger", "fa5s.times")
            quitar.clicked.connect(lambda _=False, p=pid: self._quitar(p))
            self.tabla.setCellWidget(r, 4, _centrar(quitar))

        hay = bool(self.carrito)
        self.tabla.setVisible(hay)
        self.vacio.setVisible(not hay)
        self.btn_confirmar.setEnabled(hay)
        self._actualizar_total()

    def _cambiar_cantidad(self, pid: int, valor: int, sub_item: QTableWidgetItem) -> None:
        if pid in self.carrito:
            self.carrito[pid]["cantidad"] = valor
            sub_item.setText(clp(self.carrito[pid]["precio"] * valor))
            self._actualizar_total()

    def _quitar(self, pid: int) -> None:
        self.carrito.pop(pid, None)
        self._rebuild_carrito()

    def _actualizar_total(self) -> None:
        total = sum(it["precio"] * it["cantidad"] for it in self.carrito.values())
        self.total.setText(f"Total: {clp(total)}")

    def _limpiar(self) -> None:
        self.carrito.clear()
        self._rebuild_carrito()

    def _confirmar(self) -> None:
        if not self.carrito:
            return
        items = [
            {"producto_id": pid, "cantidad": it["cantidad"], "precio_unitario": it["precio"]}
            for pid, it in self.carrito.items()
        ]
        boleta = self.boleta_num.text().strip() if self.chk_boleta.isChecked() else None
        try:
            venta_id = repo.registrar_venta(
                items, pos_origen=self.selector_pos.currentText(),
                usuario_id=self.usuario.id, boleta_sii=boleta,
            )
        except ValueError as e:
            QMessageBox.warning(self, "No se pudo confirmar la venta", str(e))
            return
        NotaVentaDialog(venta_id, self).exec()
        self._limpiar()
        self.chk_boleta.setChecked(False)
        self.boleta_num.clear()
        self._cargar_productos()  # el stock cambió


class NotaVentaDialog(QDialog):
    """Vista previa de la nota de venta (al ancho real del papel) e impresión térmica.

    La nota ya está guardada en la base; imprimir es opcional. Si la impresora
    falla, se avisa sin crashear y se ofrece reintentar o cerrar.
    """

    def __init__(self, venta_id: int, parent=None) -> None:
        super().__init__(parent)
        self.venta_id = venta_id
        self._worker: PrintWorker | None = None
        self.setWindowTitle(f"Nota de venta N° {venta_id}")
        self.setMinimumWidth(360)
        self.setStyleSheet(styles.build_stylesheet())

        # El texto se compone al ancho configurado (58mm=32, 80mm=48 chars).
        self._texto = repo.nota_texto(venta_id, printing.ancho_caracteres())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(styles.S3, styles.S3, styles.S3, styles.S3)
        lay.setSpacing(styles.S2)
        ok = QLabel(f"Nota N° {venta_id} generada")
        ok.setStyleSheet(f"color:{styles.OK}; font-weight:700; font-size:16px;")
        lay.addWidget(ok)

        vista = QPlainTextEdit(self._texto)
        vista.setReadOnly(True)
        vista.setFont(QFont("Courier New", 10))
        lay.addWidget(vista, 1)

        aviso = QLabel("Vista previa. Se imprimirá tal cual en la impresora térmica.")
        aviso.setObjectName("Subtitle")
        lay.addWidget(aviso)

        fila = QHBoxLayout()
        fila.setSpacing(styles.S1)
        fila.addStretch()
        cerrar = QPushButton("Cerrar")
        styles.style_button(cerrar, "secondary", "fa5s.times")
        cerrar.clicked.connect(self.accept)
        fila.addWidget(cerrar)
        self.btn_imprimir = QPushButton("Imprimir")
        styles.style_button(self.btn_imprimir, "primary", "fa5s.print")
        self.btn_imprimir.clicked.connect(self._imprimir)
        fila.addWidget(self.btn_imprimir)
        lay.addLayout(fila)

    def _imprimir(self) -> None:
        self.btn_imprimir.setEnabled(False)
        self.btn_imprimir.setText("Imprimiendo…")
        logo = database.get_config("negocio_logo", "") or None
        self._worker = PrintWorker(self._texto, logo, self)
        self._worker.ok.connect(self._impresion_ok)
        self._worker.error.connect(self._impresion_error)
        self._worker.start()

    def _restaurar_boton(self) -> None:
        self.btn_imprimir.setEnabled(True)
        self.btn_imprimir.setText("Imprimir")

    def _impresion_ok(self) -> None:
        self._restaurar_boton()
        QMessageBox.information(self, "Impresión", "La nota se imprimió correctamente.")

    def _impresion_error(self, mensaje: str) -> None:
        self._restaurar_boton()
        resp = QMessageBox.warning(
            self, "No se pudo imprimir",
            f"{mensaje}\n\nLa nota quedó guardada de todos modos.",
            QMessageBox.Retry | QMessageBox.Cancel, QMessageBox.Retry,
        )
        if resp == QMessageBox.Retry:
            self._imprimir()
