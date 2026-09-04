"""
core/notifier.py — Webhook and notification system for the clipper pipeline.

Supports Discord webhook, Telegram Bot API, and falls back to loguru logging.

Usage:
    notifier = Notifier(webhook_url="https://discord.com/api/webhooks/…")
    notifier.notify_clip_ready(clip, render_path="/outputs/clips/clip_1.mp4")
"""

from __future__ import annotations

import os

import requests
from loguru import logger


class Notifier:
    """
    Sends notifications when clips are ready.

    Priority order:
        1. Discord webhook (if webhook_url is set)
        2. Telegram Bot (if telegram_token + telegram_chat_id are set)
        3. Loguru log (always as fallback)
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        telegram_token: str | None = None,
        telegram_chat_id: str | None = None,
    ) -> None:
        """
        Initialise the notifier.

        Args:
            webhook_url: Discord-compatible webhook URL.
            telegram_token: Telegram bot token (from @BotFather).
            telegram_chat_id: Telegram chat / channel ID to post messages in.
        """
        # Allow environment variable overrides as a convenience
        self.webhook_url: str | None = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
        self.telegram_token: str | None = telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id: str | None = telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notify_clip_ready(self, clip: dict, render_path: str) -> None:
        """
        Send a notification when a clip has been rendered.

        Tries Discord first, then Telegram, then falls back to logging.

        Args:
            clip: ClipData-compatible dict from the pipeline.
            render_path: Absolute path to the rendered .mp4 file.
        """
        message = self.format_clip_message(clip, render_path)
        notified = False

        if self.webhook_url:
            try:
                embed = self._build_discord_embed(clip, render_path)
                self.send_discord_webhook(self.webhook_url, message, embed=embed)
                notified = True
            except Exception as exc:
                logger.warning(f"Discord notification failed: {exc}")

        if not notified and self.telegram_token and self.telegram_chat_id:
            try:
                self.send_telegram(self.telegram_token, self.telegram_chat_id, message)
                notified = True
            except Exception as exc:
                logger.warning(f"Telegram notification failed: {exc}")

        if not notified:
            logger.info(f"[Notifier] Clip ready (no webhook configured): {message}")

    # ------------------------------------------------------------------
    # Channel-specific senders
    # ------------------------------------------------------------------

    @staticmethod
    def send_discord_webhook(
        webhook_url: str,
        message: str,
        embed: dict | None = None,
    ) -> None:
        """
        POST a message (and optional embed) to a Discord webhook URL.

        Args:
            webhook_url: Full Discord webhook URL.
            message: Plain-text content of the message.
            embed: Optional Discord embed dict.

        Raises:
            requests.HTTPError: If Discord returns a non-2xx response.
        """
        payload: dict = {"content": message}
        if embed:
            payload["embeds"] = [embed]

        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.debug(f"Discord notification sent (status {resp.status_code}).")

    @staticmethod
    def send_telegram(token: str, chat_id: str, message: str) -> None:
        """
        Send a message via the Telegram Bot API.

        Args:
            token: Telegram bot token.
            chat_id: Recipient chat / channel ID.
            message: Plain text or HTML message.

        Raises:
            requests.HTTPError: If Telegram returns a non-2xx response.
        """
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.debug(f"Telegram notification sent (status {resp.status_code}).")

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_clip_message(clip: dict, render_path: str) -> str:
        """
        Build a human-readable notification message from clip metadata.

        Args:
            clip: ClipData-compatible dict.
            render_path: Path to the rendered file.

        Returns:
            Multi-line formatted string.
        """
        title = clip.get("title", "Untitled Clip")
        category = clip.get("category", "GAMING")
        score = clip.get("score", 0)
        hook = clip.get("hook_caption", "")
        duration = clip.get("duration_formatted", "")
        start_fmt = clip.get("start_formatted", "")
        end_fmt = clip.get("end_formatted", "")
        rank = clip.get("rank", "?")

        lines = [
            f"🎬 Clip #{rank} Ready — {title}",
            f"📂 File: {os.path.basename(render_path)}",
            f"🏷️  Category: {category}  |  Score: {score}/100  |  Duration: {duration}",
            f"⏱️  Range: {start_fmt} → {end_fmt}",
        ]
        if hook:
            lines.append(f'🎯 Hook: "{hook}"')

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_discord_embed(clip: dict, render_path: str) -> dict:
        """Build a Discord embed dict for a rendered clip."""
        title = clip.get("title", "Untitled Clip")
        category = clip.get("category", "GAMING")
        score = clip.get("score", 0)
        hook = clip.get("hook_caption", "")
        start_fmt = clip.get("start_formatted", "")
        end_fmt = clip.get("end_formatted", "")
        duration = clip.get("duration_formatted", "")

        fields = [
            {"name": "Category", "value": category, "inline": True},
            {"name": "Score", "value": f"{score}/100", "inline": True},
            {"name": "Duration", "value": duration, "inline": True},
            {"name": "Range", "value": f"{start_fmt} → {end_fmt}", "inline": True},
        ]
        if hook:
            fields.append({"name": "Hook Caption", "value": hook, "inline": False})

        return {
            "title": f"🎬 {title}",
            "description": f"File: `{os.path.basename(render_path)}`",
            "color": 0xFF0055,  # Pink/red brand colour
            "fields": fields,
        }
