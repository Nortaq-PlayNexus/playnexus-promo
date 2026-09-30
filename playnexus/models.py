"""Core data types. Dataclasses only, no ORM."""

from __future__ import annotations

import dataclasses
import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Mode(str, Enum):
    """How a channel is allowed to publish."""

    AUTO = "auto"        # owned asset / official API -> machine may post unattended
    APPROVE = "approve"  # community channel -> human must approve every post
    OFF = "off"          # pipeline drafts, never publishes


class State(str, Enum):
    """Lifecycle of a single Post row."""

    DRAFT = "draft"          # rendered + passed compliance, not yet timed
    SCHEDULED = "scheduled"  # has a publish_at, waiting for its window
    BLOCKED = "blocked"      # failed compliance; will never publish
    READY = "ready"          # auto mode and due now
    PENDING = "pending"      # approve mode, waiting for a human
    APPROVED = "approved"    # human approved, awaiting publish
    PUBLISHED = "published"
    FAILED = "failed"
    REJECTED = "rejected"    # human said no
    SKIPPED = "skipped"      # expired past its window, not published

    @property
    def terminal(self) -> bool:
        return self in {State.PUBLISHED, State.BLOCKED, State.REJECTED, State.SKIPPED}


@dataclass
class Service:
    """One thing PlayNexus sells."""

    slug: str
    name: str
    tagline: str
    detail: str
    keywords: list[str] = field(default_factory=list)
    page: str = ""              # path on the owned site, e.g. "/discord-bots"
    proof: str = ""             # a concrete fact: "12 bots shipped", not "quality work"
    cta: str = ""               # per-service call to action
    est_value: str = ""         # "from $150", "quote in 24h"
    audience: str = ""          # who this is for


@dataclass
class Hook:
    """One angle/idea, written once, adapted per channel."""

    id: str
    service: str          # service slug this hook sells
    angle: str            # short label, e.g. "cost-of-discord-bad-bot"
    title: str            # factual, non-marketing
    body: str             # the substance
    proof: str = ""
    cta: str = ""
    tags: list[str] = field(default_factory=list)
    link: str = ""        # optional override link
    community: str = ""   # for community channels: the exact sub/tag/community


@dataclass
class Content:
    """A Content item: a hook bound to a service, before any channel rendering."""

    id: str
    service_slug: str
    hook_id: str
    title: str
    body: str
    tags: list[str]
    link: str
    proof: str
    cta: str
    community: str = ""


@dataclass
class Rendered:
    """A Content item rendered for one specific channel."""

    channel: str
    title: str
    body: str
    link: str = ""
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)  # channel-specific payload


@dataclass
class ChannelRules:
    """Per-channel limits and bans. Mandatory: no channel may exist without one."""

    max_title: int = 300
    max_body: int = 4000
    min_body: int = 0
    max_tags: int = 0
    link_allowed: bool = True
    link_required: bool = False
    # Banned substrings (case-insensitive regex, matched against title+body).
    banned: list[str] = field(default_factory=list)
    # Required substrings for this channel to accept the post at all.
    required: list[str] = field(default_factory=list)
    # Community value policy. 0.0 disables the check.
    # For communities: fraction of the post that must be substance, not pitch.
    min_value_ratio: float = 0.0
    # True for channels where the post must NOT read as an ad (HN, Lobsters).
    no_ad_tone: bool = False
    # True for channels where the link must live in a profile/bio, not the post.
    link_in_profile_only: bool = False
    # True for third-party communities you do not own. Only these participate in the
    # cross-community `duplicate_copy` check — cross-posting to your own Bluesky,
    # Dev.to and Discord is normal distribution, not spam.
    community: bool = False


@dataclass
class Channel:
    """A configured destination."""

    name: str
    mode: Mode
    enabled: bool
    rate_per_day: int
    min_gap_minutes: int
    active_hours: list[int]        # local hours 0-23 when posting is allowed
    weekdays: list[int]            # 0=Mon .. 6=Sun
    rules: ChannelRules
    weight: int = 1                # relative frequency in the rotation
    config: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @property
    def secret_keys(self) -> list[str]:
        """Config keys that must be present in secrets.json to enable this channel."""
        out = []
        for k, v in self.config.items():
            if isinstance(v, dict) and v.get("secret"):
                out.append(k)
        return out


@dataclass
class Post:
    """One row in the queue: a Rendered bound to a channel, with schedule + state."""

    id: int | None
    content_id: str
    channel: str
    state: State
    fingerprint: str
    title: str
    body: str
    link: str
    tags: list[str]
    payload: dict[str, Any] = field(default_factory=dict)
    publish_at: _dt.datetime | None = None
    published_at: _dt.datetime | None = None
    remote_url: str = ""
    remote_id: str = ""
    attempts: int = 0
    last_error: str = ""
    created_at: _dt.datetime = field(default_factory=lambda: _dt.datetime.now(_dt.UTC))
    updated_at: _dt.datetime = field(default_factory=lambda: _dt.datetime.now(_dt.UTC))

    def as_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["state"] = self.state.value
        for k in ("publish_at", "published_at", "created_at", "updated_at"):
            d[k] = d[k].isoformat() if isinstance(d[k], _dt.datetime) else None
        return d
