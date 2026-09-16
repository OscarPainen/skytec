"""Módulo Dashboard — panel de las 3 líneas de negocio (Fase 2 / 2.5).

Todo el dato sale de modules/dashboard/repo.py (que a su vez lee de
v_operaciones). Nada de SQL acá. Los gráficos viven en
modules/dashboard/charts.py (QPainter puro, sin QtCharts/matplotlib); este
archivo es layout + estado + conexión con repo.py.

Un solo estado de selección de línea de negocio para toda la página
(self._linea_seleccionada), sincronizado entre las tarjetas, la dona y la
sección de categorías — nunca tres estados independientes.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Usuario
from modules.dashboard import repo
from modules.dashboard.charts import (
    BarrasCategorias,
    BarrasEvolucionTemporal,
    BarrasVentasMargen,
    DonaParticipacion,
)
from ui import styles

# (clave interna, etiqueta de UI, color) — un solo lugar de definición, mismo
# orden y mismo color en tarjetas, dona, barras y tablas de todo el módulo.
LINEAS = [
    ("reparacion", "Reparación", styles.LINEA_REPARACION),
    ("tecnologia", "Tecnología", styles.LINEA_TECNOLOGIA),
    ("suplemento", "Suplementos", styles.LINEA_SUPLEMENTO),
]

PERIODOS = [("Semana", "semana"), ("Mes", "mes"), ("Año", "año"), ("Todo", "todo")]

_ESTILO_SIN_CAJA = f"background:transparent; border:none; color:{styles.TEXT};"


def _clp(valor: int) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def _etiqueta_linea(linea: str) -> str:
    return next(e for c, e, _ in LINEAS if c == linea)


def _color_linea(linea: str) -> str:
    return next(c for cl, _e, c in LINEAS if cl == linea)


def _titulo_seccion(texto: str) -> QLabel:
    """Título de sección — TODOS al mismo nivel (16px/600, texto primario).
    Antes 'Categorías — X' usaba objectName Subtitle (gris, texto secundario)
    mientras el resto usaba texto primario: mismo nivel, dos estilos. Un
    título que necesita verse "menos" no es un título de sección."""
    lbl = QLabel(texto)
    lbl.setStyleSheet(
        f"background:transparent; border:none; color:{styles.TEXT}; "
        f"font-size:16px; font-weight:600; margin-top:4px;"
    )
    return lbl


# ── Encabezado de tabla con alineación por columna ──────────────────────────
class _HeaderAlineado(QHeaderView):
    """Qt solo permite UN setDefaultAlignment para toda la fila de
    encabezados; acá cada columna necesita su propia alineación (nombre a la
    izquierda, montos a la derecha, igual que sus datos), así que se pinta
    el texto a mano en vez de dejarlo centrado por defecto."""

    def __init__(self, alineaciones: list[Qt.AlignmentFlag], parent=None) -> None:
        super().__init__(Qt.Horizontal, parent)
        self._alineaciones = alineaciones
        self.setSectionsClickable(False)
        self.setFixedHeight(36)

    def paintSection(self, painter: QPainter, rect, logical_index: int) -> None:  # noqa: N802
        painter.save()
        painter.fillRect(rect, QColor(styles.SURFACE))
        painter.setPen(QPen(QColor(styles.BORDER)))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.setPen(QColor(styles.TEXT_MUTED))
        fuente = painter.font()
        fuente.setPixelSize(12)
        fuente.setBold(True)
        painter.setFont(fuente)
        alineacion = self._alineaciones[logical_index] if logical_index < len(self._alineaciones) else Qt.AlignLeft
        texto = self.model().headerData(logical_index, Qt.Horizontal) if self.model() else ""
        margen = 12
        painter.drawText(rect.adjusted(margen, 0, -margen, 0),
                          alineacion | Qt.AlignVCenter, str(texto))
        painter.restore()


# ── Tabla que crece con su contenido: una sola barra de scroll (la de la
# página), sin altura fija, con "Ver todas" en vez de paginación ───────────
class _TablaExpandible(QWidget):
    FILAS_VISIBLES = 8
    ALTO_FILA = 40

    def __init__(self, columnas: list[tuple[str, Qt.AlignmentFlag]]) -> None:
        super().__init__()
        self._alineaciones = [a for _t, a in columnas]
        self._filas: list[list[str]] = []
        self._expandido = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(styles.S1)

        self.tabla = QTableWidget(0, len(columnas))
        self.tabla.setHorizontalHeaderLabels([t for t, _a in columnas])
        self.tabla.setHorizontalHeader(_HeaderAlineado(self._alineaciones, self.tabla))
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(self.ALTO_FILA)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setSelectionMode(QTableWidget.NoSelection)
        self.tabla.setShowGrid(False)
        self.tabla.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tabla.setFrameShape(QFrame.NoFrame)
        header = self.tabla.horizontalHeader()
        for i, (_t, alineacion) in enumerate(columnas):
            modo = QHeaderView.Stretch if alineacion == Qt.AlignLeft else QHeaderView.ResizeToContents
            header.setSectionResizeMode(i, modo)
        lay.addWidget(self.tabla)

        self.vacio = QLabel("")
        self.vacio.setAlignment(Qt.AlignCenter)
        self.vacio.setFixedHeight(80)
        self.vacio.setStyleSheet(
            f"background:transparent; border:none; color:{styles.TEXT_MUTED}; font-size:13px;"
        )
        self.vacio.hide()
        lay.addWidget(self.vacio)

        self.btn_ver_todas = QPushButton()
        styles.style_button(self.btn_ver_todas, "secondary")
        self.btn_ver_todas.clicked.connect(self._expandir)
        self.btn_ver_todas.hide()
        lay.addWidget(self.btn_ver_todas)

    def set_filas(self, filas: list[list[str]], mensaje_vacio: str) -> None:
        self._filas = filas
        self._expandido = False
        self._refrescar(mensaje_vacio)

    def _refrescar(self, mensaje_vacio: str) -> None:
        mostrar = (
            self._filas if (self._expandido or len(self._filas) <= self.FILAS_VISIBLES)
            else self._filas[: self.FILAS_VISIBLES]
        )
        self.tabla.setRowCount(0)
        for fila in mostrar:
            r = self.tabla.rowCount()
            self.tabla.insertRow(r)
            for c, valor in enumerate(fila):
                item = QTableWidgetItem(valor)
                alineacion = self._alineaciones[c]
                item.setTextAlignment(int(alineacion | Qt.AlignVCenter))
                self.tabla.setItem(r, c, item)

        hay_datos = bool(self._filas)
        self.tabla.setVisible(hay_datos)
        self.vacio.setVisible(not hay_datos)
        self.vacio.setText(mensaje_vacio)

        alto_header = self.tabla.horizontalHeader().height()
        self.tabla.setFixedHeight(alto_header + len(mostrar) * self.ALTO_FILA + 2)

        restantes = len(self._filas) - self.FILAS_VISIBLES
        self.btn_ver_todas.setVisible(hay_datos and restantes > 0 and not self._expandido)
        if restantes > 0:
            self.btn_ver_todas.setText(f"Ver todas ({len(self._filas)})")

    def _expandir(self) -> None:
        self._expandido = True
        self._refrescar(self.vacio.text())


# ── Tarjeta de KPI ───────────────────────────────────────────────────────────
class _KpiTile(QFrame):
    """Anatomía fija: etiqueta (12/500, secundario) · valor (28/700,
    primario) · [línea informativa opcional] · [comparación opcional].
    El ÚNICO elemento con fondo y borde es la tarjeta — todo lo de adentro
    es transparente y sin borde, para que no queden cajas dentro de cajas."""

    def __init__(self, etiqueta: str) -> None:
        super().__init__()
        self.setObjectName("tarjetaKpi")
        self.setStyleSheet(
            f"#tarjetaKpi {{ background:{styles.BG}; border:1px solid {styles.BORDER}; "
            f"border-radius:12px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(styles.CARD_PADDING, styles.CARD_PADDING,
                                styles.CARD_PADDING, styles.CARD_PADDING)
        lay.setSpacing(styles.S1)

        self.lbl_etiqueta = QLabel(etiqueta)
        self.lbl_etiqueta.setStyleSheet(
            f"background:transparent; border:none; color:{styles.TEXT_MUTED}; "
            f"font-size:12px; font-weight:500;"
        )
        lay.addWidget(self.lbl_etiqueta)

        self.lbl_valor = QLabel("—")
        self.lbl_valor.setWordWrap(True)
        self.lbl_valor.setStyleSheet(
            f"background:transparent; border:none; color:{styles.TEXT}; "
            f"font-size:28px; font-weight:700;"
        )
        lay.addWidget(self.lbl_valor)

        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet(
            f"background:transparent; border:none; color:{styles.TEXT_MUTED}; font-size:12px;"
        )
        self.lbl_info.hide()
        lay.addWidget(self.lbl_info)

        self.lbl_delta = QLabel("")
        self.lbl_delta.setStyleSheet("background:transparent; border:none; font-size:12px; font-weight:600;")
        self.lbl_delta.hide()
        lay.addWidget(self.lbl_delta)

        lay.addStretch()

    def set_valor(self, texto: str) -> None:
        self.lbl_valor.setText(texto)

    def set_info(self, texto: str, advertencia: bool = False) -> None:
        """Línea informativa bajo el valor — SIN punto medio pegado al monto
        (Problema 2). advertencia=True para "sin costos cargados"."""
        if not texto:
            self.lbl_info.hide()
            return
        color = styles.WARN if advertencia else styles.TEXT_MUTED
        peso = 700 if advertencia else 400
        self.lbl_info.setStyleSheet(
            f"background:transparent; border:none; color:{color}; "
            f"font-size:12px; font-weight:{peso};"
        )
        self.lbl_info.setText(texto)
        self.lbl_info.show()

    def set_delta(self, pct: float | None) -> None:
        """None = esta tarjeta no muestra nada acá. La página decide si hace
        falta un único aviso de "sin comparación" debajo de toda la fila —
        no cuatro mensajes repetidos (Problema 3)."""
        if pct is None:
            self.lbl_delta.hide()
            return
        flecha = "▲" if pct >= 0 else "▼"
        color = styles.OK if pct >= 0 else styles.DANGER
        self.lbl_delta.setStyleSheet(
            f"background:transparent; border:none; color:{color}; "
            f"font-size:12px; font-weight:600;"
        )
        self.lbl_delta.setText(f"{flecha} {abs(pct):.1f}% vs período anterior")
        self.lbl_delta.show()


# ── Tarjeta de línea de negocio ──────────────────────────────────────────────
class _LineaCard(QFrame):
    clicked = Signal(str)

    def __init__(self, linea: str, etiqueta: str, color: str) -> None:
        super().__init__()
        self.linea = linea
        self._color = color
        self.setCursor(Qt.PointingHandCursor)
        self._seleccionada = False
        self._refrescar_estilo()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(styles.CARD_PADDING, styles.CARD_PADDING,
                                styles.CARD_PADDING, styles.CARD_PADDING)
        lay.setSpacing(styles.S1)

        cab = QHBoxLayout()
        cab.setSpacing(6)
        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(f"background:{color}; border-radius:5px;")
        cab.addWidget(swatch)
        nombre = QLabel(etiqueta)
        nombre.setStyleSheet(f"background:transparent; border:none; color:{styles.TEXT}; font-weight:600;")
        cab.addWidget(nombre)
        cab.addStretch()
        lay.addLayout(cab)

        self.monto = QLabel("$0")
        self.monto.setStyleSheet(
            f"background:transparent; border:none; color:{styles.TEXT}; "
            f"font-size:20px; font-weight:700;"
        )
        lay.addWidget(self.monto)

        self.meta = QLabel("")
        self.meta.setStyleSheet(f"background:transparent; border:none; color:{styles.TEXT_MUTED}; font-size:12px;")
        lay.addWidget(self.meta)

        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(6)
        self.barra.setStyleSheet(
            f"QProgressBar {{ background:{styles.BORDER}; border:none; border-radius:3px; }}"
            f"QProgressBar::chunk {{ background:{color}; border-radius:3px; }}"
        )
        lay.addWidget(self.barra)

    def set_datos(self, ventas: int, participacion_pct: float, n_items: int) -> None:
        self.monto.setText(_clp(ventas))
        self.meta.setText(f"{participacion_pct:.1f}% del total · {n_items} ítems")
        self.barra.setValue(round(participacion_pct))

    def set_seleccionada(self, valor: bool) -> None:
        self._seleccionada = valor
        self._refrescar_estilo()

    def _refrescar_estilo(self) -> None:
        # Seleccionada: borde de 2px DEL COLOR DE SU PROPIA LÍNEA + fondo al
        # 6% de opacidad de ese mismo color — nunca un color fijo (verde)
        # para todas, porque entraría en conflicto con la línea Tecnología
        # (Problema 6 del rediseño).
        c = QColor(self._color)
        if self._seleccionada:
            fondo = f"rgba({c.red()},{c.green()},{c.blue()},0.06)"
            borde, ancho = self._color, 2
        else:
            fondo = styles.BG
            borde, ancho = styles.BORDER, 1
        self.setStyleSheet(
            f"_LineaCard {{ background:{fondo}; border:{ancho}px solid {borde}; "
            f"border-radius:{styles.RADIUS}px; }}"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit(self.linea)


class DashboardPage(QWidget):
    def __init__(self, usuario: Usuario) -> None:
        super().__init__()
        self.usuario = usuario
        self._linea_seleccionada = "reparacion"
        self._desde = self._hasta = ""

        raiz_ext = QVBoxLayout(self)
        raiz_ext.setContentsMargins(0, 0, 0, 0)
        raiz_ext.setSpacing(0)

        # Un solo QScrollArea para toda la página (Problema 4 / layout final):
        # nunca una tabla o gráfico con su propio scroll anidado adentro.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        contenido = QWidget()
        raiz = QVBoxLayout(contenido)
        raiz.setContentsMargins(styles.S4, styles.S4, styles.S4, styles.S4)
        raiz.setSpacing(styles.S4)  # 32px entre secciones
        scroll.setWidget(contenido)
        raiz_ext.addWidget(scroll)

        # ── 1. Encabezado ─────────────────────────────────────────────────
        cab = QHBoxLayout()
        cab.setSpacing(styles.S1)
        titulo = QLabel("Dashboard")
        titulo.setObjectName("Title")
        cab.addWidget(titulo)
        cab.addStretch()
        self.periodo = QComboBox()
        for etiqueta, valor in PERIODOS:
            self.periodo.addItem(etiqueta, valor)
        self.periodo.setCurrentIndex(1)  # "Mes" por defecto
        self.periodo.currentIndexChanged.connect(self.recargar)
        cab.addWidget(self.periodo)
        raiz.addLayout(cab)

        # ── 2. KPIs + aviso único de "sin comparación" ──────────────────
        bloque_kpi = QVBoxLayout()
        bloque_kpi.setSpacing(styles.S1)
        fila_kpi = QHBoxLayout()
        fila_kpi.setSpacing(styles.S2)  # 16px entre tarjetas
        self.kpi_ventas = _KpiTile("Ventas")
        self.kpi_margen = _KpiTile("Margen bruto")
        self.kpi_n_ventas = _KpiTile("N° de ventas")
        self.kpi_ticket = _KpiTile("Ticket promedio")
        for k in (self.kpi_ventas, self.kpi_margen, self.kpi_n_ventas, self.kpi_ticket):
            fila_kpi.addWidget(k)
        bloque_kpi.addLayout(fila_kpi)
        self.aviso_sin_comparacion = QLabel("Sin datos del período anterior para comparar.")
        self.aviso_sin_comparacion.setStyleSheet(
            f"background:transparent; border:none; color:{styles.TEXT_MUTED}; font-size:12px;"
        )
        self.aviso_sin_comparacion.hide()
        bloque_kpi.addWidget(self.aviso_sin_comparacion)
        raiz.addLayout(bloque_kpi)

        # ── 3. Evolución temporal ────────────────────────────────────────
        raiz.addWidget(_titulo_seccion("Evolución de ventas"))
        self.evolucion = BarrasEvolucionTemporal()
        raiz.addWidget(self.evolucion)

        # ── 4. Ventas por línea de negocio ───────────────────────────────
        raiz.addWidget(_titulo_seccion("Ventas por línea de negocio"))
        fila_lineas = QHBoxLayout()
        fila_lineas.setSpacing(styles.S2)
        self.cards: dict[str, _LineaCard] = {}
        for clave, etiqueta, color in LINEAS:
            card = _LineaCard(clave, etiqueta, color)
            card.clicked.connect(self._seleccionar_linea)
            self.cards[clave] = card
            fila_lineas.addWidget(card)
        self.cards[self._linea_seleccionada].set_seleccionada(True)
        raiz.addLayout(fila_lineas)

        # ── 5. Dona de participación (40%) + Ventas vs margen (60%) ──────
        fila_graficos = QHBoxLayout()
        fila_graficos.setSpacing(styles.S2)

        col_dona = QVBoxLayout()
        col_dona.setSpacing(styles.S2)
        col_dona.addWidget(_titulo_seccion("Participación por línea"))
        fila_dona = QHBoxLayout()
        fila_dona.setSpacing(styles.S2)
        self.dona = DonaParticipacion()
        self.dona.seleccionada.connect(self._seleccionar_linea)
        fila_dona.addWidget(self.dona)
        self.leyenda_dona: dict[str, QLabel] = {}
        col_leyenda = QVBoxLayout()
        col_leyenda.setSpacing(8)
        for clave, etiqueta, color in LINEAS:
            fila_leyenda = QHBoxLayout()
            fila_leyenda.setSpacing(6)
            punto = QLabel()
            punto.setFixedSize(9, 9)
            punto.setStyleSheet(f"background:{color}; border-radius:4px; margin-top:2px;")
            fila_leyenda.addWidget(punto, 0, Qt.AlignTop)
            texto = QLabel(f"{etiqueta}\n$0 · 0.0%")
            texto.setStyleSheet(f"background:transparent; border:none; color:{styles.TEXT}; font-size:12px;")
            self.leyenda_dona[clave] = texto
            fila_leyenda.addWidget(texto)
            col_leyenda.addLayout(fila_leyenda)
        col_leyenda.addStretch()
        fila_dona.addLayout(col_leyenda, 1)
        col_dona.addLayout(fila_dona)
        fila_graficos.addLayout(col_dona, 4)

        col_margen = QVBoxLayout()
        col_margen.setSpacing(styles.S2)
        col_margen.addWidget(_titulo_seccion("Ventas vs. margen por línea"))
        self.ventas_margen = BarrasVentasMargen()
        col_margen.addWidget(self.ventas_margen)
        fila_graficos.addLayout(col_margen, 6)

        raiz.addLayout(fila_graficos)

        # ── 6. Categorías de la línea seleccionada ───────────────────────
        self.titulo_categorias = _titulo_seccion("")
        raiz.addWidget(self.titulo_categorias)
        self.barras_categorias = BarrasCategorias()
        raiz.addWidget(self.barras_categorias)
        self.tabla_categorias = _TablaExpandible([
            ("Categoría", Qt.AlignLeft), ("Ventas", Qt.AlignRight), ("N° de ítems", Qt.AlignRight),
        ])
        raiz.addWidget(self.tabla_categorias)

        # ── 7. Corte por caja ─────────────────────────────────────────────
        raiz.addWidget(_titulo_seccion("Corte por caja"))
        self.tabla_cajas = _TablaExpandible([
            ("Caja", Qt.AlignLeft), ("Ventas", Qt.AlignRight), ("N° de ventas", Qt.AlignRight),
        ])
        raiz.addWidget(self.tabla_cajas)

        raiz.addStretch()
        self.recargar()

    # ── Datos ─────────────────────────────────────────────────────────────
    def _seleccionar_linea(self, linea: str) -> None:
        self._linea_seleccionada = linea
        for clave, card in self.cards.items():
            card.set_seleccionada(clave == linea)
        self.dona.set_seleccion(linea)
        self._recargar_categorias()

    def recargar(self) -> None:
        tipo = self.periodo.currentData()
        desde, hasta = repo.rango_periodo(tipo)
        rango_anterior = repo.rango_periodo_anterior(tipo, desde, hasta)
        self._desde, self._hasta = desde, hasta

        actual = repo.resumen_periodo(desde, hasta)
        previo = repo.resumen_periodo(*rango_anterior) if rango_anterior else None

        self.kpi_ventas.set_valor(_clp(actual["ventas"]))
        self.kpi_n_ventas.set_valor(str(actual["n_ventas"]))
        self.kpi_ticket.set_valor(_clp(actual["ticket_promedio"]))
        self.kpi_margen.set_valor(_clp(actual["margen"]))
        if actual["margen_pct"] is None:
            self.kpi_margen.set_info("Sin costos cargados", advertencia=True)
        else:
            self.kpi_margen.set_info(f"{actual['margen_pct']:.1f}% sobre ventas")

        deltas = [None, None, None, None]
        if previo:
            deltas[0] = repo.variacion_pct(actual["ventas"], previo["ventas"])
            deltas[2] = repo.variacion_pct(actual["n_ventas"], previo["n_ventas"])
            deltas[3] = repo.variacion_pct(actual["ticket_promedio"], previo["ticket_promedio"])
            # Margen compara el % (no el $): un margen que sube en plata pero
            # baja en porcentaje es una alerta, no una mejora. Si a cualquiera
            # de los dos períodos le faltan costos, no hay con qué comparar.
            if actual["margen_pct"] is not None and previo["margen_pct"] is not None:
                deltas[1] = repo.variacion_pct(actual["margen_pct"], previo["margen_pct"])
        self.kpi_ventas.set_delta(deltas[0])
        self.kpi_margen.set_delta(deltas[1])
        self.kpi_n_ventas.set_delta(deltas[2])
        self.kpi_ticket.set_delta(deltas[3])
        self.aviso_sin_comparacion.setVisible(all(d is None for d in deltas))

        lineas = repo.por_linea_negocio(desde, hasta)
        por_clave = {l["linea_negocio"]: l for l in lineas}
        for clave, card in self.cards.items():
            d = por_clave[clave]
            card.set_datos(d["ventas"], d["participacion_pct"], d["n_items"])

        segmentos_dona = [
            {"clave": clave, "etiqueta": etiqueta, "color": color,
             "valor": por_clave[clave]["ventas"], "pct": por_clave[clave]["participacion_pct"]}
            for clave, etiqueta, color in LINEAS
        ]
        self.dona.set_datos(segmentos_dona, _clp(actual["ventas"]), f"{actual['n_ventas']} ventas")
        self.dona.set_seleccion(self._linea_seleccionada)
        for clave, etiqueta, _color in LINEAS:
            d = por_clave[clave]
            self.leyenda_dona[clave].setText(
                f"{etiqueta}\n{_clp(d['ventas'])} · {d['participacion_pct']:.1f}%"
            )

        self.ventas_margen.set_datos(
            [{"clave": clave, "etiqueta": etiqueta, "color": color,
              "ventas": por_clave[clave]["ventas"], "margen": por_clave[clave]["margen"],
              "margen_pct": round(por_clave[clave]["margen"] / por_clave[clave]["ventas"] * 100, 1)
              if por_clave[clave]["ventas"] else 0}
             for clave, etiqueta, color in LINEAS],
            costos_cargados=bool(actual["costo"]),
        )

        granularidad = repo.granularidad_de(tipo)
        serie = repo.serie_temporal(desde, hasta, granularidad)
        paso_etiqueta = 5 if (tipo == "mes" and granularidad == "dia") else 1
        self.evolucion.set_datos(serie, paso_etiqueta)

        self._recargar_categorias()

        cajas = repo.por_caja(desde, hasta)
        self.tabla_cajas.set_filas(
            [[c["caja"] or "—", _clp(c["ventas"]), str(c["n_ventas"])] for c in cajas],
            "Sin ventas registradas en ninguna caja en este período.",
        )

    def _recargar_categorias(self) -> None:
        etiqueta = _etiqueta_linea(self._linea_seleccionada)
        self.titulo_categorias.setText(f"Categorías — {etiqueta}")
        color = _color_linea(self._linea_seleccionada)
        categorias = repo.por_categoria(self._linea_seleccionada, self._desde, self._hasta)
        self.barras_categorias.set_datos(categorias, color)
        self.tabla_categorias.set_filas(
            [[c["categoria"], _clp(c["ventas"]), str(c["n_items"])] for c in categorias],
            f"Sin ventas de {etiqueta} en el período.",
        )
