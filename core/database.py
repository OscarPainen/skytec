"""Conexión SQLite y migraciones.

SQLite es la fuente de verdad (offline-first). Una sola base compartida por
todos los módulos. Migraciones versionadas con PRAGMA user_version: se aplican
en orden las que falten, así el esquema evoluciona sin borrar datos.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

# La base vive junto al ejecutable/proyecto para que sea 100% local y portable.
DB_PATH = Path(os.environ.get("SKYTEC_DB", Path(__file__).resolve().parent.parent / "skytec.db"))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Hash de PIN/contraseña ────────────────────────────────────────────────
# ponytail: pbkdf2 de stdlib en vez de passlib/bcrypt. Suficiente y sin
# dependencias; subir a bcrypt solo si el cliente exige política de claves.
def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hash_password(password, bytes.fromhex(salt_hex)) == stored


# ── Migraciones ───────────────────────────────────────────────────────────
# Lista ordenada. Índice+1 == versión. Agregar SQL al final nunca reordenar.
MIGRATIONS: list[str] = [
    # v1 — esquema base completo del levantamiento
    """
    CREATE TABLE productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        descripcion TEXT,
        imagen_path TEXT,
        precio_venta INTEGER NOT NULL DEFAULT 0,
        costo INTEGER NOT NULL DEFAULT 0,
        stock_actual INTEGER NOT NULL DEFAULT 0,
        categoria TEXT,
        disponible INTEGER NOT NULL DEFAULT 1,
        creado_en TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE movimientos_stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER NOT NULL REFERENCES productos(id),
        tipo TEXT NOT NULL CHECK (tipo IN ('entrada','salida','merma')),
        cantidad INTEGER NOT NULL,
        costo_unitario INTEGER,
        motivo TEXT,
        fecha TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        usuario_id INTEGER REFERENCES usuarios(id)
    );

    CREATE TABLE ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL CHECK (tipo IN ('directa','servicio_tecnico')),
        total INTEGER NOT NULL DEFAULT 0,
        fecha TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        usuario_id INTEGER REFERENCES usuarios(id),
        pos_origen TEXT,
        boleta_sii TEXT
    );

    CREATE TABLE venta_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
        producto_id INTEGER REFERENCES productos(id),
        cantidad INTEGER NOT NULL,
        precio_unitario INTEGER NOT NULL,
        subtotal INTEGER NOT NULL
    );

    CREATE TABLE solicitudes_reparacion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        modelo_telefono TEXT,
        cliente_nombre TEXT,
        cliente_email TEXT,
        cliente_telefono TEXT,
        tipo_servicio TEXT,
        fecha_entrega_solicitada TEXT,
        estado TEXT NOT NULL DEFAULT 'pendiente'
            CHECK (estado IN ('pendiente','revisada','aceptada','en_reparacion',
                              'completada','no_retirada','vencida')),
        origen TEXT NOT NULL DEFAULT 'manual' CHECK (origen IN ('web','manual')),
        firebase_id TEXT UNIQUE,
        creado_en TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE servicios_tecnicos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solicitud_id INTEGER NOT NULL REFERENCES solicitudes_reparacion(id),
        fecha_reparacion TEXT,
        precio INTEGER,
        detalles TEXT,
        estado TEXT,
        venta_id INTEGER REFERENCES ventas(id),
        agendado_en TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        rol TEXT NOT NULL DEFAULT 'vendedor' CHECK (rol IN ('admin','vendedor')),
        pin_o_password TEXT NOT NULL
    );

    CREATE TABLE config (
        clave TEXT PRIMARY KEY,
        valor TEXT
    );
    """,
    # v2 — línea de venta con descripción libre: permite que un ítem sea un
    # servicio técnico (sin producto asociado) en la misma nota de venta.
    "ALTER TABLE venta_items ADD COLUMN descripcion TEXT;",
]


def init_db() -> None:
    """Crea la base si no existe y aplica migraciones pendientes."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for i in range(version, len(MIGRATIONS)):
            conn.executescript(MIGRATIONS[i])
            conn.execute(f"PRAGMA user_version = {i + 1}")
            conn.commit()
        _seed_defaults(conn)
    finally:
        conn.close()


DEFAULT_CONFIG = {
    "negocio_nombre": "Skytec",
    "negocio_logo": "",
    "pos_1_nombre": "Tech",       # pendiente confirmar con cliente
    "pos_2_nombre": "Fit",        # pendiente confirmar con cliente
    "stock_bajo_umbral": "5",
    "impresora_conexion": "usb",   # usb | network | serial
    "impresora_ancho": "80",       # 58 | 80 (mm)
    "impresora_host": "192.168.0.100",  # conexión de red
    "impresora_puerto": "9100",
    "impresora_serial": "COM1",         # conexión serial
    "impresora_usb_vendor": "0x0416",   # conexión USB (VID/PID de la impresora)
    "impresora_usb_product": "0x5011",
}


def _seed_defaults(conn: sqlite3.Connection) -> None:
    """Datos mínimos para poder abrir la app: admin inicial y config base."""
    if conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO usuarios (nombre, rol, pin_o_password) VALUES (?,?,?)",
            ("admin", "admin", hash_password("1234")),
        )
    for clave, valor in DEFAULT_CONFIG.items():
        conn.execute(
            "INSERT OR IGNORE INTO config (clave, valor) VALUES (?,?)", (clave, valor)
        )
    conn.commit()


def get_config(clave: str, default: str | None = None) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT valor FROM config WHERE clave=?", (clave,)).fetchone()
        return row["valor"] if row else default
    finally:
        conn.close()


def set_config(clave: str, valor: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO config (clave, valor) VALUES (?,?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (clave, valor),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    # Auto-check: base en memoria, migra, verifica esquema y hash de PIN.
    import tempfile

    tmp = Path(tempfile.mkdtemp()) / "t.db"
    os.environ["SKYTEC_DB"] = str(tmp)
    globals()["DB_PATH"] = tmp
    init_db()
    init_db()  # idempotente: correr dos veces no debe fallar ni duplicar
    c = get_connection()
    tablas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"productos", "ventas", "usuarios", "config"} <= tablas, tablas
    assert c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 1, "admin duplicado"
    stored = c.execute("SELECT pin_o_password FROM usuarios WHERE nombre='admin'").fetchone()[0]
    assert verify_password("1234", stored) and not verify_password("0000", stored)
    c.close()
    print("OK database.py")
