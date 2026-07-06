import json
from abc import ABC, abstractmethod
from contextlib import _GeneratorContextManager
from typing import Any

import sqlalchemy
from sqlalchemy.engine import Connection
from sqlalchemy.engine.base import Engine

from _dependencies.common.commons import sqlalchemy_get_pool


class DBClientBase:
    def __init__(self, db: Engine | None = None) -> None:
        self._db = db or sqlalchemy_get_pool()

    def connect(self) -> _GeneratorContextManager:
        """Context manager yielding a Connection; commits on successful exit.

        Uses ``engine.begin()`` internally so that all DML is automatically
        committed when the context exits.  Read‑only transactions commit a
        no‑op, which is harmless.
        """
        return self._db.begin()


class DBClientMixinBase(ABC):
    """Base class for all DB mixins that require a ``connect()`` method.

    Declares ``connect()`` as abstract so mixins can call ``self.connect()``
    without ``# type: ignore[attr-defined]`` or ``TYPE_CHECKING`` stubs.
    """

    @abstractmethod
    def connect(self) -> _GeneratorContextManager: ...



class DBKeyValueStorageMixin(DBClientMixinBase):
    def get_key_value_item(self, key: str) -> Any:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT value FROM key_value_storage WHERE key=:key;
                                   """)
            raw_data = conn.execute(stmt, dict(key=key)).fetchone()
            return raw_data[0] if raw_data else None

    def set_key_value_item(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                INSERT INTO key_value_storage
                (key, value)
                VALUES (:key, :value)
                ON CONFLICT (key) DO UPDATE SET value = :value ;
                                   """)
            conn.execute(stmt, dict(key=key, value=json.dumps(value)))

    def delete_key_value_item(self, key: str) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                DELETE FROM key_value_storage
                WHERE key=:key;
                                   """)
            conn.execute(stmt, dict(key=key))
