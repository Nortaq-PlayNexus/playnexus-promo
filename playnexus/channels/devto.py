"""Dev.to (Forem API v1).

Verified from the Forem API docs: version 1 requires
  Accept: application/vnd.forem.api-v1+json
  api-key: <key from dev.to settings>
POST /api/articles. Authenticated users get 30 requests / 30s and 1,000 articles.
"""

from __future__ import annotations

from typing import Any

from .base import Channel, ChannelError, check_lengths, register
from ..render import Rendered


@register
class DevToChannel(Channel):
    name = "devto"
    supports_auto = True

    def verify(self) -> tuple[bool, str]:
        if not self.secret("api_key"):
            return False, "set secrets.devto.api_key (dev.to -> Settings -> API keys)"
        return True, "ok"

    def endpoint(self) -> str:
        return self.channel_cfg.config.get(
            "endpoint", "https://dev.to/api/articles"
        )

    def headers(self) -> dict[str, str]:
        return {
            "api-key": self.secret("api_key"),
            "Accept": "application/vnd.forem.api-v1+json",
        }

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        check_lengths(rendered, self.rules)
        title = (rendered.extra or {}).get("title") or rendered.title
        body = (rendered.extra or {}).get("body_markdown") or rendered.body
        if not title.strip():
            raise ChannelError("devto: empty title")
        if len(body) < 100:
            raise ChannelError(
                f"devto: body is {len(body)} chars; dev.to will not rank anything "
                f"this thin. Write the real article in hooks.json."
            )
        payload: dict[str, Any] = {
            "title": title[:128],
            "body_markdown": body,
            "published": bool(self.channel_cfg.config.get("published", True)),
            "tags": (rendered.tags or [])[:4],
            "description": (rendered.extra or {}).get("description", "")[:140],
            "canonical_url": (rendered.extra or {}).get("canonical_url") or None,
            "series": self.channel_cfg.config.get("series") or None,
        }
        if self.channel_cfg.config.get("organization"):
            payload["organization_id"] = self.channel_cfg.config["organization"]
        return payload

    def parse_response(self, resp: Any) -> dict[str, str]:
        d = resp.json()
        url = d.get("url", "")
        if url and not url.startswith("http"):
            url = f"https://dev.to{url}"
        return {"id": str(d.get("id", "")), "url": url}
