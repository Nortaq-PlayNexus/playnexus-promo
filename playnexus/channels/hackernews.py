"""Hacker News. Drafts only, deliberately.

The official API (hacker-news.firebaseio.com/v0, verified from the HackerNews/API
README) is read-only and currently has no rate limit. There is no public submit
endpoint. Submissions go through the web form, and the Show HN guidelines say to
"use factual, direct language" and to "drop any language that sounds like marketing
or sales".

So: this adapter generates a compliant title + a first comment, and refuses to
automate the submit. It also polls the public API for the score of any submission you
made by hand, which is the part that actually needs automating.
"""

from __future__ import annotations

from typing import Any

from .base import Channel, ChannelError, register
from ..http import HttpError
from ..render import Rendered

API = "https://hacker-news.firebaseio.com/v0"
SUBMIT_URL = "https://news.ycombinator.com/submit"
ITEM_URL = "https://news.ycombinator.com/item?id={id}"


@register
class HackerNewsChannel(Channel):
    name = "hackernews"
    supports_auto = False  # read API only; posting is a human action

    def verify(self) -> tuple[bool, str]:
        if not self.secret("hn_username"):
            return False, "set secrets.hackernews.hn_username (for score polling)"
        return True, "ok"

    def endpoint(self) -> str:
        return ""  # intentionally unreachable

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        """A fill-in form, not a request body."""
        e = rendered.extra or {}
        return {
            "manual": True,
            "submit_url": f"{SUBMIT_URL}?url={e.get('url', '')}&title={e.get('hn_title', '')}",
            "title": e.get("hn_title", ""),
            "url": e.get("url", ""),
            "first_comment": e.get("first_comment", ""),
            "note": e.get("note", ""),
        }

    def publish(self, rendered: Rendered) -> dict[str, str]:
        raise ChannelError(
            "hackernews: automated submission is not implemented and will not be. "
            "Use `pnx show <id> --manual` to get the pre-filled URL and the "
            "first comment to paste, then submit by hand."
        )

    # -- the part worth automating -------------------------------------

    def submission_url(self) -> str:
        return f"https://news.ycombinator.com/submitted?id={self.secret('hn_username')}"

    def latest_submissions(self, limit: int = 10) -> list[dict[str, Any]]:
        """Read-only: recent submissions + current score, so you know what worked."""
        out: list[dict[str, Any]] = []
        try:
            user = self.client.get(f"{API}/user/{self.secret('hn_username')}.json").json()
        except HttpError as e:
            raise ChannelError(f"hackernews: {e}") from e
        for sid in (user.get("submitted") or [])[:limit]:
            try:
                item = self.client.get(f"{API}/item/{sid}.json").json()
            except HttpError:
                continue
            if not item:
                continue
            out.append({
                "id": sid,
                "title": item.get("title", ""),
                "score": item.get("score", 0),
                "descendants": item.get("descendants", 0),
                "dead": item.get("dead", False),
                "url": ITEM_URL.format(id=sid),
                "at": item.get("time", 0),
            })
        return out

    def show_hn_queue(self, limit: int = 30) -> list[dict[str, Any]]:
        """What Show HN currently looks like. Read-only reconnaissance.

        Useful for calibrating tone, not for copying anyone's post.
        """
        try:
            ids = self.client.get(f"{API}/showstories.json").json() or []
        except HttpError as e:
            raise ChannelError(f"hackernews: {e}") from e
        out = []
        for sid in ids[:limit]:
            try:
                item = self.client.get(f"{API}/item/{sid}.json").json()
            except HttpError:
                continue
            if item:
                out.append({"id": sid, "title": item.get("title", ""),
                            "score": item.get("score", 0)})
        return out
