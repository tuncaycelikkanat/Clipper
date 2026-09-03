"""Shared pytest fixtures for the clipper test suite."""

import os
import tempfile

import pytest

from core.database import DatabaseManager


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing, yield it, then clean up."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db = DatabaseManager(db_path=db_path)
        db.init_db()
        yield db
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
        # Also clean up WAL/SHM files
        for suffix in ("-wal", "-shm"):
            wal_path = db_path + suffix
            if os.path.exists(wal_path):
                os.unlink(wal_path)
