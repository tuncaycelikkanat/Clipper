from unittest.mock import patch

import pytest

from backend.workers.job_store import JobState, JobStore, _utcnow, job_store
from backend.workers.pipeline_worker import run_pipeline_async


def test_utcnow():
    t = _utcnow()
    assert isinstance(t, str)
    assert "T" in t


def test_job_state_to_dict():
    job = JobState(id="j1", video_url="http://yt.com/1", status="queued", progress=10)
    d = job.to_dict()
    assert d["id"] == "j1"
    assert d["video_url"] == "http://yt.com/1"
    assert d["status"] == "queued"
    assert d["progress"] == 10


def test_job_store_crud():
    js = JobStore()
    job = js.create("http://yt.com/test")
    assert job.id is not None
    assert js.get(job.id) == job
    assert js.get("nonexistent") is None

    # List recent
    recent = js.list_recent(limit=5)
    assert len(recent) == 1
    assert recent[0].id == job.id

    # Update nonexistent returns None
    assert js.update("nonexistent", status="done") is None

    # Update all fields
    updated = js.update(
        job.id,
        status="running",
        progress=50,
        current_step="Extracting...",
        result=[{"clip": 1}],
        error_msg="some warning",
    )
    assert updated.status == "running"
    assert updated.progress == 50
    assert updated.current_step == "Extracting..."
    assert updated.result == [{"clip": 1}]
    assert updated.error_msg == "some warning"

    # Cancel
    assert js.cancel(job.id) is True
    assert job.status == "cancelled"
    # Cancelling again when already cancelled returns False
    assert js.cancel(job.id) is False
    assert js.cancel("nonexistent") is False


@pytest.mark.asyncio
async def test_job_store_sse():
    js = JobStore()
    job = js.create("http://yt.com/sse")
    q = await js.get_sse_queue(job.id)
    assert q is not None

    await js.push_sse(job.id, "progress", {"pct": 10})
    item = await q.get()
    assert item["event"] == "progress"
    assert item["data"]["pct"] == 10

    # Nonexistent job
    assert await js.get_sse_queue("nonexistent") is None
    await js.push_sse("nonexistent", "ignored", {})


@pytest.mark.asyncio
async def test_pipeline_worker_success():
    js = job_store
    job = js.create("http://yt.com/worker_success")

    mock_results = [{"title": "Clip 1", "score": 90}]

    def fake_run(**kwargs):
        cb = kwargs.get("progress_callback")
        if cb:
            cb("📥 Video bilgileri alınıyor... extract")
            cb("🎵 Ses analizi yapılıyor... audio")
            cb("📊 Klip adayları sıralanıyor... rank")
            cb("🤖 Yapay Zeka değerlendiriyor... llm")
            cb("⏱️ Sınırlar hassas hizalanıyor... align")
            cb("🎬 Klipler render ediliyor... cut")
            cb("extra message fallback")
        return mock_results

    with patch("core.pipeline.ClipperPipeline.run", side_effect=fake_run):
        await run_pipeline_async(job_id=job.id, url="http://yt.com/worker_success")

    updated = js.get(job.id)
    assert updated.status == "done"
    assert updated.progress == 100
    assert updated.result == mock_results


@pytest.mark.asyncio
async def test_pipeline_worker_failure():
    js = job_store
    job = js.create("http://yt.com/worker_failure")

    with patch("core.pipeline.ClipperPipeline.run", side_effect=RuntimeError("Pipeline crash")):
        await run_pipeline_async(job_id=job.id, url="http://yt.com/worker_failure")

    updated = js.get(job.id)
    assert updated.status == "failed"
    assert "Pipeline crash" in updated.error_msg
