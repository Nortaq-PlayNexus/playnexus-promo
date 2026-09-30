"""Channel adapter base class.

A channel implementation declares:
  * `name`              must match its key in channels.json
  * `verify(cfg)`       can it run? returns (ok, reason)
  * `build_payload(rendered, post)`  returns the exact JSON body to POST
  * `parse_response(resp)`           returns {"url":..., "id":...}

`Channel.rules` has no sensible default, so a channel added without a rules block
cannot be instantiated. The compliance gate is not optional.
"""

from __future__ import annotations

import abc
import re
from typing import Any

from ..http import Client, HttpError
from ..models import ChannelRules


class ChannelError(Exception):
    """Publication failed. Message is stored on the post and shown in `pnx queue`."""


_REGISTRY: dict[str, type["Channel"]] = {}


def register(cls: type["Channel"]) -> type["Channel"]:
    """Add a channel implementation to the registry.

    Lives here rather than in `channels/__init__.py` so that modules can register
    themselves without a circular import: the package imports the modules, and the
    modules import this function from the module below the package.
    """
    if not getattr(cls, "name", ""):
        raise ValueError(f"{cls.__name__} must define a non-empty `name`")
    _REGISTRY[cls.name] = cls
    return cls


def registered() -> dict[str, type["Channel"]]:
    return dict(_REGISTRY)


class Channel(abc.ABC):
    name: str = ""
    #: Platforms that reject credential-less or rule-less posting. Override to opt in.
    supports_auto: bool = False

    def __init__(self, cfg: Any, client: Client):
        self.cfg = cfg
        self.client = client
        self.channel_cfg = cfg.channels[self.name]
        self.business = cfg.business
        self.secrets = cfg.secrets.get(self.name, {})

    # -- introspection -------------------------------------------------

    @property
    def rules(self) -> ChannelRules:
        return self.channel_cfg.rules

    @property
    def mode(self) -> str:
        return self.channel_cfg.mode.value

    def secret(self, key: str, default: Any = "") -> Any:
        return self.secrets.get(key, default)

    @abc.abstractmethod
    def verify(self) -> tuple[bool, str]:
        """Return (configured, human-readable reason)."""

    @abc.abstractmethod
    def build_payload(self, rendered: Any) -> dict[str, Any]:
        """The exact request body. Must already satisfy `self.rules`."""

    def parse_response(self, resp: Any) -> dict[str, str]:
        """Extract {url, id} from a successful response. Default is best-effort."""
        return {"url": "", "id": ""}

    def headers(self) -> dict[str, str]:
        return {}

    def endpoint(self) -> str:
        raise NotImplementedError

    # -- publication ---------------------------------------------------

    def publish(self, rendered: Any) -> dict[str, str]:
        """POST the payload. Raises ChannelError on failure."""
        url = self.endpoint()
        if not url:
            raise ChannelError(f"{self.name}: no endpoint configured")
        payload = self.build_payload(rendered)
        try:
            resp = self.client.post(url, json_body=payload, headers=self.headers())
        except HttpError as e:
            if e.status == 429:
                raise ChannelError(
                    f"{self.name}: rate limited by the platform (429). "
                    f"Headers: {e.headers.get('retry-after') or e.headers.get('ratelimit-reset')}"
                ) from e
            raise ChannelError(f"{self.name}: {e}") from e

        out = self.parse_response(resp)
        if not out.get("id") and not out.get("url"):
            raise ChannelError(
                f"{self.name}: published but response had no id/url; "
                f"may have succeeded, verify manually before retrying. "
                f"body={resp.body[:200]}"
            )
        return out


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def truncate_utf16(text: str, limit: int) -> str:
    """Truncate to `limit` UTF-16 code units (what Bluesky/X count).

    Astral characters (emoji) are 2 units in UTF-16, so naive len() is wrong.
    """
    n = 0
    for i, ch in enumerate(text):
        n += 2 if ord(ch) > 0xFFFF else 1
        if n > limit:
            return text[:i] + "…"
    return text


def guess_tag(haystack: str, *names: str) -> str:
    for n in names:
        m = re.search(rf"<(?:{n})[ >]", haystack)
        if m:
            return f"<{n}>"
    return ""


def check_lengths(rendered: Any, rules: ChannelRules) -> None:
    """Last-mile assertion before we touch the network."""
    title = getattr(rendered, "title", "") or ""
    body = getattr(rendered, "body", "") or ""
    if len(title) > rules.max_title:
        raise ChannelError(f"{rendered.channel}: title {len(title)} > {rules.max_title}")
    if len(body) > rules.max_body:
        raise ChannelError(f"{rendered.channel}: body {len(body)} > {rules.max_body}")


# Re-exported so adapters have one obvious import for text helpers.
from ..render import fit_with_link  # noqa: E402,F401
