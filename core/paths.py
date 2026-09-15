"""Directorio de datos de la app: vive fuera del proyecto y del ejecutable.

Separar los datos (base, config, respaldos) del código a propósito: al armar
la build de producción, borrar todo lo de prueba es borrar esta carpeta, sin
tocar el repo ni el instalador.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

NOMBRE_APP = "Skytec"


def app_data_dir() -> Path:
    """Directorio de datos persistentes según el sistema operativo. Lo crea
    si no existe. No usa QStandardPaths: este módulo lo importan
    core/database.py y scripts de línea de comandos que deben poder correr
    sin que haya una QApplication viva."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    destino = base / NOMBRE_APP
    destino.mkdir(parents=True, exist_ok=True)
    return destino


if __name__ == "__main__":
    # Auto-check: misma convención que los demás módulos de core/.
    d = app_data_dir()
    assert d.is_absolute(), d
    assert d.exists(), d
    assert d.name == NOMBRE_APP, d
    print("OK paths.py:", d)
