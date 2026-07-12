"""Skytec — punto de entrada.

Cliente: Skytec · Desarrollado por: JobConsulting.
Inicializa la base local (offline-first), pide login y abre la ventana principal.
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QDialog

from core import database
from ui.login import LoginDialog
from ui.main_window import MainWindow


def main() -> int:
    database.init_db()

    app = QApplication(sys.argv)

    login = LoginDialog()
    if login.exec() != QDialog.Accepted or login.usuario is None:
        return 0

    ventana = MainWindow(login.usuario)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
