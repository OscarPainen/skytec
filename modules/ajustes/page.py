"""Módulo Ajustes — configuración del negocio, cajas e impresora térmica.

Todo se guarda en la tabla `config`. Incluye una prueba de impresión para
validar la conexión con la impresora sin tener que hacer una venta.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import database, printing
from core.config import cargar_config, guardar_config
from core.models import Usuario
from ui import styles
from workers.printing import PrintWorker


class AjustesPage(QWidget):
    def __init__(self, usuario: Usuario) -> None:
        super().__init__()
        self.usuario = usuario
        self._worker: PrintWorker | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(styles.S4, styles.S4, styles.S4, styles.S4)
        raiz.setSpacing(styles.S3)

        titulo = QLabel("Ajustes")
        titulo.setObjectName("Title")
        raiz.addWidget(titulo)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        form = QWidget()
        self.form = QVBoxLayout(form)
        self.form.setSpacing(styles.S2)
        self.form.setAlignment(Qt.AlignTop)
        scroll.setWidget(form)
        raiz.addWidget(scroll, 1)

        # ── Negocio ────────────────────────────────────────────────────────
        self._seccion("Negocio")
        self.negocio_nombre = QLineEdit(database.get_config("negocio_nombre", "Skytec"))
        self.form.addLayout(self._fila("Nombre", self.negocio_nombre))
        self.logo = QLineEdit(database.get_config("negocio_logo", ""))
        self.logo.setPlaceholderText("Sin logo (opcional)")
        btn_logo = QPushButton("Seleccionar…")
        styles.style_button(btn_logo, "secondary", "fa5s.image")
        btn_logo.clicked.connect(self._elegir_logo)
        self.form.addLayout(self._fila("Logo", self.logo, btn_logo))

        # ── Cajas (PoS) ────────────────────────────────────────────────────
        self._seccion("Cajas (Puntos de Venta)")
        self.pos1 = QLineEdit(database.get_config("pos_1_nombre", "Tech"))
        self.pos2 = QLineEdit(database.get_config("pos_2_nombre", "Fit"))
        self.form.addLayout(self._fila("Caja 1", self.pos1))
        self.form.addLayout(self._fila("Caja 2", self.pos2))

        # ── Inventario ─────────────────────────────────────────────────────
        self._seccion("Inventario")
        self.umbral = QSpinBox()
        self.umbral.setMaximum(100000)
        self.umbral.setValue(int(database.get_config("stock_bajo_umbral", "5") or 5))
        self.form.addLayout(self._fila("Umbral de stock bajo", self.umbral))

        # ── Categorías ─────────────────────────────────────────────────────
        self._seccion("Categorías")
        self._cfg = cargar_config()
        ayuda_cat = QLabel(
            "Se usan para etiquetar cada venta (reparación / tecnología / "
            "suplemento) y alimentan el Dashboard."
        )
        ayuda_cat.setObjectName("Subtitle")
        self.form.addWidget(ayuda_cat)
        self.lista_categorias = QListWidget()
        # Alto fijo (no el sizeHint por defecto, que ignora la cantidad de filas):
        # alcanza para las 3 categorías actuales + margen para 1-2 más sin scroll;
        # con más, el scroll interno de la lista sigue disponible.
        self.lista_categorias.setFixedHeight(260)
        self.form.addWidget(self.lista_categorias)
        self._refrescar_categorias()

        fila_cat = QHBoxLayout()
        fila_cat.setSpacing(styles.S1)
        self.nueva_categoria = QLineEdit()
        self.nueva_categoria.setPlaceholderText("Nueva categoría…")
        fila_cat.addWidget(self.nueva_categoria, 1)
        btn_agregar_cat = QPushButton("Agregar")
        styles.style_button(btn_agregar_cat, "secondary", "fa5s.plus")
        btn_agregar_cat.clicked.connect(self._agregar_categoria)
        fila_cat.addWidget(btn_agregar_cat)
        self.form.addLayout(fila_cat)

        # ── Impresora ──────────────────────────────────────────────────────
        self._seccion("Impresora térmica")
        self.conexion = QComboBox()
        for etiqueta, valor in [("USB", "usb"), ("Red", "network"), ("Serial", "serial")]:
            self.conexion.addItem(etiqueta, valor)
        self._set_combo(self.conexion, database.get_config("impresora_conexion", "usb"))
        self.conexion.currentIndexChanged.connect(self._actualizar_campos_conexion)
        self.form.addLayout(self._fila("Conexión", self.conexion))

        self.ancho = QComboBox()
        self.ancho.addItem("58 mm", "58")
        self.ancho.addItem("80 mm", "80")
        self._set_combo(self.ancho, database.get_config("impresora_ancho", "80"))
        self.form.addLayout(self._fila("Ancho de papel", self.ancho))

        self.host = QLineEdit(database.get_config("impresora_host", "192.168.0.100"))
        self.puerto = QLineEdit(database.get_config("impresora_puerto", "9100"))
        self.fila_host = self._fila("IP de la impresora", self.host)
        self.fila_puerto = self._fila("Puerto", self.puerto)
        self.form.addLayout(self.fila_host)
        self.form.addLayout(self.fila_puerto)

        self.serial = QLineEdit(database.get_config("impresora_serial", "COM1"))
        self.fila_serial = self._fila("Puerto serial", self.serial)
        self.form.addLayout(self.fila_serial)

        self.usb_vendor = QLineEdit(database.get_config("impresora_usb_vendor", "0x0416"))
        self.usb_product = QLineEdit(database.get_config("impresora_usb_product", "0x5011"))
        self.fila_vendor = self._fila("USB Vendor ID", self.usb_vendor)
        self.fila_product = self._fila("USB Product ID", self.usb_product)
        self.form.addLayout(self.fila_vendor)
        self.form.addLayout(self.fila_product)

        self._actualizar_campos_conexion()

        # ── Acciones ───────────────────────────────────────────────────────
        acciones = QHBoxLayout()
        acciones.setSpacing(styles.S1)
        self.btn_prueba = QPushButton("Imprimir prueba")
        styles.style_button(self.btn_prueba, "secondary", "fa5s.print")
        self.btn_prueba.clicked.connect(self._imprimir_prueba)
        acciones.addWidget(self.btn_prueba)
        acciones.addStretch()
        guardar = QPushButton("Guardar cambios")
        styles.style_button(guardar, "primary", "fa5s.check")
        guardar.clicked.connect(self._guardar)
        acciones.addWidget(guardar)
        raiz.addLayout(acciones)

    # ── Helpers de layout ───────────────────────────────────────────────────
    def _seccion(self, texto: str) -> None:
        lbl = QLabel(texto)
        lbl.setStyleSheet(
            f"color:{styles.TEXT_MUTED}; font-weight:600; font-size:13px; margin-top:6px;"
        )
        self.form.addWidget(lbl)

    def _fila(self, etiqueta: str, widget: QWidget, extra: QWidget | None = None) -> QHBoxLayout:
        fila = QHBoxLayout()
        fila.setSpacing(styles.S1)
        lbl = QLabel(etiqueta)
        lbl.setObjectName("FieldLabel")
        lbl.setFixedWidth(160)
        fila.addWidget(lbl)
        fila.addWidget(widget, 1)
        if extra is not None:
            fila.addWidget(extra)
        return fila

    @staticmethod
    def _set_combo(combo: QComboBox, valor: str) -> None:
        idx = combo.findData(valor)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    @staticmethod
    def _mostrar_fila(fila: QHBoxLayout, visible: bool) -> None:
        for i in range(fila.count()):
            w = fila.itemAt(i).widget()
            if w is not None:
                w.setVisible(visible)

    def _actualizar_campos_conexion(self) -> None:
        tipo = self.conexion.currentData()
        self._mostrar_fila(self.fila_host, tipo == "network")
        self._mostrar_fila(self.fila_puerto, tipo == "network")
        self._mostrar_fila(self.fila_serial, tipo == "serial")
        self._mostrar_fila(self.fila_vendor, tipo == "usb")
        self._mostrar_fila(self.fila_product, tipo == "usb")

    # ── Categorías ───────────────────────────────────────────────────────────
    def _refrescar_categorias(self) -> None:
        self.lista_categorias.clear()
        for cat in self._cfg["categorias"]:
            item = QListWidgetItem()
            # El QSS global de QListWidget::item agrega 12px de padding arriba/abajo
            # + 2px de margen (ver ui/styles.py): con menos alto que eso más el botón
            # (mínimo 32px), la fila se comprime y el ícono de tacho queda invisible.
            item.setSizeHint(QSize(0, 60))
            self.lista_categorias.addItem(item)
            self.lista_categorias.setItemWidget(item, self._fila_categoria(cat))

    def _fila_categoria(self, categoria: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(4, 0, 4, 0)
        h.addWidget(QLabel(categoria))
        h.addStretch()
        quitar = QPushButton()
        styles.style_button(quitar, "icon_danger", "fa5s.times")
        quitar.setToolTip("Eliminar categoría")
        quitar.clicked.connect(lambda _=False, c=categoria: self._quitar_categoria(c))
        h.addWidget(quitar)
        return w

    def _agregar_categoria(self) -> None:
        nueva = self.nueva_categoria.text().strip()
        if not nueva:
            return
        if nueva.lower() in [c.lower() for c in self._cfg["categorias"]]:
            QMessageBox.information(self, "Categorías", "Esa categoría ya existe.")
            return
        self._cfg["categorias"].append(nueva)
        guardar_config(self._cfg)
        self.nueva_categoria.clear()
        self._refrescar_categorias()

    def _quitar_categoria(self, categoria: str) -> None:
        if self._categoria_tiene_ventas(categoria):
            QMessageBox.warning(
                self, "No se puede eliminar",
                f"«{categoria}» tiene ventas registradas. No se puede eliminar "
                "una categoría con historial.",
            )
            return
        if self._categoria_tiene_productos(categoria):
            QMessageBox.warning(
                self, "No se puede eliminar",
                f"No se puede eliminar «{categoria}»: todavía hay productos "
                "con esta categoría.",
            )
            return
        self._cfg["categorias"] = [c for c in self._cfg["categorias"] if c != categoria]
        guardar_config(self._cfg)
        self._refrescar_categorias()

    @staticmethod
    def _categoria_tiene_ventas(categoria: str) -> bool:
        # Solo lectura: consulta la foto de categoría guardada en cada venta.
        conn = database.get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM venta_items WHERE categoria=?", (categoria,)
            ).fetchone()
            return row[0] > 0
        finally:
            conn.close()

    @staticmethod
    def _categoria_tiene_productos(categoria: str) -> bool:
        # Solo lectura: productos de inventario (vendidos o no) en esa categoría.
        conn = database.get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM productos WHERE categoria=?", (categoria,)
            ).fetchone()
            return row[0] > 0
        finally:
            conn.close()

    # ── Acciones ─────────────────────────────────────────────────────────────
    def _elegir_logo(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar logo", "", "Imágenes (*.png *.jpg *.jpeg *.bmp)"
        )
        if ruta:
            self.logo.setText(ruta)

    def _guardar(self) -> None:
        valores = {
            "negocio_nombre": self.negocio_nombre.text().strip() or "Skytec",
            "negocio_logo": self.logo.text().strip(),
            "pos_1_nombre": self.pos1.text().strip() or "Tech",
            "pos_2_nombre": self.pos2.text().strip() or "Fit",
            "stock_bajo_umbral": str(self.umbral.value()),
            "impresora_conexion": self.conexion.currentData(),
            "impresora_ancho": self.ancho.currentData(),
            "impresora_host": self.host.text().strip(),
            "impresora_puerto": self.puerto.text().strip() or "9100",
            "impresora_serial": self.serial.text().strip() or "COM1",
            "impresora_usb_vendor": self.usb_vendor.text().strip() or "0x0416",
            "impresora_usb_product": self.usb_product.text().strip() or "0x5011",
        }
        for clave, valor in valores.items():
            database.set_config(clave, valor)
        QMessageBox.information(self, "Ajustes", "Cambios guardados.")

    def _imprimir_prueba(self) -> None:
        self._guardar_silencioso()
        w = printing.ANCHOS.get(self.ancho.currentData(), 48)
        nombre = self.negocio_nombre.text().strip() or "Skytec"
        muestra = "\n".join([
            nombre.center(w),
            "Prueba de impresión".center(w),
            "-" * w,
            "Si lees esto, la impresora",
            "está configurada correctamente.",
        ])
        self.btn_prueba.setEnabled(False)
        self.btn_prueba.setText("Imprimiendo…")
        logo = self.logo.text().strip() or None
        self._worker = PrintWorker(muestra, logo, self)
        self._worker.ok.connect(self._prueba_ok)
        self._worker.error.connect(self._prueba_error)
        self._worker.start()

    def _guardar_silencioso(self) -> None:
        # Guarda sin el mensaje, para que la prueba use los valores actuales.
        database.set_config("impresora_conexion", self.conexion.currentData())
        database.set_config("impresora_ancho", self.ancho.currentData())
        database.set_config("impresora_host", self.host.text().strip())
        database.set_config("impresora_puerto", self.puerto.text().strip() or "9100")
        database.set_config("impresora_serial", self.serial.text().strip() or "COM1")
        database.set_config("impresora_usb_vendor", self.usb_vendor.text().strip() or "0x0416")
        database.set_config("impresora_usb_product", self.usb_product.text().strip() or "0x5011")

    def _restaurar_prueba(self) -> None:
        self.btn_prueba.setEnabled(True)
        self.btn_prueba.setText("Imprimir prueba")

    def _prueba_ok(self) -> None:
        self._restaurar_prueba()
        QMessageBox.information(self, "Prueba", "Impresión de prueba enviada correctamente.")

    def _prueba_error(self, mensaje: str) -> None:
        self._restaurar_prueba()
        QMessageBox.warning(self, "No se pudo imprimir", mensaje)
