"""Gráficos del Dashboard, dibujados a mano con QPainter (Fase 2.5).

Sin QtCharts ni matplotlib: control total de la paleta de la app y cero
peso extra en el empaquetado, para dos geometrías simples (dona y barras).

Sin lógica de negocio acá: cada clase recibe listas de dicts YA calculados
por modules/dashboard/repo.py y solo dibuja. Si hace falta un dato nuevo, se
agrega a repo.py, no se calcula en el paintEvent.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from ui import styles


def _clp(valor: int) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def _abreviar_clp(valor: float) -> str:
    """SOLO para las marcas del eje Y de la evolución temporal — es el único
    lugar del Dashboard donde la plata se abrevia (ver prompt de rediseño)."""
    signo = "-" if valor < 0 else ""
    valor = abs(valor)
    if valor >= 1_000_000:
        return f"{signo}${valor / 1_000_000:.1f}".replace(".", ",") + "M"
    if valor >= 1_000:
        return f"{signo}${round(valor / 1000)}k"
    return f"{signo}${valor:.0f}"


def _rect_redondeado_arriba(rect: QRectF, radio: float) -> QPainterPath:
    """Rectángulo con esquinas redondeadas SOLO arriba, cuadrado en la base
    — las barras nacen de una línea de base, no "flotan" (mark spec del
    skill de dataviz: "square at the baseline")."""
    r = max(0.0, min(radio, rect.width() / 2, rect.height()))
    path = QPainterPath()
    if rect.height() <= 0 or rect.width() <= 0:
        return path
    path.moveTo(rect.left(), rect.bottom())
    path.lineTo(rect.left(), rect.top() + r)
    path.quadTo(rect.left(), rect.top(), rect.left() + r, rect.top())
    path.lineTo(rect.right() - r, rect.top())
    path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + r)
    path.lineTo(rect.right(), rect.bottom())
    path.closeSubpath()
    return path


def _fuente(tamano: int, negrita: bool = False) -> QFont:
    f = QFont()
    f.setPixelSize(tamano)
    f.setBold(negrita)
    return f


def _mensaje_vacio(widget: QWidget, painter: QPainter, texto: str) -> None:
    painter.setPen(QColor(styles.TEXT_MUTED))
    painter.setFont(_fuente(13))
    painter.drawText(widget.rect(), Qt.AlignCenter | Qt.TextWordWrap, texto)


# ── Gráfico 1: dona de participación por línea ──────────────────────────────
class DonaParticipacion(QWidget):
    """Recibe [{clave, etiqueta, color, valor}] (orden fijo, ver
    modules/dashboard/page.py LINEAS) y arma sola sus porcentajes/ángulos.

    Clic en un segmento con valor > 0 emite seleccionada(clave). El estado
    de selección lo fija afuera (set_seleccion) — la dona no decide sola qué
    línea está seleccionada, para que quede sincronizada con las tarjetas.
    """

    ANCHO_ANILLO = 26
    CRECE_HOVER = 4
    seleccionada = Signal(str)

    def __init__(self, diametro: int = 180) -> None:
        super().__init__()
        self.setFixedSize(diametro, diametro)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._segmentos: list[dict] = []
        self._total_texto = "$0"
        self._subtitulo_texto = "0 ventas"
        self._hover: str | None = None
        self._seleccion: str | None = None

    def set_datos(self, segmentos: list[dict], total_texto: str, subtitulo_texto: str) -> None:
        self._segmentos = segmentos
        self._total_texto = total_texto
        self._subtitulo_texto = subtitulo_texto
        self._hover = None
        self.update()

    def set_seleccion(self, clave: str | None) -> None:
        self._seleccion = clave
        self.update()

    # ── geometría ────────────────────────────────────────────────────────
    def _rect_anillo(self) -> QRectF:
        m = self.ANCHO_ANILLO / 2 + self.CRECE_HOVER + 2
        return QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)

    def _arcos(self) -> list[tuple[dict, float, float]]:
        """[(segmento, inicio_grados, fin_grados)], sentido horario desde
        las 12, dominio [0,360). Se recalcula al vuelo: son 3 elementos."""
        total = sum(s["valor"] for s in self._segmentos)
        resultado = []
        acumulado = 0.0
        if total > 0:
            for s in self._segmentos:
                if s["valor"] <= 0:
                    continue
                span = s["valor"] / total * 360
                resultado.append((s, acumulado, acumulado + span))
                acumulado += span
        return resultado

    def _segmento_bajo_cursor(self, pos: QPointF) -> dict | None:
        centro = QPointF(self.width() / 2, self.height() / 2)
        dx, dy = pos.x() - centro.x(), pos.y() - centro.y()
        radio = math.hypot(dx, dy)
        radio_medio = self._rect_anillo().width() / 2
        banda = self.ANCHO_ANILLO / 2 + self.CRECE_HOVER
        if not (radio_medio - banda <= radio <= radio_medio + banda):
            return None
        angulo = math.degrees(math.atan2(dx, -dy))
        if angulo < 0:
            angulo += 360
        for seg, ini, fin in self._arcos():
            if ini <= angulo < fin:
                return seg
        return None

    # ── pintado ──────────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        total = sum(s["valor"] for s in self._segmentos)
        rect = self._rect_anillo()

        if total <= 0 or not self._segmentos:
            p.setPen(QPen(QColor(styles.BORDER), self.ANCHO_ANILLO))
            p.drawArc(rect, 0, 360 * 16)
            _mensaje_vacio(self, p, "Sin ventas\nen el período")
            p.end()
            return

        for seg, ini, fin in self._arcos():
            hover = seg["clave"] == self._hover
            r = rect.adjusted(-self.CRECE_HOVER, -self.CRECE_HOVER,
                               self.CRECE_HOVER, self.CRECE_HOVER) if hover else rect
            color = QColor(seg["color"])
            if self._seleccion and seg["clave"] != self._seleccion and not hover:
                color.setAlphaF(0.55)  # las no seleccionadas se atenúan un poco
            pen = QPen(color, self.ANCHO_ANILLO)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            qt_inicio = round((90 - ini) * 16)
            qt_span = round(-(fin - ini) * 16)
            p.drawArc(r, qt_inicio, qt_span)

        p.setPen(QColor(styles.TEXT))
        p.setFont(_fuente(17, negrita=True))
        centro_top = rect.adjusted(0, rect.height() * 0.30, 0, -rect.height() * 0.42)
        p.drawText(centro_top, Qt.AlignCenter, self._total_texto)
        p.setPen(QColor(styles.TEXT_MUTED))
        p.setFont(_fuente(11))
        centro_bottom = rect.adjusted(0, rect.height() * 0.56, 0, -rect.height() * 0.24)
        p.drawText(centro_bottom, Qt.AlignCenter, self._subtitulo_texto)
        p.end()

    # ── interacción ──────────────────────────────────────────────────────
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        seg = self._segmento_bajo_cursor(event.position())
        clave = seg["clave"] if seg else None
        if clave != self._hover:
            self._hover = clave
            self.update()
        if seg:
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{seg['etiqueta']}\n{_clp(seg['valor'])} · {seg.get('pct', 0):.1f}%",
                self,
            )
        else:
            QToolTip.hideText()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = None
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        seg = self._segmento_bajo_cursor(event.position())
        if seg:
            self.seleccionada.emit(seg["clave"])


# ── Gráfico 2: evolución temporal (barras verticales) ───────────────────────
class BarrasEvolucionTemporal(QWidget):
    """Recibe la lista de repo.serie_temporal(): [{clave, etiqueta, ventas,
    n_ventas}]. paso_etiqueta controla cada cuántas barras se pone una
    etiqueta en el eje X (5 para "Mes", 1 para "Semana"/"Año")."""

    ALTO = 220
    MARGEN_IZQ = 56
    MARGEN_INF = 26

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(self.ALTO)
        self.setMouseTracking(True)
        self._serie: list[dict] = []
        self._paso_etiqueta = 1
        self._hover_idx: int | None = None
        self._columnas: list[QRectF] = []
        self._barras: list[QRectF] = []

    def set_datos(self, serie: list[dict], paso_etiqueta: int = 1) -> None:
        self._serie = serie
        self._paso_etiqueta = max(1, paso_etiqueta)
        self._hover_idx = None
        self.update()

    def _area(self) -> QRectF:
        return QRectF(
            self.MARGEN_IZQ, 10,
            max(1, self.width() - self.MARGEN_IZQ - 12),
            max(1, self.height() - 10 - self.MARGEN_INF),
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        if not self._serie or not any(f["ventas"] for f in self._serie):
            _mensaje_vacio(self, p, "Sin ventas en el período.")
            p.end()
            return

        area = self._area()
        maximo = max(f["ventas"] for f in self._serie) or 1
        promedio = sum(f["ventas"] for f in self._serie) / len(self._serie)
        n = len(self._serie)
        ancho_col = area.width() / n

        # eje Y: 0 / medio / máximo, abreviado
        p.setPen(QColor(styles.TEXT_MUTED))
        p.setFont(_fuente(10))
        for frac, valor in ((0.0, 0), (0.5, maximo / 2), (1.0, maximo)):
            y = area.bottom() - area.height() * frac
            p.drawText(QRectF(0, y - 8, self.MARGEN_IZQ - 8, 16),
                       Qt.AlignRight | Qt.AlignVCenter, _abreviar_clp(valor))

        # barras y etiquetas del eje X primero...
        self._columnas = []
        self._barras = []
        for i, f in enumerate(self._serie):
            x = area.left() + i * ancho_col
            columna = QRectF(x, area.top(), ancho_col, area.height())
            self._columnas.append(columna)
            alto_barra = area.height() * (f["ventas"] / maximo) if maximo else 0
            ancho_barra = max(2.0, ancho_col * 0.6)
            rect_barra = QRectF(
                x + (ancho_col - ancho_barra) / 2, area.bottom() - alto_barra,
                ancho_barra, alto_barra,
            )
            self._barras.append(rect_barra)
            color = QColor(styles.ACCENT_HOVER if i == self._hover_idx else styles.ACCENT)
            p.fillPath(_rect_redondeado_arriba(rect_barra, styles.RADIUS_BAR), color)

            if i % self._paso_etiqueta == 0:
                p.setPen(QColor(styles.TEXT_MUTED))
                p.setFont(_fuente(9))
                p.drawText(QRectF(x, area.bottom() + 4, ancho_col, 18),
                           Qt.AlignCenter, f["etiqueta"])

        # ...promedio (línea punteada) AL FINAL, encima de las barras: con
        # una sola barra muy alta (rango corto) tapaba la etiqueta si se
        # dibujaba antes.
        y_prom = area.bottom() - area.height() * min(1.0, promedio / maximo)
        pen_prom = QPen(QColor(styles.TEXT_MUTED))
        pen_prom.setStyle(Qt.DashLine)
        p.setPen(pen_prom)
        p.drawLine(QPointF(area.left(), y_prom), QPointF(area.right(), y_prom))
        etiqueta_prom = f"Promedio {_abreviar_clp(promedio)}"
        ancho_etiqueta = p.fontMetrics().horizontalAdvance(etiqueta_prom) + 12
        rect_etiqueta = QRectF(area.right() - ancho_etiqueta, y_prom - 16, ancho_etiqueta, 15)
        p.fillRect(rect_etiqueta, QColor(styles.BG))
        p.setPen(QColor(styles.TEXT_MUTED))
        p.setFont(_fuente(9))
        p.drawText(rect_etiqueta, Qt.AlignRight | Qt.AlignVCenter, etiqueta_prom)
        p.end()

    def _indice_en(self, pos: QPointF) -> int | None:
        for i, col in enumerate(self._columnas):
            if col.contains(pos):
                return i
        return None

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        idx = self._indice_en(event.position())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        if idx is not None:
            f = self._serie[idx]
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{f['clave']}\n{_clp(f['ventas'])} · {f['n_ventas']} venta(s)",
                self,
            )
        else:
            QToolTip.hideText()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_idx = None
        self.update()


# ── Gráfico 3: barras horizontales de categorías ────────────────────────────
class BarrasCategorias(QWidget):
    """Top 8 categorías de la línea seleccionada. Recibe [{categoria,
    ventas, n_items}] YA ordenado de mayor a menor por repo.por_categoria();
    esta clase solo recorta a 8 (+ "Otras N") y dibuja."""

    MAX_FILAS = 8
    ALTO_FILA = 40
    ANCHO_NOMBRE = 140
    ANCHO_MONTO = 100

    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self._filas: list[dict] = []
        self._color = styles.ACCENT
        self._hover_idx: int | None = None
        self._rects_filas: list[QRectF] = []
        self.setMinimumHeight(80)

    def set_datos(self, categorias: list[dict], color: str) -> None:
        self._color = color
        if len(categorias) > self.MAX_FILAS:
            visibles = categorias[: self.MAX_FILAS - 1]
            resto = categorias[self.MAX_FILAS - 1:]
            otras = {
                "categoria": f"Otras {len(resto)} categorías",
                "ventas": sum(c["ventas"] for c in resto),
                "n_items": sum(c["n_items"] for c in resto),
            }
            self._filas = visibles + [otras]
        else:
            self._filas = list(categorias)
        self._hover_idx = None
        self.setMinimumHeight(max(80, len(self._filas) * self.ALTO_FILA + 8))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        if not self._filas:
            _mensaje_vacio(self, p, "Sin ventas de esta línea en el período.")
            p.end()
            return

        maximo = max(f["ventas"] for f in self._filas) or 1
        n = len(self._filas)
        barra_x0 = self.ANCHO_NOMBRE + 12
        barra_ancho_total = max(1, self.width() - self.ANCHO_NOMBRE - self.ANCHO_MONTO - 24)

        self._rects_filas = []
        for i, f in enumerate(self._filas):
            y = i * self.ALTO_FILA
            self._rects_filas.append(QRectF(0, y, self.width(), self.ALTO_FILA))

            p.setPen(QColor(styles.TEXT))
            p.setFont(_fuente(13))
            metrica = p.fontMetrics()
            texto = metrica.elidedText(f["categoria"], Qt.ElideRight, self.ANCHO_NOMBRE - 8)
            p.drawText(QRectF(0, y, self.ANCHO_NOMBRE, self.ALTO_FILA),
                       Qt.AlignVCenter | Qt.AlignLeft, texto)

            ancho_barra = barra_ancho_total * (f["ventas"] / maximo)
            alto_barra = 18
            rect_barra = QRectF(barra_x0, y + (self.ALTO_FILA - alto_barra) / 2,
                                 ancho_barra, alto_barra)
            color = QColor(self._color)
            opacidad = 1.0 - (i / (n - 1)) * 0.55 if n > 1 else 1.0
            if i == self._hover_idx:
                opacidad = min(1.0, opacidad + 0.2)
            color.setAlphaF(opacidad)
            path = QPainterPath()
            path.addRoundedRect(rect_barra, 4, 4)
            p.fillPath(path, color)

            p.setPen(QColor(styles.TEXT))
            p.setFont(_fuente(13))
            p.drawText(QRectF(self.width() - self.ANCHO_MONTO, y, self.ANCHO_MONTO, self.ALTO_FILA),
                       Qt.AlignVCenter | Qt.AlignRight, _clp(f["ventas"]))
        p.end()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        idx = next((i for i, r in enumerate(self._rects_filas) if r.contains(pos)), None)
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        if idx is not None:
            f = self._filas[idx]
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{f['categoria']}\n{_clp(f['ventas'])} · {f['n_items']} ítem(s)",
                self,
            )
        else:
            QToolTip.hideText()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_idx = None
        self.update()


# ── Gráfico 4: ventas vs margen por línea ───────────────────────────────────
class BarrasVentasMargen(QWidget):
    """3 pares de barras (ventas | margen), una por línea. Recibe
    [{clave, etiqueta, color, ventas, margen, margen_pct}] y un flag
    costos_cargados calculado por quien llama (repo no decide "cargado o
    no", eso es un umbral de presentación)."""

    ALTO = 220

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(self.ALTO)
        self.setMouseTracking(True)
        self._lineas: list[dict] = []
        self._costos_cargados = True
        self._rects: dict[tuple[int, str], QRectF] = {}
        self._hover: tuple[int, str] | None = None

    def set_datos(self, lineas: list[dict], costos_cargados: bool) -> None:
        self._lineas = lineas
        self._costos_cargados = costos_cargados
        self._hover = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # "sin ventas" primero: es el estado más general. Si encima no hay
        # costos cargados pero TAMPOCO hay ventas, el problema real es que
        # no hay datos — no tiene sentido hablar de costos faltantes.
        if not self._lineas or not any(l["ventas"] for l in self._lineas):
            _mensaje_vacio(self, p, "Sin ventas en el período.")
            p.end()
            return
        if not self._costos_cargados:
            p.setPen(QColor(styles.WARN))
            p.setFont(_fuente(13, negrita=True))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "Sin costos cargados: no se puede calcular el margen.")
            p.end()
            return

        pie_alto = 40
        area_alto = self.height() - pie_alto
        maximo = max(max(l["ventas"], max(0, l["margen"])) for l in self._lineas) or 1
        n = len(self._lineas)
        ancho_grupo = self.width() / n

        self._rects = {}
        for i, l in enumerate(self._lineas):
            cx = i * ancho_grupo + ancho_grupo / 2
            ancho_barra = min(40, ancho_grupo * 0.22)
            gap = 6

            color_ventas = QColor(l["color"])
            color_ventas.setAlphaF(0.35 if (i, "ventas") != self._hover else 0.5)
            alto_v = area_alto * (l["ventas"] / maximo)
            rect_v = QRectF(cx - ancho_barra - gap / 2, area_alto - alto_v, ancho_barra, alto_v)
            self._rects[(i, "ventas")] = rect_v
            p.fillPath(_rect_redondeado_arriba(rect_v, styles.RADIUS_BAR), color_ventas)

            color_margen = QColor(l["color"])
            if (i, "margen") == self._hover:
                color_margen = color_margen.lighter(115)
            alto_m = area_alto * (max(0, l["margen"]) / maximo)
            rect_m = QRectF(cx + gap / 2, area_alto - alto_m, ancho_barra, alto_m)
            self._rects[(i, "margen")] = rect_m
            p.fillPath(_rect_redondeado_arriba(rect_m, styles.RADIUS_BAR), color_margen)

            p.setPen(QColor(styles.TEXT))
            p.setFont(_fuente(13, negrita=True))
            p.drawText(QRectF(i * ancho_grupo, area_alto + 2, ancho_grupo, 18),
                       Qt.AlignCenter, l["etiqueta"])
            p.setPen(QColor(styles.TEXT_MUTED))
            p.setFont(_fuente(12))
            etiqueta_margen = (
                f"{l['margen_pct']:.1f}% margen" if l["margen"] >= 0 else "margen negativo"
            )
            p.drawText(QRectF(i * ancho_grupo, area_alto + 20, ancho_grupo, 16),
                       Qt.AlignCenter, etiqueta_margen)
        p.end()

    def _clave_en(self, pos: QPointF) -> tuple[int, str] | None:
        for clave, rect in self._rects.items():
            if rect.contains(pos):
                return clave
        return None

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        clave = self._clave_en(event.position())
        if clave != self._hover:
            self._hover = clave
            self.update()
        if clave:
            i, tipo = clave
            l = self._lineas[i]
            valor = l["ventas"] if tipo == "ventas" else l["margen"]
            etiqueta = "Ventas" if tipo == "ventas" else "Margen"
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{l['etiqueta']} · {etiqueta}\n{_clp(valor)}",
                self,
            )
        else:
            QToolTip.hideText()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = None
        self.update()
