"""Bluesky via AT Protocol.

Free, no approval queue, official app-password auth. The most permissive high-quality
audience you can post to programmatically, which makes it the right first target for
`auto` mode outside your own Discord.

Text is counted in UTF-16 code units and the 300-char default limit is a *grapheme*
limit in the protocol; we apply the stricter of the two.
"""

from __future__ import annotations

from typing import Any

from .base import Channel, ChannelError, register, truncate_utf16
from ..render import Rendered

DEFAULT_LIMIT = 300


@register
class BlueskyChannel(Channel):
    name = "bluesky"
    supports_auto = True

    def verify(self) -> tuple[bool, str]:
        for k in ("identifier", "app_password"):
            if not self.secret(k):
                return False, f"set secrets.bluesky.{k}"
        if not self.secret("service_url"):
            return False, "set secrets.bluesky.service_url"
        return True, "ok"

    def endpoint(self) -> str:
        base = self.secret("service_url").rstrip("/")
        return f"{base}/xrpc/com.atproto.repo.createRecord"

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret('bearer') or self.secret('app_password')}"}

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        limit = int(self.channel_cfg.config.get("max_chars", DEFAULT_LIMIT))
        text = truncate_utf16(rendered.body, limit)
        if len(text) >= limit:
            raise ChannelError(
                f"bluesky: post is {len(text)} chars after truncation; "
                f"shorten the hook (limit {limit})"
            )
        repo = self.secret("repo") or self._default_repo()
        return {
            "repo": repo,
            "collection": "app.bsky.feed.post",
            "record": {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": _now_iso(),
            },
        }

    def _default_repo(self) -> str:
        handle = self.secret("identifier", "")
        return handle if "." in handle else f"{handle}.bsky.social"

    def parse_response(self, resp: Any) -> dict[str, str]:
        data = resp.json()
        uri = data.get("uri", "")
        cid = data.get("cid", "")
        # rkey is the last path segment of the record URI
        rkey = uri.rsplit("/", 1)[-1] if uri else ""
        handle = (self.secret("repo") or self._default_repo()).split("/")[0]
        at_url = f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else ""
        return {"id": uri or cid, "url": at_url}

    def preflight(self) -> tuple[bool, str]:
        """Check the session server for a valid token before the first scheduled post."""
        base = self.secret("service_url").rstrip("/")
        try:
            self.client.get(f"{base}/xrpc/com.atproto.server.describeServer")
        except Exception as e:  # noqa: BLE001
            return False, f"bluesky service unreachable: {e}"
        return True, "ok"


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.UTC).isoformat().replace("+00:00", "Z")
