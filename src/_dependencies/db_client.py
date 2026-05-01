from typing import TYPE_CHECKING, Any

from sqlalchemy.engine import Connection
from sqlalchemy.engine.base import Engine
import sqlalchemy
import json


class DBClientBase:
    def __init__(self, db: Engine) -> None:
        self._db = db

    def connect(self) -> Connection:
        return self._db.connect()


class DBKeyValueStorageMixin:
    if TYPE_CHECKING:

        def connect(self) -> Connection: ...

    def get_key_value_item(self, key: str) -> Any:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT value FROM key_value_storage WHERE key=:key;
                                   """)
            raw_data = conn.execute(stmt, key=key).fetchone()
            return raw_data[0] if raw_data else None

    def set_key_value_item(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                INSERT INTO key_value_storage 
                (key, value) 
                VALUES (:key, :value) 
                ON CONFLICT (key) DO UPDATE SET value = :value ; 
                                   """)
            conn.execute(stmt, key=key, value=json.dumps(value))

    def delete_key_value_item(self, key: str) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                DELETE FROM key_value_storage 
                WHERE key=:key; 
                                   """)
            conn.execute(stmt, key=key)


