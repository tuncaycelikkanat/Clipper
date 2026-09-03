"""
core/instagram_uploader.py — Meta Graph API (Instagram Reels) Uploader

Uploads vertical video clips directly to Instagram Reels via official Meta Graph API v21.0.
Supports Resumable Container Upload for local files without requiring public web hosting.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

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
        access_token: Optional[str] = None,
        instagram_account_id: Optional[str] = None,
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


    def create_resumable_container(
        self,
        file_size: int,
        caption: str = "",
        share_to_feed: bool = True,
        thumb_offset: int = 1000,
        scheduled_publish_time: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Step 1: Initiate a resumable Reels container session on Meta Graph API.
        """
        if not self.is_authenticated():
            raise RuntimeError("Instagram kimlik bilgileri eksik. INSTAGRAM_ACCESS_TOKEN ve INSTAGRAM_ACCOUNT_ID gereklidir.")

        url = f"{self.BASE_URL}/{self.account_id}/media"
        params = {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "share_to_feed": str(share_to_feed).lower(),
            "thumb_offset": str(thumb_offset),
            "access_token": self.access_token,
        }
        if scheduled_publish_time:
            params["scheduled_publish_time"] = str(scheduled_publish_time)

        resp = requests.post(url, params=params, timeout=30)
        data = resp.json()

        # Meta Graph API: If scheduled_publish_time fails due to whitelist restrictions, fall back to instant publish
        if (resp.status_code != 200 or "id" not in data) and scheduled_publish_time:
            logger.warning("Meta scheduled upload failed with whitelist requirement. Falling back to instant Reels publication…")
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
    ) -> bool:
        """
        Step 2: Upload the local .mp4 binary chunks to Meta's upload URI.
        """
        path = Path(video_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Video dosyası bulunamadı: {video_path}")

        file_size = path.stat().st_size
        headers = {
            "Authorization": f"OAuth {self.access_token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Length": str(file_size),
            "Content-Type": "application/octet-stream",
        }

        with open(path, "rb") as f:
            resp = requests.post(upload_url, headers=headers, data=f, timeout=180)

        logger.debug(f"Meta rupload status: {resp.status_code}, response: {resp.text[:120]}")
        return True


    def check_container_status(self, container_id: str, timeout: int = 180, interval: int = 5) -> str:
        """
        Step 3: Poll the container until processing is FINISHED or ERROR.
        """
        url = f"{self.BASE_URL}/{container_id}"
        params = {
            "fields": "status_code,status",
            "access_token": self.access_token,
        }

        start_time = time.time()
        while time.time() - start_time < timeout:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                status_code = data.get("status_code", "").upper()
                logger.debug(f"Instagram container {container_id} status: {status_code}")

                if status_code == "FINISHED":
                    return "FINISHED"
                if status_code in ("ERROR", "EXPIRED"):
                    raise RuntimeError(f"Instagram video işleme hatası ({status_code}): {data.get('status')}")

            time.sleep(interval)

        raise TimeoutError(f"Instagram video işleme zaman aşımına uğradı ({timeout} sn).")

    def publish_container(self, container_id: str) -> Dict[str, Any]:
        """
        Step 4: Publish or finalize the verified container to the Instagram feed as a Reel.
        """
        url = f"{self.BASE_URL}/{self.account_id}/media_publish"
        params = {
            "creation_id": container_id,
            "access_token": self.access_token,
        }

        resp = requests.post(url, params=params, timeout=30)
        data = resp.json()

        if resp.status_code != 200 or "id" not in data:
            error_msg = data.get("error", {}).get("message", resp.text)
            raise RuntimeError(f"Instagram Reels yayına alınamadı: {error_msg}")

        media_id = data["id"]
        logger.success(f"Instagram Reel başarıyla yayınlandı/planlandı! Media ID: {media_id}")
        return {
            "media_id": media_id,
            "url": f"https://www.instagram.com/reel/{media_id}",
            "status": "published",
        }

    def upload_reel(
        self,
        video_path: str,
        caption: str = "",
        share_to_feed: bool = True,
        thumb_offset: int = 1000,
        scheduled_publish_time: Optional[int] = None,
        timeout: int = 180,
    ) -> Dict[str, Any]:
        """
        End-to-end workflow: Create Container -> Upload Binary -> Wait Processing -> Publish Reel.
        """
        path = Path(video_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Video bulunamadı: {video_path}")

        file_size = path.stat().st_size
        logger.info(f"Uploading Reel to Instagram ({file_size / (1024*1024):.1f} MB)…")

        # 1. Container oluştur
        init_res = self.create_resumable_container(
            file_size=file_size,
            caption=caption,
            share_to_feed=share_to_feed,
            thumb_offset=thumb_offset,
            scheduled_publish_time=scheduled_publish_time,
        )
        container_id = init_res["container_id"]
        upload_url = init_res.get("upload_url")

        # 2. Binary yükle (Eğer resumable URI döndüyse)
        if upload_url:
            logger.debug(f"Uploading binary bytes to Meta endpoint: {upload_url}")
            self.upload_binary_to_container(upload_url, str(path))

        # 3. İşleme durumunu bekle
        logger.info(f"Waiting for Meta processing (Container: {container_id})…")
        self.check_container_status(container_id, timeout=timeout)

        # 4. Yayına al / Planlamayı tamamla
        res = self.publish_container(container_id)
        if scheduled_publish_time:
            res["status"] = "scheduled"
        return res


    @staticmethod
    def generate_caption(clip: Dict[str, Any], video_title: str = "") -> str:
        """Generate an authentic, high-converting Instagram Reels caption."""
        title = clip.get("title", "").replace("#Shorts", "").strip()
        hook = clip.get("hook_caption", "").strip()

        if hook:
            opener = f"{hook} 😂\nSiz bu durumda ne yapardınız? Yorumlarda buluşalım 👇"
        else:
            opener = f"{title}\n\nFikirlerinizi yoruma bekliyorum! 👇"

        lines = [
            opener,
            "",
            f"🎬 Orijinal İçerik: {video_title}" if video_title else "",
            "",
            "#reels #gaming #oyun #oyunkesitleri #kesitler #türkçegaming #twitchtürkiye #viral",
        ]
        return "\n".join(line for line in lines if line)
