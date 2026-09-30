# PlayNexus Promo Pipeline

Automated promotion pipeline for **PlayNexus** — dev services (apps, Discord bots,
EXEs, tools, games).

**Zero pip dependencies.** Python 3.11+ stdlib only.

Read [`RESEARCH.md`](RESEARCH.md) first for *why* these channels and not others.

---

## Design

```
 business.json  ──▶ content engine ──▶ per-channel render ──▶ compliance gate
                                                                  │
                                            (violations?) ────────┴──────▶ refuse
                                                   │
                                                   ▼
                                              scheduler ──▶ SQLite queue
                                                                  │
                                            mode=auto  ───────────┤──▶ publisher ──▶ log
                                            mode=approve ─────────┘──▶ approval queue
                                                                                │
                                                                    `pnx approve <id>`
```

Four non-negotiable properties:

1. **Compliance gate runs before the scheduler, always.** A channel that fails its own
   rules never reaches the queue. See `playnexus/compliance.py`.
2. **Fingerprint dedupe.** `(service, channel, hook)` is unique. The pipeline cannot
   post the same pitch to the same channel twice, ever.
3. **Sliding-window rate limits persisted in SQLite**, not in RAM, so a restart cannot
   blow a quota. Reddit's `X-Ratelimit-*` response headers are honoured as ground truth.
4. **Two modes.** `auto` (owned channels) and `approve` (community channels).
   The community channels are *never* posted by the machine.

---

## Install

```powershell
cd C:\Users\natha\projects\playnexus-promo
python -m playnexus init        # writes config/ + data/ + secrets skeleton
```

Nothing to `pip install`.

---

## Daily use

```powershell
# 1. See what would go out, and prove every channel is configured
python -m playnexus doctor

# 2. Generate a week of content from your service catalog
python -m playnexus plan --days 7
python -m playnexus compile

# 3. Inspect the queue (approval-gated items are listed separately)
python -m playnexus queue
python -m playnexus queue --blocked      # config/hook misconfigurations
python -m playnexus show 12 --manual     # + live subreddit rules for Reddit

# 4. Publish only what is due, and only what is authorised
python -m playnexus run
python -m playnexus run --dry-run

# 5. Approve community posts, one at a time (or use the web UI)
python -m playnexus approve 12
python -m playnexus reject 13 --reason "too salesy for r/webdev"
python -m playnexus review               # http://127.0.0.1:8777
```

Other commands:

```powershell
python -m playnexus ratelimit            # per-channel quota + next legal slot
python -m playnexus stats                # what's published, blocked, failed
python -m playnexus retry                # recover skipped/failed posts
python -m playnexus done 12 --url "..."  # record a post you submitted by hand
python -m playnexus secret reddit client_id=xxx password=yyy
python -m playnexus hn                   # your HN history + score, read-only
python -m playnexus gh topics            # sync GitHub repo topics
python -m playnexus gh readme            # generate the profile README
```

Unattended, every 15 minutes:

```powershell
powershell -ExecutionPolicy Bypass -File .\schedule.ps1 -Install
```

`run` is safe to schedule: it only publishes `auto`-mode channels, only inside their
configured hours, and only within their daily cap. Community channels are never
touched without your approval.

---

## Two things the tests caught, worth knowing

**Approved ≠ auto.** An `approve`-mode channel still publishes itself once a human
approves the post. Approval is *authorisation*, not a delivery mechanism — otherwise
Reddit would require you to open a browser and copy-paste every time you approved
something, which is how approval queues get abandoned.

**The UTM link is longer than the plain one.** If you truncate a post to the platform
limit and then append a tracked URL, you blow the limit. The pipeline resolves the
tracked link *before* rendering and reserves its length (`render.fit_with_link`).
`tests/test_publish.py` asserts the Mastodon payload stays within 500 chars.

---

## Configuration

- `config/business.json` — your brand, services, links, tone. **Edit this first.**
- `config/channels.json` — per-channel mode, rate limit, active hours, rules.
  A channel is inert until you fill in its credentials in `config/secrets.json`.
- `config/hooks.json` — the angle each post takes (a "hook" is one idea, reused
  across channels so you are not writing from scratch 20 times a week).

`config/secrets.json` is gitignored. Every credential the pipeline can use is
declared there; nothing is hardcoded.

### Adding a channel

1. Add a block to `config/channels.json` with `"enabled": false`.
2. Add its `rules` — the gate is mandatory, not optional.
3. Create `playnexus/channels/<name>.py` subclassing `Channel`.
4. Register it in `playnexus/channels/__init__.py`.

The gate is intentionally unfakeable: `Channel.rules` has no default, so a channel
without a rules profile fails to instantiate.

---

## What it will not do

No automated voting, no sockpuppets, no bulk DMs, no scraping, no CAPTCHA bypass,
no duplicate copy-paste across communities. `compliance.py` enforces this and
`pnx doctor` reports any channel whose config would violate it.

## Layout

```
playnexus/
  cli.py          argparse entry point
  config.py       load + validate business/channels/hooks/secrets
  db.py           SQLite: queue, events, sliding-window counters
  models.py       Post, Content, ChannelRules, Channel, Mode, State
  content.py      service catalog + hooks -> dated content items
  render.py       content item -> per-channel payload
  compliance.py   the gate
  ratelimit.py    daily cap + min gap, DB-backed
  scheduler.py    active hours, weekdays, min gap, daily cap
  http.py         urllib client: retry, backoff, header rate-limit parsing
  pipeline.py     compile / run / approve / reject / retry
  metrics.py      UTM links
  stats.py        performance report
  review.py       local approval web UI (stdlib http.server)
  scaffold.py     config templates written by `init`
  channels/       one module per platform + _registry.py
config/           business, channels, hooks, secrets (gitignored)
data/             SQLite db + run.log (gitignored)
tests/            test_publish.py — end-to-end against a mock server
schedule.ps1      Task Scheduler install/status/uninstall
```

## Tests

```powershell
python -m tests.test_publish
```

Spins up a mock Mastodon, compiles content, publishes through the real adapter, and
asserts: bearer auth, `Idempotency-Key`, length cap respected, rate limit counted,
server `X-Ratelimit-*` parsed, UTM present in the wire payload, spam copy blocked,
HN ad-tone blocked, a channel without `rules` refused at load, credentials absent
from the database, and an unapproved community post never published.
