import os
from unittest.mock import MagicMock, patch

import pytest

from core.notifier import Notifier


@pytest.fixture
def clean_env():
    # Clean up relevant environment variables before tests
    env_vars = ["DISCORD_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    old_env = {}
    for var in env_vars:
        if var in os.environ:
            old_env[var] = os.environ.pop(var)
    yield
    for var, val in old_env.items():
        os.environ[var] = val


def test_init_from_env(clean_env):
    os.environ["DISCORD_WEBHOOK_URL"] = "http://env-discord"
    os.environ["TELEGRAM_BOT_TOKEN"] = "env-token"
    os.environ["TELEGRAM_CHAT_ID"] = "env-chat"
    notifier = Notifier()
    assert notifier.webhook_url == "http://env-discord"
    assert notifier.telegram_token == "env-token"
    assert notifier.telegram_chat_id == "env-chat"


def test_format_clip_message_contains_title():
    clip = {
        "title": "Epic Headshot",
        "category": "FPS",
        "score": 95,
        "hook_caption": "Insane shot",
        "duration_formatted": "15s",
        "start_formatted": "02:10",
        "end_formatted": "02:25",
        "rank": 1,
    }
    msg = Notifier.format_clip_message(clip, "/path/to/clip.mp4")
    assert "Epic Headshot" in msg
    assert "Insane shot" in msg
    assert "clip.mp4" in msg


def test_format_clip_message_no_hook():
    clip = {"title": "Epic Headshot", "rank": 1}
    msg = Notifier.format_clip_message(clip, "/path/to/clip.mp4")
    assert "Epic Headshot" in msg
    assert "Hook:" not in msg


@patch("requests.post")
def test_send_discord_webhook_calls_requests(mock_post):
    mock_post.return_value.status_code = 200
    Notifier.send_discord_webhook("http://fake.webhook", "Test message")
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://fake.webhook"
    assert kwargs["json"]["content"] == "Test message"
    assert "embeds" not in kwargs["json"]


@patch("requests.post")
def test_send_discord_webhook_with_embed(mock_post):
    mock_post.return_value.status_code = 200
    Notifier.send_discord_webhook("http://fake.webhook", "Test message", embed={"title": "embed title"})
    kwargs = mock_post.call_args[1]
    assert kwargs["json"]["embeds"] == [{"title": "embed title"}]


@patch("requests.post")
def test_send_discord_webhook_error(mock_post):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("http error")
    mock_post.return_value = mock_response
    with pytest.raises(Exception, match="http error"):
        Notifier.send_discord_webhook("http://fake.webhook", "Test message")


@patch("requests.post")
def test_send_telegram_success(mock_post):
    mock_post.return_value.status_code = 200
    Notifier.send_telegram("bot-token", "chat-id", "Hello")
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/botbot-token/sendMessage"
    assert kwargs["json"]["chat_id"] == "chat-id"
    assert kwargs["json"]["text"] == "Hello"


@patch("requests.post")
def test_send_telegram_error(mock_post):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("telegram error")
    mock_post.return_value = mock_response
    with pytest.raises(Exception, match="telegram error"):
        Notifier.send_telegram("bot-token", "chat-id", "Hello")


def test_notify_clip_ready_logs_when_no_webhook(clean_env):
    notifier = Notifier()
    clip = {"title": "Test Title"}
    with patch("core.notifier.logger.info") as mock_info:
        notifier.notify_clip_ready(clip, "/outputs/clips/clip_2.mp4")
        mock_info.assert_called_once()
        assert "no webhook configured" in mock_info.call_args[0][0]


@patch.object(Notifier, "send_discord_webhook")
def test_notify_clip_ready_discord_success(mock_discord):
    notifier = Notifier(webhook_url="http://discord")
    clip = {"title": "Test"}
    notifier.notify_clip_ready(clip, "clip.mp4")
    mock_discord.assert_called_once()


@patch.object(Notifier, "send_telegram")
@patch.object(Notifier, "send_discord_webhook")
def test_notify_clip_ready_discord_fails_telegram_success(mock_discord, mock_telegram):
    notifier = Notifier(webhook_url="http://discord", telegram_token="token", telegram_chat_id="chat")
    mock_discord.side_effect = Exception("discord down")

    with patch("core.notifier.logger.warning") as mock_warn:
        notifier.notify_clip_ready({"title": "Test"}, "clip.mp4")
        mock_discord.assert_called_once()
        mock_telegram.assert_called_once()
        mock_warn.assert_any_call("Discord notification failed: discord down")


@patch.object(Notifier, "send_telegram")
def test_notify_clip_ready_telegram_success_no_discord(mock_telegram):
    notifier = Notifier(telegram_token="token", telegram_chat_id="chat")
    notifier.notify_clip_ready({"title": "Test"}, "clip.mp4")
    mock_telegram.assert_called_once()


@patch.object(Notifier, "send_telegram")
@patch.object(Notifier, "send_discord_webhook")
def test_notify_clip_ready_all_fail(mock_discord, mock_telegram):
    notifier = Notifier(webhook_url="http://discord", telegram_token="token", telegram_chat_id="chat")
    mock_discord.side_effect = Exception("discord down")
    mock_telegram.side_effect = Exception("telegram down")

    with patch("core.notifier.logger.info") as mock_info, patch("core.notifier.logger.warning") as mock_warn:
        notifier.notify_clip_ready({"title": "Test"}, "clip.mp4")
        mock_discord.assert_called_once()
        mock_telegram.assert_called_once()
        assert mock_warn.call_count == 2
        mock_info.assert_called_once()
        assert "no webhook configured" in mock_info.call_args[0][0]


def test_build_discord_embed_full_clip():
    clip = {
        "title": "Epic",
        "category": "FPS",
        "score": 95,
        "hook_caption": "Insane shot",
        "duration_formatted": "15s",
        "start_formatted": "02:10",
        "end_formatted": "02:25",
    }
    embed = Notifier._build_discord_embed(clip, "clip.mp4")
    assert embed["title"] == "🎬 Epic"
    assert embed["description"] == "File: `clip.mp4`"
    assert len(embed["fields"]) == 5
    assert embed["fields"][4]["name"] == "Hook Caption"
    assert embed["fields"][4]["value"] == "Insane shot"


def test_build_discord_embed_minimal_clip():
    clip = {"title": "Epic"}
    embed = Notifier._build_discord_embed(clip, "clip.mp4")
    assert embed["title"] == "🎬 Epic"
    assert len(embed["fields"]) == 4  # category, score, duration, range
