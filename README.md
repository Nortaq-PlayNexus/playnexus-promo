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

# 3. Inspect the queue (approval-gated items are listed separately)
python -m playnexus queue
python -m playnexus show 12

# 4. Publish only what is due and only in `auto` mode
python -m playnexus run

# 5. Approve community posts one at a time (optional web UI instead)
python -m playnexus approve 12
python -m playnexus reject 13 --reason "too salesy for r/webdev"
python -m playnexus review          # http://127.0.0.1:8777
```

Windows Task Scheduler, every 15 min:

```powershell
python -m playnexus run
```

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
  models.py       Post, Content, ChannelRules
  content.py      service catalog -> content items
  render.py       content item -> per-channel payload
  compliance.py   the gate
  ratelimit.py    sliding window + token bucket
  scheduler.py    active hours, quiet days, daily caps, min gap
  http.py         urllib client: retry, backoff, header rate-limit parsing
  pipeline.py     plan / compile / run orchestration
  metrics.py      UTM links + result reporting
  channels/       one module per platform
config/           business, channels, hooks, rules
data/             SQLite db (gitignored)
```
