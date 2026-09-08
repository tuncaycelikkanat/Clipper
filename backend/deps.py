from __future__ import annotations

import threading

from core.database import DatabaseManager

_local = threading.local()


def get_db() -> DatabaseManager:
    if not hasattr(_local, "db") or _local.db is None:
        _local.db = DatabaseManager()
        _local.db.execute("PRAGMA journal_mode=WAL;")
        _local.db.execute("PRAGMA busy_timeout=5000;")
    return _local.db
