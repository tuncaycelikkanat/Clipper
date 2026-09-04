"""
core/ai_thumbnail_engine.py — YouTube Thumbnail to 2:3 Vertical Shorts Re-framing Engine

Downloads the original YouTube 16:9 thumbnail (maxresdefault.jpg) and reframes it
into a high-impact, mobile-optimized 2:3 vertical Shorts cover using Gemini Vision & Image AI.
"""

from __future__ import annotations

import io
import os
import re
import urllib.request
from typing import List, Optional
from PIL import Image
from loguru import logger
from google import genai
from google.genai import types


class AIThumbnailEngine:
    """
    Downloads original YouTube thumbnail and reframes it into 
    a high-impact 2:3 vertical Shorts cover using Gemini / Nano Banana.
    """

    UNIVERSAL_REFRAME_PROMPT = (
        "Recompose and expand this 16:9 thumbnail into a unified, high-impact vertical format. "
        "Do not treat this as a simple letterbox extension with separate horizontal bands. Instead, "
        "reimagine the entire scene as a single, coherent, purpose-built vertical poster that naturally fills the taller frame:\n\n"
        "1. SUBJECT & FOCAL HIERARCHY: Automatically identify the primary subjects (characters, streamers, figures, or vehicles) "
        "from the original image. Proportionally scale and reposition them dynamically within the vertical composition so they become "
        "the commanding focal point of the scene. Preserve their exact visual identity, facial features, expressions, proportions, and clothing/design completely.\n\n"
        "2. HEADLINE & TEXT PRESERVATION: Detect any prominent title text or logo from the original image. Keep the exact text content, wording, "
        "font style, and colors intact, and position it prominently in the upper third or focal area of the vertical frame so it reads as a bold, clean, mobile-optimized thumbnail headline.\n\n"
        "3. UNIFIED SCENE & ENVIRONMENT: Dynamically expand the background environment (sky, room, lighting, terrain, background, atmosphere, and depth of field) "
        "to wrap seamlessly around the subjects, filling the entire vertical canvas as one cohesive scene with matching perspective and atmospheric lighting. Do not duplicate or clone any character or person.\n\n"
        "4. CINEMATIC COLOR & POLISH: Apply a unified cinematic color grade with deep moody shadows, rich contrast, and vibrant highlights matching the original artistic tone.\n\n"
        "The final output must look like a professional, masterfully composed vertical thumbnail designed from the ground up for mobile screens."
    )

    IMAGE_MODELS = [
        "gemini-2.0-flash-exp",
        "gemini-2.5-flash-image",
        "imagen-3.0-generate-002",
        "gemini-3.1-flash-image",
    ]

    def __init__(self, api_key: Optional[str] = None):
        if not api_key:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                try:
                    from dotenv import load_dotenv
                    load_dotenv(".env")
                    api_key = os.environ.get("GEMINI_API_KEY")
                except Exception:
                    pass
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    @staticmethod
    def extract_youtube_id(url_or_id: str) -> Optional[str]:
        """Extracts 11-char YouTube ID from URL or returns if already an ID."""
        if not url_or_id:
            return None
        url_or_id = str(url_or_id).strip()
        if len(url_or_id) == 11 and re.match(r'^[0-9A-Za-z_-]{11}$', url_or_id):
            return url_or_id
        m = re.search(r'(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})', url_or_id)
        return m.group(1) if m else None

    def download_youtube_cover(self, video_url_or_id: str, output_path: str) -> Optional[str]:
        """Downloads the highest available resolution cover (maxres -> sd -> hq)."""
        vid = self.extract_youtube_id(video_url_or_id)
        if not vid:
            logger.warning("Could not extract YouTube ID from: {}", video_url_or_id)
            return None

        candidates = [
            f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg",
            f"https://i.ytimg.com/vi/{vid}/sddefault.jpg",
            f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        ]
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        for url in candidates:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        data = resp.read()
                        if len(data) > 2000:
                            with open(output_path, "wb") as f:
                                f.write(data)
                            logger.info("Downloaded YouTube cover for {}: {} ({} bytes)", vid, url, len(data))
                            return output_path
            except Exception as e:
                logger.debug("Failed downloading cover candidate {}: {}", url, e)
                continue

        logger.warning("No valid YouTube cover found for ID: {}", vid)
        return None

    def generate_vertical_thumbnail(
        self, 
        source_image_path: str, 
        output_path: str, 
        aspect_ratio: str = "2:3",
        prompt: Optional[str] = None,
    ) -> Optional[str]:
        """
        Sends the 16:9 cover to Gemini with the Universal Re-framing Prompt and aspect ratio 2:3.
        """
        if not os.path.exists(source_image_path):
            raise FileNotFoundError(f"Source cover not found: {source_image_path}")

        if not self.client:
            logger.warning("GEMINI_API_KEY is not set for AIThumbnailEngine.")
            return None

        prompt_to_use = prompt or self.UNIVERSAL_REFRAME_PROMPT
        pil_img = Image.open(source_image_path)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        for model_name in self.IMAGE_MODELS:
            try:
                logger.info("Attempting vertical thumbnail re-framing using model: {}", model_name)
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=[pil_img, prompt_to_use],
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(aspect_ratio=aspect_ratio)
                    )
                )

                if response and hasattr(response, "candidates") and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, "content") and candidate.content and hasattr(candidate.content, "parts"):
                        for part in candidate.content.parts:
                            if hasattr(part, "inline_data") and part.inline_data:
                                img_data = part.inline_data.data
                                image = Image.open(io.BytesIO(img_data))
                                image.save(output_path, "JPEG", quality=95)
                                logger.info("AI vertical thumbnail successfully generated -> {}", output_path)
                                return output_path
            except Exception as e:
                logger.debug("Model {} image generation failed: {} -> Trying next model...", model_name, e)
                continue

        logger.warning("AI Thumbnail generation failed across all models. Falling back to local smart crop.")
        return self._fallback_local_crop(source_image_path, output_path, aspect_ratio)

    def _fallback_local_crop(self, source_path: str, output_path: str, aspect_ratio: str = "2:3") -> Optional[str]:
        """Local high quality vertical poster fallback (Blurred background + sharp centered 16:9 cover)."""
        try:
            from PIL import ImageFilter, ImageEnhance

            img = Image.open(source_path).convert("RGB")
            w, h = img.size

            if aspect_ratio == "9:16":
                canvas_w, canvas_h = 1080, 1920
            else:  # 2:3
                canvas_w, canvas_h = 1080, 1620

            # 1. Background: Scale to cover full canvas + Gaussian blur + darken
            scale_bg = max(canvas_w / w, canvas_h / h)
            bg_w, bg_h = int(w * scale_bg), int(h * scale_bg)
            bg = img.resize((bg_w, bg_h), Image.Resampling.LANCZOS)
            bg_left = (bg_w - canvas_w) // 2
            bg_top = (bg_h - canvas_h) // 2
            bg_cropped = bg.crop((bg_left, bg_top, bg_left + canvas_w, bg_top + canvas_h))
            bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=30))
            bg_darkened = ImageEnhance.Brightness(bg_blurred).enhance(0.65)

            # 2. Foreground: Fit original 16:9 cover in center with full width
            fg_w = canvas_w
            fg_h = int(canvas_w * (h / w))
            fg = img.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

            # 3. Paste fg into center of background
            paste_y = (canvas_h - fg_h) // 2
            bg_darkened.paste(fg, (0, paste_y))

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            bg_darkened.save(output_path, "JPEG", quality=95)
            logger.info("Local 2:3 vertical poster fallback generated -> {}", output_path)
            return output_path
        except Exception as e:
            logger.error("Local vertical poster fallback failed: {}", e)
            return None

    def process_video_to_thumbnail(
        self,
        video_url_or_id: str,
        output_path: str,
        aspect_ratio: str = "2:3"
    ) -> Optional[str]:
        """End-to-end convenience method: Downloads original cover and reframes to 2:3 vertical."""
        temp_cover = output_path.replace(".jpg", "_orig_16x9.jpg")
        if not self.download_youtube_cover(video_url_or_id, temp_cover):
            return None
        
        result = self.generate_vertical_thumbnail(
            source_image_path=temp_cover,
            output_path=output_path,
            aspect_ratio=aspect_ratio
        )
        # Cleanup temp 16:9 file if desired
        if os.path.exists(temp_cover):
            try:
                os.remove(temp_cover)
            except Exception:
                pass
        return result
