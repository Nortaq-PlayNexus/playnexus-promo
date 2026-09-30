"""Telegram channel announcements.

Uses a normal bot token (not a userbot). If the pipeline ever needs to post as *you*
rather than as a bot, that is a userbot, that is against the Telegram ToS, and it is
deliberately not implemented here. Your channel's subscribers see "PlayNexus Bot",
which is fine and honest.
"""

from __future__ import annotations

from typing import Any

from .base import Channel, ChannelError, check_lengths, register
from ..render import Rendered


@register
class TelegramChannel(Channel):
    name = "telegram"
    supports_auto = True

    def verify(self) -> tuple[bool, str]:
        for k in ("bot_token", "chat_id"):
            if not self.secret(k):
                return False, f"set secrets.telegram.{k}"
        return True, "ok"

    def endpoint(self) -> str:
        return f"https://api.telegram.org/bot{self.secret('bot_token')}/sendMessage"

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        check_lengths(rendered, self.rules)
        text = rendered.body
        if len(text) > 4096:
            raise ChannelError(f"telegram: {len(text)} chars, limit is 4096")
        parse_mode = self.channel_cfg.config.get("parse_mode")
        if parse_mode and "**" in text and parse_mode == "Markdown":
            # Legacy Markdown treats *bold* and _italic_; ** breaks silently.
            parse_mode = "MarkdownV2"
            text = _to_markdown_v2(text)
        payload: dict[str, Any] = {
            "chat_id": self.secret("chat_id"),
            "text": text,
            "disable_web_page_preview": not self.channel_cfg.config.get("preview", True),
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if self.channel_cfg.config.get("silent", True):
            payload["disable_notification"] = True
        return payload

    def parse_response(self, resp: Any) -> dict[str, str]:
        d = resp.json().get("result", {})
        cid = d.get("chat", {}).get("id")
        mid = d.get("message_id")
        url = f"https://t.me/c/{cid}/{mid}" if cid and mid else ""
        return {"id": str(mid or ""), "url": url}


_V2_ESCAPE = r"_*[]()~`>#+-=|{}.!"


def _to_markdown_v2(text: str) -> str:
    """Escape MarkdownV2 reserved characters, preserving *bold* and _italic_."""
    out = []
    for ch in text:
        if ch in _V2_ESCAPE:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)
