"""Command line interface.

    python -m playnexus init
    python -m playnexus doctor
    python -m playnexus plan --days 7
    python -m playnexus compile
    python -m playnexus queue [--pending] [--blocked] [--channel X]
    python -m playnexus show 12 [--manual] [--raw]
    python -m playnexus approve 12 | reject 12 --reason "..."
    python -m playnexus run [--dry-run]
    python -m playnexus stats
    python -m playnexus review
    python -m playnexus hn
    python -m playnexus gh topics
    python -m playnexus secret reddit client_id=xxx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import content as content_mod, pipeline, scheduler, stats as stats_mod
from .channels import MANUAL_ONLY, build as build_channel, known as known_channels
from .config import Config, ConfigError, load, save_secrets
from .db import Store, iso, utcnow
from .http import Client
from .models import Mode, State

C = {
    "r": "\033[0m", "b": "\033[1m", "dim": "\033[2m",
    "red": "\033[31m", "grn": "\033[32m", "yel": "\033[33m",
    "blu": "\033[34m", "mag": "\033[35m", "cyn": "\033[36m",
}


def _c(text: str, colour: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{C.get(colour, '')}{text}{C['r']}"


def _state_colour(state: str) -> str:
    return {
        "published": "grn", "scheduled": "cyn", "ready": "cyn", "approved": "grn",
        "pending": "yel", "blocked": "red", "failed": "red", "rejected": "red",
        "skipped": "dim", "draft": "dim",
    }.get(state, "")


# ---------------------------------------------------------------------------

def _load(args: argparse.Namespace) -> tuple[Config, Store]:
    cfg = load(Path(args.config) if args.config else None)
    store = Store(cfg.data_dir / "playnexus.db")
    return cfg, store


def cmd_init(args: argparse.Namespace) -> int:
    from .scaffold import write_templates
    cfgdir = Path(args.config) if args.config else Path("config")
    written = write_templates(cfgdir)
    for p in written:
        print(f"  wrote {p}")
    print(f"\nNext: edit {cfgdir / 'business.json'}, then `python -m playnexus doctor`")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg, store = _load(args)
    client = Client()
    print(_c(f"\n{business_check(cfg)}\n", "b"))

    reg = known_channels()
    print(_c("Channels", "b"))
    problems = 0
    for name, ch in sorted(cfg.channels.items()):
        flags = []
        if name not in reg:
            flags.append("NO ADAPTER")
        if not ch.enabled:
            flags.append(_c("disabled", "dim"))
        if ch.mode is Mode.AUTO and name in MANUAL_ONLY:
            flags.append(_c("AUTO but manual-only platform", "red"))
            problems += 1
        if not ch.active_hours or not ch.weekdays:
            flags.append(_c("empty posting window", "red"))
            problems += 1
        if ch.min_gap_minutes < 30:
            flags.append(_c("min_gap < 30m, risky", "yel"))
        line = f"  {name:<14} {ch.mode.value:<8} {scheduler.describe_window(ch, cfg.business.timezone)}"
        if flags:
            line += "  " + " ".join(flags)
        print(line)

        if ch.enabled and name in reg:
            inst = build_channel(cfg, name, client)
            if inst:
                ok, reason = inst.verify()
                mark = _c(" ok ", "grn") if ok else _c("needs config", "yel")
                print(f"    {mark} {reason}")
                if not ok:
                    problems += 0  # not fatal, it's a setup step
    print()
    if problems:
        print(_c(f"{problems} problem(s) need fixing before `pnx run` is safe.", "red"))
        return 1
    print(_c("Configuration looks safe to run.", "grn"))
    return 0


def business_check(cfg: Config) -> str:
    b = cfg.business
    lines = [f"{b.name} — {b.tagline}", f"  url: {b.url or _c('NOT SET', 'red')}",
             f"  contact: {b.contact or _c('NOT SET', 'yel')}",
             f"  timezone: {b.timezone}",
             f"  services: {len(b.services)}  hooks: {len(cfg.hooks)}",
             f"  forbidden words: {len(b.forbidden)}"]
    if not b.url:
        lines.append(_c("  ! business.url is required for UTM tracking", "red"))
    uniq = [h.id for h in cfg.hooks]
    if len(uniq) != len(set(uniq)):
        lines.append(_c("  ! duplicate hook ids in hooks.json", "red"))
    return "\n".join(lines)


def cmd_plan(args: argparse.Namespace) -> int:
    cfg, store = _load(args)
    res = content_mod.plan(cfg, store, days=args.days)
    print(f"Planned {res['created']} new content items "
          f"({res['skipped']} already existed) starting {res['start']}.")
    print("Now run `python -m playnexus compile` to render + schedule them.")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    cfg, store = _load(args)
    res = pipeline.compile_pending(cfg, store, limit=args.limit)
    s = res["stats"]
    print(f"Compiled {res['content_processed']} content items:")
    for k in ("queued", "pending", "blocked", "duplicate", "no_renderer"):
        colour = "red" if k == "blocked" and s[k] else ""
        print(f"  {k:<12} {s[k]}")
    if res["blocked"]:
        print(_c("\nBlocked (fix config or the hook, then re-run compile):", "red"))
        for b in res["blocked"][:15]:
            print(f"  post {b['post_id']} [{b['channel']}] {b['content']}")
            for line in b["errors"].splitlines():
                print(f"      {line}")
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    cfg, store = _load(args)
    states = []
    if args.pending:
        states = [State.PENDING]
    elif args.blocked:
        states = [State.BLOCKED]
    elif args.scheduled:
        states = [State.SCHEDULED, State.READY, State.APPROVED]
    else:
        states = [State.PENDING, State.SCHEDULED, State.READY,
                  State.APPROVED, State.BLOCKED, State.FAILED]

    rows = []
    for s in states:
        rows.extend(store.list_posts(state=s, channel=args.channel, limit=args.limit))
    rows.sort(key=lambda r: (r["publish_at"] or r["created_at"] or ""))

    if not rows:
        print("Queue is empty. Run `python -m playnexus plan` then `compile`.")
        return 0

    for r in rows:
        st = r["state"]
        when = (r["publish_at"] or "")[:16].replace("T", " ")
        head = (f"  {r['id']:>4}  {_c(f'{st:<9}', _state_colour(st))} "
                f"{r['channel']:<12} {when:<16} {r['title'][:52]}")
        print(head)
        if st == State.BLOCKED.value and r["last_error"]:
            for line in r["last_error"].splitlines()[:3]:
                print(_c(f"         {line}", "red"))
        if r["last_error"] and st == State.FAILED.value:
            print(_c(f"         {r['last_error'][:100]}", "red"))
    print(f"\n{len(rows)} post(s). "
          f"Approve with: python -m playnexus approve <id>")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    cfg, store = _load(args)
    r = store.get_post(args.id)
    if not r:
        print(f"no post {args.id}")
        return 1
    print(_c(f"post {r['id']}  {r['channel']}  {r['state']}  mode={r['mode']}", "b"))
    print(_c(f"content: {r['content_id']}   fingerprint: {r['fingerprint'][:12]}", "dim"))
    print(_c(f"publish_at: {r['publish_at']}", "dim"))
    if r["last_error"] and r["state"] in ("blocked", "failed"):
        print(_c("\n" + r["last_error"], "red"))
    print(_c("\n" + "-" * 70, "dim"))
    print(r["title"])
    print()
    print(r["body"])
    if r["tags"]:
        print(_c(f"\ntags: {', '.join(json.loads(r['tags']))}", "dim"))

    payload = json.loads(r["payload"] or "{}")
    if args.manual or r["channel"] in MANUAL_ONLY:
        if r["channel"] == "reddit":
            try:
                sub = (payload or {}).get("subreddit") or "?"
                rules = build_channel(cfg, "reddit", Client()).sub_rules(sub)
                print(_c(f"\nr/{sub} rules (read this before posting):\n{rules}", "yel"))
            except Exception as e:  # noqa: BLE001
                print(_c(f"\n(could not fetch subreddit rules: {e})", "dim"))
        if args.raw:
            print(_c("\n" + json.dumps(payload, indent=2)[:4000], "dim"))
        elif r["channel"] == "hackernews":
            print(_c(f"\nsubmit at: {payload.get('submit_url')}", "grn"))
            print(_c("\nfirst comment to post under it:\n", "b"))
            print(payload.get("first_comment", ""))
        elif r["channel"] == "lobsters":
            print(_c(f"\nsubmit at: {payload.get('submit_url')}", "grn"))
            print(f"tags: {payload.get('tags')}")
        elif r["channel"] == "manual":
            print(_c("\ndirectories to submit to:", "b"))
            for d in (payload.get("directories") or []):
                print(f"  {d['name']:<16} {d['cost']:<14} {d['url']}")
                print(_c(f"     {d['notes']}", "dim"))
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    _, store = _load(args)
    r = pipeline.approve(store, args.id)
    print(r.get("note") or r.get("why"))
    return 0 if r["ok"] else 1


def cmd_reject(args: argparse.Namespace) -> int:
    _, store = _load(args)
    r = pipeline.reject(store, args.id, args.reason)
    print(r.get("note") or r.get("why"))
    return 0 if r["ok"] else 1


def cmd_done(args: argparse.Namespace) -> int:
    _, store = _load(args)
    r = pipeline.mark_published_manually(store, args.id, args.url or "")
    print(f"recorded manual publish: {r.get('url') or r.get('why')}")
    return 0 if r["ok"] else 1


def cmd_run(args: argparse.Namespace) -> int:
    cfg, store = _load(args)
    res = pipeline.run(cfg, store, dry_run=args.dry_run, limit=args.limit)
    if not res["results"]:
        print("Nothing due.")
        return 0
    for r in res["results"]:
        colour = {"published": "grn", "failed": "red", "deferred": "yel",
                  "skipped": "dim", "would_publish": "cyn"}.get(r["outcome"], "")
        extra = r.get("url") or r.get("why") or ""
        print(f"  {r['post_id']:>4} {r['channel']:<12} "
              f"{_c(r['outcome'], colour):<20} {str(extra)[:80]}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    cfg, store = _load(args)
    print(stats_mod.render_report(cfg, store, days=args.days))
    return 0


def cmd_ratelimit(args: argparse.Namespace) -> int:
    from . import ratelimit as rl
    cfg, store = _load(args)
    now = utcnow()
    print(_c(f"{'channel':<14} {'used':>5} {'cap':>4} {'left':>5}  {'next allowed':<22} status", "b"))
    for name, ch in sorted(cfg.channels.items()):
        used = rl.used_today(store, name, now)
        ok, why = rl.check(store, ch, now)
        nxt = scheduler.next_window(ch, cfg.business.timezone, after=now)
        mark = _c("ready", "grn") if ok else _c(why, "yel")
        print(f"  {name:<12} {used:>5} {ch.rate_per_day:>4} "
              f"{max(0, ch.rate_per_day - used):>5}  {nxt.isoformat()[:16]:<22} {mark}")
    return 0


def cmd_secret(args: argparse.Namespace) -> int:
    cfg, _ = _load(args)
    channel = args.channel
    if channel not in cfg.channels:
        print(f"unknown channel {channel!r}. known: {', '.join(sorted(cfg.channels))}")
        return 1
    for pair in args.pairs:
        k, _, v = pair.partition("=")
        if not v:
            print(f"  expected key=value, got {pair!r}")
            return 1
        save_secrets(cfg, channel, {k: v})
        print(f"  set {channel}.{k}")
    print(f"\nSaved to {cfg.config_dir / 'secrets.json'} (gitignored).")
    return 0


def cmd_hn(args: argparse.Namespace) -> int:
    cfg, _ = _load(args)
    inst = build_channel(cfg, "hackernews", Client())
    if inst is None:
        print("hackernews channel is not in channels.json")
        return 1
    ok, why = inst.verify()
    if not ok:
        print(why)
        return 1
    print(_c("\nYour recent submissions:", "b"))
    for s in inst.latest_submissions():
        flag = _c(" [DEAD]", "red") if s["dead"] else ""
        print(f"  {s['score']:>4} pts {s['descendants']:>4} com  {s['title'][:60]}{flag}")
        print(_c(f"       {s['url']}", "dim"))
    if args.queue:
        print(_c("\nCurrent Show HN (for tone calibration, not for copying):", "b"))
        for s in inst.show_hn_queue(20):
            print(f"  {s['score']:>4}  {s['title'][:70]}")
    return 0


def cmd_gh(args: argparse.Namespace) -> int:
    cfg, _ = _load(args)
    inst = build_channel(cfg, "github", Client())
    if inst is None:
        print("github channel is not in channels.json")
        return 1
    ok, why = inst.verify()
    if not ok:
        print(why)
        return 1
    if args.gh_cmd == "topics":
        repo = args.repo or cfg.channels["github"].config.get("repo", "")
        topics = [t for t in (args.topics or [])] or list(cfg.channels["github"].config.get("topics", []))
        if not repo or not topics:
            print("need --repo owner/name and either --topics or channels.json.github.topics")
            return 1
        out = inst.set_topics(repo, topics)
        print(f"set {len(topics)} topics on {repo}: {', '.join(topics)}")
        return 0
    if args.gh_cmd == "readme":
        outdir = cfg.data_dir.parent / "out" / "github" / cfg.secret("github", "username", "user")
        outdir.mkdir(parents=True, exist_ok=True)
        p = outdir / f"{cfg.secret('github', 'username', 'user')}.md"
        p.write_text(inst.render_profile_readme(cfg.business), encoding="utf-8")
        print(f"wrote {p}\nPush it to github.com/{cfg.secret('github', 'username', 'user')}/"
              f"{cfg.secret('github', 'username', 'user')}")
        return 0
    return 1


def cmd_retry(args: argparse.Namespace) -> int:
    cfg, store = _load(args)
    states = [State.SKIPPED, State.FAILED]
    if args.blocked:
        states = [State.BLOCKED]
    res = pipeline.retry(cfg, store, states=tuple(states), channel=args.channel)
    if not res["count"]:
        print("Nothing to retry.")
        return 0
    print(f"Moved {res['count']} post(s) back into the queue: "
          f"{', '.join(str(i) for i in res['moved'][:30])}")
    if State.BLOCKED in states:
        print(_c("Note: blocked posts are still blocked. Fix the reason shown by "
                 "`pnx queue --blocked` first, or the retry just re-blocks them.", "yel"))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    from .review import serve
    cfg, store = _load(args)
    serve(cfg, store, host=args.host, port=args.port, open_browser=not args.no_open)
    return 0


# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="playnexus", description="PlayNexus promotion pipeline")
    p.add_argument("--config", help="path to config directory")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="write config templates")
    s.add_argument("--config")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("doctor", help="check every channel's config and rules")
    s.add_argument("--config")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("plan", help="generate upcoming content items")
    s.add_argument("--config")
    s.add_argument("--days", type=int, default=7)
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("compile", help="render content, run the compliance gate, schedule")
    s.add_argument("--config")
    s.add_argument("--limit", type=int, default=60)
    s.set_defaults(func=cmd_compile)

    s = sub.add_parser("queue", help="list queued and pending posts")
    s.add_argument("--config")
    s.add_argument("--pending", action="store_true")
    s.add_argument("--blocked", action="store_true")
    s.add_argument("--scheduled", action="store_true")
    s.add_argument("--channel")
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(func=cmd_queue)

    s = sub.add_parser("show", help="print one post in full")
    s.add_argument("id", type=int)
    s.add_argument("--config")
    s.add_argument("--manual", action="store_true",
                   help="show the manual-submission details")
    s.add_argument("--raw", action="store_true", help="dump the channel payload as JSON")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("approve", help="approve a pending community post")
    s.add_argument("id", type=int)
    s.add_argument("--config")
    s.set_defaults(func=cmd_approve)

    s = sub.add_parser("reject", help="reject a pending post and re-queue its content")
    s.add_argument("id", type=int)
    s.add_argument("--config")
    s.add_argument("--reason", default="")
    s.set_defaults(func=cmd_reject)

    s = sub.add_parser("done", help="record a post you submitted by hand")
    s.add_argument("id", type=int)
    s.add_argument("--config")
    s.add_argument("--url", default="")
    s.set_defaults(func=cmd_done)

    s = sub.add_parser("run", help="publish everything due, in auto mode only")
    s.add_argument("--config")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("stats", help="performance report")
    s.add_argument("--config")
    s.add_argument("--days", type=int, default=30)
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("ratelimit", help="per-channel quota and next allowed time")
    s.add_argument("--config")
    s.set_defaults(func=cmd_ratelimit)

    s = sub.add_parser("secret", help="store a credential")
    s.add_argument("channel")
    s.add_argument("pairs", nargs="+", help="key=value")
    s.add_argument("--config")
    s.set_defaults(func=cmd_secret)

    s = sub.add_parser("hn", help="your HN submission history (read-only)")
    s.add_argument("--config")
    s.add_argument("--queue", action="store_true", help="also show current Show HN")
    s.set_defaults(func=cmd_hn)

    s = sub.add_parser("gh", help="github helpers")
    s.add_argument("gh_cmd", choices=["topics", "readme"])
    s.add_argument("--config")
    s.add_argument("--repo")
    s.add_argument("--topics", nargs="*")
    s.set_defaults(func=cmd_gh)

    s = sub.add_parser("retry", help="return skipped/failed posts to the queue")
    s.add_argument("--config")
    s.add_argument("--channel")
    s.add_argument("--blocked", action="store_true",
                   help="also retry blocked posts (they usually re-block)")
    s.set_defaults(func=cmd_retry)

    s = sub.add_parser("review", help="local web UI for approving posts")
    s.add_argument("--config")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8777)
    s.add_argument("--no-open", action="store_true")
    s.set_defaults(func=cmd_review)

    return p


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252 and will mangle the em-dashes and box
    # characters in our violation messages. Force UTF-8 rather than degrade to '?'.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as e:
        print(_c(f"config error: {e}", "red"), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
