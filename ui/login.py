"""Login único de Skytec (usuario + PIN/contraseña)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import database
from core.models import Usuario
from ui import styles


class LoginDialog(QDialog):
    """Devuelve el Usuario autenticado en `self.usuario` al aceptar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.usuario: Usuario | None = None
        self.setWindowTitle("Skytec — Ingreso")
        self.setFixedWidth(360)
        self.setStyleSheet(styles.build_stylesheet())

        nombre_negocio = database.get_config("negocio_nombre", "Skytec")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(styles.S4, styles.S4, styles.S4, styles.S4)
        lay.setSpacing(styles.S2)

        brand = QLabel(nombre_negocio)
        brand.setObjectName("Title")
        brand.setAlignment(Qt.AlignCenter)
        lay.addWidget(brand)

        sub = QLabel("Inicia sesión para continuar")
        sub.setObjectName("Subtitle")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)

        self.usuario_input = QLineEdit()
        self.usuario_input.setPlaceholderText("Usuario")
        self.usuario_input.setText("admin")
        lay.addWidget(self.usuario_input)

        self.clave_input = QLineEdit()
        self.clave_input.setPlaceholderText("PIN o contraseña")
        self.clave_input.setEchoMode(QLineEdit.Password)
        self.clave_input.returnPressed.connect(self._intentar)
        lay.addWidget(self.clave_input)

        self.error = QLabel("")
        self.error.setStyleSheet(f"color: {styles.DANGER};")
        self.error.setAlignment(Qt.AlignCenter)
        self.error.hide()
        lay.addWidget(self.error)

        entrar = QPushButton("Entrar")
        entrar.clicked.connect(self._intentar)
        lay.addWidget(entrar)

    def _intentar(self) -> None:
        nombre = self.usuario_input.text().strip()
        clave = self.clave_input.text()
        conn = database.get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM usuarios WHERE nombre = ?", (nombre,)
            ).fetchone()
        finally:
            conn.close()

        if row and database.verify_password(clave, row["pin_o_password"]):
            self.usuario = Usuario.from_row(row)
            self.accept()
        else:
            self.error.setText("Usuario o clave incorrectos")
            self.error.show()
            self.clave_input.clear()
            self.clave_input.setFocus()
