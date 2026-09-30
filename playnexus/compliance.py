"""The compliance gate.

Every rendered post passes through `check()` before it can be scheduled. This is not
advisory. A non-empty violation list means the post goes to `State.BLOCKED` and is
never published by the machine, no matter what the channel's mode is.

What it enforces:
  * platform length/tag limits
  * per-channel banned and required substrings
  * the business-wide forbidden-word list
  * community value ratio (a pitch must be mostly substance)
  * no-ad-tone detection for anti-marketing communities like Hacker News
  * link placement (inline vs. profile-only)
  * global anti-spam invariants: no vote/DM/mention automation, no duplicate copy

The last group is the important one. See RESEARCH.md, "What the pipeline will
deliberately NOT do".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .config import Business, find_urls
from .models import ChannelRules, Rendered


@dataclass
class Violation:
    code: str
    message: str
    fatal: bool = True

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass
class Report:
    violations: list[Violation] = field(default_factory=list)

    @property
    def fatal(self) -> list[Violation]:
        return [v for v in self.violations if v.fatal]

    @property
    def ok(self) -> bool:
        return not self.fatal

    def add(self, code: str, message: str, fatal: bool = True) -> None:
        self.violations.append(Violation(code, message, fatal))

    def extend(self, other: "Report") -> None:
        self.violations.extend(other.violations)


# --------------------------------------------------------------------------
# Global anti-spam invariants. These apply to EVERY channel, always.
# --------------------------------------------------------------------------

BANNED_BEHAVIOURS = [
    (r"\bautomatically\s+(upvote|vote)\b", "automated voting is never permitted"),
    (r"\bupvote\s+(this|my)\s+(post|comment)\b", "upvote-begging is not advertising"),
    (r"\b(join|add)\s+(my|our)\s+server\b", "server-invite spamming"),
    (r"\b(dm|pm)\s+me\b", "DM solicitation"),
    (r"\bsend\s+me\s+a\s+(message|pm|dm)\b", "DM solicitation"),
    (r"\b(buy|purchase|order)\s+now\b", "hard-sell language in a community channel"),
    (r"\blimited\s+time\s+offer\b", "pressure/urgency language"),
    (r"\bact\s+now\b", "pressure/urgency language"),
    (r"\b100%\s+guarantee[ds]?\b", "unsubstantiated claim"),
    # Superlatives only count as ad claims when they are attached to the seller or
    # to money. "the cheapest way to find out whether an idea works" is ordinary
    # technical English and must not be blocked.
    (r"\b(we|i|our|my)\b[^.!?]{0,40}\b(cheapest|lowest[- ]priced|best[- ]priced)\b",
     "unsubstantiated superlative about the seller"),
    (r"\b(cheapest|lowest[- ]priced|best[- ]priced)\s+(rates?|prices?|quotes?|pricing)\b",
     "pricing superlative"),
    (r"\bbest\s+in\s+the\s+world\b", "unsubstantiated superlative"),
    (r"\bno\.?\s?1\s+(in|on|for|among)\b", "unsubstantiated superlative"),
    (r"\bcheck\s+out\s+my\b", "link-dropping opener"),
    (r"\bpromo\s+code\b", "coupon-dropping"),
    (r"\b(also|and)\s+my\s+site\b", "site-list spamming"),
    (r"\bvisit\s+my\s+profile\b", "profile-begging"),
    (r"@[A-Za-z0-9_]{2,20}\s+[A-Za-z0-9_]{2,20}\b", "mass mention pattern"),
]

# Words that make a post read like an ad. Fatal only on `no_ad_tone` channels.
AD_TONE = [
    (r"\bamazing\b", "hype adjective"),
    (r"\bstunning\b", "hype adjective"),
    (r"\brevolutionary\b", "hype adjective"),
    (r"\bgame[- ]?changer\b", "hype adjective"),
    (r"\bworld[- ]class\b", "unsubstantiated superlative"),
    (r"\bcutting[- ]edge\b", "unsubstantiated superlative"),
    (r"\bseamless(ly)?\b", "marketing filler"),
    (r"\bwe'?d love to help you\b", "sales voice"),
    (r"\bcontact us today\b", "sales voice"),
    (r"\bget started\b", "sales voice"),
    (r"\bdon'?t miss out\b", "pressure language"),
    (r"\bexcited to (announce|share)\b", "hype opener"),
    (r"\bhumble\b", "cliche opener"),
    (r"\blegacy\b", "marketing filler"),
    (r"\baffordable\b", "sales voice"),
    (r"\btrusted by\b", "unsubstantiated social proof"),
    (r"\bhigh[- ]quality\b", "unsubstantiated claim"),
    (r"\bprofessional\b", "unsubstantiated claim"),
    (r"\bexpert\b", "unsubstantiated claim"),
    (r"\blooking for a (developer|dev|freelancer)\b", "recruiting language"),
    (r"\bhiring\b", "recruiting language"),
    (r"\byour (business|company)\b", "sales voice"),
]


def _compile(patterns: Iterable[Any]) -> list[tuple[re.Pattern[str], str]]:
    """Compile (pattern, explanation) pairs, surfacing bad config loudly."""
    out: list[tuple[re.Pattern[str], str]] = []
    for entry in patterns:
        if isinstance(entry, tuple):
            pattern, why = entry
        else:
            pattern, why = entry, ""
        try:
            out.append((re.compile(pattern, re.IGNORECASE), why))
        except re.error as e:
            raise ValueError(f"bad compliance regex {pattern!r}: {e}") from e
    return out


_GLOBAL_BANNED = _compile(BANNED_BEHAVIOURS)
_AD_TONE = _compile(AD_TONE)


def value_ratio(text: str) -> float:
    """Fraction of the post's non-link words that are substance rather than pitch.

    Approximated as: words that are NOT inside a URL, NOT in the CTA tail, and NOT
    pure stopword/marketing filler. Deliberately crude and conservative — if this
    under-counts substance, the gate is stricter than a human mod, which is the
    direction you want to err in.
    """
    cleaned = re.sub(r"https?://\S+", " ", text or "")
    words = [w for w in re.findall(r"[a-z']+", cleaned.lower()) if len(w) > 2]
    if not words:
        return 0.0
    pitchy = {"available", "services", "service", "contact", "pricing", "packages",
              "hire", "booked", "book", "starting", "starts", "quote", "dm", "reach",
              "reachout", "custom", "solutions", "offer", "offers", "offering"}
    n_pitchy = sum(1 for w in words if w in pitchy)
    return max(0.0, (len(words) - n_pitchy) / len(words))


def check(rendered: Rendered, rules: ChannelRules, business: Business,
          channel_mode: str, *, seen_bodies: set[str] | None = None) -> Report:
    """Run every applicable rule. Returns a Report; `report.ok` means publishable."""
    rep = Report()
    text = f"{rendered.title}\n\n{rendered.body}"

    # --- length limits -------------------------------------------------
    if len(rendered.title) > rules.max_title:
        rep.add("title_too_long",
                f"title {len(rendered.title)} > {rules.max_title} chars")
    if len(rendered.body) > rules.max_body:
        rep.add("body_too_long",
                f"body {len(rendered.body)} > {rules.max_body} chars")
    if len(rendered.body) < rules.min_body:
        rep.add("body_too_short",
                f"body {len(rendered.body)} < {rules.min_body} chars (channel wants substance)")
    if rules.max_tags and len(rendered.tags) > rules.max_tags:
        rep.add("too_many_tags",
                f"{len(rendered.tags)} tags > {rules.max_tags} allowed")

    # --- link policy ---------------------------------------------------
    urls = find_urls(text)
    if not rules.link_allowed and urls:
        rep.add("link_not_allowed",
                f"channel forbids links, found {len(urls)}")
    if rules.link_required and not rendered.link and not urls:
        rep.add("link_required", "channel requires a link")
    if rules.link_in_profile_only and urls:
        rep.add("link_in_post",
                "this channel requires the link in the profile/bio, not the post body")

    # --- required / banned substrings ----------------------------------
    for pat in rules.required:
        if not re.search(pat, text, re.IGNORECASE):
            rep.add("missing_required", f"required pattern not found: {pat!r}")
    for pat in rules.banned:
        try:
            hit = re.search(pat, text, re.IGNORECASE)
        except re.error:
            rep.add("bad_config", f"channel rules contain invalid regex {pat!r}")
            continue
        if hit:
            rep.add("banned_phrase", f"matched banned pattern {pat!r}: {hit.group(0)!r}")

    # --- business-wide forbidden words ---------------------------------
    for w in business.forbidden:
        if w and re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE):
            rep.add("forbidden_word", f"{w!r} is on the business forbidden list")

    # --- global anti-spam invariants -----------------------------------
    for rx, why in _GLOBAL_BANNED:
        m = rx.search(text)
        if m:
            rep.add("spam_behaviour", f"{m.group(0)!r} — {why}")

    # --- anti-ad-tone for picky communities ----------------------------
    if rules.no_ad_tone:
        for rx, why in _AD_TONE:
            m = rx.search(text)
            if m:
                rep.add("ad_tone",
                        f"{m.group(0)!r} reads as marketing; this channel is "
                        f"anti-ad ({why})")

    # --- community value ratio -----------------------------------------
    if rules.min_value_ratio > 0:
        r = value_ratio(text)
        if r < rules.min_value_ratio:
            rep.add("low_value_ratio",
                    f"substance ratio {r:.2f} < required {rules.min_value_ratio:.2f} "
                    f"(too much pitch, not enough value)")

    # --- duplicate copy across communities ------------------------------
    # Only applies between third-party communities. Cross-posting the same post to
    # your own Bluesky / Dev.to / Discord is normal distribution, not spam, and
    # punishing it would just mean paying you for nothing.
    if seen_bodies and rules.community:
        key = re.sub(r"\s+", " ", text.strip().lower())[:400]
        if key in seen_bodies:
            rep.add("duplicate_copy",
                    "identical copy already queued for another community; community "
                    "rules require adapted, not duplicated, posts")

    # --- sanity: an approve-gated channel must not be machine-posted ----
    if channel_mode == "auto" and rules.min_value_ratio > 0.5:
        rep.add("unsafe_mode",
                "channel demands high value ratio but is in 'auto' mode; a human must "
                "review this one", fatal=True)

    return rep


def format_report(rep: Report) -> str:
    if rep.ok and not rep.violations:
        return "PASS - no violations"
    lines = []
    for v in rep.violations:
        lines.append(f"  [{'BLOCK' if v.fatal else 'warn '}] {v}")
    return "\n".join(lines)
