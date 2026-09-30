"""Reddit. The highest-intent audience for dev services, and the easiest to get banned from.

Verified against the Reddit Data API Wiki (updated 2026-05-11):
  * OAuth is mandatory. Unauthenticated traffic is blocked outright.
  * A descriptive User-Agent is mandatory, in the form
        <platform>:<app ID>:<version string> (by /u/<username>)
    Generic agents (Python/urllib, Java/1.8) are throttled hard. We never lie about ours.
  * Free tier: 100 queries per minute per OAuth client-id, averaged over a 10-minute
    window (so bursts are tolerated). Tracked in the X-Ratelimit-* response headers.
  * Data must be deleted within 48h of being removed upstream. We are stateless about
    Reddit content: we store only the post id and the permalink we ourselves created.

The API limit is not the real constraint. The real constraint is each subreddit's
self-promotion rule, which is why this channel is hard-wired to `approve` mode in
channels.json and why the compliance gate enforces a value ratio on it.
"""

from __future__ import annotations

import base64
import datetime as _dt
import time
from typing import Any

from .base import Channel, ChannelError, check_lengths, register
from ..http import HttpError
from ..render import Rendered

AUTH_URL = "https://www.reddit.com/api/v1/access_token"


@register
class RedditChannel(Channel):
    name = "reddit"
    supports_auto = False  # never unattended; every post is human-approved

    def __init__(self, cfg: Any, client: Any):
        super().__init__(cfg, client)
        self._token: str | None = None
        self._token_exp: float = 0.0

    # -- config ---------------------------------------------------------

    @property
    def user_agent(self) -> str:
        """Built from real config. Reddit explicitly requires this format."""
        ua = self.channel_cfg.config.get("user_agent")
        if ua:
            return ua
        return (
            f"linux:playnexus.promo:{__import__('playnexus').__version__} "
            f"(by /u/{self.secret('username', 'unknown')})"
        )

    def verify(self) -> tuple[bool, str]:
        for k in ("client_id", "client_secret", "username", "password", "subreddit"):
            if not self.secret(k):
                return False, f"set secrets.reddit.{k}"
        ua = self.user_agent
        if "(by /u/" not in ua or ua.count(":") < 2:
            return False, (
                f"user_agent {ua!r} does not match Reddit's required format: "
                f"<platform>:<appID>:<version> (by /u/<username>)"
            )
        return True, "ok"

    # -- auth -----------------------------------------------------------

    def token(self, force: bool = False) -> str:
        """OAuth token, cached until shortly before expiry."""
        if not force and self._token and time.time() < self._token_exp - 60:
            return self._token

        basic = base64.b64encode(
            f"{self.secret('client_id')}:{self.secret('client_secret')}".encode()
        ).decode()
        # `password` grant for a script app: lets us post as the account itself.
        form = {
            "grant_type": "password",
            "username": self.secret("username"),
            "password": self.secret("password"),
        }
        try:
            resp = self.client.post(
                AUTH_URL, form=form,
                headers={
                    "Authorization": f"Basic {basic}",
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                },
            )
        except HttpError as e:
            if e.status == 401:
                raise ChannelError(
                    "reddit: 401 from access_token. Check client_id/client_secret, and "
                    "that this is a 'script' app with the correct redirect uri."
                ) from e
            if e.status == 429:
                raise ChannelError("reddit: rate limited during auth; back off") from e
            raise ChannelError(f"reddit auth failed: {e}") from e

        d = resp.json()
        if "access_token" not in d:
            raise ChannelError(f"reddit: no access_token in response: {d}")
        self._token = d["access_token"]
        self._token_exp = time.time() + float(d.get("expires_in", 3600))
        return self._token

    # -- publish --------------------------------------------------------

    def endpoint(self) -> str:
        base = self.channel_cfg.config.get("api_base", "https://oauth.reddit.com")
        return f"{base.rstrip('/')}/api/submit"

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"bearer {self.token()}",
            "User-Agent": self.user_agent,
        }

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        check_lengths(rendered, self.rules)
        extra = rendered.extra or {}
        subreddit = extra.get("subreddit") or self.secret("subreddit")
        if not subreddit:
            raise ChannelError(
                "reddit: no target subreddit. Set secrets.reddit.subreddit or put "
                "\"community\": \"subredditname\" on the hook in hooks.json."
            )
        subreddit = subreddit.lstrip("/r/").strip("/")
        if not subreddit.replace("_", "").isalnum():
            raise ChannelError(f"reddit: bad subreddit name {subreddit!r}")
        return {
            "sr": subreddit,
            "title": (extra.get("title") or rendered.title)[:300],
            "text": (extra.get("text") or rendered.body)[:40000],
            "kind": "self",
            "api_type": "json",
            "resubmit": False,      # never silently edit an existing submission
            "sendreplies": False,  # we do not participate in comment threads
            "nsfw": False,
            "spoiler": False,
        }

    def parse_response(self, resp: Any) -> dict[str, str]:
        d = resp.json()
        errors = d.get("json", {}).get("errors") or []
        if errors:
            raise ChannelError(
                "reddit rejected the post: "
                + "; ".join(f"{e.get('error_code')}: {e.get('message')}" for e in errors)
            )
        data = (d.get("json", {}).get("data") or {})
        things = data.get("things") or []
        if not things:
            raise ChannelError(f"reddit: no thing id in response: {str(d)[:200]}")
        permalink = (things[0].get("permalink") or "").lstrip("/")
        base = self.channel_cfg.config.get("web_base", "https://www.reddit.com")
        url = f"{base}/{permalink}" if permalink else ""
        return {"id": str(things[0].get("id", "")), "url": url}

    # -- read-only helpers (used by the reviewer, never to post) --------

    def sub_rules(self, subreddit: str) -> str:
        """Fetch a subreddit's public rules page text so you can read them first.

        Read-only. This exists so the human reviewing an approval actually knows what
        the rules are, instead of guessing.
        """
        base = self.channel_cfg.config.get("web_base", "https://www.reddit.com")
        try:
            resp = self.client.get(
                f"{base}/r/{subreddit.lstrip('/r/')}/about/rules.json",
                headers={"User-Agent": self.user_agent},
            )
            rules = resp.json().get("rules", [])
            return "\n".join(f"- {r.get('short_name')}: {r.get('description', '')[:400]}"
                             for r in rules)
        except HttpError as e:
            return f"(could not fetch rules: {e})"

    def ratelimit_state(self) -> dict[str, float]:
        """X-Ratelimit-* from the last call. Lets `pnx ratelimit` show real headroom."""
        return dict(self.client.last_rate_limit)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)
