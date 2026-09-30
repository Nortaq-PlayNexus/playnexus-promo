"""When should a post go out?

Turns "a post exists" into "a post has a defensible timestamp". Respecting active
hours is not a nicety: posting into a community's dead hours is the single most
reliable way to get a post ignored, which reads to moderators as a bad post.
"""

from __future__ import annotations

import datetime as _dt
import random
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import ratelimit
from .db import Store, utcnow
from .models import Channel


def tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _in_window(local: _dt.datetime, ch: Channel) -> bool:
    return local.weekday() in ch.weekdays and local.hour in ch.active_hours


def next_window(ch: Channel, tzname: str, *, after: _dt.datetime | None = None,
                search_days: int = 21, jitter: bool = True) -> _dt.datetime:
    """Earliest UTC instant at/after `after` that falls inside the channel's window."""
    after = after or utcnow()
    zone = tz(tzname)
    local = after.astimezone(zone)

    if not ch.active_hours or not ch.weekdays:
        return after

    for day_offset in range(search_days):
        base = (local + _dt.timedelta(days=day_offset)).replace(
            minute=0, second=0, microsecond=0
        )
        for hour in sorted(ch.active_hours):
            cand_local = base.replace(hour=hour)
            if cand_local.weekday() not in ch.weekdays:
                continue
            if cand_local < local:
                continue
            cand = cand_local.astimezone(_dt.UTC)
            if cand < after:
                continue
            if jitter:
                # Spread posts across the hour so a batch doesn't land as a burst.
                cand = cand + _dt.timedelta(minutes=random.randint(4, 56))
            return cand
    # No configured window in three weeks: fall back to tomorrow same hour.
    return (local + _dt.timedelta(days=1)).astimezone(_dt.UTC)


def pick_time(store: Store, ch: Channel, tzname: str, *,
              earliest: _dt.datetime | None = None,
              max_search: int = 400) -> _dt.datetime:
    """Choose a publish time for a new post on this channel.

    Satisfies three constraints simultaneously, iterating until all three hold:
      1. the time falls inside an active window (weekday + hours, in the business TZ)
      2. it is at least `min_gap_minutes` after the channel's last *scheduled or
         published* post -- counting queued work, otherwise compiling a week of
         content collapses every post into the same hour
      3. the channel's daily cap for that day is not already full, so overflow rolls
         forward to the next window instead of piling up

    The search is bounded so a pathological config (e.g. an empty active_hours list
    combined with a cap of 0) degrades to a sane value instead of spinning.
    """
    base = earliest or utcnow()
    cand = next_window(ch, tzname, after=base)
    step = _dt.timedelta(minutes=1)

    for _ in range(max_search):
        # 3. daily cap -- move on if this day is already fully booked
        if store.scheduled_on_day(ch.name, cand) >= ch.rate_per_day:
            cand = next_window(ch, tzname, after=cand + step)
            continue

        # 2. min gap since the most recent queued-or-shipped post
        last = store.last_activity(ch.name)
        if last is not None:
            floor = last + _dt.timedelta(minutes=ch.min_gap_minutes)
            if cand < floor:
                cand = next_window(ch, tzname, after=floor)
                continue

        return cand

    return cand


def is_due(ch: Channel, tzname: str, now: _dt.datetime | None = None) -> bool:
    now = now or utcnow()
    local = now.astimezone(tz(tzname))
    return _in_window(local, ch)


def describe_window(ch: Channel, tzname: str) -> str:
    zone = tz(tzname).key
    days = "daily" if len(ch.weekdays) == 7 else (
        ",".join(_DAY[d] for d in ch.weekdays) or "never"
    )
    hours = "all hours" if len(ch.active_hours) == 24 else (
        f"{min(ch.active_hours):02d}:00-{max(ch.active_hours) + 1:02d}:00"
    )
    return f"{days} {hours} {zone}, cap {ch.rate_per_day}/day, gap {ch.min_gap_minutes}m"


_DAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
