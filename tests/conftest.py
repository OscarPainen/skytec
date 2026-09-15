"""Fixture compartida: cada test corre contra su propia base SQLite temporal,
nunca contra la base real del negocio.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from core import database


@pytest.fixture
def db_temporal(monkeypatch):
    tmp = Path(tempfile.mkdtemp()) / "t.db"
    monkeypatch.setenv("SKYTEC_DB", str(tmp))
    monkeypatch.setattr(database, "DB_PATH", tmp)
    database.init_db()
    yield tmp
