"""Discord webhook channel.

Free, zero-permission, and the only channel where you can be as loud as you want
*because you own the room*. Requires no bot token — the webhook URL is the credential.

Hard rule enforced here: `allowed_mentions.parse = []`. A promo pipeline that can
mass-ping is a spam pipeline, so the capability is not present in the code at all.
"""

from __future__ import annotations

import re
from typing import Any

from .base import Channel, ChannelError, check_lengths, register
from ..render import Rendered

WEBHOOK_RE = re.compile(
    r"^https://(?:\w+\.)?discord(?:app)?\.com/api/(?:v\d+/)?webhooks/(\d+)/([\w-]+)"
)


@register
class DiscordChannel(Channel):
    name = "discord"
    supports_auto = True

    def verify(self) -> tuple[bool, str]:
        url = self.secret("webhook_url")
        if not url:
            return False, "set secrets.discord.webhook_url"
        if not WEBHOOK_RE.match(url.strip()):
            return False, "webhook_url is not a valid Discord webhook URL"
        return True, "ok"

    def endpoint(self) -> str:
        return (self.secret("webhook_url") or "").strip() + (
            f"?wait=true" if not self.secret("webhook_url", "").find("?") else ""
        )

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        check_lengths(rendered, self.rules)
        # render.discord already produced a complete embed payload in `extra`.
        payload: dict[str, Any] = dict(rendered.extra)
        embeds = payload.get("embeds") or []
        for e in embeds:
            e.setdefault("allowed_mentions", {"parse": []})
        if not embeds and not payload.get("content"):
            raise ChannelError("discord: nothing to send (no embed, no content)")
        # Re-assert the no-ping invariant after render.
        payload["allowed_mentions"] = {"parse": [], "users": [], "roles": []}
        if len(embeds) > 10:
            raise ChannelError("discord: max 10 embeds per webhook message")
        if not self.secret("username_override") and "username" in payload:
            del payload["username"]  # only overridable with the webhook's own token
        elif self.secret("username_override"):
            payload["username"] = self.secret("username_override")
        return payload

    def parse_response(self, resp: Any) -> dict[str, str]:
        data = resp.json()
        return {"id": str(data.get("id", "")), "url": data.get("webhook_url", "")}
