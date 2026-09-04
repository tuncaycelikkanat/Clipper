"""
core/feed.py — Channel/Playlist Feed Manager

Fetches and filters recent videos from YouTube channels and playlists
using yt-dlp, enabling automated new-video discovery for the scheduler.
"""

from __future__ import annotations

from typing import Any

import yt_dlp
from loguru import logger


class ChannelFeed:
    """Retrieves video listings from YouTube channels and playlists via yt-dlp."""

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

        # Sort newest-first by upload_date string ('YYYYMMDD'). Videoları tarihsiz
        # (upload_date boş) olanları "en yeni" kabul et (büyük bir anahtarla) ki
        # tarihi eksik olsa bile yeni videolar en üstte kalsın ve anchor tespitinde
        # kaçırılmasın.
        videos.sort(
            key=lambda v: v["upload_date"] if v["upload_date"] else "99999999",
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
    ) -> list[dict[str, Any]]:
        """Return only videos that have not yet been processed.

        Fetches up to ``max_count * 3`` recent videos from the channel and
        filters out IDs present in *processed_ids*.

        Args:
            channel_url:    YouTube channel or playlist URL.
            processed_ids:  List of video IDs already processed/stored.
            max_count:      Maximum number of *new* videos to return (default 10).

        Returns:
            Subset of :meth:`get_channel_videos` results excluding processed IDs,
            still sorted newest-first.
        """
        # Fetch more than needed so filtering still yields max_count results.
        fetch_count = max(max_count * 3, 30)
        all_videos = cls.get_channel_videos(channel_url, max_count=fetch_count)

        seen = set(processed_ids)
        new_videos = [v for v in all_videos if v["id"] not in seen]

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
