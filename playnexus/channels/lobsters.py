"""Lobsters. Drafts only.

Invite-gated, tag-based, and far quieter than HN, which makes it the community most
tolerant of a technical write-up that happens to be about your own work. There is an
API but it requires an account you get by invitation, and posting is manual.
"""

from __future__ import annotations

from typing import Any

from .base import Channel, ChannelError, register
from ..render import Rendered

SUBMIT_URL = "https://lobste.rs/new"


@register
class LobstersChannel(Channel):
    name = "lobsters"
    supports_auto = False

    def verify(self) -> tuple[bool, str]:
        return True, "draft-only channel; nothing to configure"

    def endpoint(self) -> str:
        return ""

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        e = rendered.extra or {}
        return {
            "manual": True,
            "submit_url": SUBMIT_URL,
            "title": e.get("title", ""),
            "url": e.get("url", ""),
            "description": e.get("description", ""),
            "tags": e.get("tags", []),
        }

    def publish(self, rendered: Rendered) -> dict[str, str]:
        raise ChannelError(
            "lobsters: manual submission only. Use `pnx show <id> --manual`."
        )
