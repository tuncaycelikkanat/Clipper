"""
core/instagram_uploader.py — Meta Graph API (Instagram Reels) Uploader

Uploads vertical video clips directly to Instagram Reels via official Meta Graph API v21.0.
Supports Resumable Container Upload for local files without requiring public web hosting.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


class InstagramUploader:
    """Official Meta Graph API client for publishing Instagram Reels."""

    GRAPH_API_VERSION = "v21.0"
    BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    def __init__(
        self,
        access_token: str | None = None,
        instagram_account_id: str | None = None,
    ) -> None:
        load_dotenv(override=True)
        self._explicit_token = access_token
        self._explicit_account = instagram_account_id

    @property
    def access_token(self) -> str:
        if self._explicit_token:
            return self._explicit_token
        load_dotenv(override=True)
        return os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()

    @property
    def account_id(self) -> str:
        if self._explicit_account:
            return self._explicit_account
        load_dotenv(override=True)
        return os.environ.get("INSTAGRAM_ACCOUNT_ID", "").strip()

    def is_authenticated(self) -> bool:
        """Return True if both access token and account ID are present."""
        return bool(self.access_token and self.account_id)

    def upload_temp_cover_image(self, thumbnail_path: str, clip_id: str | None = None) -> str | None:
        """Uploads local thumbnail or returns public cover URL so Meta Graph API can download it via cover_url."""
        if not thumbnail_path or not os.path.exists(thumbnail_path):
            return None

        public_base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
        if public_base and clip_id:
            public_thumb_url = f"{public_base}/api/clips/{clip_id}/thumbnail"
            logger.info("Using local server public cover_url for Instagram: {}", public_thumb_url)
            return public_thumb_url

        try:
            boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
            with open(thumbnail_path, "rb") as f:
                img_bytes = f.read()

            body = (
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="reqtype"\r\n\r\nfileupload\r\n'
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="time"\r\n\r\n72h\r\n'
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="fileToUpload"; filename="cover.jpg"\r\n'
                    f"Content-Type: image/jpeg\r\n\r\n"
                ).encode()
                + img_bytes
                + f"\r\n--{boundary}--\r\n".encode()
            )

            import urllib.request

            req = urllib.request.Request(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                url = resp.read().decode("utf-8").strip()
                if url.startswith("http"):
                    logger.info("Generated public cover_url for Instagram: {}", url)
                    return url
        except Exception as e:
            logger.warning("Could not create public cover_url for Instagram: {}", e)
        return None

    def create_resumable_container(
        self,
        file_size: int,
        caption: str = "",
        share_to_feed: bool = True,
        thumb_offset: int = 1000,
        cover_url: str | None = None,
        scheduled_publish_time: int | None = None,
    ) -> dict[str, Any]:
        """
        Step 1: Initiate a resumable Reels container session on Meta Graph API.
        """
        if not self.is_authenticated():
            raise RuntimeError(
                "Instagram kimlik bilgileri eksik. INSTAGRAM_ACCESS_TOKEN ve INSTAGRAM_ACCOUNT_ID gereklidir."
            )

        url = f"{self.BASE_URL}/{self.account_id}/media"
        params = {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "share_to_feed": str(share_to_feed).lower(),
            "access_token": self.access_token,
        }
        if cover_url:
            params["cover_url"] = cover_url
        else:
            params["thumb_offset"] = str(thumb_offset)

        if scheduled_publish_time:
            params["scheduled_publish_time"] = str(scheduled_publish_time)

        resp = requests.post(url, params=params, timeout=30)
        data = resp.json()

        # Meta Graph API: If cover_url fails or is rejected, fallback to thumb_offset
        if (resp.status_code != 200 or "id" not in data) and cover_url:
            logger.warning("Container creation with cover_url failed. Retrying with thumb_offset…")
            params.pop("cover_url", None)
            params["thumb_offset"] = str(thumb_offset)
            resp = requests.post(url, params=params, timeout=30)
            data = resp.json()

        # Meta Graph API: If scheduled_publish_time fails due to whitelist restrictions, fall back to instant publish
        if (resp.status_code != 200 or "id" not in data) and scheduled_publish_time:
            logger.warning(
                "Meta scheduled upload failed with whitelist requirement. Falling back to instant Reels publication…"
            )
            params.pop("scheduled_publish_time", None)
            resp = requests.post(url, params=params, timeout=30)
            data = resp.json()

        if resp.status_code != 200 or "id" not in data:
            error_msg = data.get("error", {}).get("message", resp.text)
            raise RuntimeError(f"Instagram Reels container oluşturulamadı: {error_msg}")

        return {
            "container_id": data["id"],
            "upload_url": data.get("uri"),  # Resumable upload URI
        }

    def upload_binary_to_container(
        self,
        upload_url: str,
        video_path: str,
        max_retries: int = 3,
    ) -> bool:
        """
        Step 2: Upload the local .mp4 binary chunks to Meta's upload URI with retries.
        Uses curl as primary native binary transport (avoids urllib3/requests proxy header chunking issues with Meta),
        falling back to requests if curl is not available.
        """
        path = Path(video_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Video dosyası bulunamadı: {video_path}")

        file_size = path.stat().st_size
        last_err = ""

        # 1. Primary: Native curl binary upload (Meta rupload strongly prefers this)
        import shutil
        import subprocess

        if shutil.which("curl"):
            for attempt in range(1, max_retries + 1):
                try:
                    cmd = [
                        "curl",
                        "-s",
                        "-w",
                        "\nHTTP_STATUS: %{http_code}\n",
                        "-X",
                        "POST",
                        upload_url,
                        "-H",
                        f"Authorization: OAuth {self.access_token}",
                        "-H",
                        "offset: 0",
                        "-H",
                        f"file_size: {file_size}",
                        "-H",
                        "Content-Type: application/octet-stream",
                        "--data-binary",
                        f"@{str(path)}",
                    ]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                    stdout = res.stdout or ""
                    status_code = None
                    if "HTTP_STATUS: " in stdout:
                        try:
                            status_code = int(stdout.split("HTTP_STATUS: ")[1].split("\n")[0].strip())
                        except Exception:
                            status_code = None

                    logger.debug(f"Meta rupload curl (attempt {attempt}/{max_retries}) status: {status_code}")
                    if status_code in (200, 201) or '"success":true' in stdout:
                        logger.info(f"Meta binary upload successful via curl ({file_size / (1024 * 1024):.1f} MB).")
                        return True

                    last_err = f"HTTP {status_code}: {stdout[:200]}"
                    logger.warning(f"Meta rupload curl attempt {attempt} failed: {last_err}")
                except Exception as e:
                    last_err = str(e)
                    logger.warning(f"Meta rupload curl attempt {attempt} error: {e}")

                if attempt < max_retries:
                    time.sleep(attempt * 3)

        # 2. Fallback: Python requests upload
        headers = {
            "Authorization": f"OAuth {self.access_token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Length": str(file_size),
            "Content-Type": "application/octet-stream",
        }

        for attempt in range(1, max_retries + 1):
            try:
                with open(path, "rb") as f:
                    resp = requests.post(upload_url, headers=headers, data=f, timeout=240)

                logger.debug(f"Meta rupload requests (attempt {attempt}/{max_retries}) status: {resp.status_code}")
                if resp.status_code in (200, 201):
                    logger.info(f"Meta binary upload successful ({file_size / (1024 * 1024):.1f} MB).")
                    return True

                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(f"Meta rupload attempt {attempt} failed: {last_err}")
            except Exception as e:
                last_err = str(e)
                logger.warning(f"Meta rupload attempt {attempt} error: {e}")

            if attempt < max_retries:
                time.sleep(attempt * 2)

        raise RuntimeError(f"Meta rupload binary aktarımı başarısız oldu: {last_err}")

    def check_container_status(self, container_id: str, timeout: int = 360, interval: int = 5) -> str:
        """
        Step 3: Poll the container until processing is FINISHED, PUBLISHED, or ERROR.
        """
        url = f"{self.BASE_URL}/{container_id}"
        params = {
            "fields": "status_code,status,id",
            "access_token": self.access_token,
        }

        start_time = time.time()
        poll_count = 0
        while time.time() - start_time < timeout:
            poll_count += 1
            try:
                resp = requests.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    status_code = data.get("status_code", "").upper()
                    elapsed = int(time.time() - start_time)
                    logger.debug(f"Instagram container {container_id} status: {status_code} ({elapsed}s)")

                    if status_code in ("FINISHED", "PUBLISHED"):
                        logger.info(f"Instagram container {container_id} is ready ({status_code}) after {elapsed}s.")
                        return status_code
                    if status_code in ("ERROR", "EXPIRED"):
                        err_detail = data.get("status") or status_code
                        raise RuntimeError(f"Instagram video işleme hatası ({status_code}): {err_detail}")
                else:
                    logger.warning(f"Meta status query failed (HTTP {resp.status_code}): {resp.text[:200]}")
            except requests.RequestException as req_err:
                logger.debug(f"Status poll connection issue: {req_err}")

            # Adaptive polling interval (5s -> 8s -> 10s)
            current_interval = interval if poll_count < 6 else (interval + 3 if poll_count < 15 else 10)
            time.sleep(current_interval)

        raise TimeoutError(f"Instagram video işleme zaman aşımına uğradı ({timeout} sn). Video Meta sunucularında henüz işlenemedi.")

    def publish_container(self, container_id: str, max_retries: int = 3) -> dict[str, Any]:
        """
        Step 4: Publish or finalize the verified container to the Instagram feed as a Reel.
        Includes retry mechanism for Meta's transient propagation delay errors.
        """
        url = f"{self.BASE_URL}/{self.account_id}/media_publish"
        params = {
            "creation_id": container_id,
            "access_token": self.access_token,
        }
        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                # Meta video işleme bittikten hemen sonra CDN yayılımı için ilk denemede 3sn bekle
                if attempt == 1:
                    time.sleep(3)
                resp = requests.post(url, params=params, timeout=35)
                data = resp.json()
                if resp.status_code == 200 and "id" in data:
                    media_id = data["id"]
                    logger.success(f"Instagram Reel başarıyla yayınlandı! Media ID: {media_id}")
                    return {
                        "media_id": media_id,
                        "url": f"https://www.instagram.com/reel/{media_id}",
                        "status": "published",
                    }
                err_obj = data.get("error", {})
                last_error = err_obj.get("message", resp.text)
                err_code = err_obj.get("code")
                # Meta Error Code 2 veya "retry your request later" transient hatası
                if attempt < max_retries and (err_code == 2 or "retry" in last_error.lower() or resp.status_code >= 500):
                    wait_sec = 6 * attempt  # 6s, 12s
                    logger.warning(
                        f"Meta media_publish geçici gecikme hatası (deneme {attempt}/{max_retries}): {last_error}. "
                        f"{wait_sec} sn bekleyip tekrar deneniyor…"
                    )
                    time.sleep(wait_sec)
                    continue
                break
            except requests.RequestException as req_exc:
                last_error = str(req_exc)
                if attempt < max_retries:
                    time.sleep(5 * attempt)
                    continue
                break
        raise RuntimeError(f"Instagram Reels yayına alınamadı: {last_error}")

    def upload_reel(
        self,
        video_path: str,
        caption: str = "",
        share_to_feed: bool = True,
        thumb_offset: int = 1000,
        thumbnail_path: str | None = None,
        cover_url: str | None = None,
        scheduled_publish_time: int | None = None,
        timeout: int = 360,
    ) -> dict[str, Any]:
        """
        End-to-end workflow: Create Container -> Upload Binary -> Wait Processing -> Publish Reel.
        """
        path = Path(video_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Video bulunamadı: {video_path}")

        file_size = path.stat().st_size
        logger.info(f"Uploading Reel to Instagram ({file_size / (1024 * 1024):.1f} MB)…")

        # Resolve cover_url if local thumbnail_path is provided
        resolved_cover_url = cover_url
        if not resolved_cover_url and thumbnail_path and os.path.exists(thumbnail_path):
            resolved_cover_url = self.upload_temp_cover_image(thumbnail_path)

        # 1 & 2. Container oluştur ve Binary yükle (Meta container'ı geçersiz kılarsa yeni container ile tekrar dener)
        max_container_attempts = 2
        last_upload_err = ""
        container_id = ""

        for container_attempt in range(1, max_container_attempts + 1):
            try:
                init_res = self.create_resumable_container(
                    file_size=file_size,
                    caption=caption,
                    share_to_feed=share_to_feed,
                    thumb_offset=thumb_offset,
                    cover_url=resolved_cover_url,
                    scheduled_publish_time=scheduled_publish_time,
                )
                container_id = init_res["container_id"]
                upload_url = init_res.get("upload_url")

                if upload_url:
                    logger.debug(
                        f"Uploading binary bytes to Meta endpoint: {upload_url} (Container attempt {container_attempt}/{max_container_attempts})"
                    )
                    self.upload_binary_to_container(upload_url, str(path), max_retries=2)

                # Yükleme başarılı, döngüden çık
                break
            except Exception as e:
                last_upload_err = str(e)
                logger.warning(f"Meta container yükleme denemesi {container_attempt}/{max_container_attempts} başarısız: {e}")
                if container_attempt < max_container_attempts:
                    time.sleep(3)
                else:
                    raise RuntimeError(f"Instagram Reels yükleme başarısız oldu: {last_upload_err}")

        # 3. İşleme durumunu bekle
        logger.info(f"Waiting for Meta processing (Container: {container_id})…")
        self.check_container_status(container_id, timeout=timeout)

        # 4. Yayına al / Planlamayı tamamla
        res = self.publish_container(container_id)
        if scheduled_publish_time:
            res["status"] = "scheduled"
        return res

    @staticmethod
    def generate_caption(
        clip: dict[str, Any],
        video_title: str = "",
        instagram_username: str = "",
        game_name: str = "",
        tags: list[str] | None = None,
        instagram_caption_override: str = "",
    ) -> str:
        """Generate an authentic, high-converting Instagram Reels caption with 20+ hashtags."""

        # Eğer AI tarafından üretilmiş özel bir Instagram caption varsa onu kullan
        if instagram_caption_override and instagram_caption_override.strip():
            return instagram_caption_override.strip()

        title = clip.get("title", "").replace("#Shorts", "").strip()
        hook = clip.get("hook_caption", "").strip()
        category = str(clip.get("category", "GAMING")).upper()

        # İlk satır: Hook veya başlık (caption'ın başına çarpıcı metin — Instagram'da title alanı yok)
        if hook:
            opener = f"{hook} 😂"
        elif title:
            opener = title
        else:
            opener = "Bu pozisyona inanamadım 😭"

        # Yoruma çeken soru (kategoriye göre değişen)
        if any(k in category for k in ["CLUTCH", "EPIC"]):
            question = "Siz bu pozisyonda ne yapardınız? 🎯"
        elif any(k in category for k in ["FUNNY", "FAIL"]):
            question = "Bunu gören herkes aynı tepkiyi verdi 😂 Siz ne yapardınız?"
        elif any(k in category for k in ["RAGE", "TILT"]):
            question = "Bu anı yaşasanız cihazı fırlatır mıydınız? 😡"
        else:
            question = "Fikirlerinizi yoruma bekliyorum! 👇"

        # Yayıncı mention
        mention_line = f"📌 {instagram_username}" if instagram_username else ""

        # Oyun bazlı hashtag'lar
        game_tags: list[str] = []
        if game_name:
            slug = game_name.lower().replace(" ", "")
            game_tags = [f"#{slug}", f"#{slug}türkiye", f"#{slug}clips", f"#{slug}highlight"]

        # Yayıncı bazlı hashtag'lar
        extra_tags: list[str] = []
        if tags:
            for t in tags[:8]:
                clean = t.lower().replace(" ", "").replace("-", "")
                if clean and len(clean) > 2:
                    extra_tags.append(f"#{clean}")

        # Temel Instagram hashtag seti (keşfet + gaming niche)
        base_hashtags = [
            "#reels", "#fyp", "#keşfet", "#viral", "#gaming", "#oyun",
            "#twitch", "#twitchturkiye", "#türkçeyayın", "#oyunkesitleri",
            "#türkçeoyun", "#gamer", "#gamingturkiye", "#highlight",
            "#shorts", "#komik", "#eğlenceli", "#youtube", "#tiktok", "#clip",
        ]

        # Tüm hashtag'leri birleştir (tekrarsız, toplam 20+ hedef)
        all_hashtags: list[str] = []
        seen: set[str] = set()
        for h in game_tags + extra_tags + base_hashtags:
            if h not in seen:
                seen.add(h)
                all_hashtags.append(h)

        hashtag_block = " ".join(all_hashtags[:30])  # Instagram 30 hashtag limiti

        lines = [opener, "", question]
        if mention_line:
            lines += ["", mention_line]
        lines += ["", hashtag_block]

        return "\n".join(line for line in lines if line is not None).strip()

