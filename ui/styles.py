"""Sistema de diseño centralizado de Skytec.

Un solo lugar para colores, espaciado y tipografía. Paleta neutra + un único
acento. Todo el resto de la UI referencia estas constantes o el stylesheet.
Grilla de 8px.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIntValidator, QPalette
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

try:  # qtawesome opcional: sin él, los botones quedan sin ícono pero funcionan.
    import qtawesome as qta
except Exception:  # pragma: no cover
    qta = None

# ── Paleta ────────────────────────────────────────────────────────────────
ACCENT = "#2563EB"        # único color de acento (azul "sky")
ACCENT_HOVER = "#1D4ED8"
ACCENT_PRESSED = "#1E40AF"  # presionado (un paso más oscuro que hover)
ACCENT_SOFT = "#EFF4FE"   # fondo tenue del acento (selección, chips)

BG = "#FFFFFF"            # fondo de contenido
BG_SIDEBAR = "#0F172A"    # navegación lateral (slate oscuro)
SURFACE = "#F8FAFC"       # tarjetas, campos
BORDER = "#E2E8F0"

TEXT = "#0F172A"          # texto principal
TEXT_MUTED = "#64748B"    # secundario / placeholders
TEXT_ON_DARK = "#E2E8F0"  # texto sobre sidebar
TEXT_ON_ACCENT = "#FFFFFF"

OK = "#16A34A"
WARN = "#D97706"          # stock bajo, vencidos
DANGER = "#DC2626"
DANGER_SOFT = "rgba(220,38,38,0.08)"   # hover destructivo (8%)
DANGER_SOFT2 = "rgba(220,38,38,0.16)"  # pressed destructivo

# ── Métrica (8px) ─────────────────────────────────────────────────────────
S1, S2, S3, S4 = 8, 16, 24, 32
RADIUS = 8
FONT_FAMILY = "Inter, 'Segoe UI', system-ui, sans-serif"


@lru_cache(maxsize=None)
def _chevron_url() -> str:
    """Renderiza un chevron de qtawesome a PNG para usarlo como flecha del combo.

    QSS solo acepta rutas de imagen (no QIcon), por eso lo cacheamos en disco.
    Requiere una QApplication viva (siempre lo está al construir ventanas).
    """
    if qta is None:
        return ""
    try:
        cache = Path(__file__).resolve().parent.parent / "assets" / "_cache"
        cache.mkdir(parents=True, exist_ok=True)
        ruta = cache / "chevron_down.png"
        qta.icon("fa5s.chevron-down", color=TEXT_MUTED).pixmap(QSize(14, 14)).save(str(ruta))
        return ruta.as_posix()
    except Exception:  # pragma: no cover
        return ""


def build_stylesheet() -> str:
    """QSS global de la aplicación."""
    chevron = _chevron_url()
    flecha = (
        f"QComboBox::down-arrow {{ image: url({chevron}); width: 14px; height: 14px; }}"
        if chevron else ""
    )
    return f"""
    * {{
        font-family: {FONT_FAMILY};
        font-size: 14px;
        color: {TEXT};
    }}
    QMainWindow, QDialog, QWidget#Content {{ background: {BG}; }}

    /* Áreas de contenido: el scroll y su contenedor heredan el fondo claro.
       Sin esto, el viewport/contenedor caen a un fondo oscuro por defecto y
       rompen la coherencia (catálogo de Inventario, formulario de Ajustes). */
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}

    /* Navegación lateral */
    QWidget#Sidebar {{ background: {BG_SIDEBAR}; }}
    QLabel#Brand {{
        color: {TEXT_ON_ACCENT}; font-size: 20px; font-weight: 700;
        padding: {S3}px {S2}px {S2}px {S2}px;
    }}
    QPushButton#NavButton {{
        background: transparent; color: {TEXT_ON_DARK};
        text-align: left; border: none; border-radius: {RADIUS}px;
        padding: {S1 + 2}px {S2}px; margin: 2px {S1}px; font-size: 15px;
    }}
    QPushButton#NavButton:hover {{ background: rgba(255,255,255,0.06); }}
    QPushButton#NavButton:checked {{
        background: {ACCENT}; color: {TEXT_ON_ACCENT}; font-weight: 600;
    }}

    /* Botones — 3 variantes reutilizables (aplicar con ui.styles.style_button).
       Nota: Qt QSS no soporta transition/box-shadow/cursor. Los cambios de
       estado usan pseudo-estados :hover/:pressed; la sombra sutil del primario
       se aplica con QGraphicsDropShadowEffect y el cursor con setCursor(), todo
       dentro del helper para no repetir código por botón. */

    /* PRIMARIO (variante por defecto de QPushButton) */
    QPushButton {{
        background: {ACCENT}; color: {TEXT_ON_ACCENT}; border: none;
        border-radius: {RADIUS}px; padding: 10px 18px; font-weight: 600;
    }}
    QPushButton:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton:pressed {{ background: {ACCENT_PRESSED}; }}
    QPushButton:disabled {{ background: {BORDER}; color: {TEXT_MUTED}; }}

    /* SECUNDARIO */
    QPushButton#Secondary {{
        background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
        font-weight: 500;
    }}
    QPushButton#Secondary:hover {{ background: {ACCENT_SOFT}; border: 1px solid {ACCENT}; }}
    QPushButton#Secondary:pressed {{ background: {BORDER}; }}
    QPushButton#Secondary:disabled {{ background: {BG}; color: {TEXT_MUTED}; border: 1px solid {BORDER}; }}

    /* DESTRUCTIVO / MERMA */
    QPushButton#Danger {{
        background: transparent; color: {DANGER}; border: 1px solid {DANGER};
        border-radius: {RADIUS}px; padding: 10px 18px; font-weight: 600;
    }}
    QPushButton#Danger:hover {{ background: {DANGER_SOFT}; }}
    QPushButton#Danger:pressed {{ background: {DANGER_SOFT2}; }}
    QPushButton#Danger:disabled {{ background: transparent; color: {TEXT_MUTED}; border: 1px solid {BORDER}; }}

    /* ÍCONO COMPACTO (acciones por fila en tablas/catálogo) */
    QPushButton#IconButton {{
        background: transparent; border: none; border-radius: {RADIUS}px;
        padding: 6px; min-width: 32px; min-height: 32px; font-weight: 500;
    }}
    QPushButton#IconButton:hover {{ background: {ACCENT_SOFT}; }}
    QPushButton#IconButton:pressed {{ background: {BORDER}; }}

    /* ÍCONO destructivo (quitar ítem del carrito): danger al hover */
    QPushButton#IconDanger {{
        background: transparent; border: none; border-radius: {RADIUS}px;
        min-width: 32px; min-height: 32px; padding: 6px;
    }}
    QPushButton#IconDanger:hover {{ background: {DANGER_SOFT}; }}
    QPushButton#IconDanger:pressed {{ background: {DANGER_SOFT2}; }}

    /* Campos: mismo alto (~40px), borde, radio y foco unificados.
       Ningún nativo queda "por defecto". */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
        background: {BG}; color: {TEXT};
        border: 1px solid {BORDER}; border-radius: {RADIUS}px;
        min-height: 24px; padding: 6px 12px;
        selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
    }}
    QTextEdit {{
        background: {BG}; color: {TEXT}; border: 1px solid {BORDER};
        border-radius: {RADIUS}px; padding: 8px 12px;
        selection-background-color: {ACCENT_SOFT};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QDateEdit:focus, QTextEdit:focus {{ border: 1px solid {ACCENT}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        background: {SURFACE}; color: {TEXT_MUTED};
    }}

    /* Spinner nativo oculto (Opción B: campo numérico limpio, se escribe directo) */
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        width: 0; height: 0; border: none;
    }}

    /* ComboBox: chevron limpio + popup estilizado (sin gris nativo de Windows) */
    QComboBox::drop-down {{ border: none; width: 26px; }}
    {flecha}
    QComboBox QAbstractItemView {{
        background: {BG}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
        padding: 4px; outline: none;
        selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 30px; padding: 4px 8px; border-radius: 6px;
    }}

    /* Tablas: headers suaves, filas con separador tenue, sin grid duro */
    QTableWidget, QTableView {{
        background: {BG}; border: none; gridline-color: transparent;
        selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
    }}
    QTableWidget::item, QTableView::item {{
        padding: 6px 8px; border-bottom: 1px solid {BORDER};
    }}
    QTableWidget::item:hover {{ background: {SURFACE}; }}
    QTableWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
    QHeaderView::section {{
        background: {SURFACE}; color: {TEXT_MUTED};
        border: none; border-bottom: 1px solid {BORDER};
        padding: 8px; font-weight: 600;
    }}
    QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

    /* Listas: sin recuadro duro, ítems con padding cómodo integrados al fondo */
    QListWidget {{ background: transparent; border: none; outline: none; }}
    QListWidget::item {{
        padding: 12px; border-radius: {RADIUS}px; margin: 2px 0; color: {TEXT};
    }}
    QListWidget::item:hover {{ background: {SURFACE}; }}
    QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}

    /* Checkbox custom (nada de indicador nativo) */
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px; border: 1px solid {BORDER};
        border-radius: 5px; background: {BG};
    }}
    QCheckBox::indicator:hover {{ border: 1px solid {ACCENT}; }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}

    /* Barras de scroll discretas */
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 30px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    /* Stepper de cantidad [−] N [+] (ver QuantityStepper) */
    QPushButton#StepperBtn {{
        background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
        border-radius: {RADIUS}px; min-width: 36px; max-width: 36px;
        min-height: 36px; padding: 0;
    }}
    QPushButton#StepperBtn:hover {{ background: {ACCENT_SOFT}; border: 1px solid {ACCENT}; }}
    QPushButton#StepperBtn:pressed {{ background: {BORDER}; }}
    QPushButton#StepperBtn:disabled {{ background: {BG}; color: {TEXT_MUTED}; border: 1px solid {BORDER}; }}
    QLineEdit#StepperField {{ min-height: 36px; min-width: 46px; padding: 0 4px; }}

    /* Estados vacíos / títulos auxiliares */
    QLabel#Title {{ font-size: 22px; font-weight: 600; }}
    QLabel#Subtitle {{ color: {TEXT_MUTED}; }}
    QLabel#EmptyState {{ color: {TEXT_MUTED}; font-size: 15px; }}
    QLabel#FieldLabel {{ color: {TEXT}; font-weight: 500; font-size: 13px; }}

    /* Zona de carga de imagen (formulario Nuevo producto) */
    QFrame#DropZone {{
        background: {SURFACE}; border: 1px dashed {BORDER}; border-radius: 12px;
    }}
    QFrame#DropZone:hover {{ border: 1px dashed {ACCENT}; }}

    /* Indicador de conexión */
    QLabel#StatusOnline {{ color: {OK}; }}
    QLabel#StatusOffline {{ color: {TEXT_MUTED}; }}
    """


# ── Helper de botones ───────────────────────────────────────────────────────
# variante -> (objectName del QSS, color del ícono acorde al texto)
_BUTTON_VARIANTS = {
    "primary": ("Primary", TEXT_ON_ACCENT),
    "secondary": ("Secondary", TEXT),
    "danger": ("Danger", DANGER),
    "icon": ("IconButton", TEXT_MUTED),
    "icon_danger": ("IconDanger", DANGER),
}


def style_button(btn: QPushButton, variant: str = "primary", icon: str | None = None) -> QPushButton:
    """Aplica una variante visual coherente a un QPushButton.

    Reutilizable en todos los módulos (Inventario, PoS, Servicio Técnico): fija
    objectName (para el QSS), cursor de mano, ícono qtawesome del color correcto
    y, en el primario, una sombra sutil. Evita stylesheets inline por botón.
    `icon` es un nombre qtawesome, p.ej. "fa5s.plus".
    """
    object_name, icon_color = _BUTTON_VARIANTS[variant]
    btn.setObjectName(object_name)
    btn.setCursor(Qt.PointingHandCursor)
    if icon and qta is not None:
        btn.setIcon(qta.icon(icon, color=icon_color))
        btn.setIconSize(QSize(16, 16))
    if variant == "primary":
        sombra = QGraphicsDropShadowEffect(btn)
        sombra.setBlurRadius(14)
        sombra.setOffset(0, 2)
        sombra.setColor(QColor(15, 23, 42, 45))  # slate translúcido, sutil
        btn.setGraphicsEffect(sombra)
    # Re-aplicar el estilo por si el botón ya estaba visible al cambiar objectName.
    if btn.style():
        btn.style().unpolish(btn)
        btn.style().polish(btn)
    return btn


def apply_palette(app) -> None:
    """Ajustes de paleta que el QSS no cubre (color del placeholder). Llamar una vez."""
    pal = app.palette()
    pal.setColor(QPalette.PlaceholderText, QColor(TEXT_MUTED))
    app.setPalette(pal)


# ── Componente reutilizable: stepper de cantidad [−] N [+] ──────────────────
class QuantityStepper(QWidget):
    """Control de cantidad moderno: botón menos, valor editable centrado, botón más.

    Reemplaza al QSpinBox con flechas apiladas. API mínima compatible con lo que
    usa el PoS: value(), setValue(), setMaximum(), setMinimum() y señal
    valueChanged(int). El botón − se deshabilita en el mínimo y + en el máximo.
    """

    valueChanged = Signal(int)

    def __init__(self, value: int = 1, minimum: int = 1, maximum: int = 999, parent=None) -> None:
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._value = max(minimum, min(maximum, value))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.btn_menos = self._boton("fa5s.minus")
        self.btn_menos.clicked.connect(lambda: self.setValue(self._value - 1))
        self.campo = QLineEdit(str(self._value))
        self.campo.setObjectName("StepperField")
        self.campo.setAlignment(Qt.AlignCenter)
        self.campo.setValidator(QIntValidator(minimum, maximum, self))
        self.campo.editingFinished.connect(self._desde_campo)
        self.btn_mas = self._boton("fa5s.plus")
        self.btn_mas.clicked.connect(lambda: self.setValue(self._value + 1))

        lay.addWidget(self.btn_menos)
        lay.addWidget(self.campo)
        lay.addWidget(self.btn_mas)
        self._sincronizar()

    def _boton(self, icono: str) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("StepperBtn")
        btn.setCursor(Qt.PointingHandCursor)
        if qta is not None:
            btn.setIcon(qta.icon(icono, color=TEXT))
            btn.setIconSize(QSize(14, 14))
        return btn

    def value(self) -> int:
        return self._value

    def setValue(self, valor: int) -> None:
        valor = max(self._min, min(self._max, int(valor)))
        cambiado = valor != self._value
        self._value = valor
        self._sincronizar()
        if cambiado:
            self.valueChanged.emit(valor)

    def setMinimum(self, minimo: int) -> None:
        self._min = minimo
        self.campo.validator().setBottom(minimo)
        self.setValue(self._value)

    def setMaximum(self, maximo: int) -> None:
        self._max = maximo
        self.campo.validator().setTop(maximo)
        self.setValue(self._value)

    def _desde_campo(self) -> None:
        try:
            self.setValue(int(self.campo.text()))
        except ValueError:
            self._sincronizar()

    def _sincronizar(self) -> None:
        if self.campo.text() != str(self._value):
            self.campo.setText(str(self._value))
        self.btn_menos.setEnabled(self._value > self._min)
        self.btn_mas.setEnabled(self._value < self._max)
