import os
import re
import subprocess
from typing import Optional, Callable, List, Dict, Any
import yt_dlp
from core.subtitles import SubtitleGenerator

class VideoCutter:
    """Extracts, formats, color-grades, and adds single-line Karaoke subtitles & hook cards to video clips."""

    def __init__(self, output_dir: str = "outputs/clips"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def cut_clip(
        self,
        url: str,
        start_time: float,
        end_time: float,
        clip_id: str,
        video_title: str = "clip",
        hook_caption: str = "",
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
        render_mode: str = "square_1x1_black",
        add_subtitles: bool = True,
        add_hook_card: bool = True,
        enhance_colors: bool = True,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Full-featured programmatic video editor:
        - Stream seek extraction
        - 1:1 Square / 9:16 Vertical formatting
        - Color grading & vibrancy boost
        - Single-line Karaoke word-by-word animated subtitles
        - First 3-sec floating hook title card
        """
        clean_title = re.sub(r'[^\w\s-]', '', video_title).strip().replace(' ', '_')[:25]
        edit_tags = f"{render_mode}_sub{'1' if add_subtitles else '0'}_hk{'1' if add_hook_card else '0'}_col{'1' if enhance_colors else '0'}"
        filename = f"{clean_title}_clip_{clip_id}_{int(start_time)}s_{int(end_time)}s_{edit_tags}.mp4"
        output_path = os.path.join(self.output_dir, filename)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            if progress_callback:
                progress_callback(f"Önbellekte bulundu: {filename}")
            return output_path

        temp_raw_cut = os.path.join(self.output_dir, f"raw_cut_{clip_id}_{int(start_time)}s.mp4")

        # Step 1: Fast Stream Seeking Cut (if not exists)
        if not os.path.exists(temp_raw_cut) or os.path.getsize(temp_raw_cut) == 0:
            if progress_callback:
                progress_callback(f"Stream üzerinden kesiliyor ({int(start_time)}s - {int(end_time)}s)...")

            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'download_ranges': yt_dlp.utils.download_range_func(None, [(start_time, end_time)]),
                'outtmpl': temp_raw_cut,
                'force_keyframes_at_cuts': True,
                'overwrites': True,
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except Exception:
                ydl_opts_fallback = {
                    'format': 'mp4/best',
                    'download_ranges': yt_dlp.utils.download_range_func(None, [(start_time, end_time)]),
                    'outtmpl': temp_raw_cut,
                    'force_keyframes_at_cuts': True,
                    'overwrites': True,
                    'quiet': True,
                    'no_warnings': True,
                    'extractor_args': {'youtube': {'player_client': ['android']}}
                }
                with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl:
                    ydl.download([url])

        if not os.path.exists(temp_raw_cut) or os.path.getsize(temp_raw_cut) == 0:
            raise RuntimeError("Ham video kesiti oluşturulamadı.")

        # Step 2: Prepare Subtitles (Single-line Karaoke ASS file) if enabled
        ass_path = None
        if add_subtitles and transcript_segments:
            if progress_callback:
                progress_callback("Dinamik tek satır Karaoke altyazı üretiliyor...")
            ass_path = os.path.join(self.output_dir, f"sub_{clip_id}_{int(start_time)}s.ass")
            
            is_vert = "9x16" in render_mode
            SubtitleGenerator.generate_ass_file(
                transcript_segments=transcript_segments,
                clip_start_sec=start_time,
                clip_end_sec=end_time,
                output_path=ass_path,
                video_width=1080,
                video_height=1920 if is_vert else 1080,
                font_size=42 if is_vert else 34,
                margin_v=240 if is_vert else 100
            )

        # Step 3: Construct FFmpeg Filter Graph
        if progress_callback:
            progress_callback("Programatik efektler (Renk + Kanca + Karaoke Altyazı) uygulanıyor...")

        filter_parts = []

        # A. Aspect Ratio Framing
        if render_mode == "square_1x1_black":
            filter_parts.append("scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2:color=black")
        elif render_mode == "shorts_9x16_black":
            filter_parts.append("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black")
        elif render_mode == "shorts_9x16_blur":
            filter_parts.append("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black")
        else: # original 16:9
            filter_parts.append("scale=1920:1080:force_original_aspect_ratio=decrease")

        # B. Color Grading (Vibrancy & Contrast Enhancement)
        if enhance_colors:
            filter_parts.append("eq=saturation=1.20:contrast=1.08:brightness=0.01,unsharp=3:3:0.6:3:3:0.3")

        # C. Floating Hook Title Card (First 3.5 seconds)
        if add_hook_card and hook_caption:
            clean_hook = re.sub(r'[\'"\\]', '', hook_caption).strip()[:50]
            hook_filter = (
                f"drawtext=text='{clean_hook}':font='DejaVu Sans':fontsize=32:fontcolor=white:"
                f"box=1:boxcolor=black@0.75:boxborderw=10:x=(w-text_w)/2:y=60:"
                f"enable='between(t,0,3.5)'"
            )
            filter_parts.append(hook_filter)

        # D. Dynamic Subtitles (ASS Burn-in)
        if ass_path and os.path.exists(ass_path):
            safe_ass = ass_path.replace(":", "\\:").replace("\\", "/")
            filter_parts.append(f"ass='{safe_ass}'")

        full_vf = ",".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            "-i", temp_raw_cut,
            "-vf", full_vf,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "21",
            "-c:a", "aac",
            "-b:a", "128k",
            output_path
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except subprocess.CalledProcessError as e:
            # Fallback without subtitle filter if libass error occurs
            filter_parts_fallback = [p for p in filter_parts if not p.startswith("ass=")]
            cmd_fallback = [
                "ffmpeg", "-y",
                "-i", temp_raw_cut,
                "-vf", ",".join(filter_parts_fallback),
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "21",
                "-c:a", "aac",
                "-b:a", "128k",
                output_path
            ]
            subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        if os.path.exists(temp_raw_cut):
            try:
                os.remove(temp_raw_cut)
            except Exception:
                pass

        if progress_callback:
            progress_callback("Klip başarıyla düzenlendi ve hazırlandı!")

        return output_path
