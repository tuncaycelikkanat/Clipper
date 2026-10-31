"""backend/api/routes/auth.py — YouTube OAuth2 flow."""

from __future__ import annotations

import os
import sys

_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _R not in sys.path:
    sys.path.insert(0, _R)

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import InstalledAppFlow
from loguru import logger

from core.uploader import YouTubeUploader, _SCOPES

router = APIRouter(prefix="/auth", tags=["auth"])


_PENDING_VERIFIERS: dict[str, str] = {}


def _get_redirect_uri(request: Request | None = None) -> str:
    if request:
        base_url = str(request.base_url).rstrip("/")
        return f"{base_url}/api/auth/youtube/callback"
    return "http://localhost:8000/api/auth/youtube/callback"


@router.get("/youtube/status")
async def youtube_auth_status():
    try:
        uploader = YouTubeUploader()
        authenticated = uploader.is_authenticated()
        return {"authenticated": authenticated}
    except Exception as e:
        return {"authenticated": False, "error": str(e)}


@router.get("/youtube/url")
async def youtube_auth_url(request: Request):
    """Generates and returns Google OAuth2 consent screen URL with PKCE tracking."""
    uploader = YouTubeUploader()
    if not os.path.exists(uploader.credentials_path):
        raise HTTPException(
            status_code=400,
            detail=f"credentials.json bulunamadı ({uploader.credentials_path}). Lütfen Google Cloud Console'dan OAuth credentials dosyasını ekleyin.",
        )

    try:
        redirect_uri = _get_redirect_uri(request)
        flow = InstalledAppFlow.from_client_secrets_file(
            uploader.credentials_path,
            _SCOPES,
            redirect_uri=redirect_uri,
        )
        auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")
        if flow.code_verifier:
            _PENDING_VERIFIERS[state] = flow.code_verifier
            # Clean up old verifiers if too many accumulated
            if len(_PENDING_VERIFIERS) > 20:
                for k in list(_PENDING_VERIFIERS.keys())[:-10]:
                    _PENDING_VERIFIERS.pop(k, None)
        return {"url": auth_url}
    except Exception as e:
        logger.error("OAuth URL generation error: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/youtube/callback", response_class=HTMLResponse)
async def youtube_auth_callback(code: str, request: Request, state: str | None = None):
    """Handles OAuth2 code exchange redirect from Google with PKCE code_verifier."""
    uploader = YouTubeUploader()
    if not os.path.exists(uploader.credentials_path):
        raise HTTPException(status_code=400, detail="credentials.json not found")

    try:
        redirect_uri = _get_redirect_uri(request)
        flow = InstalledAppFlow.from_client_secrets_file(
            uploader.credentials_path,
            _SCOPES,
            redirect_uri=redirect_uri,
        )
        if not state or state not in _PENDING_VERIFIERS:
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        code_verifier = _PENDING_VERIFIERS.pop(state)

        fetch_kwargs: dict[str, str] = {"code": code}
        if code_verifier:
            fetch_kwargs["code_verifier"] = code_verifier

        flow.fetch_token(**fetch_kwargs)
        creds = flow.credentials
        uploader._save_token(creds)
        logger.success("YouTube OAuth2 successfully authenticated via web callback.")

        return HTMLResponse(
            content="""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <title>YouTube Bağlantısı Başarılı</title>
  <style>
    body {
      background-color: #09090b;
      color: #fafafa;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
    }
    .card {
      background: #18181b;
      border: 1px solid #27272a;
      border-radius: 12px;
      padding: 32px 40px;
      text-align: center;
      max-width: 420px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    .icon {
      font-size: 48px;
      margin-bottom: 16px;
    }
    h1 {
      font-size: 20px;
      color: #22c55e;
      margin: 0 0 8px 0;
    }
    p {
      font-size: 14px;
      color: #a1a1aa;
      margin: 0 0 20px 0;
      line-height: 1.5;
    }
    .btn {
      background: #dc2626;
      color: white;
      border: none;
      border-radius: 6px;
      padding: 10px 20px;
      font-size: 13px;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>YouTube Bağlantısı Başarılı!</h1>
    <p>Google hesabınız başarıyla yetkilendirildi. Bu sekmeyi kapatıp Clipper paneline dönebilirsiniz.</p>
    <button class="btn" onclick="window.close()">Pencereyi Kapat</button>
  </div>
  <script>
    if (window.opener) {
      window.opener.postMessage({ type: 'YOUTUBE_AUTH_SUCCESS' }, '*');
    }
    setTimeout(() => {
      window.close();
    }, 2500);
  </script>
</body>
</html>""",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("OAuth code exchange error: {}", e)
        return HTMLResponse(
            status_code=500,
            content=f"""<!DOCTYPE html>
<html>
<body style="background:#09090b; color:#ef4444; font-family:sans-serif; text-align:center; padding-top:50px;">
  <h2>❌ Yetkilendirme Başarısız</h2>
  <p style="color:#a1a1aa;">Hata detayı: {e}</p>
</body>
</html>""",
        )


@router.post("/youtube/authenticate")
async def youtube_authenticate():
    """Trigger the OAuth2 browser flow on the server side."""
    try:
        uploader = YouTubeUploader()
        uploader.authenticate()
        return {"success": True, "authenticated": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
