"""tests/test_job_store_concurrency.py — Concurrent access tests for JobStore."""

import threading
from backend.workers.job_store import JobStore


def test_job_store_concurrent_access():
    """Verify JobStore behaves safely under concurrent multi-threaded writes and reads."""
    store = JobStore()
    errors = []

    def writer(worker_id: int):
        for i in range(50):
            try:
                job = store.create(f"https://youtube.com/watch?v=vid_{worker_id}_{i}")
                store.update(job.id, progress=i * 2, status="running")
                fetched = store.get(job.id)
                assert fetched is not None
                assert fetched.progress == i * 2
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer, args=(w,)) for w in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Encountered {len(errors)} concurrency errors: {errors[:3]}"
    assert len(store.list_recent(limit=500)) == 400
