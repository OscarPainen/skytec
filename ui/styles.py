"""Sistema de diseño centralizado de Skytec.

Un solo lugar para colores, espaciado y tipografía. Paleta neutra + un único
acento. Todo el resto de la UI referencia estas constantes o el stylesheet.
Grilla de 8px.
"""
from __future__ import annotations

# ── Paleta ────────────────────────────────────────────────────────────────
ACCENT = "#2563EB"        # único color de acento (azul "sky")
ACCENT_HOVER = "#1D4ED8"
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

# ── Métrica (8px) ─────────────────────────────────────────────────────────
S1, S2, S3, S4 = 8, 16, 24, 32
RADIUS = 8
FONT_FAMILY = "Inter, 'Segoe UI', system-ui, sans-serif"


def build_stylesheet() -> str:
    """QSS global de la aplicación."""
    return f"""
    * {{
        font-family: {FONT_FAMILY};
        font-size: 14px;
        color: {TEXT};
    }}
    QMainWindow, QDialog, QWidget#Content {{ background: {BG}; }}

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

    /* Botones */
    QPushButton {{
        background: {ACCENT}; color: {TEXT_ON_ACCENT}; border: none;
        border-radius: {RADIUS}px; padding: {S1}px {S2}px; font-weight: 600;
    }}
    QPushButton:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton:disabled {{ background: {BORDER}; color: {TEXT_MUTED}; }}
    QPushButton#Secondary {{
        background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
    }}
    QPushButton#Secondary:hover {{ background: {ACCENT_SOFT}; }}

    /* Campos */
    QLineEdit, QComboBox, QSpinBox, QTextEdit, QDateEdit {{
        background: {BG}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
        padding: {S1}px; selection-background-color: {ACCENT_SOFT};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{
        border: 1px solid {ACCENT};
    }}

    /* Estados vacíos / títulos auxiliares */
    QLabel#Title {{ font-size: 22px; font-weight: 700; }}
    QLabel#Subtitle {{ color: {TEXT_MUTED}; }}
    QLabel#EmptyState {{ color: {TEXT_MUTED}; font-size: 15px; }}

    /* Indicador de conexión */
    QLabel#StatusOnline {{ color: {OK}; }}
    QLabel#StatusOffline {{ color: {TEXT_MUTED}; }}
    """
