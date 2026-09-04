import os
import sqlite3


class DatabaseManager:
    def __init__(self, db_path="clipper.db"):
        self.db_path = db_path
        self._ensure_db_dir()

    def _ensure_db_dir(self):
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    _connect = get_connection

    def init_db(self):
        from .schema import SCHEMA_SQL

        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
