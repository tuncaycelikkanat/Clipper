"""
core/scheduler_manager.py — Background Channel Monitoring Scheduler

Wraps APScheduler's BackgroundScheduler to periodically check YouTube
channels for new videos and trigger processing callbacks.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    _APSCHEDULER_AVAILABLE = True
except ImportError:  # pragma: no cover
    _APSCHEDULER_AVAILABLE = False
    BackgroundScheduler = None  # type: ignore[assignment,misc]
    IntervalTrigger = None  # type: ignore[assignment,misc]

try:
    from core.logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from core.database import DatabaseManager  # noqa: F401 — optional
except ImportError:
    DatabaseManager = None  # type: ignore[assignment,misc]


class SchedulerManager:
    """Background scheduler for periodic channel monitoring.

    Usage::

        scheduler = SchedulerManager()
        scheduler.on_new_videos = my_callback  # called with (channel_url, [video_dicts])
        scheduler.start()

        job_id = scheduler.add_channel_job(
            "https://www.youtube.com/@PewDiePie", interval_hours=6
        )
        scheduler.list_jobs()
        scheduler.remove_job(job_id)
        scheduler.stop()
    """

    def __init__(self) -> None:
        if not _APSCHEDULER_AVAILABLE:
            raise ImportError(
                "APScheduler kurulu değil. Lütfen şunu çalıştırın: "
                "pip install apscheduler"
            )
        self._scheduler: BackgroundScheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1}
        )
        # Optional callback: Callable[[str, list[dict]], None]
        # Receives (channel_url, new_video_list) whenever new videos are found.
        self.on_new_videos: Optional[Callable[[str, List[Dict[str, Any]]], None]] = None

        # Internal registry: job_id -> channel_url
        self._job_registry: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background scheduler.

        Safe to call multiple times; no-op if already running.
        """
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("SchedulerManager başlatıldı.")

    def stop(self) -> None:
        """Gracefully stop the background scheduler.

        Waits for running jobs to complete before shutting down.
        Safe to call when already stopped.
        """
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            logger.info("SchedulerManager durduruldu.")

    # ------------------------------------------------------------------
    # Job Management
    # ------------------------------------------------------------------

    def add_channel_job(
        self,
        channel_url: str,
        interval_hours: int = 24,
        job_id: Optional[str] = None,
    ) -> str:
        """Register a recurring job that checks *channel_url* every N hours.

        Args:
            channel_url:    YouTube channel or playlist URL to monitor.
            interval_hours: How often (in hours) to check for new videos.
            job_id:         Optional explicit job ID; auto-generated if omitted.

        Returns:
            The job ID string that can later be used with :meth:`remove_job`.

        Raises:
            RuntimeError: If a job with the given *job_id* already exists.
        """
        if job_id is None:
            job_id = f"channel_{uuid.uuid4().hex[:8]}"

        if self._scheduler.get_job(job_id):
            raise RuntimeError(f"Job ID zaten mevcut: {job_id}")

        self._scheduler.add_job(
            func=self._run_channel_check,
            trigger=IntervalTrigger(hours=interval_hours),
            id=job_id,
            name=f"ChannelCheck:{channel_url[:60]}",
            args=[channel_url],
            replace_existing=False,
        )
        self._job_registry[job_id] = channel_url
        logger.info(
            "Kanal job eklendi: id=%s url=%s her %dh",
            job_id,
            channel_url,
            interval_hours,
        )
        return job_id

    def remove_job(self, job_id: str) -> None:
        """Remove a previously registered channel monitoring job.

        Args:
            job_id: Job ID returned by :meth:`add_channel_job`.

        Raises:
            KeyError: If *job_id* is not registered.
        """
        if not self._scheduler.get_job(job_id):
            raise KeyError(f"Job bulunamadı: {job_id}")
        self._scheduler.remove_job(job_id)
        self._job_registry.pop(job_id, None)
        logger.info("Job kaldırıldı: %s", job_id)

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of all registered jobs with their metadata.

        Returns:
            List of dicts::

                [
                    {
                        'id':          str,
                        'name':        str,
                        'channel_url': str,
                        'next_run':    str,   # ISO-8601 datetime string or ''
                        'trigger':     str,
                    },
                    ...
                ]
        """
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "channel_url": self._job_registry.get(job.id, ""),
                    "next_run": next_run.isoformat() if next_run else "",
                    "trigger": str(job.trigger),
                }
            )
        return jobs

    def get_status(self) -> Dict[str, Any]:
        """Return the current scheduler status.

        Returns:
            Dict with keys ``running`` (bool) and ``job_count`` (int).
        """
        return {
            "running": self._scheduler.running,
            "job_count": len(self._scheduler.get_jobs()),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_channel_check(self, channel_url: str) -> None:
        """Internal APScheduler callback that checks for new videos.

        Imports :class:`~core.feed.ChannelFeed` lazily to avoid circular
        imports and to remain functional even if the feed module has issues.

        Args:
            channel_url: The channel URL to check.
        """
        logger.info("Kanal kontrolü başlıyor: %s", channel_url)
        try:
            from core.feed import ChannelFeed  # lazy import

            # Determine already-processed IDs from DB (optional)
            processed_ids: List[str] = []
            if DatabaseManager is not None:
                try:
                    db = DatabaseManager()
                    processed_ids = db.get_processed_video_ids(channel_url)
                except Exception as db_err:
                    logger.warning("DB sorgu hatası, atlanıyor: %s", db_err)

            new_videos = ChannelFeed.get_new_videos(
                channel_url, processed_ids=processed_ids, max_count=10
            )

            if new_videos:
                logger.info(
                    "%d yeni video bulundu: %s", len(new_videos), channel_url
                )
                if self.on_new_videos is not None:
                    self.on_new_videos(channel_url, new_videos)
            else:
                logger.info("Yeni video yok: %s", channel_url)

        except Exception as exc:
            logger.error(
                "Kanal kontrolü sırasında hata (%s): %s", channel_url, exc
            )
