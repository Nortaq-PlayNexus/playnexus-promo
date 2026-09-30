"""Config templates written by `pnx init`.

The channels.json here is the real deliverable of the research phase: every channel's
actual documented limits, banned patterns and value ratio, encoded so the compliance
gate can enforce them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BUSINESS = {
    "name": "PlayNexus",
    "tagline": "I build the thing you keep putting off.",
    "url": "https://playnexus.dev",
    "contact": "hello@playnexus.dev",
    "discord_invite": "",
    "timezone": "America/New_York",
    "tone": "direct, technical, specific numbers over adjectives. never hype.",
    "rules_note": (
        "A service shop survives on repeat clients and referrals, not on reach. "
        "Every post should be something you would post if nobody paid you."
    ),
    "utm_source": "playnexus",
    "utm_medium": "promo",
    "languages": ["en"],
    "forbidden_words": [
        "amazing", "stunning", "revolutionary", "game-changer", "world-class",
        "seamless", "cutting-edge", "leverage", "synergy", "passionate",
        "dedicated", "one-stop", "bespoke", "best-in-class",
    ],
    "hashtags": ["buildinpublic", "indiedev", "discordbot"],
    "services": [
        {
            "slug": "discord-bots",
            "name": "Discord bots",
            "tagline": "Bots that do the boring part of running your server.",
            "detail": (
                "Custom commands, moderation, ticketing, economy and role systems, "
                "music, onboarding, analytics dashboards. Deployed on your own host "
                "or mine, with source handed over."
            ),
            "keywords": ["discord", "bot", "moderation", "automation", "ticket"],
            "page": "/discord-bots",
            "proof": "",
            "cta": "Describe the command set you want and I'll tell you what's feasible.",
            "est_value": "from $150",
            "audience": "server owners tired of doing it by hand",
        },
        {
            "slug": "exe-tools",
            "name": "Windows EXE tools",
            "tagline": "Double-clickable tools, signed, no Python install needed.",
            "detail": (
                "Batch utilities, GUI front-ends for scripts, file and media processors, "
                "internal tools for teams who don't write code. PyInstaller or native, "
                "with a proper icon and a changelog."
            ),
            "keywords": ["windows", "exe", "pyinstaller", "automation", "tooling"],
            "page": "/exe-tools",
            "proof": "",
            "cta": "Send me the manual process you do by hand; I'll automate it.",
            "est_value": "from $120",
            "audience": "people who need a tool, not a tutorial",
        },
        {
            "slug": "apps-web",
            "name": "Web & desktop apps",
            "tagline": "Small apps that do one job properly.",
            "detail": (
                "Dashboards, internal CRUD, booking and scheduling, data entry, "
                "browser extensions, Electron/Tauri wrappers. Shipped with a build "
                "you can run yourself."
            ),
            "keywords": ["app", "webapp", "electron", "tauri", "dashboard"],
            "page": "/apps",
            "proof": "",
            "cta": "",
            "est_value": "quote in 24h",
            "audience": "",
        },
        {
            "slug": "games",
            "name": "Games",
            "tagline": "Small games, and the tools that make them.",
            "detail": (
                "Roblox and Unity projects, game-jam entries, prototypes that prove a "
                "mechanic works before you commit to it."
            ),
            "keywords": ["game", "roblox", "unity", "gamedev", "robloxstudio"],
            "page": "/games",
            "proof": "",
            "cta": "",
            "est_value": "",
            "audience": "",
        },
    ],
}


HOOKS = {
    "_readme": (
        "One hook = one idea, written once and rendered ~10 ways. "
        "`id` must be unique. `community` targets a specific subreddit/tag."
    ),
    "hooks": [
        {
            "id": "dc-bot-scope-creep",
            "service": "discord-bots",
            "angle": "why-your-discord-bot-needs-a-scope-document",
            "title": "Your Discord bot will need a scope document before it needs a database",
            "body": (
                "The most common way a Discord bot project dies is not a bad idea, "
                "it's an unbounded one. The bot needs a role, which needs a database, "
                "which needs a migration story, which needs someone to own it. Four "
                "weeks of scope negotiation that nobody wrote down.\n\n"
                "So before writing a line of code I write a one-page answer to four "
                "questions: which guild can run this with the permissions the bot "
                "actually requests; what happens when the bot is offline for an hour; "
                "who deletes the data and when; what the bot does that a human admin "
                "would object to. If any of those four is unanswerable, the project is "
                "not scoped yet, and the right move is to say so before taking money.\n\n"
                "The scope document is also the only reliable way to stop a project "
                "growing sideways. Every 'while you're in there' request gets checked "
                "against it, and either it fits or it becomes phase two."
            ),
            "proof": "",
            "cta": "If you're starting a Discord bot, send me the idea and I'll tell you which of those four questions you haven't answered yet.",
            "tags": ["discord", "discordbot", "webdev", "programming"],
            "community": "Discord_Bots",
        },
        {
            "id": "exe-not-a-tutorial",
            "service": "exe-tools",
            "angle": "shipping-a-tool-not-a-tutorial",
            "title": "A script you have to install Python to run is not a finished tool",
            "body": (
                "The gap between 'it works on my machine' and 'here, double-click it' "
                "is where most internal tools die.\n\n"
                "Shipping a Windows executable means: bundling the interpreter and every "
                "dependency, handling missing VC++ runtimes, failing with a readable "
                "message instead of a traceback, writing to a config file the user can "
                "actually find, and having a version number somewhere visible. None of "
                "that is the interesting part of the work and all of it is the part "
                "that decides whether anyone outside your machine can use the thing.\n\n"
                "The other half is not quietly ignoring the warnings. An unsigned EXE "
                "triggering SmartScreen looks exactly like malware, so the fix is code "
                "signing, a real icon, an About dialog with a publisher name, and "
                "shipping through a known channel so the first-run reputation check "
                "has something to work with."
            ),
            "proof": "",
            "cta": "If you have a script that only you can run, that's a solvable problem, not a lost cause.",
            "tags": ["python", "windows", "programming", "tooling"],
        },
        {
            "id": "game-prototype-first",
            "service": "games",
            "angle": "prototype-a-mechanic-before-a-game",
            "title": "Prototype the one mechanic, not the game",
            "body": (
                "The cheapest way to find out whether a game idea works is to build the "
                "single mechanic it depends on and nothing else. No menus, no art "
                "pipeline, no save system, no progression.\n\n"
                "If the loop isn't fun with a grey box and one sound effect, adding "
                "content will not save it, and you'll have spent your time finding out. "
                "If it is fun, you now know what to build, which is a completely "
                "different and much better position to be in.\n\n"
                "This works for Roblox and Unity identically: script the core verb, "
                "wire one input to one output, put a counter on screen so you can feel "
                "the feedback loop, and play it twenty times."
            ),
            "proof": "",
            "cta": "",
            "tags": ["gamedev", "gamedesign", "indiedev", "roblox"],
        },
        {
            "id": "app-one-job",
            "service": "apps-web",
            "angle": "shrink-the-scope-until-it-is-obvious",
            "title": "The best small apps do one job and refuse to do a second",
            "body": (
                "A request for 'an app to manage our inventory, invoices, staff "
                "schedule and customer emails' is four projects that will all be "
                "mediocre. Splitting it into the one that has a daily user — usually "
                "inventory — and deferring the rest produces something people open "
                "every morning instead of a thing they log into once and abandon.\n\n"
                "The practical version: pick the one screen someone needs on a Tuesday "
                "morning, build only that, and make the data model tolerant of the "
                "other three arriving later. Same database, incremental shipping, no "
                "rewrite in six months.\n\n"
                "The discipline that makes this work is writing down what the app will "
                "not do, and treating that list as binding."
            ),
            "proof": "",
            "cta": "",
            "tags": ["webdev", "programming", "softwarearchitecture", "buildinpublic"],
        },
    ],
}


def _rules(**kw: Any) -> dict[str, Any]:
    base = {
        "max_title": 300, "max_body": 4000, "min_body": 0, "max_tags": 0,
        "link_allowed": True, "link_required": False,
        "banned": [], "required": [], "min_value_ratio": 0.0,
        "no_ad_tone": False, "link_in_profile_only": False,
    }
    base.update(kw)
    return base


CHANNELS: dict[str, Any] = {
    "_readme": (
        "mode: auto   = you own the surface, safe to publish unattended\n"
        "mode: approve= community, requires a human for every single post\n"
        "rate_per_day is a ceiling the pipeline will never exceed, not a target.\n"
        "Every block MUST have a `rules` object; the pipeline refuses to start a "
        "channel without one."
    ),
    "channels": {

        # ---- Tier 1: owned ------------------------------------------------
        "discord": {
            "enabled": True, "mode": "auto", "rate_per_day": 3,
            "min_gap_minutes": 240,
            "active_hours": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
            "weekdays": [0, 1, 2, 3, 4, 5, 6], "weight": 3,
            "notes": "Your own server. Webhook only, no bot token needed.",
            "webhook_url": {"secret": True,
                            "hint": "Server Settings > Integrations > Webhooks"},
            "username_override": "",
            "rules": _rules(
                max_title=256, max_body=4096, max_tags=0,
                banned=[r"\bping\b", r"@everyone", r"@here"],
            ),
        },

        "bluesky": {
            "enabled": True, "mode": "auto", "rate_per_day": 4,
            "min_gap_minutes": 180,
            "active_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
            "weekdays": [0, 1, 2, 3, 4, 5, 6], "weight": 3,
            "notes": "Free AT Protocol API. Best permission-free reach per unit of effort.",
            "max_chars": 300,
            "identifier": {"secret": True, "hint": "your handle, e.g. you.bsky.social"},
            "app_password": {"secret": True, "hint": "Settings > App Passwords"},
            "bearer": {"secret": True, "hint": "optional JWT from com.atproto.server.createSession"},
            "service_url": {"secret": True, "hint": "https://bsky.social"},
            "repo": {"secret": True, "hint": "did:plc:... ; derived from handle if blank"},
            "rules": _rules(max_title=80, max_body=300, max_tags=2,
                            banned=[r"\b(we|i|our|my)\b[^.!?]{0,40}"
                                    r"\b(cheap(est)?|guarantee[ds]?)\b"]),
        },

        "mastodon": {
            "enabled": True, "mode": "auto", "rate_per_day": 3,
            "min_gap_minutes": 240,
            "active_hours": [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
            "weekdays": [0, 1, 2, 3, 4, 5, 6], "weight": 2,
            "notes": "Any instance. Idempotency-Key set so retries cannot double-post.",
            "max_chars": 500,
            "visibility": "public",
            "allow_sensitive": False,
            "instance": {"secret": True, "hint": "https://mastodon.social"},
            "access_token": {"secret": True, "hint": "Settings > Development > Access token"},
            "rules": _rules(max_title=80, max_body=500, max_tags=3),
        },

        "telegram": {
            "enabled": False, "mode": "auto", "rate_per_day": 2,
            "min_gap_minutes": 480,
            "active_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
            "weekdays": [0, 1, 2, 3, 4, 5, 6], "weight": 2,
            "notes": "Cheapest newsletter available. Use a bot token, never a userbot.",
            "parse_mode": "Markdown", "preview": True, "silent": True,
            "bot_token": {"secret": True, "hint": "@BotFather"},
            "chat_id": {"secret": True, "hint": "@channelname or -100..."},
            "rules": _rules(max_title=100, max_body=4096),
        },

        "devto": {
            "enabled": True, "mode": "auto", "rate_per_day": 1,
            "min_gap_minutes": 1440,
            "active_hours": [8, 9, 10, 11, 12, 13, 14, 15],
            "weekdays": [1, 2, 3, 4, 5], "weight": 2,
            "notes": "30 req/30s, 1000 articles total. Genuinely compounding SEO.",
            "endpoint": "https://dev.to/api/articles",
            "published": True,
            "organization": "",
            "api_key": {"secret": True, "hint": "dev.to > Settings > API keys"},
            "rules": _rules(max_title=128, max_body=100000, min_body=400, max_tags=4,
                            banned=[r"\bcheck out my\b", r"\bbuy\b"]),
        },

        "hashnode": {
            "enabled": False, "mode": "approve", "rate_per_day": 1,
            "min_gap_minutes": 1440,
            "active_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17],
            "weekdays": [1, 2, 3, 4, 5], "weight": 1,
            "notes": "Lower traffic than dev.to. Worth a human read before publishing.",
            "endpoint": "https://gql.hashnode.com/",
            "cover_image": "",
            "api_key": {"secret": True, "hint": "Hashnode > Settings > Developer"},
            "bearer": {"secret": True, "hint": "optional"},
            "publication_id": {"secret": True, "hint": "Settings > Publications"},
            "rules": _rules(max_title=100, max_body=50000, min_body=400, max_tags=5),
        },

        "github": {
            "enabled": True, "mode": "approve", "rate_per_day": 2,
            "min_gap_minutes": 1440,
            "active_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
            "weekdays": [0, 1, 2, 3, 4, 5, 6], "weight": 1,
            "notes": ("Topics are the useful part: they are how people search "
                      "'discord bot developer'. `pnx gh topics` / `pnx gh readme`."),
            "repo": "playnexus/portfolio",
            "topics": ["discord-bot", "discord-bot-development", "python",
                       "exe-tools", "game-development", "hired", "freelance"],
            "token": {"secret": True, "hint": "Settings > Developer settings > PAT"},
            "username": {"secret": True, "hint": "your github username"},
            "rules": _rules(max_title=120, max_body=60000),
        },

        # ---- Tier 2: community -------------------------------------------
        "reddit": {
            "enabled": True, "mode": "approve", "rate_per_day": 1,
            "min_gap_minutes": 720,
            # Most dev subreddits are US-heavy and dead overnight UTC.
            "active_hours": [13, 14, 15, 16, 17, 18, 19, 20, 21, 22],
            "weekdays": [1, 2, 3, 4, 5], "weight": 4,
            "notes": (
                "100 QPM per OAuth client (10-min average), verified. The API is not "
                "the limit - each sub's self-promo rule is. READ IT: "
                "`pnx show <id> --manual` fetches the live rules. 9:1 value ratio "
                "is common; several subs ban promotion outright."
            ),
            "user_agent": "linux:playnexus.promo:1.0.0 (by /u/REPLACE_ME)",
            "api_base": "https://oauth.reddit.com",
            "web_base": "https://www.reddit.com",
            "client_id": {"secret": True, "hint": "Reddit > Preferences > Apps > script"},
            "client_secret": {"secret": True},
            "username": {"secret": True},
            "password": {"secret": True},
            "subreddit": {"secret": True, "hint": "default target; hook.community overrides"},
            "rules": _rules(
                max_title=300, max_body=12000, min_body=400, max_tags=0,
                # A dev-sub pitch that is more pitch than substance gets removed.
                min_value_ratio=0.55,
                link_allowed=True, link_required=False,
                banned=[r"\bdiscount\b", r"\bfree quote\b",
                        r"\b(we|i|our|my)\b[^.!?]{0,40}\b(cheap(est)?|lowest[- ]priced)\b",
                        r"\bupvote\b", r"\bclick here\b", r"\bcheck (out|it) out\b",
                        r"\bsign ?up\b", r"\blimited time\b"],
                community=True,
            ),
        },

        "hackernews": {
            "enabled": True, "mode": "approve", "rate_per_day": 1,
            "min_gap_minutes": 10080,  # one per week. enforced.
            "active_hours": [8, 9, 10, 11, 12, 13],  # mid-morning PST beats Monday 9am
            "weekdays": [1, 2, 3, 4], "weight": 1,
            "notes": (
                "Public API is read-only (verified: no rate limit, no submit endpoint). "
                "Submission is a web form. Show HN guidance: drop all marketing and "
                "sales language. This is a credibility channel, not a volume channel."
            ),
            "hn_username": {"secret": True},
            "rules": _rules(
                max_title=80, max_body=5000, min_body=300,
                no_ad_tone=True,
                min_value_ratio=0.7,
                link_allowed=True, link_required=True,
                banned=[r"\b(hire|contact|call to action|sign ?up|order now|get a quote)\b",
                        r"\b(we|our) (are|is) (a )?(reliable|trusted|professional|expert)\b",
                        r"\b(affordable|cheap|cheapest) (rates|prices|pricing)\b",
                        r"\bmy clients?\b", r"\byour business\b", r"\bwe build\b"],
                community=True,
            ),
        },

        "lobsters": {
            "enabled": False, "mode": "approve", "rate_per_day": 1,
            "min_gap_minutes": 4320,
            "active_hours": [8, 9, 10, 11, 12, 13, 14, 15, 16, 17],
            "weekdays": [1, 2, 3, 4, 5], "weight": 1,
            "notes": "Invite-gated. Tolerant of a technical write-up about your own work.",
            "rules": _rules(max_title=100, max_body=5000, min_body=300,
                            no_ad_tone=True, min_value_ratio=0.65, community=True,
                            banned=[r"\b(hire|contact)\b"]),
        },

        "manual": {
            "enabled": True, "mode": "approve", "rate_per_day": 2,
            "min_gap_minutes": 1440,
            "active_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
            "weekdays": [0, 1, 2, 3, 4, 5], "weight": 1,
            "notes": ("Directory and launch-site form filler: Product Hunt, BetaList, "
                      "Fazier, DevHunt, Uneed, top.gg, Disboard, itch.io, Fiverr, "
                      "Freelancer, Indie Hackers. `pnx show <id> --manual` lists what "
                      "is still unsubmitted."),
            "rules": _rules(max_title=80, max_body=4000, max_tags=8),
        },
    },
}


def write_templates(config_dir: Path) -> list[Path]:
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, data in (("business.json", BUSINESS), ("channels.json", CHANNELS),
                       ("hooks.json", HOOKS)):
        p = config_dir / name
        if not p.exists():
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
            written.append(p)

    p = config_dir / "secrets.json"
    if not p.exists():
        p.write_text(json.dumps({ch: {} for ch in CHANNELS["channels"]}, indent=2) + "\n",
                     encoding="utf-8")
        written.append(p)

    gitignore = config_dir.parent / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "config/secrets.json\ndata/\nout/\n__pycache__/\n*.pyc\n", encoding="utf-8"
        )
        written.append(gitignore)
    return written
