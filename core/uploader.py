"""
core/uploader.py — YouTube Shorts upload via the YouTube Data API v3.

Usage:
    uploader = YouTubeUploader()
    if not uploader.is_authenticated():
        uploader.authenticate()   # Opens browser once
    result = uploader.upload_short(video_path, title, description, tags)

Prerequisites:
    1. Go to https://console.cloud.google.com/
    2. Create a project → enable "YouTube Data API v3".
    3. Create OAuth 2.0 credentials (Desktop app) → download as credentials.json
       and place it in the project root (or pass credentials_path explicitly).
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request

# Google API imports — installed via pip install google-api-python-client google-auth-oauthlib
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from loguru import logger

# OAuth scopes required for uploading videos, setting thumbnails, and managing playlists
_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

_SETUP_INSTRUCTIONS = """
YouTube API credentials not found at '{path}'.

To set up YouTube upload:
1. Visit https://console.cloud.google.com/
2. Create (or select) a project.
3. Enable the "YouTube Data API v3".
4. Go to APIs & Services → Credentials → Create Credentials → OAuth client ID.
5. Choose "Desktop app", download the JSON file.
6. Save it as '{path}' in your project root.
"""


class YouTubeUploader:
    """Handles OAuth2 authentication and video uploads to YouTube Shorts."""

    def __init__(
        self,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
    ) -> None:
        """
        Initialise uploader.

        Args:
            credentials_path: Path to the OAuth2 client-secrets JSON file
                              downloaded from Google Cloud Console.
            token_path: Path where the user token will be cached after first
                        authentication.
        """
        self.credentials_path = str(Path(credentials_path).resolve())
        self.token_path = str(Path(token_path).resolve())
        self._credentials: Credentials | None = None

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def is_authenticated(self) -> bool:
        """Return True if a valid (non-expired) token exists on disk."""
        if not os.path.exists(self.token_path):
            return False
        try:
            creds = Credentials.from_authorized_user_file(self.token_path, _SCOPES)
            if creds and creds.valid:
                self._credentials = creds
                return True
            # Try refreshing
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                self._save_token(creds)
                self._credentials = creds
                return True
        except Exception as exc:
            logger.warning(f"Token validation failed: {exc}")
        return False

    def authenticate(self) -> None:
        """
        Run the OAuth2 browser flow to obtain and cache user credentials.
        Opens the default browser for the Google consent screen.

        Raises:
            FileNotFoundError: If credentials.json is missing (with setup
                               instructions).
        """
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(_SETUP_INSTRUCTIONS.format(path=self.credentials_path))

        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, _SCOPES)
        creds = flow.run_local_server(port=0)
        self._save_token(creds)
        self._credentials = creds
        logger.info("YouTube OAuth2 authentication successful. Token saved.")

    def _save_token(self, creds: Credentials) -> None:
        """Persist credentials to token_path."""
        with open(self.token_path, "w") as fh:
            fh.write(creds.to_json())

    def _get_credentials(self) -> Credentials:
        """Return valid credentials, raising if not authenticated."""
        if self._credentials and self._credentials.valid:
            return self._credentials
        if self.is_authenticated():
            return self._credentials  # type: ignore[return-value]
        raise RuntimeError("Not authenticated. Call authenticate() first or check token.json.")

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def get_playlists(self) -> list[dict]:
        """Return the authenticated user's playlists as [{id, title}]."""
        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
        playlists = []
        next_page = None
        while True:
            resp = (
                youtube.playlists()
                .list(
                    part="snippet",
                    mine=True,
                    maxResults=50,
                    pageToken=next_page,
                )
                .execute()
            )
            for item in resp.get("items", []):
                playlists.append(
                    {
                        "id": item["id"],
                        "title": item["snippet"]["title"],
                    }
                )
            next_page = resp.get("nextPageToken")
            if not next_page:
                break
        return playlists

    def add_to_playlist(self, video_id: str, playlist_id: str) -> None:
        """Insert video_id into the given playlist."""
        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id,
                    },
                }
            },
        ).execute()
        logger.info(f"Added video {video_id} to playlist {playlist_id}.")

    def upload_short(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        thumbnail_path: str | None = None,
        made_for_kids: bool = False,
        language: str = "tr",
        location_description: str = "Istanbul, Turkey",
        playlist_id: str | None = None,
        publish_at: str | None = None,
    ) -> dict:
        """
        Upload a video file as a YouTube Short.

        Args:
            video_path: Absolute or relative path to the .mp4 file.
            title: Video title (max 100 chars).
            description: Video description.
            tags: List of tag strings.
            thumbnail_path: Optional path to .jpg thumbnail file to attach.
            made_for_kids: Whether the video is made for children.
            language: BCP-47 language code for video & audio (default "tr").
            location_description: Human-readable recording location for geo-tag.
            playlist_id: If set, video is added to this YouTube playlist after upload.
            publish_at: Optional ISO-8601 UTC timestamp string (e.g. '2026-08-23T10:00:00.000Z')
                        for scheduled publishing. If set, privacyStatus is set to 'private' until that time.
        """
        video_path = str(Path(video_path).resolve())
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        # YouTube Shorts must be ≤60 s and vertical — we trust the caller.
        # Adding #Shorts to description helps the algorithm classify it.
        shorts_description = description
        if "#Shorts" not in shorts_description:
            shorts_description = f"{description}\n\n#Shorts".strip()

        status_dict: dict = {
            "privacyStatus": "private" if publish_at else "public",
            "selfDeclaredMadeForKids": made_for_kids,
        }
        if publish_at:
            status_dict["publishAt"] = publish_at

        body = {
            "snippet": {
                "title": title[:100],
                "description": shorts_description,
                "tags": tags or [],
                "categoryId": "20",  # Gaming
                "defaultLanguage": language,
                "defaultAudioLanguage": language,
            },
            "status": status_dict,
            "recordingDetails": {
                "locationDescription": location_description,
            },
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=4 * 1024 * 1024,  # 4 MB chunks
        )

        logger.info(f"Uploading '{title}' to YouTube…")
        request = youtube.videos().insert(
            part="snippet,status,recordingDetails",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.debug(f"Upload progress: {pct}%")

        video_id = response.get("id", "")
        upload_status = response.get("status", {}).get("uploadStatus", "unknown")
        url = f"https://www.youtube.com/shorts/{video_id}"
        logger.success(f"Upload complete → {url}")

        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                logger.info(f"Uploading custom thumbnail for video {video_id}…")
                thumb_media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=thumb_media,
                ).execute()
                logger.success("Custom thumbnail uploaded successfully.")
            except Exception as e:
                logger.warning(f"Could not upload custom thumbnail: {e}")

        if playlist_id:
            try:
                self.add_to_playlist(video_id, playlist_id)
                logger.success(f"Added to playlist {playlist_id}.")
            except Exception as e:
                logger.warning(f"Could not add to playlist: {e}")

        return {
            "video_id": video_id,
            "url": url,
            "status": upload_status,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def generate_description(clip: dict, video_title: str) -> str:
        """
        Auto-generate a YouTube Shorts description from clip metadata.

        Args:
            clip: ClipData-compatible dict from the pipeline.
            video_title: The original source video title.

        Returns:
            Formatted description string.
        """
        hook = clip.get("hook_caption", "").strip()
        category = str(clip.get("category", "GAMING")).upper()

        if hook:
            opener = f"{hook} 😂 Sizce burada ne yapılmalıydı?"
        elif any(c in category for c in ["FUNNY", "FAIL"]):
            opener = "Gülmekten yarıldığım anlardan biri ahahah. Sizce kim haklı? Yorumlara yazın 👇"
        elif any(c in category for c in ["CLUTCH", "EPIC"]):
            opener = "Böyle bir son saniye pozisyonunda ne yapardınız? Yorumlarda buluşalım 👇"
        else:
            opener = "Yayın sırasında yaşanan o efsane an! Düşüncelerinizi yorumlara bekliyorum."

        lines = [
            opener,
            "",
            f"🎬 Orijinal İçerik: {video_title}",
            "",
            "#Shorts #Gaming #OyunKesitleri #Oyun #Trending",
        ]
        return "\n".join(lines)

    def update_video_metadata(self, video_id: str, title: str, description: str, tags: list, category_id: str = "20"):
        from googleapiclient.discovery import build

        creds = self._get_credentials()
        if not creds:
            raise Exception("No credentials")
        youtube = build("youtube", "v3", credentials=creds)
        body = {
            "id": video_id,
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
                "defaultLanguage": "tr",
                "defaultAudioLanguage": "tr",
            },
        }
        res = youtube.videos().update(part="snippet", body=body).execute()
        return res
