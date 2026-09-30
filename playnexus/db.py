"""SQLite persistence: content library, post queue, event log, rate counters.

Sliding-window counters live in the DB rather than in RAM on purpose: an in-memory
limiter forgets everything on restart, and a restart is exactly how you blow a
daily quota and get an account suspended.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .models import Content, Post, Rendered, State

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS content (
    id          TEXT PRIMARY KEY,
    service     TEXT NOT NULL,
    hook_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]',
    link        TEXT NOT NULL DEFAULT '',
    proof       TEXT NOT NULL DEFAULT '',
    cta         TEXT NOT NULL DEFAULT '',
    community   TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    consumed    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS posts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id   TEXT NOT NULL REFERENCES content(id),
    channel      TEXT NOT NULL,
    mode         TEXT NOT NULL,
    state        TEXT NOT NULL,
    fingerprint  TEXT NOT NULL,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    link         TEXT NOT NULL DEFAULT '',
    tags         TEXT NOT NULL DEFAULT '[]',
    payload      TEXT NOT NULL DEFAULT '{}',
    publish_at   TEXT,
    published_at TEXT,
    remote_url   TEXT NOT NULL DEFAULT '',
    remote_id    TEXT NOT NULL DEFAULT '',
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE (fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_posts_state ON posts(state, publish_at);
CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel, state);

CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at      TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT '',
    kind    TEXT NOT NULL,
    post_id INTEGER,
    message TEXT NOT NULL DEFAULT '',
    data    TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_at ON events(at);

CREATE TABLE IF NOT EXISTS counters (
    channel TEXT NOT NULL,
    bucket  TEXT NOT NULL,
    ts      TEXT NOT NULL,
    PRIMARY KEY (channel, bucket, ts)
);

CREATE TABLE IF NOT EXISTS kv (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);
"""


def utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def iso(dt: _dt.datetime | None) -> str | None:
    return dt.astimezone(_dt.UTC).isoformat() if dt else None


def parse_iso(s: str | None) -> _dt.datetime | None:
    if not s:
        return None
    d = _dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=_dt.UTC)


def fingerprint(content_id: str, channel: str, variant: str = "") -> str:
    raw = f"{content_id}|{channel}|{variant}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False because the review server is a ThreadingHTTPServer:
        # each request lands on a new thread, and the default would raise
        # "SQLite objects created in a thread can only be used in that same thread"
        # on every DB route. Callers that share a Store across threads MUST
        # serialise access -- review.py does, with a module-level lock.
        self.con = sqlite3.connect(
            str(self.path), timeout=30, isolation_level=None,
            check_same_thread=False,
        )
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---------- content ----------

    def put_content(self, c: Content) -> bool:
        """Insert content. Returns False if the id already exists."""
        try:
            self.con.execute(
                "INSERT INTO content (id,service,hook_id,title,body,tags,link,proof,"
                "cta,community,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (c.id, c.service_slug, c.hook_id, c.title, c.body,
                 json.dumps(c.tags), c.link, c.proof, c.cta, c.community, iso(utcnow())),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_content(self, content_id: str) -> dict[str, Any] | None:
        r = self.con.execute("SELECT * FROM content WHERE id=?", (content_id,)).fetchone()
        return dict(r) if r else None

    def content_count(self) -> int:
        return self.con.execute("SELECT COUNT(*) c FROM content").fetchone()["c"]

    def prune_content(self, keep_ids: Iterable[str]) -> int:
        keep = list(keep_ids)
        if not keep:
            return 0
        q = ",".join("?" * len(keep))
        cur = self.con.execute(
            f"DELETE FROM content WHERE id NOT IN ({q}) AND consumed=0", keep
        )
        return cur.rowcount or 0

    # ---------- posts ----------

    def add_post(self, p: Post, mode: str) -> Post | None:
        """Insert a post. Returns the post, or None if the fingerprint already exists."""
        try:
            cur = self.con.execute(
                "INSERT INTO posts (content_id,channel,mode,state,fingerprint,title,body,"
                "link,tags,payload,publish_at,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.content_id, p.channel, mode, p.state.value, p.fingerprint, p.title,
                 p.body, p.link, json.dumps(p.tags), json.dumps(p.payload),
                 iso(p.publish_at), iso(p.created_at), iso(p.updated_at)),
            )
            p.id = cur.lastrowid
            return p
        except sqlite3.IntegrityError:
            return None

    def get_post(self, post_id: int) -> dict[str, Any] | None:
        r = self.con.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        return dict(r) if r else None

    def update_post(self, post_id: int, **fields: Any) -> None:
        if not fields:
            return
        for k in ("tags", "payload"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k])
        for k in ("publish_at", "published_at"):
            if k in fields:
                fields[k] = iso(fields[k])
        fields["updated_at"] = iso(utcnow())
        cols = ", ".join(f"{k}=?" for k in fields)
        self.con.execute(
            f"UPDATE posts SET {cols} WHERE id=?",
            (*fields.values(), post_id),
        )

    def set_state(self, post_id: int, state: State, **fields: Any) -> None:
        self.update_post(post_id, state=state.value, **fields)

    def due_posts(self, now: _dt.datetime | None = None, states: tuple[State, ...] =
                  (State.SCHEDULED, State.READY, State.APPROVED)) -> list[dict[str, Any]]:
        now = now or utcnow()
        q = ",".join("?" * len(states))
        rows = self.con.execute(
            f"SELECT * FROM posts WHERE state IN ({q}) AND publish_at <= ? "
            f"ORDER BY publish_at ASC",
            (*[s.value for s in states], iso(now)),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_posts(self, state: State | None = None, channel: str | None = None,
                   limit: int = 50) -> list[dict[str, Any]]:
        where, args = [], []
        if state:
            where.append("state=?")
            args.append(state.value)
        if channel:
            where.append("channel=?")
            args.append(channel)
        sql = "SELECT * FROM posts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY COALESCE(publish_at, created_at) DESC, id DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def exists_fingerprint(self, fp: str) -> bool:
        r = self.con.execute("SELECT 1 FROM posts WHERE fingerprint=?", (fp,)).fetchone()
        return r is not None

    def counts_by_state(self) -> dict[str, int]:
        rows = self.con.execute("SELECT state, COUNT(*) c FROM posts GROUP BY state").fetchall()
        return {r["state"]: r["c"] for r in rows}

    def counts_by_channel(self) -> dict[str, dict[str, int]]:
        rows = self.con.execute(
            "SELECT channel, state, COUNT(*) c FROM posts GROUP BY channel, state"
        ).fetchall()
        out: dict[str, dict[str, int]] = {}
        for r in rows:
            out.setdefault(r["channel"], {})[r["state"]] = r["c"]
        return out

    # ---------- events ----------

    def log(self, kind: str, message: str = "", channel: str = "",
            post_id: int | None = None, data: dict[str, Any] | None = None) -> None:
        self.con.execute(
            "INSERT INTO events (at,channel,kind,post_id,message,data) VALUES (?,?,?,?,?,?)",
            (iso(utcnow()), channel, kind, post_id, message, json.dumps(data or {})),
        )

    def events(self, limit: int = 50, kind: str | None = None) -> list[dict[str, Any]]:
        if kind:
            rows = self.con.execute(
                "SELECT * FROM events WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, limit)
            ).fetchall()
        else:
            rows = self.con.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- counters ----------

    def count_in_window(self, channel: str, bucket: str, since: _dt.datetime) -> int:
        r = self.con.execute(
            "SELECT COUNT(*) c FROM counters WHERE channel=? AND bucket=? AND ts >= ?",
            (channel, bucket, iso(since)),
        ).fetchone()
        return r["c"]

    def bump(self, channel: str, bucket: str = "publish") -> None:
        self.con.execute(
            "INSERT INTO counters (channel,bucket,ts) VALUES (?,?,?)",
            (channel, bucket, iso(utcnow())),
        )

    def last_publish(self, channel: str) -> _dt.datetime | None:
        r = self.con.execute(
            "SELECT ts FROM counters WHERE channel=? AND bucket='publish' "
            "ORDER BY ts DESC LIMIT 1", (channel,),
        ).fetchone()
        return parse_iso(r["ts"]) if r else None

    # -- scheduled (not yet published) -----------------------------------
    #
    # The scheduler must respect work that is already queued, not just work that has
    # already shipped. Without these two, compiling a week of content dumps every
    # post for a channel into the same hourly window and the min-gap rule is a no-op.

    _LIVE_STATES = ("scheduled", "ready", "approved", "pending")

    def last_scheduled(self, channel: str) -> _dt.datetime | None:
        q = ",".join("?" * len(self._LIVE_STATES))
        r = self.con.execute(
            f"SELECT publish_at FROM posts WHERE channel=? AND state IN ({q}) "
            f"AND publish_at IS NOT NULL ORDER BY publish_at DESC LIMIT 1",
            (channel, *self._LIVE_STATES),
        ).fetchone()
        return parse_iso(r["publish_at"]) if r else None

    def last_activity(self, channel: str) -> _dt.datetime | None:
        """Latest of (last actual publish, last scheduled post)."""
        a, b = self.last_publish(channel), self.last_scheduled(channel)
        if a and b:
            return max(a, b)
        return a or b

    def scheduled_on_day(self, channel: str, day: _dt.datetime) -> int:
        q = ",".join("?" * len(self._LIVE_STATES))
        start = day.astimezone(_dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + _dt.timedelta(days=1)
        r = self.con.execute(
            f"SELECT COUNT(*) c FROM posts WHERE channel=? AND state IN ({q}) "
            f"AND publish_at >= ? AND publish_at < ?",
            (channel, *self._LIVE_STATES, iso(start), iso(end)),
        ).fetchone()
        return r["c"]

    # ---------- kv ----------

    def kv_get(self, k: str, default: Any = None) -> Any:
        r = self.con.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(r["v"]) if r else default

    def kv_set(self, k: str, v: Any) -> None:
        self.con.execute(
            "INSERT INTO kv (k,v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (k, json.dumps(v)),
        )


def row_to_post(row: dict[str, Any]) -> Post:
    return Post(
        id=row["id"],
        content_id=row["content_id"],
        channel=row["channel"],
        state=State(row["state"]),
        fingerprint=row["fingerprint"],
        title=row["title"],
        body=row["body"],
        link=row["link"],
        tags=json.loads(row["tags"] or "[]"),
        payload=json.loads(row["payload"] or "{}"),
        publish_at=parse_iso(row["publish_at"]),
        published_at=parse_iso(row["published_at"]),
        remote_url=row["remote_url"],
        remote_id=row["remote_id"],
        attempts=row["attempts"],
        last_error=row["last_error"],
        created_at=parse_iso(row["created_at"]) or utcnow(),
        updated_at=parse_iso(row["updated_at"]) or utcnow(),
    )


def make_render_post(rendered: Rendered, content_id: str, mode: str) -> Post:
    return Post(
        id=None,
        content_id=content_id,
        channel=rendered.channel,
        state=State.DRAFT,
        fingerprint=fingerprint(content_id, rendered.channel),
        title=rendered.title,
        body=rendered.body,
        link=rendered.link,
        tags=rendered.tags,
        payload=rendered.extra,
    )
