"""Configuración local en JSON — solo para ajustes que aún no tienen un lugar
en la tabla `config` de SQLite (por ahora: categorías).

El resto de los ajustes (nombre del negocio, cajas, umbral de stock, impresora)
ya vive en SQLite vía core.database.get_config/set_config — eso no se toca acá,
para no tener dos sistemas de configuración compitiendo por lo mismo.
"""
from __future__ import annotations

import json
from pathlib import Path

from core import database

DEFAULTS: dict = {
    # Sin tildes a propósito: coincide con lo que ya hay en la base
    # (productos.categoria) y con el valor fijo "reparacion" que usa
    # modules/servicio_tecnico/repo.py al generar la venta de una reparación.
    "categorias": ["reparacion", "tecnologia", "suplemento"],
}


def _config_path() -> Path:
    # Se calcula en cada llamada (no al importar) para respetar cambios de
    # database.DB_PATH, igual que hacen los auto-checks de database.py/repo.py.
    return database.DB_PATH.parent / "skytec_config.json"


def cargar_config() -> dict:
    """Lee el JSON. Si no existe lo crea con DEFAULTS. Si le faltan claves
    (ajustes agregados después), las rellena con su default sin pisar el resto."""
    ruta = _config_path()
    if not ruta.exists():
        guardar_config(DEFAULTS.copy())
        return DEFAULTS.copy()
    with open(ruta, "r", encoding="utf-8") as f:
        config = json.load(f)
    faltantes = False
    for clave, valor in DEFAULTS.items():
        if clave not in config:
            config[clave] = valor
            faltantes = True
    if faltantes:
        guardar_config(config)
    return config


def guardar_config(config: dict) -> None:
    ruta = _config_path()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # Auto-check: mismo patrón que core/database.py (base temporal + asserts).
    import os
    import tempfile

    tmp = Path(tempfile.mkdtemp()) / "t.db"
    os.environ["SKYTEC_DB"] = str(tmp)
    database.DB_PATH = tmp

    config = cargar_config()
    assert config == DEFAULTS, config
    print("Config inicial:", config)

    config["categorias"].append("accesorios")
    guardar_config(config)
    config2 = cargar_config()
    assert config2["categorias"][-1] == "accesorios", config2

    # Simula un JSON viejo al que le falta una clave (compatibilidad futura)
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump({}, f)
    config3 = cargar_config()
    assert config3["categorias"] == DEFAULTS["categorias"], config3

    print("OK config.py")
