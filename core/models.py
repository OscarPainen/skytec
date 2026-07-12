"""Modelos de datos (dataclasses que reflejan las tablas SQLite).

Livianos a propósito: no son un ORM, solo tipado y `from_row` para convertir
un sqlite3.Row en objeto. La lógica de acceso vive en cada módulo.
Precios y montos se guardan en CLP como enteros (sin decimales).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, fields
from typing import Any, TypeVar

T = TypeVar("T", bound="_Base")


@dataclass
class _Base:
    @classmethod
    def from_row(cls: type[T], row: sqlite3.Row | dict[str, Any]) -> T:
        data = dict(row)
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Usuario(_Base):
    id: int
    nombre: str
    rol: str  # admin | vendedor
    pin_o_password: str

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"


@dataclass
class Producto(_Base):
    id: int
    nombre: str
    descripcion: str | None
    imagen_path: str | None
    precio_venta: int
    costo: int
    stock_actual: int
    categoria: str | None
    disponible: int
    creado_en: str

    @property
    def valor_inventario(self) -> int:
        return self.stock_actual * self.costo


@dataclass
class MovimientoStock(_Base):
    id: int
    producto_id: int
    tipo: str  # entrada | salida | merma
    cantidad: int
    costo_unitario: int | None
    motivo: str | None
    fecha: str
    usuario_id: int | None


@dataclass
class Venta(_Base):
    id: int
    tipo: str  # directa | servicio_tecnico
    total: int
    fecha: str
    usuario_id: int | None
    pos_origen: str | None
    boleta_sii: str | None


@dataclass
class VentaItem(_Base):
    id: int
    venta_id: int
    producto_id: int | None
    cantidad: int
    precio_unitario: int
    subtotal: int


@dataclass
class SolicitudReparacion(_Base):
    id: int
    modelo_telefono: str | None
    cliente_nombre: str | None
    cliente_email: str | None
    cliente_telefono: str | None
    tipo_servicio: str | None
    fecha_entrega_solicitada: str | None
    estado: str
    origen: str  # web | manual
    firebase_id: str | None
    creado_en: str


@dataclass
class ServicioTecnico(_Base):
    id: int
    solicitud_id: int
    fecha_reparacion: str | None
    precio: int | None
    detalles: str | None
    estado: str | None
    venta_id: int | None
    agendado_en: str
