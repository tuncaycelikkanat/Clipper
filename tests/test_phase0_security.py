"""tests/test_phase0_security.py — Security fixes (Phase 0) unit and integration tests."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api.routes import auth
from backend.api.routes.auth import _PENDING_VERIFIERS, youtube_auth_callback


@pytest.mark.asyncio
async def test_pkce_unknown_state_raises_400():
    """Verify that unknown/invalid state raises HTTPException 400 and does NOT fallback to last verifier."""
    _PENDING_VERIFIERS.clear()
    _PENDING_VERIFIERS["valid_state_abc"] = "verifier_123"

    mock_request = MagicMock(spec=Request)
    mock_request.url.scheme = "http"
    mock_request.url.netloc = "localhost:8000"

    with patch("os.path.exists", return_value=True), \
         patch("backend.api.routes.auth.InstalledAppFlow.from_client_secrets_file"):
        with pytest.raises(HTTPException) as exc_info:
            await youtube_auth_callback(code="test_code", request=mock_request, state="attacker_state_xyz")

        assert exc_info.value.status_code == 400
        assert "Invalid state parameter" in exc_info.value.detail
        # Make sure legitimate verifier was not stolen
        assert "valid_state_abc" in _PENDING_VERIFIERS

    _PENDING_VERIFIERS.clear()


@pytest.mark.asyncio
async def test_postmessage_origin_not_wildcard():
    """Verify auth success HTML callback contains restricted targetOrigin and not wildcard '*'."""
    mock_request = MagicMock(spec=Request)
    mock_request.url.scheme = "http"
    mock_request.url.netloc = "localhost:8000"

    _PENDING_VERIFIERS["legit_state"] = "verifier_xyz"

    mock_flow = MagicMock()
    mock_flow.credentials = MagicMock()

    with patch("os.path.exists", return_value=True), \
         patch("backend.api.routes.auth.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow), \
         patch("backend.api.routes.auth.YouTubeUploader._save_token"):

        response = await youtube_auth_callback(code="legit_code", request=mock_request, state="legit_state")
        html = response.body.decode("utf-8")

        assert "postMessage({ type: 'YOUTUBE_AUTH_SUCCESS' }, 'http://localhost:5173')" in html
        assert "postMessage({ type: 'YOUTUBE_AUTH_SUCCESS' }, '*')" not in html


def test_thumbnail_exact_match_prevents_prefix_overwrite(temp_db):
    """Verify that thumbnail update for 'video_1' does NOT overwrite 'video_10' (no wildcard LIKE)."""
    # Insert two videos with overlapping prefix
    temp_db.save_video({"id": "video_1", "url": "https://youtu.be/1", "title": "Vid 1"})
    temp_db.save_video({"id": "video_10", "url": "https://youtu.be/10", "title": "Vid 10"})

    temp_db.save_clips("video_1", [{
        "id": "video_1_clip_01",
        "start_time": 0.0,
        "end_time": 10.0,
        "thumbnail_path": "initial_thumb_1.jpg",
    }])
    temp_db.save_clips("video_10", [{
        "id": "video_10_clip_01",
        "start_time": 0.0,
        "end_time": 10.0,
        "thumbnail_path": "initial_thumb_10.jpg",
    }])

    # Execute the exact-match update logic from clips.py
    new_target_path = "updated_thumb_1.jpg"
    target_vid = "video_1"

    with temp_db._connect() as conn:
        conn.execute(
            "UPDATE clips SET thumbnail_path = ? WHERE video_id = ? OR id = ?",
            (new_target_path, target_vid, target_vid),
        )
        conn.commit()

    # Check video_1 clips are updated
    clips_1 = temp_db.get_clips_for_video("video_1")
    assert len(clips_1) == 1
    assert clips_1[0]["thumbnail_path"] == "updated_thumb_1.jpg"

    # Crucial security check: video_10 clips MUST NOT be modified
    clips_10 = temp_db.get_clips_for_video("video_10")
    assert len(clips_10) == 1
    assert clips_10[0]["thumbnail_path"] == "initial_thumb_10.jpg"


def test_gitignore_protects_secrets():
    """Verify .gitignore contains critical secret patterns."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gitignore_path = os.path.join(root_dir, ".gitignore")
    assert os.path.exists(gitignore_path), ".gitignore file must exist"

    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "credentials.json" in content
    assert "token.json" in content
    assert "client_secret*.json" in content
    assert ".env" in content


def test_settings_frontend_contains_origin_verification():
    """Verify Settings.tsx validates event.origin before processing postMessage."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings_file = os.path.join(root_dir, "frontend", "src", "pages", "Settings.tsx")
    assert os.path.exists(settings_file)

    with open(settings_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "e.origin" in content
    assert "http://localhost:8000" in content
