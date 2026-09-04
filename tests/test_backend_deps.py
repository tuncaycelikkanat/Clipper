from backend.db.database import DatabaseManager
from backend.deps import get_db


def test_get_db_dependency():
    db = get_db()
    assert isinstance(db, DatabaseManager)
