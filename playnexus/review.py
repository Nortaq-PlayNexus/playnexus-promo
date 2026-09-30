"""Local review UI.

Binds to 127.0.0.1 by default. There is no auth because there is no reason for it to
be reachable off-box; if you change --host to 0.0.0.0 you have put an unauthenticated
"publish to my accounts" endpoint on your LAN, so don't.

Stdlib http.server only. No framework, no build step.
"""

from __future__ import annotations

import html
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import pipeline
from .config import Config
from .db import Store
from .models import State

_LOCK = threading.Lock()

STYLE = """
:root{--bg:#0f1115;--card:#171a21;--fg:#e6e8ee;--dim:#8b93a7;--line:#262b36;
--grn:#3fb950;--red:#f85149;--yel:#d29922;--cyn:#58a6ff;--acc:#6d5dfb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:940px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:32px 0 12px;
color:var(--dim);text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.sub{color:var(--dim);font-size:13px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:18px 20px;margin-bottom:14px}
.meta{display:flex;gap:10px;align-items:center;flex-wrap:wrap;
font-size:12px;color:var(--dim);margin-bottom:10px}
.pill{padding:2px 9px;border-radius:99px;font-size:11px;font-weight:600;
text-transform:uppercase;letter-spacing:.04em}
.p-pending{background:#3d2e0b;color:var(--yel)}
.p-approved,.p-published{background:#0f2c17;color:var(--grn)}
.p-blocked,.p-failed{background:#3d1414;color:var(--red)}
.p-scheduled,.p-ready{background:#0d2438;color:var(--cyn)}
.ch{background:#221f3d;color:#b7adff}
.title{font-size:17px;font-weight:650;margin-bottom:10px;line-height:1.35}
.body{white-space:pre-wrap;font-size:14px;color:#cdd3e0;background:#11141a;
border:1px solid var(--line);border-radius:7px;padding:14px;margin-bottom:14px;
max-height:340px;overflow:auto}
.link{font-size:12px;color:var(--cyn);word-break:break-all;margin-bottom:12px}
.actions{display:flex;gap:9px;flex-wrap:wrap}
button{font:inherit;font-size:13px;font-weight:600;padding:7px 15px;border-radius:7px;
border:1px solid var(--line);background:#1e222b;color:var(--fg);cursor:pointer}
button:hover{border-color:var(--acc)}
button.ok{background:#12351d;border-color:#1d5c2c;color:#7ee787}
button.no{background:#3a1414;border-color:#6b2020;color:#ff9492}
.viol{background:#2a1416;border:1px solid #5c2226;color:#ffb4ae;border-radius:7px;
padding:11px 13px;font-size:12.5px;white-space:pre-wrap;margin-bottom:12px;
font-family:ui-monospace,Consolas,monospace}
.empty{color:var(--dim);text-align:center;padding:60px 0}
code{background:#11141a;padding:1px 5px;border-radius:4px;font-size:12.5px}
.legend{color:var(--dim);font-size:12.5px;margin-top:34px;line-height:1.8}
"""

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>PlayNexus review</title><style>{style}</style></head><body><div class=wrap>
<h1>PlayNexus review</h1>
<div class=sub>{sub}</div>
{body}
<div class=legend>
<b>Only auto-mode channels ever publish without you.</b> Approving a post means
<i>you</i> have read it and confirmed it fits that community's rules.<br>
Blocked posts are shown so you can see which channel/hook pairs are misconfigured &mdash;
that is a config bug, not a content problem.<br>
Refresh to reload. Nothing here is sent anywhere: it is a local HTTP server bound to
127.0.0.1.
</div></div></body></html>"""


def _card(post: dict[str, Any], store: Store) -> str:
    pid = post["id"]
    state = post["state"]
    payload = json.loads(post["payload"] or "{}")
    manual = post["channel"] in ("hackernews", "lobsters", "manual")

    parts = [f'<div class=card><div class=meta>']
    parts.append(f'<span class="pill p-{state}">{state}</span>')
    parts.append(f'<span class="pill ch">{html.escape(post["channel"])}</span>')
    parts.append(f'<span>mode={html.escape(post["mode"])}</span>')
    parts.append(f'<span>post #{pid}</span>')
    when = (post["publish_at"] or "")[:16].replace("T", " ")
    parts.append(f'<span>{when}</span>')
    parts.append('</div>')

    parts.append(f'<div class=title>{html.escape(post["title"])}</div>')
    if post["link"]:
        parts.append(f'<div class=link>{html.escape(post["link"])}</div>')
    if state == "blocked" and post["last_error"]:
        parts.append(f'<div class=viol>{html.escape(post["last_error"])}</div>')
    elif state == "failed" and post["last_error"]:
        parts.append(f'<div class=viol>{html.escape(post["last_error"])}</div>')
    parts.append(f'<div class=body>{html.escape(post["body"])}</div>')

    if manual and payload.get("submit_url"):
        parts.append(f'<div class=link>submit at: {html.escape(payload["submit_url"])}</div>')

    if state == "pending":
        parts.append('<div class=actions>')
        parts.append(f'<button class=ok onclick="act({pid},\'approve\')">Approve</button>')
        parts.append(f'<button class=no onclick="reject({pid})">Reject</button>')
        parts.append('</div>')
    elif state in ("approved", "scheduled", "ready"):
        parts.append(f'<button onclick="markDone({pid})">Mark posted manually</button>')
    parts.append('</div>')
    return "".join(parts)


SCRIPT = """
<script>
async function act(id, what){
  const r = await fetch('/api/'+what+'?id='+id, {method:'POST'});
  const j = await r.json();
  if(j.ok){ location.reload(); } else { alert(j.why || 'failed'); }
}
async function reject(id){
  const why = prompt('Why reject? (the content is re-queued so you can fix it)');
  if(why === null) return;
  const r = await fetch('/api/reject?id='+id+'&reason='+encodeURIComponent(why),
                        {method:'POST'});
  const j = await r.json();
  if(j.ok){ location.reload(); } else { alert(j.why || 'failed'); }
}
async function markDone(id){
  const url = prompt('URL of the post you submitted by hand', '');
  if(url === null) return;
  const r = await fetch('/api/done?id='+id+'&url='+encodeURIComponent(url), {method:'POST'});
  if((await r.json()).ok){ location.reload(); }
}
</script>"""


def make_handler(cfg: Config, store: Store):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # silence access log
            pass

        def _send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8") -> None:
            b = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            if u.path == "/api/health":
                self._send(200, json.dumps({"ok": True}), "application/json")
                return
            with _LOCK:
                rows = store.list_posts(state=State.PENDING, limit=100)
                rows += store.list_posts(state=State.SCHEDULED, limit=100)
                rows += store.list_posts(state=State.APPROVED, limit=100)
                rows += store.list_posts(state=State.BLOCKED, limit=50)
                rows += store.list_posts(state=State.FAILED, limit=50)
            rows.sort(key=lambda r: (r["state"] == "pending", r["publish_at"] or r["created_at"]))
            pend = sum(1 for r in rows if r["state"] == "pending")
            blk = sum(1 for r in rows if r["state"] == "blocked")
            sub = f"{pend} awaiting your approval &middot; {len(rows)} total &middot; {blk} blocked"
            body = ("".join(_card(r, store) for r in rows)
                    if rows else
                    '<div class=empty>Nothing queued.<br><br>Run '
                    '<code>python -m playnexus plan --days 7</code> then '
                    '<code>python -m playnexus compile</code>.</div>')
            self._send(200, PAGE.format(style=STYLE, sub=sub, body=body).replace(
                "</body>", SCRIPT + "</body>"))

        def do_POST(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            q = parse_qs(u.query)
            pid = int((q.get("id") or ["0"])[0])
            with _LOCK:
                if u.path == "/api/approve":
                    res = pipeline.approve(store, pid)
                elif u.path == "/api/reject":
                    res = pipeline.reject(store, pid, (q.get("reason") or [""])[0])
                elif u.path == "/api/done":
                    res = pipeline.mark_published_manually(store, pid, (q.get("url") or [""])[0])
                else:
                    self._send(404, json.dumps({"ok": False, "why": "no route"}),
                               "application/json")
                    return
                store.con.commit()
            self._send(200, json.dumps(res), "application/json")

    return Handler


def serve(cfg: Config, store: Store, host: str = "127.0.0.1", port: int = 8777,
          open_browser: bool = True) -> None:
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: binding to {host} exposes an unauthenticated write endpoint. "
              f"Only do this on a network you trust.")
    srv = ThreadingHTTPServer((host, port), make_handler(cfg, store))
    url = f"http://{host}:{port}/"
    print(f"Review UI on {url}  (ctrl-c to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()
