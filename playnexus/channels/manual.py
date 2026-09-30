"""Directory / launch-site form filler.

Product Hunt, BetaList, Fazier, DevHunt, Uneed, top.gg, Disboard, itch.io, Fiverr —
all free tier, all essentially HTML forms, none with a write API that a solo dev
should be automating against their ToS.

What this channel does that is actually worth automating: it produces the *complete,
correct, deduplicated* set of fields for each submission, and it tracks which
directories you have already applied to so you don't apply twice. That bookkeeping is
the part humans are bad at.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from .base import Channel, ChannelError, register
from ..render import Rendered

#: slug -> (name, url, cost, notes)
DIRECTORIES = {
    "producthunt": ("Product Hunt", "https://www.producthunt.com/posts/new", "free (makers)",
                    "Official GraphQL API exists, but free-tier launches still benefit "
                    "from a human making the first comment and hunter-timing it."),
    "betalist": ("BetaList", "https://www.betalist.com/submit", "free",
                 "Wants a 300-char description and 1 screenshot. Reject rate is high."),
    "fazier": ("Fazier", "https://www.fazier.com/submit", "free",
               "Good reach for dev tools. Wants 2-4 tags and a working link."),
    "devhunt": ("DevHunt", "https://devhunt.com/submit", "free",
                "Notable for tools/utilities specifically."),
    "uneed": ("Uneed", "https://uneed.best/submit", "free",
              "High volume, low quality audience. Submit once, never again."),
    "topgg": ("top.gg", "https://top.gg/bots", "free listing",
              "THE Discord bot directory. Non-negotiable if you build bots. Has a real "
              "API for stats + application commands; the listing itself is a form."),
    "disboard": ("Disboard", "https://disboard.org/en/servers/new", "free",
                 "Largest Discord server directory. Needs a real member count and icon."),
    "discordme": ("discord.me", "https://discord.me/new", "free",
                  "Secondary directory. Low effort, low return."),
    "itchio": ("itch.io", "https://itch.io/profile/new", "free",
               "Essential for the games side. No public write API."),
    "fiverr": ("Fiverr", "https://www.fiverr.com/users/createlevelone", "free listing",
               "3 free pitches/month. Best direct-revenue channel for 'build anything'."),
    "freelancer": ("Freelancer", "https://www.freelancer.com/", "free listing",
                   "Bid-based. Free bids are heavily competitive; use for volume only."),
    "indiehackers": ("Indie Hackers", "https://www.indiehackers.com/products/new", "free",
                     "Good for the story angle, not the sales angle."),
}


@register
class ManualChannel(Channel):
    name = "manual"
    supports_auto = False

    def verify(self) -> tuple[bool, str]:
        return True, "form-filler; nothing to configure"

    def endpoint(self) -> str:
        return ""

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        e = dict(rendered.extra or {})
        for slug, (name, url, cost, notes) in DIRECTORIES.items():
            e.setdefault("directories", []).append({
                "slug": slug, "name": name, "url": url,
                "cost": cost, "notes": notes,
            })
        return e

    def publish(self, rendered: Rendered) -> dict[str, str]:
        raise ChannelError("manual: nothing to publish. Use `pnx show <id> --manual`.")

    # -- the bookkeeping that actually matters ---------------------------

    def ledger_path(self) -> Path:
        return Path(self.cfg.config_dir).parent / "data" / "directories.json"

    def load_ledger(self) -> dict[str, Any]:
        p = self.ledger_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def record_submission(self, directory: str, *, url: str = "",
                          note: str = "") -> dict[str, Any]:
        led = self.load_ledger()
        led.setdefault(directory, []).append({
            "at": _dt.datetime.now(_dt.UTC).isoformat(),
            "url": url,
            "note": note,
        })
        self.ledger_path().parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path().write_text(
            json.dumps(led, indent=2, sort_keys=True), encoding="utf-8"
        )
        return led

    def pending(self) -> list[str]:
        led = self.load_ledger()
        return sorted(set(DIRECTORIES) - set(led))

    def submitted(self) -> list[str]:
        return sorted(self.load_ledger())
