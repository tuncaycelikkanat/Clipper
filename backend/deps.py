from backend.db.database import DatabaseManager


def get_db():
    return DatabaseManager()
