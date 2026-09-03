"""
core/thumbnail.py — Thumbnail Generator

Extracts high-quality JPEG thumbnail frames from local video files or
YouTube stream URLs using FFmpeg and yt-dlp.
"""

from __future__ import annotations

import os
import subprocess
from typing import List

from loguru import logger


class ThumbnailGenerator:
    """Generates JPEG thumbnail images from video clips or YouTube URLs."""

    # Default JPEG quality for FFmpeg (2 = near-lossless, 31 = worst)
    JPEG_QUALITY: int = 3

    @classmethod
    def extract_best_frame(
        cls,
        video_path: str,
        peak_time: float,
        output_path: str,
        width: int = 1280,
        height: int = 720,
    ) -> str:
        """Extract a single frame at *peak_time* from a local video file.

        Uses FFmpeg's fast seek (``-ss`` before ``-i``) to jump directly
        to the requested timestamp and capture one frame.  The frame is
        scaled to *width* × *height* while preserving aspect ratio with
        black letter-boxing.

        Args:
            video_path:  Path to the local video file (.mp4, .mkv, …).
            peak_time:   Timestamp in seconds to extract the frame from.
            output_path: Destination JPEG file path (created/overwritten).
            width:       Output image width in pixels (default 1280).
            height:      Output image height in pixels (default 720).

        Returns:
            *output_path* on success.

        Raises:
            RuntimeError: If FFmpeg exits with a non-zero status or the
                          output file was not created.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Scale preserving aspect ratio, pad with black to exact dimensions
        scale_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
        )

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(peak_time),
            "-i", video_path,
            "-vframes", "1",
            "-vf", scale_filter,
            "-q:v", str(cls.JPEG_QUALITY),
            output_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"FFmpeg thumbnail çıkarma başarısız oldu: {stderr[:300]}"
            ) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFmpeg bulunamadı. Lütfen kurulu olduğundan emin olun."
            ) from exc

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(
                f"Thumbnail oluşturulamadı (boş dosya): {output_path}"
            )

        logger.info(
            "extract_best_frame: thumbnail oluşturuldu -> {} (t={:.2f}s)",
            output_path,
            peak_time,
        )
        return output_path

    @classmethod
    def extract_best_frame_from_url(
        cls,
        url: str,
        start_time: float,
        peak_time: float,
        output_path: str,
    ) -> str:
        """Efficiently extract a thumbnail frame from a YouTube video URL.

        Rather than downloading the entire video, this method uses yt-dlp
        to resolve the best video stream URL and then instructs FFmpeg to
        seek to *peak_time* within that stream.

        Args:
            url:         YouTube video URL.
            start_time:  Clip start in seconds (used as a seek hint to keep
                         FFmpeg from reading the entire file up to
                         *peak_time*).
            peak_time:   Exact timestamp (seconds) to extract.
            output_path: Destination JPEG file path.

        Returns:
            *output_path* on success.

        Raises:
            RuntimeError: On yt-dlp resolution failure or FFmpeg error.
        """
        import yt_dlp

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        ydl_opts = {
            "format": "bestvideo[ext=mp4][height<=720]/bestvideo/best",
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info.get("url") or ""
                if not stream_url:
                    for fmt in info.get("formats", []):
                        if fmt.get("vcodec") != "none" and fmt.get("url"):
                            stream_url = fmt["url"]
                            break
        except Exception as exc:
            raise RuntimeError(
                f"yt-dlp stream URL çözümlenemedi: {exc}"
            ) from exc

        if not stream_url:
            raise RuntimeError("Geçerli video stream URL'si bulunamadı.")

        # Use start_time as an outer seek to speed up; peak_time as inner seek
        relative_peak = peak_time - start_time
        if relative_peak < 0:
            relative_peak = 0.0

        cmd = [
            "ffmpeg", "-y",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-ss", str(start_time),
            "-i", stream_url,
            "-ss", str(relative_peak),
            "-vframes", "1",
            "-q:v", str(cls.JPEG_QUALITY),
            output_path,
        ]

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=15,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("FFmpeg bulunamadı.") from exc
        except Exception as exc:
            # Fallback: YouTube orijinal video thumbnail resmini indir
            fb_thumb = info.get("thumbnail") if 'info' in locals() else None
            if fb_thumb:
                try:
                    import urllib.request
                    urllib.request.urlretrieve(fb_thumb, output_path)
                    logger.info("extract_best_frame_from_url: FFmpeg stream yerine fallback thumbnail indirildi -> {}", output_path)
                    return output_path
                except Exception:
                    pass
            stderr = ""
            if hasattr(exc, "stderr") and exc.stderr:
                stderr = exc.stderr.decode("utf-8", errors="replace")[:200]
            raise RuntimeError(
                f"Stream thumbnail çıkarma başarısız: {stderr or str(exc)}"
            ) from exc

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"Thumbnail oluşturulamadı: {output_path}")

        logger.info(
            "extract_best_frame_from_url: thumbnail oluşturuldu -> {} (t={:.2f}s)",
            output_path,
            peak_time,
        )
        return output_path

    @classmethod
    def batch_generate_thumbnails(
        cls,
        clips: List[dict],
        video_path_or_url: str,
        output_dir: str = "outputs/thumbnails",
    ) -> List[str]:
        """Generate thumbnail images for a list of clip dicts.

        For each clip in *clips*, extracts a frame at the clip's
        ``peak_time`` (falling back to the midpoint of
        ``start_time``/``end_time``).  Thumbnails are saved to
        *output_dir* as ``clip_{rank}_thumb.jpg``.

        Args:
            clips:              List of clip dicts.  Each must have at least
                                ``rank`` (int) and either ``peak_time``
                                (float) or ``start_time`` + ``end_time``
                                (float).
            video_path_or_url:  Local path to a downloaded video file **or**
                                a YouTube URL.  If the string starts with
                                ``http``, :meth:`extract_best_frame_from_url`
                                is used; otherwise :meth:`extract_best_frame`.
            output_dir:         Directory to write thumbnails into.
                                Created automatically if it does not exist.

        Returns:
            List of successfully generated thumbnail paths (skips failures
            without raising).
        """
        os.makedirs(output_dir, exist_ok=True)
        is_url = video_path_or_url.startswith("http")
        generated: List[str] = []

        for clip in clips:
            rank = clip.get("rank", 0)
            c_id = clip.get("clip_id") or clip.get("id")
            if not c_id:
                import uuid
                c_id = str(uuid.uuid4())[:8]
            
            start = float(clip.get("start_time", 0.0))
            end = float(clip.get("end_time", start + 30.0))
            peak = float(clip.get("peak_time", (start + end) / 2.0))
            
            out_path = os.path.join(output_dir, f"clip_{c_id}_thumb.jpg")

            try:
                if is_url:
                    cls.extract_best_frame_from_url(
                        url=video_path_or_url,
                        start_time=start,
                        peak_time=peak,
                        output_path=out_path,
                    )
                else:
                    dur = max(1.0, end - start)
                    local_seek = (peak - start) if (peak >= start and start > 0) else peak
                    local_seek = max(0.1, min(dur - 0.2, local_seek))
                    cls.extract_best_frame(
                        video_path=video_path_or_url,
                        peak_time=local_seek,
                        output_path=out_path,
                    )
                generated.append(out_path)
            except Exception as exc:
                logger.warning(
                    "batch_generate_thumbnails: Klip #{} thumbnail hatası: {}",
                    rank,
                    exc,
                )

        logger.info(
            "batch_generate_thumbnails: {}/{} thumbnail oluşturuldu",
            len(generated),
            len(clips),
        )
        return generated

    @classmethod
    def extract_candidates(
        cls,
        clip: dict,
        video_path_or_url: str,
        output_dir: str = "outputs/thumbnails",
    ) -> List[str]:
        """Extract multiple high-impact candidate frames for a single clip.
        
        Extracts:
        - 1. Peak Shock (Zirve ses / aksiyon patlaması)
        - 2. Hook Frame (İlk 2 saniyedeki kanca anı)
        - 3. Action Climax (%75 aksiyon düğümü)
        """
        os.makedirs(output_dir, exist_ok=True)
        is_url = video_path_or_url.startswith("http")
        rank = clip.get("rank", 1)
        start = float(clip.get("start_time", 0.0))
        end = float(clip.get("end_time", start + 30.0))
        dur = max(1.0, end - start)
        
        # 3 Key candidate timestamps
        peak_t = float(clip.get("peak_time", start + dur * 0.5))
        hook_t = min(end - 0.5, start + 2.0)
        action_t = min(end - 0.5, start + dur * 0.75)

        points = [
            ("main", peak_t, f"clip_{rank}_thumb.jpg"),
            ("hook", hook_t, f"clip_{rank}_thumb_hook.jpg"),
            ("action", action_t, f"clip_{rank}_thumb_action.jpg"),
        ]

        created = []
        for name, t_stamp, fname in points:
            out_file = os.path.join(output_dir, fname)
            try:
                if is_url:
                    cls.extract_best_frame_from_url(video_path_or_url, start, t_stamp, out_file)
                else:
                    # If extracting from a rendered clip, convert absolute video time to local clip time
                    local_seek = (t_stamp - start) if (t_stamp >= start and start > 0) else t_stamp
                    local_seek = max(0.1, min(dur - 0.2, local_seek))
                    cls.extract_best_frame(video_path_or_url, local_seek, out_file)
                created.append(out_file)
            except Exception as e:
                logger.warning(f"Failed candidate {name} for clip {rank}: {e}")

        return created

    @classmethod
    def generate_ai_vertical_thumbnail(
        cls,
        video_url_or_id: str,
        output_path: str,
        aspect_ratio: str = "2:3",
        api_key: Optional[str] = None,
    ) -> Optional[str]:
        """Downloads original YouTube 16:9 cover and reframes it into 2:3 vertical Shorts thumbnail using Gemini."""
        try:
            from core.ai_thumbnail_engine import AIThumbnailEngine
            engine = AIThumbnailEngine(api_key=api_key)
            return engine.process_video_to_thumbnail(
                video_url_or_id=video_url_or_id,
                output_path=output_path,
                aspect_ratio=aspect_ratio,
            )
        except Exception as e:
            logger.warning("generate_ai_vertical_thumbnail failed: {}", e)
            return None
