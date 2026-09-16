"""Skytec — punto de entrada.

Cliente: Skytec · Desarrollado por: JobConsulting.
Inicializa la base local (offline-first), pide login y abre la ventana principal.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication, QDialog

from core import backup, database
from ui import styles
from ui.login import LoginDialog
from ui.main_window import MainWindow


def main() -> int:
    # Sin esto, SKYTEC_RESEND_API_KEY/SKYTEC_RESEND_FROM del .env nunca
    # llegan a os.environ y la recuperación por correo queda "no
    # configurada" aunque el archivo tenga las claves reales.
    load_dotenv(Path(__file__).resolve().parent / ".env")

    database.init_db()
    backup.hacer_backup_diario()  # nunca lanza: un respaldo roto no bloquea la venta

    app = QApplication(sys.argv)
    styles.apply_palette(app)

    login = LoginDialog()
    if login.exec() != QDialog.Accepted or login.usuario is None:
        return 0

    ventana = MainWindow(login.usuario)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
