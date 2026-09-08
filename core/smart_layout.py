"""
core/smart_layout.py — Akıllı Dikey Video Düzenleyici (Facecam Pro-Split & Sinematik Blur)
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from google import genai
from google.genai import types
from loguru import logger

try:
    import cv2

    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


class SmartLayoutEngine:
    """Yapay zeka tabanlı Facecam tespiti ve dikey video şablon motoru."""

    _facecam_cache: dict[str, dict[str, Any]] = {}

    def __init__(self, api_key: str | None = None):
        if not api_key:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                from dotenv import load_dotenv

                load_dotenv(".env")
                api_key = os.environ.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key else None
        self._facecam_cache = {}

    def detect_facecam(self, video_path: str, sample_time_sec: float = 3.0) -> dict[str, Any]:
        """Video karesinden yayıncının canlı kamera kutusunu cache destekli olarak tespit eder."""
        if video_path in self._facecam_cache:
            logger.debug("Facecam cache hit: {}", video_path)
            return dict(self._facecam_cache[video_path])

        result = self._detect_facecam_uncached(video_path, sample_time_sec)
        if self.client is not None or result.get("found") is True:
            self._facecam_cache[video_path] = result
        return result

    def _detect_facecam_uncached(self, video_path: str, sample_time_sec: float = 3.0) -> dict[str, Any]:
        """Video karesinden yayıncının canlı kamera kutusunu Gemini Model Havuzu ile tespit eder."""
        frame = None
        image_bytes = None

        if _CV2_AVAILABLE and os.path.exists(video_path):
            cap = cv2.VideoCapture(video_path)
            for t_sec in [sample_time_sec, max(0.5, sample_time_sec - 2.0), sample_time_sec + 2.0]:
                cap.set(cv2.CAP_PROP_POS_MSEC, t_sec * 1000)
                ret, f = cap.read()
                if ret and f is not None and f.shape[0] > 100:
                    frame = f
                    break
            cap.release()

        # FFmpeg fallback if frame is None
        if frame is None:
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(sample_time_sec),
                "-i",
                video_path,
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
            ]
            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
                if proc.stdout and len(proc.stdout) > 50:
                    image_bytes = proc.stdout
            except Exception as e:
                logger.debug("FFmpeg frame capture error: {}", e)

        if not image_bytes and frame is not None and _CV2_AVAILABLE:
            _, buffer = cv2.imencode(".jpg", frame)
            image_bytes = buffer.tobytes()

        if not self.client or not image_bytes:
            return {"found": False, "corner": "none", "box_1000": {"ymin": 0, "xmin": 0, "ymax": 0, "xmax": 0}}

        prompt = """Bu bir YouTube oyun/yayın videosundan alınmış ekran görüntüsüdür.
Ekranda yayıncının kendi odasından canlı kamera görüntüsü (Facecam / Webcam kutusu) var mı?
Önemli Kurallar:
- Oyun içi 3D karakterleri, oyun içi portreleri, mini haritaları veya chat kutularını ASLA facecam sanma.
- Yalnızca gerçek bir insanın odasından çekilen kamera kutusunu (genellikle sol/sağ alt veya sol/sağ üst köşede dikdörtgen çerçeve) tespit et.
- Eğer gerçek yayıncı kamerası varsa: "found": true, "corner": "<köşe>", "box_1000": {"ymin": int, "xmin": int, "ymax": int, "xmax": int} (0-1000 normalize koordinatlar) döndür.
- Eğer kamera yoksa: "found": false, "corner": "none", "box_1000": {"ymin":0,"xmin":0,"ymax":0,"xmax":0} döndür.

JSON formatında yanıt ver:
{
  "found": true/false,
  "corner": "bottom_left" | "bottom_right" | "top_left" | "top_right" | "left_center" | "none",
  "box_1000": {"ymin": int, "xmin": int, "ymax": int, "xmax": int}
}"""
        model_pool = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
        ]

        for model_name in model_pool:
            try:
                contents_payload: Any = [types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), prompt]
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents_payload,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                res = json.loads(response.text) if (response and response.text) else {}
                logger.info(
                    "Facecam AI detection result using {}: found={}, corner={}",
                    model_name,
                    res.get("found"),
                    res.get("corner"),
                )
                return res
            except Exception as e:
                err_str = str(e)
                logger.debug(
                    "Model {} denemesi başarısız: {} -> Havuzdaki sıradaki modele geçiliyor...",
                    model_name,
                    err_str[:80],
                )
                continue

        return {"found": False, "corner": "none", "box_1000": {"ymin": 0, "xmin": 0, "ymax": 0, "xmax": 0}}

    def build_ffmpeg_filter(
        self,
        src_w: int = 1920,
        src_h: int = 1080,
        facecam_info: dict[str, Any] | None = None,
    ) -> tuple[str, bool]:
        """FFmpeg dikey layout filtre zincirini üretir (AR-GE altın standardı)."""
        facecam_info = facecam_info or {}
        has_cam = facecam_info.get("found", False)

        if has_cam and "box_1000" in facecam_info:
            box = facecam_info["box_1000"]
            x1 = int(box.get("xmin", 0) * src_w / 1000)
            y1 = int(box.get("ymin", 0) * src_h / 1000)
            x2 = int(box.get("xmax", 0) * src_w / 1000)
            y2 = int(box.get("ymax", 0) * src_h / 1000)

            x1 = (x1 // 2) * 2
            y1 = (y1 // 2) * 2
            bw = ((max(10, x2 - x1)) // 2) * 2
            bh = ((max(10, y2 - y1)) // 2) * 2

            # Sanity checks: webcam box cannot be taller than 55% or wider than 50% of screen
            if bh > (src_h * 0.55) or bw > (src_w * 0.50) or bw < 40 or bh < 30:
                logger.warning(
                    "Geçersiz / aşırı büyük webcam boyutu tespit edildi (bw={}, bh={}). Sinematik blur moduna geçiliyor.",
                    bw,
                    bh,
                )
                has_cam = False

        if has_cam:
            # Aspect ratio locked camera height calculation
            cam_h = int(1080 * (bh / bw))
            # Clamp camera height between 360px and 680px so game video is never squeezed
            cam_h = max(360, min(680, cam_h))
            cam_h = (cam_h // 2) * 2
            game_h = 1920 - cam_h

            filter_str = f"""
            [0:v]scale=1920:1080,crop=936:1080:492:0,scale=1080:{game_h}:flags=lanczos[top];
            [1:v]scale=1920:1080,crop={bw}:{bh}:{x1}:{y1},scale=1080:{cam_h}:flags=lanczos[bot];
            [top][bot]vstack=inputs=2[v]
            """
            return filter_str.strip(), True
        else:
            filter_str = """
            [0:v]scale=1920:1080,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5[bg];
            [0:v]scale=1920:1080,crop=896:1080:512:0,scale=1080:1320:flags=lanczos[fg];
            [bg][fg]overlay=0:300[v]
            """
            return filter_str.strip(), False
