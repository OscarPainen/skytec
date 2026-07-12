"""Módulo Inventario — vista de catálogo (grid de tarjetas) y diálogos.

Cada tarjeta muestra imagen, nombre, precio, stock y aviso de stock bajo.
Al hacer clic se abren las acciones: entrada de mercadería, merma, cambiar
disponibilidad o eliminar. Crear producto desde el botón superior.
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Producto, Usuario
from modules.inventario import repo
from ui import styles

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "productos"
CARD_W = 220        # ancho fijo de tarjeta; las columnas fluyen según el ancho
CARD_IMG_H = 120


def clp(valor: int) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def _pixmap(imagen: str | None, w: int, h: int) -> QPixmap | None:
    if not imagen:
        return None
    ruta = ASSETS / imagen
    if not ruta.exists():
        return None
    pm = QPixmap(str(ruta))
    if pm.isNull():
        return None
    return pm.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)


# ── Tarjeta de producto ─────────────────────────────────────────────────────
class _Card(QFrame):
    def __init__(self, producto: Producto, umbral: int, on_click) -> None:
        super().__init__()
        self._on_click = on_click
        self.setFixedWidth(CARD_W)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"_Card {{ background:{styles.BG}; border:1px solid {styles.BORDER};"
            f" border-radius:12px; }}"
            f"_Card:hover {{ border:1px solid {styles.ACCENT}; }}"
        )
        # Sombra suave y difusa; se eleva un poco al hover.
        self._sombra = QGraphicsDropShadowEffect(self)
        self._sombra.setColor(QColor(15, 23, 42, 30))
        self.setGraphicsEffect(self._sombra)
        self._elevar(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(styles.S1, styles.S1, styles.S1, styles.S1)
        lay.setSpacing(6)
        lay.addWidget(self._area_imagen(producto))

        nombre = QLabel(producto.nombre)
        nombre.setStyleSheet("font-weight:600;")
        nombre.setWordWrap(True)
        lay.addWidget(nombre)

        precio = QLabel(clp(producto.precio_venta))
        precio.setStyleSheet(f"color:{styles.ACCENT}; font-weight:600;")
        lay.addWidget(precio)

        fila = QHBoxLayout()
        stock = QLabel(f"Stock: {producto.stock_actual}")
        stock.setStyleSheet(f"color:{styles.TEXT_MUTED};")
        fila.addWidget(stock)
        fila.addStretch()
        if producto.stock_actual <= umbral:
            bajo = QLabel("Stock bajo")
            bajo.setStyleSheet(
                f"color:{styles.WARN}; font-weight:600; font-size:12px;"
            )
            fila.addWidget(bajo)
        lay.addLayout(fila)

    def _area_imagen(self, producto: Producto) -> QWidget:
        # ponytail: la foto no se recorta en esquinas (requiere máscara); el
        # contenedor sí es redondeado. Basta para el look; máscara si se pide.
        pm = _pixmap(producto.imagen_path, CARD_W - 8, CARD_IMG_H)
        if pm:
            img = QLabel()
            img.setFixedHeight(CARD_IMG_H)
            img.setAlignment(Qt.AlignCenter)
            img.setPixmap(pm)
            img.setStyleSheet(f"background:{styles.SURFACE}; border-radius:8px;")
            return img
        # "Sin imagen" diseñado: ícono sutil + texto pequeño sobre surface
        zona = QWidget()
        zona.setFixedHeight(CARD_IMG_H)
        zona.setStyleSheet(f"background:{styles.SURFACE}; border-radius:8px;")
        vl = QVBoxLayout(zona)
        vl.setAlignment(Qt.AlignCenter)
        vl.setSpacing(4)
        ico = QLabel()
        ico.setAlignment(Qt.AlignCenter)
        if styles.qta is not None:
            ico.setPixmap(styles.qta.icon("fa5s.image", color=styles.BORDER).pixmap(28, 28))
        vl.addWidget(ico)
        txt = QLabel("Sin imagen")
        txt.setAlignment(Qt.AlignCenter)
        txt.setStyleSheet(f"color:{styles.TEXT_MUTED}; font-size:12px; background:transparent;")
        vl.addWidget(txt)
        return zona

    def _elevar(self, on: bool) -> None:
        self._sombra.setBlurRadius(24 if on else 14)
        self._sombra.setOffset(0, 6 if on else 3)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._elevar(True)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._elevar(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._on_click()


# ── Página principal del módulo ─────────────────────────────────────────────
class InventarioPage(QWidget):
    def __init__(self, usuario: Usuario) -> None:
        super().__init__()
        self.usuario = usuario

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(styles.S4, styles.S4, styles.S4, styles.S4)
        raiz.setSpacing(styles.S3)

        # Encabezado: título + metadatos al lado + acciones a la derecha
        cab = QHBoxLayout()
        cab.setSpacing(styles.S1)
        titulo = QLabel("Inventario")
        titulo.setObjectName("Title")
        cab.addWidget(titulo)
        cab.addSpacing(styles.S1)
        self.resumen = QLabel("")
        self.resumen.setObjectName("Subtitle")
        cab.addWidget(self.resumen, 0, Qt.AlignBottom)  # alineado a la línea base
        cab.addStretch()
        plantilla = QPushButton("Descargar plantilla")
        styles.style_button(plantilla, "secondary", "fa5s.file-download")
        plantilla.clicked.connect(self._descargar_plantilla)
        cab.addWidget(plantilla)
        cargar = QPushButton("Cargar desde Excel")
        styles.style_button(cargar, "primary", "fa5s.file-excel")
        cargar.clicked.connect(self._cargar_excel)
        cab.addWidget(cargar)
        nuevo = QPushButton("Nuevo producto")
        styles.style_button(nuevo, "primary", "fa5s.plus")
        nuevo.clicked.connect(self._nuevo_producto)
        cab.addWidget(nuevo)
        raiz.addLayout(cab)

        # Filtros
        filtros = QHBoxLayout()
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText("Buscar por nombre…")
        self.buscar.textChanged.connect(self.recargar)
        filtros.addWidget(self.buscar, 2)
        self.categoria = QComboBox()
        self.categoria.currentIndexChanged.connect(self.recargar)
        filtros.addWidget(self.categoria, 1)
        self.mostrar_no_disp = QComboBox()
        self.mostrar_no_disp.addItems(["Solo disponibles", "Incluir no disponibles"])
        self.mostrar_no_disp.currentIndexChanged.connect(self.recargar)
        filtros.addWidget(self.mostrar_no_disp, 1)
        raiz.addLayout(filtros)

        # Grid con scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.contenedor = QWidget()
        self.grid = QGridLayout(self.contenedor)
        self.grid.setSpacing(styles.S2)  # gap consistente de 16px
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.contenedor)
        raiz.addWidget(self.scroll, 1)
        self._cards: list[_Card] = []

        self.vacio = QLabel("No hay productos que mostrar.")
        self.vacio.setObjectName("EmptyState")
        self.vacio.setAlignment(Qt.AlignCenter)
        raiz.addWidget(self.vacio)

        self._cargar_categorias()
        self.recargar()

    def _cargar_categorias(self) -> None:
        actual = self.categoria.currentText()
        self.categoria.blockSignals(True)
        self.categoria.clear()
        self.categoria.addItem("Todas las categorías", None)
        for cat in repo.categorias():
            self.categoria.addItem(cat, cat)
        idx = self.categoria.findText(actual)
        if idx >= 0:
            self.categoria.setCurrentIndex(idx)
        self.categoria.blockSignals(False)

    def recargar(self) -> None:
        # Descartar tarjetas anteriores
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        productos = repo.listar_productos(
            busqueda=self.buscar.text().strip(),
            categoria=self.categoria.currentData(),
            incluir_no_disponibles=self.mostrar_no_disp.currentIndex() == 1,
        )
        self.vacio.setVisible(not productos)
        self.scroll.setVisible(bool(productos))

        umbral = repo.umbral_stock_bajo()
        self._cards = [
            _Card(p, umbral, lambda pid=p.id: self._abrir_acciones(pid))
            for p in productos
        ]
        self._relayout()

        unidades, valor = repo.valor_inventario()
        self.resumen.setText(f"{unidades} unidades · {clp(valor)} en inventario")

    def _columnas(self) -> int:
        ancho = self.scroll.viewport().width()
        return max(1, (ancho + styles.S2) // (CARD_W + styles.S2))

    def _relayout(self) -> None:
        """Reubica las tarjetas en columnas según el ancho disponible (arriba-izq)."""
        while self.grid.count():
            self.grid.takeAt(0)  # solo desanclar; las tarjetas viven en self._cards
        cols = self._columnas()
        for i, card in enumerate(self._cards):
            self.grid.addWidget(card, i // cols, i % cols)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._cards:
            self._relayout()

    def _nuevo_producto(self) -> None:
        dlg = NuevoProductoDialog(self.usuario, self)
        if dlg.exec() == QDialog.Accepted:
            self._cargar_categorias()
            self.recargar()

    def _abrir_acciones(self, producto_id: int) -> None:
        dlg = AccionesProductoDialog(producto_id, self.usuario, self)
        dlg.exec()
        self._cargar_categorias()
        self.recargar()

    # ── Carga masiva vía Excel ──────────────────────────────────────────────
    def _descargar_plantilla(self) -> None:
        from modules.inventario import excel

        carpeta = Path.home() / "Downloads"
        if carpeta.exists():
            destino = carpeta / "plantilla_inventario_skytec.xlsx"
        else:  # fallback si no hay carpeta de Descargas
            ruta, _ = QFileDialog.getSaveFileName(
                self, "Guardar plantilla", "plantilla_inventario_skytec.xlsx",
                "Excel (*.xlsx)",
            )
            if not ruta:
                return
            destino = Path(ruta)
        try:
            excel.generar_plantilla(destino)
        except Exception:
            QMessageBox.warning(
                self, "No se pudo guardar",
                "No pudimos guardar la plantilla. Revisa que el archivo no esté "
                "abierto en Excel e inténtalo de nuevo.",
            )
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("Plantilla lista")
        box.setText(f"Se guardó la plantilla en:\n{destino}")
        abrir = box.addButton("Abrir carpeta", QMessageBox.ActionRole)
        box.addButton("Cerrar", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is abrir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(destino.parent)))

    def _cargar_excel(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo", "", "Excel (*.xlsx)"
        )
        if not ruta:
            return
        # Lectura en QThread para no congelar la UI.
        self._worker = _LecturaWorker(ruta, self)
        self._worker.listo.connect(self._mostrar_preview)
        self._worker.error.connect(
            lambda m: QMessageBox.warning(self, "No se pudo leer el archivo", m)
        )
        self._worker.start()

    def _mostrar_preview(self, filas: list) -> None:
        if not filas:
            QMessageBox.information(
                self, "Sin datos", "El archivo no tenía filas para importar."
            )
            return
        dlg = ImportPreviewDialog(filas, self.usuario, self)
        if dlg.exec() == QDialog.Accepted:
            self._cargar_categorias()
            self.recargar()


def _spin_clp(maximo: int = 100_000_000) -> QSpinBox:
    sp = QSpinBox()
    sp.setMaximum(maximo)
    sp.setPrefix("$ ")
    sp.setGroupSeparatorShown(True)
    return sp


# ── Zona de carga de imagen (clic para elegir, muestra miniatura) ───────────
class _DropZone(QFrame):
    def __init__(self, on_click) -> None:
        super().__init__()
        self._on_click = on_click
        self.setObjectName("DropZone")
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._on_click()


# ── Diálogo: nuevo producto ─────────────────────────────────────────────────
class NuevoProductoDialog(QDialog):
    def __init__(self, usuario: Usuario, parent=None) -> None:
        super().__init__(parent)
        self.usuario = usuario
        self._imagen_origen: Path | None = None
        self.setWindowTitle("Nuevo producto")
        self.setMinimumWidth(520)
        self.setStyleSheet(styles.build_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(styles.S3, styles.S3, styles.S3, styles.S3)
        root.setSpacing(styles.S2)

        titulo = QLabel("Nuevo producto")
        titulo.setObjectName("Title")
        root.addWidget(titulo)
        sub = QLabel("Los campos con * son obligatorios.")
        sub.setObjectName("Subtitle")
        root.addWidget(sub)

        # Campos (mismos widgets y nombres de antes)
        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("Ej: Cargador USB-C 20W")
        self.categoria = QLineEdit()
        self.categoria.setPlaceholderText("Ej: Accesorios")
        self.precio = _spin_clp()
        self.costo = _spin_clp()
        self.stock = QSpinBox()
        self.stock.setMaximum(1_000_000)
        self.descripcion = QLineEdit()
        self.descripcion.setPlaceholderText("Opcional")

        root.addLayout(self._campo("Nombre", self.nombre, obligatorio=True))
        root.addLayout(self._campo("Categoría", self.categoria))

        fila_nums = QHBoxLayout()
        fila_nums.setSpacing(styles.S2)
        fila_nums.addLayout(self._campo("Precio de venta", self.precio))
        fila_nums.addLayout(self._campo("Costo unitario", self.costo))
        fila_nums.addLayout(self._campo("Stock inicial", self.stock))
        root.addLayout(fila_nums)

        root.addLayout(self._campo("Descripción", self.descripcion))

        # Zona de imagen con miniatura
        self.img_zona = _DropZone(self._elegir_imagen)
        zl = QHBoxLayout(self.img_zona)
        zl.setContentsMargins(styles.S2, styles.S2, styles.S2, styles.S2)
        zl.setSpacing(styles.S2)
        self.img_thumb = QLabel()
        self.img_thumb.setFixedSize(56, 56)
        self.img_thumb.setAlignment(Qt.AlignCenter)
        self.img_thumb.setStyleSheet(
            f"background:{styles.BG}; border-radius:{styles.RADIUS}px; color:{styles.TEXT_MUTED};"
        )
        self._set_thumb_placeholder()
        self.img_label = QLabel("Haz clic para seleccionar una imagen (opcional)")
        self.img_label.setStyleSheet(f"color:{styles.TEXT_MUTED};")
        zl.addWidget(self.img_thumb)
        zl.addWidget(self.img_label, 1)
        root.addLayout(self._campo("Imagen", self.img_zona))

        # Footer: acciones a la derecha con gap
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
        root.addSpacing(styles.S1)
        root.addLayout(acciones)

    def _campo(self, texto: str, widget: QWidget, obligatorio: bool = False) -> QVBoxLayout:
        """Etiqueta arriba del campo; asterisco de acento si es obligatorio."""
        cont = QVBoxLayout()
        cont.setSpacing(4)
        marca = f" <span style='color:{styles.ACCENT}'>*</span>" if obligatorio else ""
        lbl = QLabel(f"{texto}{marca}")
        lbl.setObjectName("FieldLabel")
        lbl.setTextFormat(Qt.RichText)
        cont.addWidget(lbl)
        cont.addWidget(widget)
        return cont

    def _set_thumb_placeholder(self) -> None:
        if styles.qta is not None:
            self.img_thumb.setPixmap(
                styles.qta.icon("fa5s.image", color=styles.TEXT_MUTED).pixmap(24, 24)
            )
        else:
            self.img_thumb.setText("IMG")

    def _elegir_imagen(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen", "", "Imágenes (*.png *.jpg *.jpeg *.webp)"
        )
        if ruta:
            self._imagen_origen = Path(ruta)
            self.img_label.setText(self._imagen_origen.name)
            pm = QPixmap(ruta)
            if not pm.isNull():
                self.img_thumb.setPixmap(
                    pm.scaled(56, 56, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                )

    def _guardar(self) -> None:
        nombre = self.nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Falta el nombre", "El nombre es obligatorio.")
            return
        imagen_nombre = ""
        if self._imagen_origen:
            ASSETS.mkdir(parents=True, exist_ok=True)
            imagen_nombre = f"{uuid.uuid4().hex}{self._imagen_origen.suffix.lower()}"
            shutil.copy(self._imagen_origen, ASSETS / imagen_nombre)
        repo.crear_producto(
            nombre=nombre,
            precio_venta=self.precio.value(),
            costo=self.costo.value(),
            stock_inicial=self.stock.value(),
            categoria=self.categoria.text().strip(),
            descripcion=self.descripcion.text().strip(),
            imagen_path=imagen_nombre,
            usuario_id=self.usuario.id,
        )
        self.accept()


# ── Diálogo: acciones sobre un producto existente ───────────────────────────
class AccionesProductoDialog(QDialog):
    def __init__(self, producto_id: int, usuario: Usuario, parent=None) -> None:
        super().__init__(parent)
        self.producto_id = producto_id
        self.usuario = usuario
        self.setMinimumWidth(400)
        self.setStyleSheet(styles.build_stylesheet())

        productos = {p.id: p for p in repo.listar_productos(incluir_no_disponibles=True)}
        self.producto = productos[producto_id]
        self.setWindowTitle(self.producto.nombre)

        lay = QVBoxLayout(self)
        lay.setSpacing(styles.S2)

        info = QLabel(
            f"Stock actual: {self.producto.stock_actual}  ·  "
            f"Costo: {clp(self.producto.costo)}  ·  "
            f"Venta: {clp(self.producto.precio_venta)}"
        )
        info.setStyleSheet(f"color:{styles.TEXT_MUTED};")
        lay.addWidget(info)

        # Entrada de mercadería
        lay.addWidget(self._titulo("Registrar entrada"))
        self.ent_cant = QSpinBox(); self.ent_cant.setMaximum(1_000_000); self.ent_cant.setMinimum(1)
        self.ent_costo = _spin_clp(); self.ent_costo.setValue(self.producto.costo)
        f1 = QHBoxLayout()
        f1.addWidget(QLabel("Cantidad")); f1.addWidget(self.ent_cant)
        f1.addWidget(QLabel("Costo unit.")); f1.addWidget(self.ent_costo)
        btn_ent = QPushButton("Agregar"); btn_ent.clicked.connect(self._entrada)
        styles.style_button(btn_ent, "primary", "fa5s.plus")
        f1.addWidget(btn_ent)
        lay.addLayout(f1)

        # Merma
        lay.addWidget(self._titulo("Registrar merma / baja de stock"))
        self.merma_cant = QSpinBox(); self.merma_cant.setMaximum(1_000_000); self.merma_cant.setMinimum(1)
        self.merma_motivo = QLineEdit(); self.merma_motivo.setPlaceholderText("Motivo")
        f2 = QHBoxLayout()
        f2.addWidget(QLabel("Cantidad")); f2.addWidget(self.merma_cant)
        f2.addWidget(self.merma_motivo, 1)
        btn_merma = QPushButton("Dar de baja"); btn_merma.clicked.connect(self._merma)
        styles.style_button(btn_merma, "danger", "fa5s.exclamation-triangle")
        f2.addWidget(btn_merma)
        lay.addLayout(f2)

        # Disponibilidad + eliminar
        lay.addWidget(self._titulo("Otras acciones"))
        f3 = QHBoxLayout()
        texto = "Marcar disponible" if not self.producto.disponible else "Marcar no disponible"
        self.btn_disp = QPushButton(texto)
        icono_disp = "fa5s.eye" if not self.producto.disponible else "fa5s.eye-slash"
        styles.style_button(self.btn_disp, "secondary", icono_disp)
        self.btn_disp.clicked.connect(self._toggle_disp)
        f3.addWidget(self.btn_disp)
        btn_del = QPushButton("Eliminar")
        styles.style_button(btn_del, "danger", "fa5s.trash")
        btn_del.clicked.connect(self._eliminar)
        f3.addWidget(btn_del)
        f3.addStretch()
        cerrar = QPushButton("Cerrar")
        styles.style_button(cerrar, "secondary", "fa5s.times")
        cerrar.clicked.connect(self.accept)
        f3.addWidget(cerrar)
        lay.addLayout(f3)

    def _titulo(self, texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setStyleSheet("font-weight:600; margin-top:6px;")
        return lbl

    def _entrada(self) -> None:
        try:
            repo.registrar_entrada(
                self.producto_id, self.ent_cant.value(), self.ent_costo.value(),
                self.usuario.id,
            )
        except ValueError as e:
            QMessageBox.warning(self, "No se pudo registrar", str(e)); return
        self.accept()

    def _merma(self) -> None:
        motivo = self.merma_motivo.text().strip()
        if not motivo:
            QMessageBox.warning(self, "Falta el motivo", "Indica el motivo de la baja.")
            return
        try:
            repo.registrar_merma(self.producto_id, self.merma_cant.value(), motivo, self.usuario.id)
        except ValueError as e:
            QMessageBox.warning(self, "No se pudo registrar", str(e)); return
        self.accept()

    def _toggle_disp(self) -> None:
        repo.set_disponible(self.producto_id, not self.producto.disponible)
        self.accept()

    def _eliminar(self) -> None:
        if QMessageBox.question(
            self, "Eliminar producto",
            f"¿Eliminar «{self.producto.nombre}» definitivamente?",
        ) != QMessageBox.Yes:
            return
        try:
            repo.eliminar_producto(self.producto_id)
        except ValueError as e:
            QMessageBox.warning(self, "No se puede eliminar", str(e)); return
        self.accept()


# ── Worker de lectura (QThread) ─────────────────────────────────────────────
class _LecturaWorker(QThread):
    listo = Signal(list)   # list[FilaImport]
    error = Signal(str)    # mensaje ya en lenguaje humano

    def __init__(self, ruta: str, parent=None) -> None:
        super().__init__(parent)
        self.ruta = ruta

    def run(self) -> None:
        from modules.inventario import excel

        try:
            self.listo.emit(excel.leer_archivo(self.ruta))
        except excel.ExcelError as e:
            self.error.emit(str(e))
        except Exception:
            self.error.emit(excel.MSG_ILEGIBLE)


# ── Vista previa de la importación ──────────────────────────────────────────
class ImportPreviewDialog(QDialog):
    _COLS = ["Fila", "Nombre", "Categoría", "Precio", "Costo", "Stock", "Disp.", "Estado"]

    def __init__(self, filas: list, usuario: Usuario, parent=None) -> None:
        super().__init__(parent)
        self.filas = filas
        self.usuario = usuario
        self.setWindowTitle("Vista previa de la importación")
        self.setMinimumSize(760, 480)
        self.setStyleSheet(styles.build_stylesheet())

        lay = QVBoxLayout(self)
        lay.setSpacing(styles.S2)

        validas = [f for f in filas if f.valida and not f.es_duplicado]
        dups = [f for f in filas if f.valida and f.es_duplicado]
        errores = [f for f in filas if not f.valida]
        self._hay_validas_o_dups = bool(validas or dups)

        resumen = QLabel(
            f"{len(validas)} productos válidos · {len(errores)} con errores · "
            f"{len(dups)} duplicados"
        )
        resumen.setStyleSheet("font-weight:600;")
        lay.addWidget(resumen)

        tabla = QTableWidget(len(filas), len(self._COLS))
        tabla.setHorizontalHeaderLabels(self._COLS)
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        tabla.verticalHeader().setVisible(False)
        tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tabla.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)

        rojo = QColor(254, 226, 226)
        ambar = QColor(254, 243, 199)
        for r, f in enumerate(filas):
            if not f.valida:
                estado, color = f.error, rojo
            elif f.es_duplicado:
                estado, color = "Duplicado (según política elegida)", ambar
            else:
                estado, color = "OK", None
            celdas = [
                str(f.numero_fila), f.nombre, f.categoria, clp(f.precio_venta),
                clp(f.costo), str(f.stock_inicial), "Sí" if f.disponible else "No",
                estado,
            ]
            for c, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                if color is not None:
                    item.setBackground(color)
                if c == 7 and not f.valida:
                    item.setToolTip(f.error)
                tabla.setItem(r, c, item)
        lay.addWidget(tabla, 1)

        # Política de duplicados + acciones
        pie = QHBoxLayout()
        pie.setSpacing(styles.S1)
        pie.addWidget(QLabel("Duplicados:"))
        self.politica = QComboBox()
        self.politica.addItem("Omitir duplicados", "omitir")
        self.politica.addItem("Sumar stock al existente", "sumar")
        pie.addWidget(self.politica)
        pie.addStretch()
        cancelar = QPushButton("Cancelar")
        styles.style_button(cancelar, "secondary", "fa5s.times")
        cancelar.clicked.connect(self.reject)
        pie.addWidget(cancelar)
        self.btn_importar = QPushButton("Importar solo las válidas")
        styles.style_button(self.btn_importar, "primary", "fa5s.check")
        self.btn_importar.clicked.connect(self._importar)
        self.btn_importar.setEnabled(self._hay_validas_o_dups)
        pie.addWidget(self.btn_importar)
        lay.addLayout(pie)

    def _importar(self) -> None:
        from modules.inventario import excel

        # ponytail: import inline; para miles de filas mover a QThread.
        rep = excel.importar(self.filas, self.politica.currentData(), self.usuario.id)
        partes = [f"{rep['importados']} productos importados correctamente."]
        if rep["sumados"]:
            partes.append(f"{rep['sumados']} sumados a productos existentes.")
        if rep["omitidos_dup"]:
            partes.append(f"{rep['omitidos_dup']} omitidos por estar duplicados.")
        if rep["omitidos_error"]:
            partes.append(f"{rep['omitidos_error']} filas omitidas por errores.")
        QMessageBox.information(self, "Importación finalizada", "\n".join(partes))
        self.accept()
