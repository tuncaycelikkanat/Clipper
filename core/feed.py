"""
core/feed.py — Channel/Playlist Feed Manager

Fetches and filters recent videos from YouTube channels and playlists
using yt-dlp, enabling automated new-video discovery for the scheduler.
"""

from __future__ import annotations

import datetime
import re
from typing import Any
import xml.etree.ElementTree as ET

import requests
import yt_dlp
from loguru import logger


class ChannelFeed:
    """Retrieves video listings from YouTube channels and playlists via yt-dlp."""

    @staticmethod
    def extract_channel_id(url: str) -> str | None:
        """URL veya metinden 24 karakterlik YouTube UC... kanal ID'sini ayıklar."""
        m = re.search(r"(?:channel/|videos\.xml\?channel_id=)(UC[a-zA-Z0-9_-]{22})", url)
        if m:
            return m.group(1)
        return None

    @classmethod
    def fetch_youtube_rss_videos(cls, channel_id: str, timeout: float = 6.0) -> list[dict[str, Any]]:
        """YouTube resmi Atom RSS beslemesi üzerinden kesin ISO yayın tarihleriyle son videoları çeker."""
        clean_id = channel_id.strip()
        if not clean_id or not clean_id.startswith("UC"):
            return []

        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={clean_id}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            resp = requests.get(rss_url, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                logger.debug("YouTube RSS returned status {} for channel {}", resp.status_code, clean_id)
                return []

            root = ET.fromstring(resp.text)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "yt": "http://www.youtube.com/xml/schemas/2015",
            }
            results: list[dict[str, Any]] = []
            for entry in root.findall("atom:entry", ns):
                vid_elem = entry.find("yt:videoId", ns)
                title_elem = entry.find("atom:title", ns)
                pub_elem = entry.find("atom:published", ns)
                if vid_elem is not None and vid_elem.text:
                    vid_id = vid_elem.text.strip()
                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Başlıksız"
                    published_iso = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""
                    upload_date = published_iso[:10].replace("-", "") if published_iso else ""
                    results.append(
                        {
                            "id": vid_id,
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                            "title": title,
                            "upload_date": upload_date,
                            "published_at": published_iso,
                            "duration": 0,
                            "view_count": 0,
                        }
                    )
            logger.debug("YouTube RSS retrieved {} videos for channel {}", len(results), clean_id)
            return results
        except Exception as exc:
            logger.debug("Failed to fetch YouTube RSS for {}: {}", clean_id, exc)
            return []

    @staticmethod
    def is_video_too_old(
        video: dict[str, Any],
        max_age_days: int | None = None,
        allow_undated: bool = True,
    ) -> bool:
        """Videonun yayınlanma tarihi max_age_days sınırını aşıyorsa True döner."""
        if not max_age_days or max_age_days <= 0:
            return False

        if video.get("is_older_than_rss"):
            return True

        # 1. ISO 8601 yayın tarihi kontrolü
        pub = video.get("published_at")
        if pub:
            try:
                dt = datetime.datetime.fromisoformat(pub.replace("Z", "+00:00"))
                age = datetime.datetime.now(datetime.timezone.utc) - dt
                return age.total_seconds() > (max_age_days * 86400)
            except Exception:
                pass

        # 2. YYYYMMDD upload_date kontrolü
        u_date = video.get("upload_date")
        if u_date and len(u_date) == 8:
            try:
                dt = datetime.datetime.strptime(u_date, "%Y%m%d").replace(tzinfo=datetime.timezone.utc)
                age = datetime.datetime.now(datetime.timezone.utc) - (dt + datetime.timedelta(days=1))
                return age.total_seconds() > (max_age_days * 86400)
            except Exception:
                pass

        return not allow_undated


    _BASE_OPTS: dict[str, Any] = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,  # fast metadata-only listing
        "ignoreerrors": True,
        "http_headers": {"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8"},
        "extractor_args": {"youtube": ["lang=tr"]},
    }

    @staticmethod
    def normalize_channel_url(url: str) -> str:
        """Kanal URL'sini sonuna /videos ekleyerek video sekmesine yönlendirir."""
        clean = url.strip().rstrip("/")
        if (
            ("youtube.com" in clean or "youtu.be" in clean)
            and "list=" not in clean
            and not any(
                clean.endswith(tab)
                for tab in ("/videos", "/shorts", "/streams", "/playlists", "/featured", "/community")
            )
        ):
            clean += "/videos"
        return clean

    @classmethod
    def get_channel_videos(
        cls,
        channel_url: str,
        max_count: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve recent videos from a YouTube channel or playlist URL.

        Uses yt-dlp's flat extraction to quickly gather metadata without
        downloading any video content.

        Args:
            channel_url: YouTube channel URL (``/c/``, ``/@``, ``/channel/``)
                         or playlist URL (``playlist?list=…``).
            max_count:   Maximum number of videos to return (default 20).

        Returns:
            List of video dicts sorted newest-first
        """
        normalized_url = cls.normalize_channel_url(channel_url)
        opts = dict(cls._BASE_OPTS)
        opts["playlistend"] = max_count * 2  # Biraz fazla çekip filtrele

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(normalized_url, download=False)
        except Exception as exc:
            # Fallback to original url if normalized failed
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(channel_url, download=False)
            except Exception:
                raise RuntimeError(f"Kanal/oynatma listesi bilgileri alınamadı: {exc}") from exc

        if info is None:
            raise RuntimeError(f"yt-dlp kanal URL'sinden veri döndürmedi: {channel_url}")

        raw_entries = info.get("entries") or []
        # Flatten nested entries (e.g. tabs)
        entries: list[dict[str, Any]] = []
        for e in raw_entries:
            if not e:
                continue
            if isinstance(e, dict) and "entries" in e and isinstance(e["entries"], list):
                entries.extend([sub for sub in e["entries"] if sub])
            else:
                entries.append(e)

        videos: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            vid_id = str(entry.get("id") or "").strip()
            if not vid_id:
                continue

            # Kanal ID'lerini (UC...) veya oynatma listesi sekme başlıklarını filtrele
            if vid_id.startswith("UC") and len(vid_id) >= 20:
                continue
            if entry.get("ie_key") in ("YoutubeTab", "YoutubeChannel") or (
                entry.get("_type") == "playlist" and "entries" not in entry
            ):
                continue

            videos.append(
                {
                    "id": vid_id,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "title": entry.get("title") or "Başlıksız",
                    "upload_date": entry.get("upload_date") or "",
                    "duration": int(entry.get("duration") or 0),
                    "view_count": int(entry.get("view_count") or 0),
                }
            )

        # Try to resolve channel_id and enrich with RSS feed data (for real publication dates)
        channel_id = cls.extract_channel_id(channel_url) or (info.get("channel_id") if info else None)
        rss_videos: list[dict[str, Any]] = []
        if channel_id:
            rss_videos = cls.fetch_youtube_rss_videos(channel_id)

        if rss_videos:
            rss_map = {rv["id"]: rv for rv in rss_videos}
            for v in videos:
                if v["id"] in rss_map:
                    v["published_at"] = rss_map[v["id"]].get("published_at", "")
                    if not v.get("upload_date"):
                        v["upload_date"] = rss_map[v["id"]].get("upload_date", "")
                else:
                    v["is_older_than_rss"] = True
            # Include any RSS videos not extracted by flat extraction
            existing_ids = {v["id"] for v in videos}
            for rv in reversed(rss_videos):
                if rv["id"] not in existing_ids:
                    videos.insert(0, rv)

        # Sort newest-first by published_at (ISO datetime) or upload_date ('YYYYMMDD')
        videos.sort(
            key=lambda v: v.get("published_at") or v.get("upload_date") or "",
            reverse=True,
        )

        logger.info("get_channel_videos: {} geçerli video alındı (URL: {})", len(videos), channel_url)
        return videos[:max_count]

    @classmethod
    def get_new_videos(
        cls,
        channel_url: str,
        processed_ids: list[str],
        max_count: int = 10,
        max_age_days: int | None = None,
    ) -> list[dict[str, Any]]:
        fetch_count = max(max_count * 3, 30)
        all_videos = cls.get_channel_videos(channel_url, max_count=fetch_count)

        seen = set(processed_ids)
        new_videos = [
            v for v in all_videos
            if v["id"] not in seen and not cls.is_video_too_old(v, max_age_days)
        ]

        logger.info(
            "get_new_videos: {} yeni, {} işlenmiş, {} toplam alındı",
            len(new_videos),
            len(seen),
            len(all_videos),
        )
        return new_videos[:max_count]

    @classmethod
    def get_video_ids_from_playlist(cls, playlist_url: str) -> list[str]:
        """Extract only the video IDs from a YouTube playlist.

        Args:
            playlist_url: YouTube playlist URL (``playlist?list=…``).

        Returns:
            Ordered list of video ID strings.

        Raises:
            RuntimeError: If yt-dlp fails to process the playlist.
        """
        try:
            with yt_dlp.YoutubeDL(cls._BASE_OPTS) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
        except Exception as exc:
            raise RuntimeError(f"Oynatma listesi ID'leri alınamadı: {exc}") from exc

        if info is None:
            return []

        entries = info.get("entries") or []
        ids = [e["id"] for e in entries if e and e.get("id")]

        logger.info("get_video_ids_from_playlist: {} ID alındı ({})", len(ids), playlist_url)
        return ids
