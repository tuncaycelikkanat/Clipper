from backend.deps import get_db
from backend.db.database import DatabaseManager

def test_get_db_dependency():
    db = get_db()
    assert isinstance(db, DatabaseManager)
