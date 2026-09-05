"""
core/cutter.py — Video Kesici, Dikey Sinematik Şablon ve Altyazı Motoru
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from typing import Any

import yt_dlp
from loguru import logger

from core.smart_layout import SmartLayoutEngine
from core.subtitles import SubtitleGenerator

try:
    from core.whisper_transcriber import WhisperTranscriber

    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False


class VideoCutter:
    """Extracts, formats, color-grades, and adds Karaoke subtitles & hook cards to video clips."""

    def __init__(
        self,
        output_dir: str = "outputs/clips",
        smart_layout: SmartLayoutEngine | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.smart_layout = smart_layout or SmartLayoutEngine()
        os.makedirs(self.output_dir, exist_ok=True)

    _STREAM_CACHE: dict[str, dict[str, Any]] = {}

    def cut_clip(
        self,
        url: str,
        start_time: float,
        end_time: float,
        clip_id: str,
        video_title: str = "clip",
        hook_caption: str = "",
        transcript_segments: list[dict[str, Any]] | None = None,
        render_mode: str = "shorts_9x16_black",
        add_subtitles: bool = False,
        add_hook_card: bool = False,
        enhance_colors: bool = True,
        use_whisper: bool = True,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str:
        clean_title = re.sub(r"[^\w\s-]", "", video_title).strip().replace(" ", "_")[:25]
        edit_tags = (
            f"{render_mode}"
            f"_sub{'1' if add_subtitles else '0'}"
            f"_hk{'1' if add_hook_card else '0'}"
            f"_col{'1' if enhance_colors else '0'}"
            f"_wsp{'1' if use_whisper else '0'}"
        )
        filename = f"{clean_title}_clip_{clip_id}_{int(start_time)}s_{int(end_time)}s_{edit_tags}.mp4"
        output_path = os.path.join(self.output_dir, filename)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            if progress_callback:
                progress_callback(f"Önbellekte bulundu: {filename}")
            return output_path

        temp_raw_cut = os.path.join(self.output_dir, f"raw_cut_{clip_id}_{int(start_time)}s.mp4")
        os.makedirs(os.path.dirname(temp_raw_cut), exist_ok=True)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        def is_valid_cut_file(p: str) -> bool:
            return os.path.exists(p) and os.path.getsize(p) > 0

        temp_raw_base = os.path.splitext(temp_raw_cut)[0]
        actual_raw_cut = None
        for ext in [".mp4", ".webm", ".mkv", ".m4v", ""]:
            cand = f"{temp_raw_base}{ext}" if ext else temp_raw_cut
            if is_valid_cut_file(cand):
                actual_raw_cut = cand
                break

        # Step 1: Fast Stream Seeking Cut
        if not actual_raw_cut:
            dur = max(1.0, end_time - start_time)
            # Local file direct seek
            if not url.startswith(("http://", "https://")) and os.path.exists(url):
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-ss",
                        str(start_time),
                        "-t",
                        str(dur),
                        "-i",
                        url,
                        "-c:v",
                        "libx264",
                        "-preset",
                        "ultrafast",
                        "-crf",
                        "18",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        "-avoid_negative_ts",
                        "make_zero",
                        "-shortest",
                        temp_raw_cut,
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if is_valid_cut_file(temp_raw_cut):
                    actual_raw_cut = temp_raw_cut
            else:
                # Fast Direct Stream Seeking (FFmpeg direct HTTP range request with ultrafast frame & audio sync)
                try:
                    if url not in VideoCutter._STREAM_CACHE:
                        ydl_opts_fast = {
                            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                            "quiet": True,
                            "no_warnings": True,
                        }
                        with yt_dlp.YoutubeDL(ydl_opts_fast) as ydl:
                            VideoCutter._STREAM_CACHE[url] = ydl.extract_info(url, download=False)

                    info = VideoCutter._STREAM_CACHE.get(url)
                    if info:
                        if "requested_formats" in info and len(info["requested_formats"]) >= 2:
                            v_url = info["requested_formats"][0].get("url")
                            a_url = info["requested_formats"][1].get("url")
                            if v_url and a_url:
                                cmd = [
                                    "ffmpeg",
                                    "-y",
                                    "-ss",
                                    str(start_time),
                                    "-t",
                                    str(dur),
                                    "-reconnect",
                                    "1",
                                    "-reconnect_at_eof",
                                    "1",
                                    "-reconnect_streamed",
                                    "1",
                                    "-reconnect_delay_max",
                                    "5",
                                    "-i",
                                    v_url,
                                    "-ss",
                                    str(start_time),
                                    "-t",
                                    str(dur),
                                    "-reconnect",
                                    "1",
                                    "-reconnect_at_eof",
                                    "1",
                                    "-reconnect_streamed",
                                    "1",
                                    "-reconnect_delay_max",
                                    "5",
                                    "-i",
                                    a_url,
                                    "-c:v",
                                    "libx264",
                                    "-preset",
                                    "ultrafast",
                                    "-crf",
                                    "18",
                                    "-c:a",
                                    "aac",
                                    "-b:a",
                                    "192k",
                                    "-avoid_negative_ts",
                                    "make_zero",
                                    "-shortest",
                                    temp_raw_cut,
                                ]
                                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                if is_valid_cut_file(temp_raw_cut):
                                    actual_raw_cut = temp_raw_cut
                        elif info.get("url"):
                            s_url = info["url"]
                            cmd = [
                                "ffmpeg",
                                "-y",
                                "-ss",
                                str(start_time),
                                "-t",
                                str(dur),
                                "-reconnect",
                                "1",
                                "-reconnect_at_eof",
                                "1",
                                "-reconnect_streamed",
                                "1",
                                "-reconnect_delay_max",
                                "5",
                                "-i",
                                s_url,
                                "-c:v",
                                "libx264",
                                "-preset",
                                "ultrafast",
                                "-crf",
                                "18",
                                "-c:a",
                                "aac",
                                "-b:a",
                                "192k",
                                "-avoid_negative_ts",
                                "make_zero",
                                "-shortest",
                                temp_raw_cut,
                            ]
                            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if is_valid_cut_file(temp_raw_cut):
                                actual_raw_cut = temp_raw_cut
                except Exception as exc:
                    logger.warning("Fast stream seek failed, trying fallback: {}", exc)

                # Fallback: yt-dlp download_ranges
                if not actual_raw_cut:

                    def download_ranges_callback(info_dict, ydl):
                        return [
                            {
                                "start_time": max(0.0, start_time),
                                "end_time": end_time,
                            }
                        ]

                    ydl_opts_primary = {
                        "format": "bestvideo[height<=1080][fps>=60]+bestaudio/bestvideo[height<=1080]+bestaudio/best",
                        "outtmpl": f"{temp_raw_base}.%(ext)s",
                        "download_ranges": download_ranges_callback,
                        "force_keyframes_at_cuts": True,
                        "concurrent_fragment_downloads": 4,
                        "buffersize": 1048576,
                        "retries": 3,
                        "quiet": True,
                        "no_warnings": True,
                    }

                    try:
                        with yt_dlp.YoutubeDL(ydl_opts_primary) as ydl:
                            ydl.download([url])
                    except Exception as exc:
                        logger.warning("Primary yt-dlp download attempt failed: {}", exc)

                    for ext in [".webm", ".mp4", ".mkv", ".m4v"]:
                        cand = f"{temp_raw_base}{ext}"
                        if is_valid_cut_file(cand):
                            actual_raw_cut = cand
                            break

                if not actual_raw_cut:
                    ydl_opts_fallback = {
                        "format": "bestvideo[height<=720]+bestaudio/best",
                        "outtmpl": f"{temp_raw_base}.%(ext)s",
                        "download_ranges": download_ranges_callback,
                        "force_keyframes_at_cuts": True,
                        "concurrent_fragment_downloads": 4,
                        "buffersize": 1048576,
                        "retries": 3,
                        "quiet": True,
                    }
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl:
                            ydl.download([url])
                    except Exception as exc:
                        logger.warning("Fallback yt-dlp download attempt failed: {}", exc)

                    for ext in [".webm", ".mp4", ".mkv", ".m4v"]:
                        cand = f"{temp_raw_base}{ext}"
                        if is_valid_cut_file(cand):
                            actual_raw_cut = cand
                            break

        if not actual_raw_cut or not os.path.exists(actual_raw_cut):
            raise RuntimeError("Ham video kesiti oluşturulamadı.")

        temp_raw_cut = actual_raw_cut

        # Step 2: Prepare Subtitles
        ass_path: str | None = None
        if add_subtitles:
            is_vert = "9x16" in render_mode or "smart" in render_mode
            sub_width = 1080
            sub_height = 1920 if is_vert else 1080
            sub_font = 42 if is_vert else 34
            sub_margin = 240 if is_vert else 100

            ass_path = os.path.join(self.output_dir, f"sub_{clip_id}_{int(start_time)}s.ass")
            whisper_used = False
            if use_whisper and _WHISPER_AVAILABLE:
                if progress_callback:
                    progress_callback("faster-whisper ile kelime zaman damgaları üretiliyor...")
                try:
                    transcriber = WhisperTranscriber(model_size="base", device="cpu", compute_type="int8")
                    word_segments = transcriber.transcribe_from_video(temp_raw_cut, language="tr")
                    if word_segments:
                        end_time - start_time
                        SubtitleGenerator.generate_ass_from_words(
                            word_segments=word_segments,
                            clip_start_sec=start_time,
                            clip_end_sec=end_time,
                            output_path=ass_path,
                            video_width=sub_width,
                            video_height=sub_height,
                            font_size=sub_font,
                            margin_v=sub_margin,
                        )
                        whisper_used = True
                        if progress_callback:
                            progress_callback(
                                f"Whisper: {len(word_segments)} kelime zaman damgalandı, ASS oluşturuldu."
                            )
                    else:
                        if progress_callback:
                            progress_callback("Whisper kelime bulamadı, YouTube ASR'ye geri dönülüyor...")
                except Exception as e:
                    logger.warning("Whisper transcription failed, falling back to ASR: {}", e)
                    if progress_callback:
                        progress_callback("Whisper hatası, YouTube ASR'ye geri dönülüyor...")

            if not whisper_used and transcript_segments:
                if progress_callback:
                    progress_callback("Dinamik tek satır Karaoke altyazı üretiliyor...")
                SubtitleGenerator.generate_ass_file(
                    transcript_segments=transcript_segments,
                    clip_start_sec=start_time,
                    clip_end_sec=end_time,
                    output_path=ass_path,
                    video_width=sub_width,
                    video_height=sub_height,
                    font_size=sub_font,
                    margin_v=sub_margin,
                )
            elif not whisper_used:
                ass_path = None

        # Step 3: FFmpeg Assembly
        filter_parts = []
        is_vertical = "9x16" in render_mode or "smart" in render_mode

        if is_vertical:
            if progress_callback:
                progress_callback("Akıllı Dikey Düzenleyici (Facecam / Sinematik Blur) uygulanıyor...")
            engine = SmartLayoutEngine()
            facecam_info = engine.detect_facecam(temp_raw_cut, sample_time_sec=min(3.0, (end_time - start_time) / 2.0))
            base_filter, has_cam = engine.build_ffmpeg_filter(facecam_info=facecam_info)

            post_filters = []
            if enhance_colors:
                post_filters.append("eq=saturation=1.20:contrast=1.08:brightness=0.01,unsharp=3:3:0.6:3:3:0.3")
            if add_hook_card and hook_caption:
                clean_hook = re.sub(r"[\'\"\\]", "", hook_caption).strip()[:50]
                alpha_expr = "if(lt(t,0.3),t/0.3,if(lt(t,3.0),1,max(0,(3.5-t)/0.5)))"
                post_filters.append(
                    f"drawtext=text='{clean_hook}':font='DejaVu Sans':fontsize=32:fontcolor=white:"
                    f"box=1:boxcolor=black@0.75:boxborderw=10:x=(w-text_w)/2:y=60:"
                    f"alpha='{alpha_expr}':enable='between(t,0,3.5)'"
                )
            if ass_path and os.path.exists(ass_path):
                safe_ass = ass_path.replace(":", "\\:").replace("\\", "/")
                post_filters.append(f"ass='{safe_ass}'")

            post_str = ("," + ",".join(post_filters)) if post_filters else ""
            complex_filter = (
                f"{base_filter};[v]{post_str.lstrip(',')}[outv]" if post_filters else f"{base_filter};[v]null[outv]"
            )

            if has_cam:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    temp_raw_cut,
                    "-i",
                    temp_raw_cut,
                    "-filter_complex",
                    complex_filter,
                    "-map",
                    "[outv]",
                    "-map",
                    "0:a",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "60",
                    "-c:a",
                    "aac",
                    "-ar",
                    "48000",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    "-af",
                    "asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11",
                    output_path,
                ]
            else:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    temp_raw_cut,
                    "-filter_complex",
                    complex_filter,
                    "-map",
                    "[outv]",
                    "-map",
                    "0:a",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "60",
                    "-c:a",
                    "aac",
                    "-ar",
                    "48000",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    "-af",
                    "asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11",
                    output_path,
                ]
        else:
            if render_mode == "square_1x1_black":
                filter_parts.append(
                    "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2:color=black"
                )
            elif render_mode == "shorts_9x16_black":
                filter_parts.append(
                    "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black"
                )
            else:
                filter_parts.append("scale=1920:1080:force_original_aspect_ratio=decrease")

            if enhance_colors:
                filter_parts.append("eq=saturation=1.20:contrast=1.08:brightness=0.01,unsharp=3:3:0.6:3:3:0.3")
            if add_hook_card and hook_caption:
                clean_hook = re.sub(r"[\'\"\\]", "", hook_caption).strip()[:50]
                alpha_expr = "if(lt(t,0.3),t/0.3,if(lt(t,3.0),1,max(0,(3.5-t)/0.5)))"
                filter_parts.append(
                    f"drawtext=text='{clean_hook}':font='DejaVu Sans':fontsize=32:fontcolor=white:"
                    f"box=1:boxcolor=black@0.75:boxborderw=10:x=(w-text_w)/2:y=60:"
                    f"alpha='{alpha_expr}':enable='between(t,0,3.5)'"
                )
            if ass_path and os.path.exists(ass_path):
                safe_ass = ass_path.replace(":", "\\:").replace("\\", "/")
                filter_parts.append(f"ass='{safe_ass}'")

            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                temp_raw_cut,
                "-vf",
                ",".join(filter_parts),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "18",
                "-r",
                "60",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                "-af",
                "asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11",
                output_path,
            ]

        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError as err:
            logger.warning("Primary FFmpeg render failed: {}. Retrying without subtitles...", err)
            if is_vertical:
                fallback_complex = f"{base_filter};[v]eq=saturation=1.20:contrast=1.08:brightness=0.01[outv]"
                if has_cam:
                    cmd_fallback = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        temp_raw_cut,
                        "-i",
                        temp_raw_cut,
                        "-filter_complex",
                        fallback_complex,
                        "-map",
                        "[outv]",
                        "-map",
                        "0:a",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "slow",
                        "-crf",
                        "18",
                        "-r",
                        "60",
                        "-c:a",
                        "aac",
                        "-ar",
                        "48000",
                        "-b:a",
                        "128k",
                        "-movflags",
                        "+faststart",
                        "-af",
                        "asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11",
                        output_path,
                    ]
                else:
                    cmd_fallback = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        temp_raw_cut,
                        "-filter_complex",
                        fallback_complex,
                        "-map",
                        "[outv]",
                        "-map",
                        "0:a",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "slow",
                        "-crf",
                        "18",
                        "-r",
                        "60",
                        "-c:a",
                        "aac",
                        "-ar",
                        "48000",
                        "-b:a",
                        "128k",
                        "-movflags",
                        "+faststart",
                        "-af",
                        "asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11",
                        output_path,
                    ]
            else:
                filter_parts_fallback = [p for p in filter_parts if not p.startswith("ass=")]
                cmd_fallback = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    temp_raw_cut,
                    "-vf",
                    ",".join(filter_parts_fallback) if filter_parts_fallback else "scale=1920:1080",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "slow",
                    "-crf",
                    "18",
                    "-r",
                    "60",
                    "-c:a",
                    "aac",
                    "-ar",
                    "48000",
                    "-b:a",
                    "128k",
                    "-movflags",
                    "+faststart",
                    "-af",
                    "asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11",
                    output_path,
                ]
            subprocess.run(cmd_fallback, capture_output=True, check=True)

        if os.path.exists(temp_raw_cut):
            try:
                os.remove(temp_raw_cut)
            except OSError as e:
                logger.debug("Could not remove temp cut file {}: {}", temp_raw_cut, e)

        if progress_callback:
            progress_callback("Klip başarıyla düzenlendi ve hazırlandı!")

        return output_path
