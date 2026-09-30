"""Hashnode (GraphQL `publishPost`).

Free. Lower dev traffic than Dev.to, so this is `approve` by default in
channels.json — worth a human glance before it goes out.
"""

from __future__ import annotations

from typing import Any

from .base import Channel, ChannelError, check_lengths, register
from ..render import Rendered

MUTATION = """
mutation PublishPost($input: PublishPostInput!) {
  publishPost(input: $input) {
    post { id slug url }
    errors { message type }
  }
}
"""


@register
class HashnodeChannel(Channel):
    name = "hashnode"
    supports_auto = True

    def verify(self) -> tuple[bool, str]:
        if not self.secret("api_key"):
            return False, "set secrets.hashnode.api_key"
        if not self.secret("publication_id"):
            return False, "set secrets.hashnode.publication_id"
        return True, "ok"

    def endpoint(self) -> str:
        return self.channel_cfg.config.get("endpoint", "https://gql.hashnode.com/")

    def headers(self) -> dict[str, str]:
        h = {"Authorization": self.secret("api_key")}
        if self.secret("bearer"):
            h["Authorization"] = f"Bearer {self.secret('bearer')}"
        return h

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        check_lengths(rendered, self.rules)
        body = (rendered.extra or {}).get("content_markdown") or rendered.body
        if len(body) < 100:
            raise ChannelError(f"hashnode: body only {len(body)} chars, too thin")
        return {
            "query": MUTATION,
            "variables": {
                "input": {
                    "title": ((rendered.extra or {}).get("title") or rendered.title)[:100],
                    "contentMarkdown": body,
                    "coverImage": {"url": self.channel_cfg.config.get("cover_image", "")
                                   or self.business.url + "/og.png"},
                    "tags": (rendered.tags or [])[:5],
                    "canonicalUrl": (rendered.extra or {}).get("canonical_url") or None,
                    "subtitle": self.business.tagline[:120],
                    "publicationId": self.secret("publication_id"),
                }
            },
        }

    def parse_response(self, resp: Any) -> dict[str, str]:
        d = resp.json()
        if d.get("errors"):
            raise ChannelError(f"hashnode: {d['errors']}")
        result = (d.get("data") or {}).get("publishPost") or {}
        errs = result.get("errors") or []
        if errs:
            raise ChannelError(f"hashnode: {errs}")
        post = result.get("post") or {}
        return {"id": str(post.get("id", "")), "url": post.get("url", "")}
