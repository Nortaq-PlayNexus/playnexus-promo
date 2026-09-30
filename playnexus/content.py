"""Content generation.

The expensive part of promotion is deciding *what to say*. This module turns the
service catalog in business.json plus the angles in hooks.json into dated, rotating
Content items — so the pipeline has something to say every day without you writing
from scratch 20 times a week.

Hooks are the unit of thinking. A hook is one idea, written once, rendered ten ways.
"""

from __future__ import annotations

import datetime as _dt
import itertools
import json
import random
from typing import Any

from .config import Config
from .db import Store, utcnow
from .models import Content, Hook, Service


def content_id(hook_id: str, day: _dt.date) -> str:
    return f"{hook_id}@{day.isoformat()}"


def hooks_for_service(cfg: Config, service_slug: str) -> list[Hook]:
    return [h for h in cfg.hooks if h.service == service_slug]


def build_content(cfg: Config, hook: Hook, day: _dt.date) -> Content:
    svc = cfg.business.service(hook.service)
    return Content(
        id=content_id(hook.id, day),
        service_slug=hook.service,
        hook_id=hook.id,
        title=hook.title,
        body=hook.body,
        tags=list(hook.tags or svc.keywords),
        link=hook.link,
        proof=hook.proof or svc.proof,
        cta=hook.cta,
        community=hook.community,
    )


def rotation_order(cfg: Config, start: _dt.date, days: int,
                   *, exclude_services: set[str] | None = None) -> list[tuple[Hook, _dt.date]]:
    """Pick one hook per day, rotating through services so the feed isn't lopsided.

    Deterministic given (start, days, seed) so re-running `plan` doesn't reshuffle
    tomorrow's queue.
    """
    rng = random.Random(f"playnexus:{start.isoformat()}:{days}")
    per_service = {s.slug: hooks_for_service(cfg, s.slug) for s in cfg.business.services}
    per_service = {k: v for k, v in per_service.items() if v}
    if exclude_services:
        per_service = {k: v for k, v in per_service.items() if k not in exclude_services}
    if not per_service:
        return []

    slugs = sorted(per_service)
    pools: dict[str, list[Hook]] = {k: list(v) for k, v in per_service.items()}
    for k in pools:
        rng.shuffle(pools[k])

    out: list[tuple[Hook, _dt.date]] = []
    counter = itertools.count()
    for i in range(days):
        day = start + _dt.timedelta(days=i)
        # prefer a service not used for the last 2 days
        recent = [h.service for h, _ in out[-2:]]
        candidates = [s for s in slugs if s not in recent] or slugs
        slug = candidates[i % len(candidates)]
        pool = pools[slug]
        if not pool:
            pool = pools[slug] = hooks_for_service(cfg, slug)
        hook = pool[next(counter) % len(pool)]
        out.append((hook, day))
    return out


def plan(cfg: Config, store: Store, *, days: int = 7,
         start: _dt.date | None = None) -> dict[str, Any]:
    """Create Content rows for the next `days`. Idempotent: existing ids are kept."""
    start = start or utcnow().date()
    created, skipped = 0, 0
    items: list[str] = []
    for hook, day in rotation_order(cfg, start, days):
        c = build_content(cfg, hook, day)
        if store.put_content(c):
            created += 1
            items.append(c.id)
        else:
            skipped += 1
    store.log("plan", f"planned {created} new content items for {days} days "
                      f"({skipped} already existed)")
    return {"created": created, "skipped": skipped, "ids": items,
            "start": start.isoformat(), "days": days}


def load_content(store: Store, content_id_: str) -> Content | None:
    row = store.get_content(content_id_)
    if not row:
        return None
    return Content(
        id=row["id"],
        service_slug=row["service"],
        hook_id=row["hook_id"],
        title=row["title"],
        body=row["body"],
        tags=json.loads(row["tags"] or "[]"),
        link=row["link"],
        proof=row["proof"],
        cta=row["cta"],
        community=row["community"],
    )


def all_content(store: Store, limit: int = 100) -> list[Content]:
    rows = store.con.execute(
        "SELECT id FROM content ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [c for c in (load_content(store, r["id"]) for r in rows) if c]


def uncompiled_content(store: Store) -> list[Content]:
    """Content with no post row yet."""
    rows = store.con.execute(
        "SELECT c.id FROM content c LEFT JOIN posts p ON p.content_id = c.id "
        "WHERE p.id IS NULL ORDER BY c.id ASC"
    ).fetchall()
    return [c for c in (load_content(store, r["id"]) for r in rows) if c]
