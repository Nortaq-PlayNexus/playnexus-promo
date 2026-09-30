"""Rate limiting and scheduling windows.

Two independent brakes, because they solve different problems:

  ratelimit.py  — "have I gone over my allowance?"   (per-channel counters, DB-backed)
  scheduler.py  — "is it a good time at all?"        (active hours, min gap, daily cap)

Neither one replaces the other, and neither one replaces the compliance gate.
"""

from __future__ import annotations

import datetime as _dt

from .db import Store, utcnow
from .models import Channel


class RateExceeded(Exception):
    pass


def _start_of_day(now: _dt.datetime) -> _dt.datetime:
    return now.astimezone(_dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def used_today(store: Store, channel: str, now: _dt.datetime | None = None) -> int:
    now = now or utcnow()
    return store.count_in_window(channel, "publish", _start_of_day(now))


def remaining_today(store: Store, ch: Channel, now: _dt.datetime | None = None) -> int:
    return max(0, ch.rate_per_day - used_today(store, ch.name, now))


def last_publish(store: Store, channel: str) -> _dt.datetime | None:
    return store.last_publish(channel)


def check(store: Store, ch: Channel, now: _dt.datetime | None = None) -> tuple[bool, str]:
    """Return (ok, reason). Read-only; does not consume quota."""
    now = now or utcnow()
    used = used_today(store, ch.name, now)
    if used >= ch.rate_per_day:
        return False, f"daily cap reached ({used}/{ch.rate_per_day})"

    last = last_publish(store, ch.name)
    if last is not None:
        gap_min = (now - last).total_seconds() / 60.0
        if gap_min < ch.min_gap_minutes:
            wait = int(ch.min_gap_minutes - gap_min)
            return False, f"min gap not met (last {int(gap_min)}m ago, need {ch.min_gap_minutes}m; wait {wait}m)"
    return True, "ok"


def consume(store: Store, ch: Channel) -> None:
    """Record that a publish attempt happened. Call this *before* the network call."""
    store.bump(ch.name, "publish")


def note_server_limit(client_last_rate_limit: dict[str, float], cap: int) -> None:
    """Reserved hook: fold a server-reported remaining quota back into scheduling.

    Kept separate from `check` so channel modules can surface it without the
    scheduler needing to know which header format a given platform uses.
    """
    remaining = client_last_rate_limit.get("remaining")
    if remaining is not None and remaining <= 0:
        raise RateExceeded("server reported zero remaining quota")
