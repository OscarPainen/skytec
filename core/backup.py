"""Respaldos locales de la base y de la configuración.

Regla dura: un respaldo fallido no puede impedir que el negocio abra la caja.
Todo lo que se llama desde main.py traga sus excepciones y devuelve None.
"""
from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

from core import database

MAX_RESPALDOS = 15


def _dir_backups() -> Path:
    # A partir de database.DB_PATH.parent (no de app_data_dir() directo):
    # así respeta el override de SKYTEC_DB igual que core/config.py, y un
    # self-check con una base temporal no le escribe respaldos de prueba al
    # directorio real de producción.
    d = database.DB_PATH.parent / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rotar(patron: str) -> None:
    """Conserva solo los MAX_RESPALDOS archivos más recientes que matchean
    el patrón. El nombre incluye la fecha en formato YYYYMMDD, así que el
    orden alfabético ya es orden cronológico."""
    archivos = sorted(_dir_backups().glob(patron))
    de_mas = archivos[: len(archivos) - MAX_RESPALDOS] if len(archivos) > MAX_RESPALDOS else []
    for viejo in de_mas:
        viejo.unlink(missing_ok=True)


def _respaldar_config() -> None:
    origen = database.DB_PATH.parent / "skytec_config.json"
    if not origen.exists():
        return
    destino = _dir_backups() / f"skytec_config-{date.today():%Y%m%d}.json"
    if not destino.exists():
        shutil.copy2(origen, destino)
    _rotar("skytec_config-*.json")


def hacer_backup_diario() -> Path | None:
    """VACUUM INTO de la base a backups/skytec-YYYYMMDD.db. No hace nada si
    ya existe el de hoy. Nunca lanza: cualquier falla se ignora en silencio,
    porque un respaldo roto no puede bloquear la apertura de caja."""
    try:
        destino = _dir_backups() / f"skytec-{date.today():%Y%m%d}.db"
        if destino.exists():
            return None
        conn = database.get_connection()
        try:
            conn.execute("VACUUM INTO ?", (str(destino),))
        finally:
            conn.close()
        _rotar("skytec-*.db")
        _respaldar_config()
        return destino
    except Exception:
        return None


def respaldar_ahora(etiqueta: str) -> Path:
    """Respaldo inmediato, sin el dedupe diario de hacer_backup_diario(): para
    antes de una operación destructiva (scripts/reset_db.py). A diferencia del
    respaldo automático, ESTE SÍ lanza si falla — antes de borrar datos hay que
    saber con certeza si el respaldo se hizo, no asumirlo en silencio.

    Prefijo "respaldo-" (no "skytec-") a propósito: que no matchee el glob
    "skytec-*.db" de _rotar(), o competiría por el mismo cupo de 15 con los
    respaldos diarios y podría terminar borrado sin que nadie lo pida. Estos
    respaldos deliberados no se rotan solos."""
    # microsegundos incluidos: dos llamadas en el mismo segundo (poco probable
    # en uso real, pero posible en un test) no deben pisarse el nombre.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destino = _dir_backups() / f"respaldo-{etiqueta}-{ts}.db"
    conn = database.get_connection()
    try:
        conn.execute("VACUUM INTO ?", (str(destino),))
    finally:
        conn.close()
    return destino


if __name__ == "__main__":
    # Auto-check: base temporal propia, no toca los datos reales del negocio.
    import os
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp())
    os.environ["SKYTEC_DB"] = str(tmp_dir / "t.db")
    database.DB_PATH = tmp_dir / "t.db"
    database.init_db()

    r1 = hacer_backup_diario()
    assert r1 is not None and r1.exists(), r1
    r2 = hacer_backup_diario()
    assert r2 is None, "no debería duplicar el respaldo del mismo día"

    # Rotación: simula 20 respaldos con fechas falsas (no hay que esperar
    # 20 días) y verifica que sobrevivan exactamente los 15 más recientes.
    carpeta = _dir_backups()
    for archivo in carpeta.glob("skytec-*.db"):
        archivo.unlink()
    for i in range(20):
        (carpeta / f"skytec-202601{i + 1:02d}.db").write_bytes(b"x")
    _rotar("skytec-*.db")
    restantes = sorted(carpeta.glob("skytec-*.db"))
    assert len(restantes) == 15, len(restantes)
    assert restantes[0].name == "skytec-20260106.db", restantes[0].name
    assert restantes[-1].name == "skytec-20260120.db", restantes[-1].name

    # respaldar_ahora(): no dedupe, dos llamadas seguidas dejan dos archivos
    r3 = respaldar_ahora("antes-reset")
    r4 = respaldar_ahora("antes-reset")
    assert r3 != r4 and r3.exists() and r4.exists(), (r3, r4)

    print("OK backup.py")
