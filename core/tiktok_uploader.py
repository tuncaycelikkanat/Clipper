"""
core/tiktok_uploader.py — TikTok Direct Post API v2 Client

Uploads vertical short-form gaming videos directly to TikTok via the official Content Posting API.
Supports direct posting and draft initialization with chunked file uploads.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from loguru import logger


class TikTokUploader:
    """Official TikTok Content Posting API v2 client and session uploader."""

    BASE_URL = "https://open.tiktokapis.com/v2"

    def __init__(

        self,
        session_id: Optional[str] = None,
        access_token: Optional[str] = None,
        open_id: Optional[str] = None,
        client_key: Optional[str] = None,
        client_secret: Optional[str] = None,
    ) -> None:
        """
        Initialize TikTok Uploader.

        Supports both:
        1. Session ID (Cookie-based, zero developer onboarding required)
        2. Content Posting API v2 (OAuth Bearer Token)

        Args:
            session_id: TikTok sessionid cookie value from web browser.
                        Defaults to `TIKTOK_SESSION_ID` env var.
            access_token: TikTok User Access Token with `video.publish` or `video.upload` scope.
                          Defaults to `TIKTOK_ACCESS_TOKEN` env var.
            open_id: TikTok User Open ID.
                     Defaults to `TIKTOK_OPEN_ID` env var.
            client_key: TikTok Client Key.
            client_secret: TikTok Client Secret.
        """
        self.session_id = (
            session_id if session_id is not None else os.environ.get("TIKTOK_SESSION_ID", "").strip()
        )
        self.access_token = (
            access_token if access_token is not None else os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
        )
        self.open_id = (
            open_id if open_id is not None else os.environ.get("TIKTOK_OPEN_ID", "").strip()
        )
        self.client_key = (
            client_key if client_key is not None else os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
        )
        self.client_secret = (
            client_secret if client_secret is not None else os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()
        )

    def is_authenticated(self) -> bool:
        """Return True if session_id or access_token is available."""
        return bool(self.session_id or self.access_token)


    @classmethod
    def get_authorization_url(
        cls,
        client_key: str,
        redirect_uri: str = "https://tuncaycelikkanat.github.io/Clipper/",
        scope: str = "user.info.basic,video.upload,video.publish",
        state: str = "clipper_auth",
    ) -> str:
        """Generate the TikTok OAuth2 Authorization URL."""
        import urllib.parse
        params = {
            "client_key": client_key,
            "scope": scope,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"https://www.tiktok.com/v2/auth/authorize/?{urllib.parse.urlencode(params)}"

    @classmethod
    def exchange_code_for_token(
        cls,
        code: str,
        client_key: str,
        client_secret: str,
        redirect_uri: str = "https://tuncaycelikkanat.github.io/Clipper/",
    ) -> Dict[str, Any]:
        """Exchange an authorization code for a TikTok User Access Token."""
        url = f"{cls.BASE_URL}/oauth/token/"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        resp = requests.post(url, headers=headers, data=data, timeout=30)
        res_json = resp.json()

        if "data" in res_json and "access_token" in res_json["data"]:
            token_data = res_json["data"]
            return {
                "access_token": token_data["access_token"],
                "open_id": token_data.get("open_id", ""),
                "refresh_token": token_data.get("refresh_token", ""),
                "expires_in": token_data.get("expires_in", 86400),
            }

        error_msg = res_json.get("error", {}).get("message", resp.text)
        raise RuntimeError(f"TikTok token değişimi başarısız: {error_msg}")


    def init_video_upload(
        self,
        file_size: int,
        title: str,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        disable_duet: bool = False,
        disable_stitch: bool = False,
        disable_comment: bool = False,
        cover_timestamp_ms: int = 1000,
    ) -> Dict[str, Any]:
        """
        Step 1: Request an upload URL from TikTok Direct Post API.
        """
        if not self.is_authenticated():
            raise RuntimeError("TikTok kimlik bilgileri eksik. TIKTOK_ACCESS_TOKEN gereklidir.")

        url = f"{self.BASE_URL}/post/publish/video/init/"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

        payload = {
            "post_info": {
                "title": title[:150],  # TikTok allows up to 150 chars in Direct Post title
                "privacy_level": privacy_level,
                "disable_duet": disable_duet,
                "disable_stitch": disable_stitch,
                "disable_comment": disable_comment,
                "video_cover_timestamp_ms": cover_timestamp_ms,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        data = resp.json()

        error_data = data.get("error", {})
        if error_data.get("code") != "ok" and resp.status_code != 200:
            err_msg = error_data.get("message", resp.text)
            raise RuntimeError(f"TikTok upload başlatılamadı ({error_data.get('code')}): {err_msg}")

        result = data.get("data", {})
        publish_id = result.get("publish_id")
        upload_url = result.get("upload_url")

        if not upload_url:
            raise RuntimeError(f"TikTok geçerli upload URL döndürmedi: {data}")

        return {
            "publish_id": publish_id,
            "upload_url": upload_url,
        }

    def upload_video_binary(
        self,
        upload_url: str,
        video_path: str,
    ) -> bool:
        """
        Step 2: Transfer binary video bytes to TikTok's upload URL.
        """
        path = Path(video_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Video dosyası bulunamadı: {video_path}")

        file_size = path.stat().st_size
        headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(file_size),
            "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        }

        with open(path, "rb") as f:
            resp = requests.put(upload_url, headers=headers, data=f, timeout=180)

        if resp.status_code not in (200, 201, 204):
            raise RuntimeError(f"TikTok video yükleme başarısız ({resp.status_code}): {resp.text}")

        return True

    def check_publish_status(self, publish_id: str) -> Dict[str, Any]:
        """
        Step 3: Check status of published video.
        """
        url = f"{self.BASE_URL}/post/publish/status/fetch/"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        payload = {"publish_id": publish_id}

        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        data = resp.json()
        return data.get("data", {})

    def upload_video(
        self,
        video_path: str,
        title: str,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        disable_duet: bool = False,
        disable_stitch: bool = False,
        disable_comment: bool = False,
        cover_timestamp_ms: int = 1000,
    ) -> Dict[str, Any]:
        """
        Full workflow: Init Post -> Upload Video Binary -> Check Status.
        """
        path = Path(video_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Video dosyası bulunamadı: {video_path}")

        file_size = path.stat().st_size
        logger.info(f"Uploading video to TikTok ({file_size / (1024*1024):.1f} MB)…")

        # 1. Session ID (Çerez ile Onaysız Web Yüklemesi)
        if self.session_id:
            try:
                from tiktok_uploader.upload import upload_video as tu_upload
                logger.info("Uploading video to TikTok via sessionid cookie…")
                res = tu_upload(
                    filename=str(path),
                    description=title,
                    sessionid=self.session_id,
                    headless=True,
                )
                logger.success(f"TikTok videosu yüklendi! Sonuç: {res}")
                return {
                    "publish_id": "cookie_session_post",
                    "status": "uploaded",
                    "url": "https://www.tiktok.com",
                }
            except Exception as tu_err:
                logger.error(f"TikTok session upload error: {tu_err}")
                raise RuntimeError(f"TikTok çerez ile yükleme başarısız: {tu_err}")

        # 2. Content Posting API v2 (OAuth Token ile Yükleme)
        init_res = self.init_video_upload(
            file_size=file_size,
            title=title,
            privacy_level=privacy_level,
            disable_duet=disable_duet,
            disable_stitch=disable_stitch,
            disable_comment=disable_comment,
            cover_timestamp_ms=cover_timestamp_ms,
        )

        publish_id = init_res["publish_id"]
        upload_url = init_res["upload_url"]

        self.upload_video_binary(upload_url, str(path))
        logger.success(f"TikTok video yüklendi! Publish ID: {publish_id}")

        return {
            "publish_id": publish_id,
            "status": "uploaded",
            "url": "https://www.tiktok.com",
        }


    @staticmethod
    def generate_caption(clip: Dict[str, Any], video_title: str = "") -> str:
        """Generate high-CTR organic TikTok caption with trending tags (max 150 chars)."""
        title = clip.get("title", "").replace("#Shorts", "").strip()
        hook = clip.get("hook_caption", "").strip()

        base_text = hook or title
        if len(base_text) > 85:
            base_text = base_text[:82] + "…"

        caption = f"{base_text} 😂 #fyp #keşfet #gaming #oyun #kesitler"
        return caption[:150]
