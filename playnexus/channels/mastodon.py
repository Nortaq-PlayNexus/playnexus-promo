"""Mastodon. Any instance, official REST API, free.

Instance rate limits vary and are returned in headers, which our HTTP client already
parses. We send `Idempotency-Key` so a network retry can't double-post.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .base import (Channel, ChannelError, check_lengths, fit_with_link, register,
                   truncate_utf16)
from ..render import Rendered


@register
class MastodonChannel(Channel):
    name = "mastodon"
    supports_auto = True

    def verify(self) -> tuple[bool, str]:
        for k in ("instance", "access_token"):
            if not self.secret(k):
                return False, f"set secrets.mastodon.{k}"
        inst = self.secret("instance")
        if not str(inst).startswith("http"):
            return False, "secrets.mastodon.instance must include https://"
        return True, "ok"

    def endpoint(self) -> str:
        return f"{self.secret('instance').rstrip('/')}/api/v1/statuses"

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret('access_token')}"}

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        check_lengths(rendered, self.rules)
        limit = int(self.channel_cfg.config.get("max_chars", 500))
        # The adapter is the authority on final length. `fit_with_link` reserves room
        # for the UTM-tagged URL so it can never be truncated off and re-appended.
        status = fit_with_link(rendered.body, rendered.link, limit)
        if len(status) > limit:
            raise ChannelError(
                f"mastodon: {len(status)} chars, limit {limit} — shorten the hook"
            )
        payload: dict[str, Any] = {
            "status": status,
            "visibility": self.channel_cfg.config.get("visibility", "public"),
            "language": (self.business.languages or ["en"])[0],
        }
        if not self.channel_cfg.config.get("allow_sensitive", False):
            payload["sensitive"] = False
        return payload

    def idempotency_key(self, rendered: Rendered) -> str:
        raw = f"{self.name}|{rendered.title}|{rendered.body[:120]}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def publish(self, rendered: Rendered) -> dict[str, str]:
        url = self.endpoint()
        payload = self.build_payload(rendered)
        hdrs = {**self.headers(), "Idempotency-Key": self.idempotency_key(rendered)}
        from ..http import HttpError
        try:
            resp = self.client.post(url, json_body=payload, headers=hdrs)
        except HttpError as e:
            raise ChannelError(f"mastodon: {e}") from e
        return self.parse_response(resp)

    def parse_response(self, resp: Any) -> dict[str, str]:
        d = resp.json()
        return {"id": str(d.get("id", "")), "url": d.get("url", "")}
