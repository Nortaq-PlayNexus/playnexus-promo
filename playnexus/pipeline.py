"""Pipeline orchestration: compile -> schedule -> publish.

`compile()` is the only place a post is created, and it always runs the compliance
gate first. `run()` is the only place a post leaves the machine, and it refuses
anything whose channel mode is not AUTO.

The separation matters: you can re-run `compile` as often as you like and it will
never publish, and you can leave `run` in a Task Scheduler and it will never publish
to a community channel.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from . import compliance, content as content_mod, ratelimit, render, scheduler
from .channels import MANUAL_ONLY, build as build_channel
from .channels.base import ChannelError
from .config import Config
from .db import Store, fingerprint, make_render_post, utcnow
from .http import Client
from .models import Content, Mode, Post, State


# ---------------------------------------------------------------------------
# compile: content -> queued posts
# ---------------------------------------------------------------------------

def compile_pending(cfg: Config, store: Store, *, limit: int = 60,
                    now: _dt.datetime | None = None) -> dict[str, Any]:
    """Render every uncompiled Content item for every enabled channel.

    Returns counts by outcome. A `blocked` post is written to the DB with its
    violations recorded, so `pnx queue --blocked` can show you exactly which
    channel/hook combinations are misconfigured.
    """
    now = now or utcnow()
    tzname = cfg.business.timezone
    pending = content_mod.uncompiled_content(store)[:limit]

    stats: dict[str, int] = {"queued": 0, "blocked": 0, "duplicate": 0,
                             "no_renderer": 0, "pending": 0, "approved": 0}
    blocked: list[dict[str, Any]] = []
    # bodies already queued, so `duplicate_copy` can fire across channels
    seen_bodies: set[str] = set()

    for c in pending:
        placed = False
        for ch_name, ch in cfg.channels.items():
            if not ch.enabled or ch.mode is Mode.OFF:
                continue

            # Resolve the UTM-tagged link BEFORE rendering, so the renderer's length
            # truncation accounts for the fact that a tracked URL is longer than a
            # plain one. Doing this after render is how you get posts that are over
            # Bluesky's 300-char cap by the time they hit the API.
            tracked = _tracked(cfg, ch_name, c) if cfg.business.url else ""
            rendered = render.render_for(ch_name, c, cfg.business, link=tracked)
            if rendered is None:
                stats["no_renderer"] += 1
                continue

            rep = compliance.check(
                rendered, ch.rules, cfg.business, ch.mode.value,
                seen_bodies=seen_bodies,
            )
            fp = fingerprint(c.id, ch_name)

            if store.exists_fingerprint(fp):
                stats["duplicate"] += 1
                continue

            p = make_render_post(rendered, c.id, ch.mode.value)
            p.payload = {**(rendered.extra or {}), "_violations": [
                str(v) for v in rep.violations]}

            if not rep.ok:
                p.state = State.BLOCKED
                p.last_error = compliance.format_report(rep)
                store.add_post(p, ch.mode.value)
                store.log("blocked", p.last_error, ch_name, p.id,
                          {"content": c.id})
                blocked.append({"post_id": p.id, "channel": ch_name,
                                "content": c.id, "errors": p.last_error})
                stats["blocked"] += 1
                placed = True
                continue

            # schedule
            when = scheduler.pick_time(store, ch, tzname, earliest=now)
            p.publish_at = when
            p.state = State.PENDING if ch.mode is Mode.APPROVE else State.SCHEDULED

            inst = store.add_post(p, ch.mode.value)
            if inst is None:
                stats["duplicate"] += 1
                continue
            store.log("queued",
                      f"{ch_name}: scheduled {when.isoformat()} ({p.state.value})",
                      ch_name, p.id, {"content": c.id})
            stats["pending" if p.state is State.PENDING else "queued"] += 1
            if ch.rules.community:
                import re
                seen_bodies.add(re.sub(r"\s+", " ",
                                       f"{rendered.title}\n\n{rendered.body}".strip().lower())[:400])
            placed = True

        if placed:
            store.con.execute("UPDATE content SET consumed=1 WHERE id=?", (c.id,))

    return {"stats": stats, "blocked": blocked, "content_processed": len(pending)}


def _tracked(cfg: Config, channel: str, c: Content) -> str:
    """UTM-tagged service-page link for this (channel, hook) pair."""
    from . import metrics
    return metrics.tracked(
        cfg.business,
        metrics.service_path(cfg.business, c.service_slug),
        channel,
        c.hook_id,
    )


# ---------------------------------------------------------------------------
# run: publish what is due
# ---------------------------------------------------------------------------

def run(cfg: Config, store: Store, *, dry_run: bool = False,
        client: Client | None = None, limit: int = 20,
        now: _dt.datetime | None = None) -> dict[str, Any]:
    now = now or utcnow()
    client = client or Client()
    results: list[dict[str, Any]] = []
    due = store.due_posts(now=now)[:limit]

    for row in due:
        pid = row["id"]
        ch_name = row["channel"]
        ch = cfg.channels.get(ch_name)
        if ch is None:
            store.set_state(pid, State.SKIPPED, last_error="channel no longer configured")
            continue

        # Authorisation, not mechanism. An `approve`-mode channel still publishes
        # itself -- the human approving the post is what unlocks it. What the
        # pipeline must never do is publish an *unapproved* post to a community.
        if ch.mode is Mode.OFF:
            results.append({"post_id": pid, "channel": ch_name, "outcome": "skipped",
                            "why": "channel mode is off"})
            continue
        if ch.mode is Mode.APPROVE and row["state"] != State.APPROVED.value:
            results.append({"post_id": pid, "channel": ch_name, "outcome": "held",
                            "why": "community channel: awaiting human approval "
                                   f"(state={row['state']})"})
            continue

        ok, why = ratelimit.check(store, ch, now)
        if not ok:
            # Re-schedule rather than leaving it overdue: a post that is blocked only
            # by a min-gap or a daily cap will never become legal on its own, and
            # leaving it in the past just makes every subsequent `run` re-evaluate it.
            nxt = scheduler.pick_time(store, ch, cfg.business.timezone,
                                      earliest=now + _dt.timedelta(minutes=1))
            store.set_state(pid, State.SCHEDULED, publish_at=nxt, last_error=why)
            store.log("deferred", f"{why}; moved to {nxt.isoformat()}", ch_name, pid)
            results.append({"post_id": pid, "channel": ch_name, "outcome": "deferred",
                            "why": f"{why} -> {nxt.isoformat()[:16]}"})
            continue

        inst = build_channel(cfg, ch_name, client)
        if inst is None:
            store.set_state(pid, State.SKIPPED, last_error="no adapter registered")
            results.append({"post_id": pid, "channel": ch_name, "outcome": "skipped",
                            "why": "no adapter registered"})
            continue

        configured, reason = inst.verify()
        if not configured:
            # Keep the post. A missing secret is a setup step, not a reason to
            # throw away queued work -- configure it later and the post still runs.
            nxt = scheduler.pick_time(store, ch, cfg.business.timezone,
                                      earliest=now + _dt.timedelta(hours=1))
            store.set_state(pid, State.SCHEDULED, publish_at=nxt,
                            last_error=f"not configured: {reason}")
            store.log("held", f"not configured: {reason}", ch_name, pid)
            results.append({"post_id": pid, "channel": ch_name, "outcome": "held",
                            "why": f"not configured: {reason}"})
            continue

        if dry_run:
            results.append({"post_id": pid, "channel": ch_name, "outcome": "would_publish",
                            "title": row["title"][:60]})
            continue

        ratelimit.consume(store, ch)  # count the attempt, not just the success
        from .db import row_to_post
        from .render import Rendered
        post = row_to_post(row)
        rendered = Rendered(ch_name, post.title, post.body, post.link,
                            post.tags, post.payload)

        store.update_post(pid, attempts=post.attempts + 1)
        try:
            out = inst.publish(rendered)
        except ChannelError as e:
            store.set_state(pid, State.FAILED, last_error=str(e))
            store.log("failed", str(e), ch_name, pid)
            results.append({"post_id": pid, "channel": ch_name, "outcome": "failed",
                            "why": str(e)})
            continue
        except Exception as e:  # noqa: BLE001
            store.set_state(pid, State.FAILED, last_error=f"unexpected: {e!r}")
            store.log("failed", repr(e), ch_name, pid)
            results.append({"post_id": pid, "channel": ch_name, "outcome": "failed",
                            "why": repr(e)})
            continue

        store.set_state(pid, State.PUBLISHED, published_at=utcnow(),
                        remote_url=out.get("url", ""), remote_id=out.get("id", ""),
                        last_error="")
        store.log("published", out.get("url", ""), ch_name, pid)
        results.append({"post_id": pid, "channel": ch_name, "outcome": "published",
                        "url": out.get("url", "")})

    return {"ran_at": now.isoformat(), "considered": len(due), "results": results}


# ---------------------------------------------------------------------------
# human actions
# ---------------------------------------------------------------------------

def approve(store: Store, post_id: int) -> dict[str, Any]:
    row = store.get_post(post_id)
    if not row:
        return {"ok": False, "why": f"no post {post_id}"}
    if row["state"] != State.PENDING.value:
        return {"ok": False, "why": f"post {post_id} is {row['state']}, not pending"}
    if row["mode"] != Mode.APPROVE.value:
        return {"ok": False, "why": f"post {post_id} is mode={row['mode']}, "
                                   f"no approval needed"}
    store.set_state(post_id, State.APPROVED)
    store.log("approved", "human approved", row["channel"], post_id)
    return {"ok": True, "post_id": post_id, "note": "approved; `pnx run` will post it "
                                                    "when its window arrives"}


def reject(store: Store, post_id: int, reason: str = "") -> dict[str, Any]:
    row = store.get_post(post_id)
    if not row:
        return {"ok": False, "why": f"no post {post_id}"}
    store.set_state(post_id, State.REJECTED, last_error=reason)
    store.log("rejected", reason or "no reason given", row["channel"], post_id)
    # Free the fingerprint so a corrected version can be re-queued.
    store.con.execute("DELETE FROM posts WHERE id=? AND state=?",
                      (post_id, State.REJECTED.value))
    store.con.execute("UPDATE content SET consumed=0 WHERE id=?", (row["content_id"],))
    return {"ok": True, "post_id": post_id, "note": "rejected; content re-queued"}


def mark_published_manually(store: Store, post_id: int, url: str = "") -> dict[str, Any]:
    """Record a post you submitted by hand (HN, Lobsters, a directory)."""
    row = store.get_post(post_id)
    if not row:
        return {"ok": False, "why": f"no post {post_id}"}
    store.set_state(post_id, State.PUBLISHED, published_at=utcnow(), remote_url=url)
    store.log("published_manual", url, row["channel"], post_id)
    return {"ok": True, "post_id": post_id, "url": url}


def retry(cfg: Config, store: Store,
          states: tuple[State, ...] = (State.SKIPPED, State.FAILED),
          channel: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Return stuck posts to the queue.

    `skipped` and `failed` are terminal, which is right for reporting and wrong for
    operations: fixing a bad secret or a bad rate limit should not require editing
    the SQLite file by hand. Approve-mode channels come back as PENDING, auto-mode
    as SCHEDULED, so a human's earlier compliance decision is preserved.
    """
    moved: list[int] = []
    for st in states:
        for row in store.list_posts(state=st, channel=channel, limit=limit):
            pid = row["id"]
            name = row["channel"]
            ch = cfg.channels.get(name) or _ChannelShim(name, row["mode"])
            target = State.PENDING if row["mode"] == Mode.APPROVE.value else State.SCHEDULED
            when = scheduler.pick_time(store, ch, cfg.business.timezone,
                                      earliest=utcnow())
            store.set_state(pid, target, publish_at=when, last_error="")
            store.log("retry", f"{st.value} -> {target.value}", name, pid)
            moved.append(pid)
    return {"ok": True, "moved": moved, "count": len(moved)}


class _ChannelShim:
    """Minimal Channel stand-in for a destination no longer present in channels.json.

    `retry` needs a Channel to ask about windows and gaps. Falling back to permissive
    defaults recovers the post rather than stranding it, because the queued content
    is the thing that actually matters.
    """

    def __init__(self, name: str, mode: str) -> None:
        self.name = name
        self.mode = Mode(mode) if mode in {m.value for m in Mode} else Mode.AUTO
        self.rate_per_day = 1
        self.min_gap_minutes = 60
        self.active_hours = list(range(24))
        self.weekdays = [0, 1, 2, 3, 4, 5, 6]
