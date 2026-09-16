"""Login único de Skytec (usuario + PIN/contraseña), con cambio de
contraseña obligatorio en el primer ingreso y recuperación por correo.
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import database
from core.models import Usuario
from ui import styles
from workers.recuperacion import RecuperacionWorker

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _enmascarar_email(email: str) -> str:
    """"ana@skytec.cl" -> "a**@skytec.cl" — para mostrar en la UI sin
    exponer el correo completo."""
    usuario, _, dominio = email.partition("@")
    if not dominio:
        return email
    if len(usuario) <= 1:
        oculto = usuario + "*"
    else:
        oculto = usuario[0] + "*" * (len(usuario) - 1)
    return f"{oculto}@{dominio}"


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
        styles.style_button(entrar, "primary")
        entrar.clicked.connect(self._intentar)
        lay.addWidget(entrar)

        olvido = QPushButton("¿Olvidaste tu contraseña?")
        styles.style_button(olvido, "secondary")
        olvido.clicked.connect(self._olvido_contrasena)
        lay.addWidget(olvido)

    def _intentar(self) -> None:
        nombre = self.usuario_input.text().strip()
        clave = self.clave_input.text()
        fila = database.autenticar(nombre, clave)

        if fila is None:
            self.error.setText("Usuario o clave incorrectos")
            self.error.show()
            self.clave_input.clear()
            self.clave_input.setFocus()
            return

        if fila["debe_cambiar_password"]:
            dlg = PrimerIngresoDialog(fila["id"], fila["nombre"], fila["email"], self)
            if dlg.exec() != QDialog.Accepted:
                # Cambio cancelado: no se otorga acceso con la clave vieja
                # (podría ser la temporal de una recuperación, o la 1234
                # sembrada) — vuelve a la pantalla de login sin entrar.
                self.clave_input.clear()
                self.clave_input.setFocus()
                return
            fila = database.autenticar(nombre, dlg.nueva_clave)
            if fila is None:  # no debería pasar nunca, pero por las dudas
                self.error.setText("Ocurrió un problema al actualizar tu clave. Probá de nuevo.")
                self.error.show()
                return

        self.usuario = Usuario.from_row(fila)
        self.accept()

    def _olvido_contrasena(self) -> None:
        RecuperarPasswordDialog(self.usuario_input.text().strip(), self).exec()


class PrimerIngresoDialog(QDialog):
    """Cambio de contraseña obligatorio: primer ingreso de un usuario nuevo,
    o clave temporal recién recibida por correo. No se puede cerrar con la
    X — o se completa, o se cancela con el botón (y el login no avanza)."""

    def __init__(self, usuario_id: int, nombre: str, email_actual: str | None,
                 parent=None) -> None:
        super().__init__(parent)
        self.usuario_id = usuario_id
        self.nombre = nombre
        self.nueva_clave = ""
        self.setWindowTitle("Cambio de contraseña obligatorio")
        self.setFixedWidth(380)
        self.setStyleSheet(styles.build_stylesheet())
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(styles.S4, styles.S4, styles.S4, styles.S4)
        lay.setSpacing(styles.S2)

        titulo = QLabel("Por seguridad, tenés que cambiar tu contraseña")
        titulo.setObjectName("Title")
        titulo.setWordWrap(True)
        lay.addWidget(titulo)

        sub = QLabel(
            f"Hola {nombre}. Elegí una contraseña nueva y dejá un correo — "
            "lo vamos a usar solo si alguna vez necesitás recuperar el acceso."
        )
        sub.setObjectName("Subtitle")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        lbl1 = QLabel("Contraseña nueva")
        lbl1.setObjectName("FieldLabel")
        lay.addWidget(lbl1)
        self.clave1 = QLineEdit()
        self.clave1.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.clave1)

        lbl2 = QLabel("Repetí la contraseña")
        lbl2.setObjectName("FieldLabel")
        lay.addWidget(lbl2)
        self.clave2 = QLineEdit()
        self.clave2.setEchoMode(QLineEdit.Password)
        self.clave2.returnPressed.connect(self._confirmar)
        lay.addWidget(self.clave2)

        lbl3 = QLabel("Correo")
        lbl3.setObjectName("FieldLabel")
        lay.addWidget(lbl3)
        self.email_input = QLineEdit(email_actual or "")
        self.email_input.setPlaceholderText("tu@correo.cl")
        lay.addWidget(self.email_input)

        self.error = QLabel("")
        self.error.setStyleSheet(f"color: {styles.DANGER};")
        self.error.setWordWrap(True)
        self.error.hide()
        lay.addWidget(self.error)

        guardar = QPushButton("Guardar y continuar")
        styles.style_button(guardar, "primary")
        guardar.clicked.connect(self._confirmar)
        lay.addWidget(guardar)

        cancelar = QPushButton("Cancelar (no voy a entrar)")
        styles.style_button(cancelar, "secondary")
        cancelar.clicked.connect(self.reject)
        lay.addWidget(cancelar)

    def _confirmar(self) -> None:
        c1, c2 = self.clave1.text(), self.clave2.text()
        email = self.email_input.text().strip()

        if len(c1) < 4:
            return self._mostrar_error("La contraseña debe tener al menos 4 caracteres.")
        if c1 != c2:
            return self._mostrar_error("Las contraseñas no coinciden.")
        if not _EMAIL_RE.match(email):
            return self._mostrar_error("El correo no parece válido.")

        database.completar_primer_ingreso(self.usuario_id, c1, email)
        self.nueva_clave = c1
        self.accept()

    def _mostrar_error(self, texto: str) -> None:
        self.error.setText(texto)
        self.error.show()


class RecuperarPasswordDialog(QDialog):
    """Pide el usuario y dispara el envío de una clave temporal por correo
    (Resend). El envío corre en un hilo aparte para no congelar la UI."""

    def __init__(self, nombre_sugerido: str, parent=None) -> None:
        super().__init__(parent)
        self._worker: RecuperacionWorker | None = None
        self.setWindowTitle("Recuperar contraseña")
        self.setFixedWidth(360)
        self.setStyleSheet(styles.build_stylesheet())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(styles.S4, styles.S4, styles.S4, styles.S4)
        lay.setSpacing(styles.S2)

        titulo = QLabel("Recuperar contraseña")
        titulo.setObjectName("Title")
        lay.addWidget(titulo)

        sub = QLabel(
            "Te mandamos una contraseña temporal al correo que dejaste "
            "configurado. Vas a tener que cambiarla apenas entres."
        )
        sub.setObjectName("Subtitle")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        lbl = QLabel("Usuario")
        lbl.setObjectName("FieldLabel")
        lay.addWidget(lbl)
        self.usuario_input = QLineEdit(nombre_sugerido)
        self.usuario_input.returnPressed.connect(self._enviar)
        lay.addWidget(self.usuario_input)

        self.mensaje = QLabel("")
        self.mensaje.setWordWrap(True)
        self.mensaje.hide()
        lay.addWidget(self.mensaje)

        self.btn_enviar = QPushButton("Enviar contraseña temporal")
        styles.style_button(self.btn_enviar, "primary")
        self.btn_enviar.clicked.connect(self._enviar)
        lay.addWidget(self.btn_enviar)

        cerrar = QPushButton("Cerrar")
        styles.style_button(cerrar, "secondary")
        cerrar.clicked.connect(self.reject)
        lay.addWidget(cerrar)

    def _enviar(self) -> None:
        nombre = self.usuario_input.text().strip()
        if not nombre:
            return
        self.btn_enviar.setEnabled(False)
        self.btn_enviar.setText("Enviando…")
        self._worker = RecuperacionWorker(nombre, self)
        self._worker.ok.connect(self._enviado_ok)
        self._worker.error.connect(self._enviado_error)
        self._worker.start()

    def _restaurar_boton(self) -> None:
        self.btn_enviar.setEnabled(True)
        self.btn_enviar.setText("Enviar contraseña temporal")

    def _enviado_ok(self, email: str) -> None:
        self._restaurar_boton()
        QMessageBox.information(
            self, "Listo",
            f"Te mandamos una contraseña temporal a {_enmascarar_email(email)}.\n\n"
            "Iniciá sesión con esa clave; el sistema te va a pedir que la cambies.",
        )
        self.accept()

    def _enviado_error(self, mensaje: str) -> None:
        self._restaurar_boton()
        self.mensaje.setStyleSheet(f"color: {styles.DANGER};")
        self.mensaje.setText(mensaje)
        self.mensaje.show()
