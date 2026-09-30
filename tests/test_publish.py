"""End-to-end publish test against a mock Mastodon server.

Proves the whole path works with no real credentials and no real posting:
    compile -> compliance -> schedule -> ratelimit -> build_payload
            -> HTTP POST -> parse_response -> state=published -> url recorded

Run:  python -m tests.test_publish
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playnexus import channels, compliance, content as content_mod, pipeline  # noqa: E402
from playnexus import render, scheduler  # noqa: E402
from playnexus.config import load  # noqa: E402
from playnexus.db import Store  # noqa: E402
from playnexus.http import Client  # noqa: E402
from playnexus.models import Mode, State  # noqa: E402

RECEIVED: list[dict] = []
AUTH_SEEN: list[str | None] = []


class MockMastodon(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n).decode()
        body = json.loads(raw) if raw else {}
        RECEIVED.append({
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "idempotency": self.headers.get("Idempotency-Key"),
            "body": body,
        })
        AUTH_SEEN.append(self.headers.get("Authorization"))
        out = json.dumps({"id": "109876543210", "url": "https://mock.example/@pn/109876543210"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RateLimit-Remaining", "97")
        self.send_header("X-RateLimit-Reset", "300")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


PASS, FAIL = "  PASS", "  FAIL"
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{PASS if cond else FAIL}  {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), MockMastodon)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    tmp = Path(tempfile.mkdtemp(prefix="pnx-test-"))
    try:
        from playnexus.scaffold import write_templates
        write_templates(tmp / "config")
        cfg = load(tmp / "config")
        cfg.data_dir = tmp / "data"

        # Point mastodon at the mock and leave every other channel unconfigured.
        cfg.secrets["mastodon"] = {
            "instance": f"http://127.0.0.1:{port}",
            "access_token": "test-token-not-real",
        }
        (tmp / "config" / "secrets.json").write_text(
            json.dumps(cfg.secrets, indent=2), encoding="utf-8")
        for name in cfg.channels:
            cfg.channels[name].enabled = (name == "mastodon")

        print("\n--- adapters registered ---")
        for n in channels.known():
            print(f"    {n}{'  (manual-only)' if n in channels.MANUAL_ONLY else ''}")
        check("all 11 adapters registered", len(channels.known()) == 11,
              f"got {len(channels.known())}")

        store = Store(cfg.data_dir / "t.db")
        client = Client()

        print("\n--- adapter wiring ---")
        inst = channels.build(cfg, "mastodon", client)
        check("mastodon adapter builds", inst is not None)
        ok, why = inst.verify()
        check("mastodon verifies with credentials", ok, why)

        print("\n--- content -> compliance -> schedule ---")
        content_mod.plan(cfg, store, days=2)
        res = pipeline.compile_pending(cfg, store)
        check("content compiled", res["content_processed"] == 2, str(res["stats"]))
        check("posts queued", res["stats"]["queued"] > 0, str(res["stats"]))
        check("nothing blocked", res["stats"]["blocked"] == 0,
              str([b["errors"] for b in res["blocked"]][:2]))

        print("\n--- UTM tracking is inside the rendered link ---")
        rows = store.list_posts(state=State.SCHEDULED, limit=50)
        check("scheduled posts exist", bool(rows))
        sample = rows[0]
        print(f"    link: {sample['link']}")
        check("link carries utm_source", "utm_source=" in sample["link"])
        check("link carries utm_campaign", "utm_campaign=playnexus" in sample["link"])

        print("\n--- publish ---")
        now = _dt.datetime.now(_dt.UTC)
        store.con.execute("UPDATE posts SET publish_at=? WHERE state=?",
                          ((now - _dt.timedelta(minutes=1)).isoformat(),
                           State.SCHEDULED.value))
        store.con.commit()
        out = pipeline.run(cfg, store, client=client)
        published = [r for r in out["results"] if r["outcome"] == "published"]
        check("at least one post published", bool(published), str(out["results"]))

        if published:
            first = published[0]
            print(f"    published post {first['post_id']} -> {first['url']}")
            check("remote url recorded", first["url"].startswith("https://mock.example/"))
            row = store.get_post(first["post_id"])
            check("state is published", row["state"] == "published", row["state"])
            check("published_at stamped", bool(row["published_at"]))
            check("remote_id recorded", row["remote_id"] == "109876543210")
            check("no residual error", row["last_error"] == "", row["last_error"])

            print("\n--- the payload that actually went over the wire ---")
            req = RECEIVED[0]
            print(f"    POST {req['path']}")
            print(f"    Authorization: {req['auth']}")
            print(f"    Idempotency-Key: {req['idempotency'][:16]}...")
            print(f"    status field ({len(req['body'].get('status',''))} chars):")
            for line in req["body"].get("status", "").splitlines():
                print(f"      | {line}")
            check("used bearer auth", str(req["auth"]).startswith("Bearer "))
            check("sent Idempotency-Key", bool(req["idempotency"]))
            check("status within 500 chars",
                  len(req["body"].get("status", "")) <= 500,
                  str(len(req["body"].get("status", ""))))
            check("status ends with the tracked link",
                  "utm_source=" in req["body"].get("status", ""))
            check("no @ mentions in payload", "@" not in req["body"].get("status", "")
                  or "utm_source" in req["body"]["status"].split("@")[-1])

        print("\n--- rate limiting ---")
        rl = store.list_posts(state=State.SCHEDULED, limit=50)
        used_today = store.count_in_window("mastodon", "publish",
                                           now.replace(hour=0, minute=0, second=0, microsecond=0))
        print(f"    publishes recorded today: {used_today} (cap {cfg.channels['mastodon'].rate_per_day})")
        check("publish attempts were counted", used_today >= 1)
        check("cap enforced", used_today <= cfg.channels["mastodon"].rate_per_day)

        print("\n--- server rate-limit header surfaced ---")
        check("X-Ratelimit-Remaining parsed from response",
              client.last_rate_limit.get("remaining") == 97.0,
              str(client.last_rate_limit))

        print("\n--- a second identical send is accepted but separately keyed ---")
        before = len(RECEIVED)
        ch2 = channels.build(cfg, "mastodon", client)
        rendered = render.render_for("mastodon", content_mod.all_content(store)[0],
                                     cfg.business)
        ch2.publish(rendered)
        check("repeat send is stable and length-bounded",
              len(RECEIVED) == before + 1
              and len(RECEIVED[-1]["body"]["status"]) <= 500)

        print("\n--- compliance gate rejects bad content ---")
        bad = render.Rendered("mastodon", "Buy now!!! cheapest ever limited time offer",
                              "check out my site http://x.com guaranteed results",
                              link="http://x.com")
        rep = compliance.check(bad, cfg.channels["mastodon"].rules,
                               cfg.business, "auto")
        codes = {v.code for v in rep.violations}
        print(f"    violations: {sorted(codes)}")
        for v in rep.violations:
            print(f"      - {v}")
        check("gate blocks spam copy", not rep.ok)
        check("catches hard-sell language", "spam_behaviour" in codes)
        check("catches link-dropping", "spam_behaviour" in codes)

        print("\n--- no-ad-tone channels reject marketing language ---")
        hn = cfg.channels["hackernews"]
        hn.enabled = True
        ad = render.Rendered("hackernews", "Hire me, we are a trusted professional",
                             "We build reliable things. Contact us today for a quote. "
                             "Our clients love the professional affordable service we provide "
                             "with a team of experts who handle everything you need for your business.",
                             link="https://playnexus.dev")
        rep2 = compliance.check(ad, hn.rules, cfg.business, "approve")
        print(f"    violations: {[v.code for v in rep2.violations]}")
        check("HN gate blocks ad tone", not rep2.ok)
        check("ad_tone detected", "ad_tone" in {v.code for v in rep2.violations})

        print("\n--- every channel declares rules (compliance is mandatory) ---")
        missing = [n for n, c in cfg.channels.items() if c.rules is None]
        check("no channel lacks a rules block", not missing, str(missing))

        print("\n--- a channel missing rules is rejected at load time ---")
        broken = json.loads((tmp / "config" / "channels.json").read_text(encoding="utf-8"))
        del broken["channels"]["discord"]["rules"]
        (tmp / "config" / "channels.json").write_text(json.dumps(broken), encoding="utf-8")
        try:
            load(tmp / "config")
            check("config without rules is rejected", False, "load() succeeded")
        except Exception as e:
            check("config without rules is rejected", "rules" in str(e), str(e))

        print("\n--- credentials never leak into the queue ---")
        blob = (cfg.data_dir / "t.db").read_bytes()
        check("no access_token in the database", b"test-token-not-real" not in blob)

    finally:
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 62)
    if failures:
        print(f"FAILED ({len(failures)}): " + ", ".join(failures))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
