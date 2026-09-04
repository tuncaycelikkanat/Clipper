"""
backend/workers/pipeline_worker.py — Async pipeline runner.
Wraps core.pipeline.ClipperPipeline in a thread pool executor.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from typing import Any

from loguru import logger

from backend.workers.job_store import job_store


def _map_message_to_step_and_pct(msg: str, target_clips: int) -> tuple[str, int]:
    m = msg.lower()

    if "video bilgileri" in m or "ısı haritası" in m or "indiril" in m:
        return "extract", 15
    elif "ses frekansı" in m or "ses analizi" in m or "audio" in m or "dsp" in m or "enerji" in m or "vokal" in m:
        return "audio", 30
    elif "potansiyel klip" in m or "aday" in m or "sıralan" in m or "füzyon" in m or "yorum" in m:
        return "rank", 45
    elif "yapay zeka" in m or "gemini" in m or "değerlendir" in m or "yargı" in m or "llm" in m:
        return "llm", 60
    elif (
        "sınır" in m
        or "hizalan" in m
        or "kapak" in m
        or "thumbnail" in m
        or "alignment" in m
        or "oyun türü" in m
        or "yayıncı" in m
    ):
        return "align", 75
    elif (
        "dikey" in m
        or "render" in m
        or "facecam" in m
        or "kesil" in m
        or "whisper" in m
        or "altyazı" in m
        or "layout" in m
        or "başlık" in m
    ):
        clip_match = re.search(r"klip\s*#?(\d+)", m)
        if clip_match:
            c_idx = int(clip_match.group(1))
            pct = 75 + int((min(c_idx, target_clips) / max(1, target_clips)) * 22)
            return "cut", min(98, pct)
        return "cut", 85
    elif "tamamlandı" in m or "bitti" in m or "üretildi" in m:
        return "cut", 100
    return "processing", 50


async def run_pipeline_async(
    job_id: str,
    url: str,
    target_clips: int = 3,
    render_mode: str = "shorts_9x16_blur",
    add_subtitles: bool = True,
    add_hook_card: bool = True,
    enhance_colors: bool = True,
    api_key: str | None = None,
) -> None:
    """Launch pipeline in thread pool, stream progress via job_store SSE."""
    main_loop = asyncio.get_running_loop()

    job_store.update(job_id, status="running", progress=5, current_step="🚀 Pipeline başlatılıyor...")
    await job_store.push_sse(
        job_id, "progress", {"step": "extract", "progress": 5, "message": "🚀 Pipeline başlatılıyor..."}
    )

    def progress_callback(msg: str) -> None:
        step_name, pct = _map_message_to_step_and_pct(msg, target_clips)
        job_store.update(job_id, progress=pct, current_step=msg)
        try:
            asyncio.run_coroutine_threadsafe(
                job_store.push_sse(job_id, "progress", {"step": step_name, "progress": pct, "message": msg}),
                main_loop,
            )
        except Exception as exc:
            logger.debug("Failed to push SSE progress: {}", exc)

    try:
        from core.pipeline import ClipperPipeline

        results: list[dict[str, Any]] = await asyncio.to_thread(
            ClipperPipeline.run,
            url=url,
            target_clips=target_clips,
            render_mode=render_mode,
            add_subtitles=add_subtitles,
            add_hook_card=add_hook_card,
            enhance_colors=enhance_colors,
            api_key=api_key,
            progress_callback=progress_callback,
        )

        job_store.update(
            job_id, status="done", progress=100, current_step="🎉 Tüm klipler başarıyla üretildi!", result=results
        )
        await job_store.push_sse(job_id, "done", {"clips": results, "count": len(results)})
        logger.info("Pipeline job {} completed: {} clips", job_id, len(results))

    except Exception as exc:
        err = str(exc)
        logger.error("Pipeline job {} failed: {}", job_id, err)
        job_store.update(job_id, status="failed", error_msg=err)
        await job_store.push_sse(job_id, "error", {"message": err})
