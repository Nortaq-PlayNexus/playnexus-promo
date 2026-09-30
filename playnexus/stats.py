"""Performance reporting.

Answers one question: which channels are producing published posts, and which are
just producing blocked ones? Everything else is decoration.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from .config import Config
from .db import Store, parse_iso, utcnow
from .models import State

C = {"r": "\033[0m", "b": "\033[1m", "dim": "\033[2m",
     "red": "\033[31m", "grn": "\033[32m", "yel": "\033[33m", "cyn": "\033[36m"}


def _c(t: str, k: str) -> str:
    return f"{C.get(k,'')}{t}{C['r']}" if t else t


def channel_summary(store: Store) -> list[dict[str, Any]]:
    out = []
    for channel, states in sorted(store.counts_by_channel().items()):
        total = sum(states.values())
        out.append({
            "channel": channel,
            "total": total,
            "published": states.get(State.PUBLISHED.value, 0),
            "pending": states.get(State.PENDING.value, 0),
            "scheduled": states.get(State.SCHEDULED.value, 0),
            "approved": states.get(State.APPROVED.value, 0),
            "blocked": states.get(State.BLOCKED.value, 0),
            "failed": states.get(State.FAILED.value, 0),
            "rejected": states.get(State.REJECTED.value, 0),
        })
    return out


def published_last_n_days(store: Store, days: int) -> list[dict[str, Any]]:
    since = utcnow() - _dt.timedelta(days=days)
    rows = store.con.execute(
        "SELECT channel, COUNT(*) c, remote_url FROM posts "
        "WHERE state=? AND published_at >= ? GROUP BY channel",
        (State.PUBLISHED.value, since.isoformat()),
    ).fetchall()
    return [{"channel": r["channel"], "count": r["c"]} for r in rows]


def top_failure_reasons(store: Store, limit: int = 8) -> list[tuple[str, int]]:
    rows = store.con.execute(
        "SELECT last_error FROM posts WHERE state IN (?,?) AND last_error != '' "
        "ORDER BY updated_at DESC LIMIT 200",
        (State.BLOCKED.value, State.FAILED.value),
    ).fetchall()
    counts: dict[str, int] = {}
    for r in rows:
        first = (r["last_error"] or "").strip().splitlines()
        key = first[0].strip() if first else "?"
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:limit]


def render_report(cfg: Config, store: Store, days: int = 30) -> str:
    rows = channel_summary(store)
    counts = store.counts_by_state()
    out: list[str] = []

    out.append(_c("\nQueue totals", "b"))
    if not counts:
        out.append("  (empty — run `python -m playnexus plan && python -m playnexus compile`)")
    else:
        for state, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            colour = "grn" if state == "published" else (
                "red" if state in ("blocked", "failed") else "dim")
            out.append(f"  {_c(f'{state:<12}', colour)} {n}")

    out.append(_c(f"\nPublished, last {days} days", "b"))
    recent = {r["channel"]: r["count"] for r in published_last_n_days(store, days)}
    if not recent:
        out.append("  nothing published yet")
    else:
        for ch, n in sorted(recent.items(), key=lambda kv: -kv[1]):
            rate = cfg.channels[ch].rate_per_day if ch in cfg.channels else 0
            out.append(f"  {ch:<14} {n:>4} posts   (cap {rate}/day)")

    if rows:
        out.append(_c("\nPer channel", "b"))
        out.append(f"  {'channel':<14}{'pub':>5}{'pend':>6}{'sch':>5}"
                   f"{'appr':>6}{'block':>7}{'fail':>6}")
        for r in rows:
            out.append(f"  {r['channel']:<14}{r['published']:>5}{r['pending']:>6}"
                       f"{r['scheduled']:>5}{r['approved']:>6}{r['blocked']:>7}"
                       f"{r['failed']:>6}")

    reasons = top_failure_reasons(store)
    if reasons:
        out.append(_c("\nTop blocked/failed reasons (fix these, they are config bugs)", "yel"))
        for reason, n in reasons:
            out.append(f"  {n:>4}  {reason[:88]}")

    out.append(_c("\nNext: `python -m playnexus ratelimit` to see posting headroom.", "dim"))
    return "\n".join(out)
