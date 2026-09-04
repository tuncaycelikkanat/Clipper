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


@pytest.fixture(autouse=True)
def reset_test_state():
    """Reset global in-memory states between tests."""
    import core.scoring_config as SC
    from backend.workers.job_store import job_store

    orig_runs = SC.ENSEMBLE_RUNS
    orig_band = SC.BAND_LABELS_ENABLED
    orig_cap = SC.MUNDANE_SCORE_CAP
    orig_hook = SC.HOOK_STRENGTH_WEIGHT
    orig_emo = SC.EMOTION_WEIGHT
    orig_story = SC.STORY_COMPLETENESS_WEIGHT
    orig_sig = SC.SIGNAL_VALIDATION_WEIGHT

    yield

    SC.ENSEMBLE_RUNS = orig_runs
    SC.BAND_LABELS_ENABLED = orig_band
    SC.MUNDANE_SCORE_CAP = orig_cap
    SC.HOOK_STRENGTH_WEIGHT = orig_hook
    SC.EMOTION_WEIGHT = orig_emo
    SC.STORY_COMPLETENESS_WEIGHT = orig_story
    SC.SIGNAL_VALIDATION_WEIGHT = orig_sig
    job_store._jobs.clear()

