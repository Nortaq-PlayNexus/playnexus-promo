"""Render a Content item into a channel-specific payload.

The same hook becomes a 300-char Bluesky post, a Markdown Dev.to article body, a
3000-char Telegram announcement and a 80-char Hacker News title. Adapting is the
point: communities that receive copy-pasted marketing copy moderate against it, and
the compliance gate's `duplicate_copy` check enforces that the adaptation is real.
"""

from __future__ import annotations

import re

from .config import Business
from .models import Content, Rendered, Service

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]+",
    flags=re.UNICODE,
)

#: Bluesky counts a post as 300 graphemes.
BLUESKY_LIMIT = 300


def _clean(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", (text or "").strip())


def _truncate(text: str, limit: int, marker: str = "…") -> str:
    """Truncate on a word boundary, never mid-word, never mid-URL."""
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - len(marker))]
    # don't leave a half URL
    if "http" in cut:
        last_ok = cut.rfind(" ")
        if last_ok > limit * 0.5:
            cut = cut[:last_ok]
    else:
        sp = cut.rfind(" ")
        if sp > limit * 0.6:
            cut = cut[:sp]
    return cut.rstrip(" ,.;:-") + marker


def _first_sentences(text: str, n: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+", _clean(text))
    return " ".join(parts[:n]).strip()


def service_for(business: Business, slug: str) -> Service:
    return business.service(slug)


def link_for(business: Business, svc: Service, content: Content,
             override: str = "") -> str:
    """The link this post should carry.

    `override` exists so the pipeline can hand in an already-UTM-tagged URL *before*
    rendering. Doing the substitution after render means the tracked URL (always
    longer than the plain one) lands past the length truncation and blows the cap.
    """
    if override:
        return override
    if content.link:
        return content.link
    if svc.page and business.url:
        return business.url + svc.page
    return business.url


def cta_for(business: Business, svc: Service, content: Content) -> str:
    return content.cta or svc.cta or ""


# ---------------------------------------------------------------------------
# Channel renderers. Each returns a Rendered. Length discipline is applied here
# as well as in the compliance gate, so a well-formed render never trips a limit.
# ---------------------------------------------------------------------------

def render_bluesky(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    hook = f"{content.title}\n\n{_first_sentences(content.body, 2)}"
    if content.proof:
        hook += f"\n\n{content.proof}"
    cta = cta_for(business, svc, content)
    if cta and svc.est_value:
        cta = f"{cta} ({svc.est_value})"
    if cta:
        hook += f"\n\n{cta}"
    tags = business.hashtags[:2]  # 2 is plenty; more reads as spam
    if tags:
        hook += "\n\n" + " ".join(f"#{t.lstrip('#')}" for t in tags)
    # Reserve room for the link so it cannot be truncated off, then append it.
    body = fit_with_link(hook, link, BLUESKY_LIMIT)
    title = _truncate(content.title, 80)
    return Rendered("bluesky", title, body, link=link, tags=tags,
                    extra={"text": body, "facets_note": "links auto-linked by client"})


def render_mastodon(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    parts = [_clean(content.body)]
    if content.proof:
        parts.append(f"__{content.proof}__")
    if svc.est_value:
        parts.append(f"{svc.est_value}.")
    cta = cta_for(business, svc, content)
    if cta:
        parts.append(cta)
    parts.append(f"\n{link}")
    if business.hashtags:
        parts.append(" ".join(f"#{t.lstrip('#')}" for t in business.hashtags[:3]))
    body = _truncate("\n\n".join(parts), 480)
    return Rendered("mastodon", _truncate(content.title, 80), body, link=link,
                    tags=business.hashtags[:3], extra={"text": body, "visibility": "public"})


def render_telegram(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    svc_line = f"**{svc.name}** — {svc.tagline}"
    if svc.est_value:
        svc_line += f" · {svc.est_value}"
    parts = [f"*{content.title}*", "", _clean(content.body), ""]
    if content.proof:
        parts += [f"✅ {content.proof}", ""]
    if svc.audience:
        parts += [f"👤 For: {svc.audience}", ""]
    parts += [svc_line, ""]
    cta = cta_for(business, svc, content)
    if cta:
        parts += [cta, ""]
    parts += [link]
    body = _truncate("\n".join(parts), 4000)
    return Rendered("telegram", _truncate(content.title, 100), body, link=link,
                    extra={"text": body, "parse_mode": "Markdown",
                           "disable_web_page_preview": False})


def render_discord(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    """Discord webhook embed. Richest owned surface — use all 10 fields well."""
    fields: list[dict[str, str]] = []
    for kw in svc.keywords[:3]:
        fields.append({"name": kw.title(), "value": "✓", "inline": True})
    if content.proof:
        fields.insert(0, {"name": "Track record", "value": content.proof[:256], "inline": False})
    if svc.audience:
        fields.append({"name": "Who it's for", "value": svc.audience[:256], "inline": False})
    if svc.est_value:
        fields.append({"name": "Budget", "value": svc.est_value[:256], "inline": True})
    cta = cta_for(business, svc, content)
    if cta:
        fields.append({"name": "Next step", "value": cta[:256], "inline": False})

    description = _truncate(_clean(content.body), 4000)
    payload = {
        "embeds": [{
            "title": _truncate(content.title, 256),
            "description": description,
            "url": link or None,
            "color": 0x6D5DFB,
            "fields": fields[:10],
            "footer": {"text": f"{business.name} · {business.tagline}"[:2048]},
        }],
        "allowed_mentions": {"parse": []},   # hard rule: never ping anyone
    }
    if not payload["embeds"][0]["url"]:
        payload["embeds"][0].pop("url")
    payload["username"] = business.name
    return Rendered("discord", content.title, description, link=link,
                    extra=payload)


def render_devto(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    body = _clean(content.body)
    extras = []
    if content.proof:
        extras.append(f"### Where this has been done\n\n{content.proof}")
    if svc.detail:
        extras.append(f"### What {svc.name} covers\n\n{svc.detail}")
    if content.cta or svc.cta:
        extras.append(
            f"### Working together\n\n{content.cta or svc.cta}"
            + (f" {svc.est_value}." if svc.est_value else "")
        )
    extras.append(f"---\n\n{service_note(business)}")
    full = "\n\n".join([body] + extras)
    tags = [t.lower().replace(" ", "") for t in
            (content.tags or svc.keywords)][:4]
    return Rendered("devto", _truncate(content.title, 128), full, link=link, tags=tags,
                    extra={"title": _truncate(content.title, 128),
                           "body_markdown": full,
                           "published": True,
                           "tags": tags,
                           "description": _truncate(svc.tagline, 140),
                           "canonical_url": link or None})


def service_note(business: Business) -> str:
    return f"*{business.name}* — {business.tagline} · {business.url}"


def fit_with_link(text: str, link: str, limit: int, marker: str = "…") -> str:
    """Fit `text` + `link` into `limit` characters, with the link guaranteed to survive.

    Order matters here and getting it wrong is a real bug. If you truncate the
    assembled post first, a UTM-tagged URL (always longer than the plain one) gets cut
    off the end; the adapter then notices the link is missing, re-appends it, and the
    final post is over the platform limit. So the link's length is reserved up front
    and only the prose gets trimmed.
    """
    text = (text or "").strip()
    link = (link or "").strip()
    if not link:
        return text[:limit]
    if link in text:
        return text[:limit]

    room = limit - len(link) - 2  # the "\n\n" separator
    if room <= 0:
        return link[:limit]
    if len(text) <= room:
        return f"{text}\n\n{link}"
    cut = text[:room]
    sp = cut.rfind(" ")
    if sp > room * 0.6:
        cut = cut[:sp]
    return f"{cut.rstrip(' ,.;:-')}{marker}\n\n{link}"


def render_hashnode(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    full = "\n\n".join([
        _clean(content.body),
        "",
        "---",
        "",
        service_note(business),
    ])
    return Rendered("hashnode", _truncate(content.title, 100), full, link=link,
                    tags=(content.tags or svc.keywords)[:4],
                    extra={"title": _truncate(content.title, 100),
                           "content_markdown": full,
                           "tags": (content.tags or svc.keywords)[:4],
                           "canonical_url": link or None})


def render_reddit(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    """Reddit: title is everything. Body must lead with substance.

    The CTA is placed at the very end and the link is omitted from the body by
    default, because the vast majority of dev subs treat an inline link in a
    "look at my thing" post as reason to remove it. Flip `link_in_body` in
    channels.json if a given sub is known to allow it.
    """
    title = _truncate(content.title, 300)
    body = _clean(content.body)
    if content.proof:
        body += f"\n\n{content.proof}"
    body += f"\n\n---\n{service_note(business)}"
    return Rendered("reddit", title, body, link=link, tags=[],
                    extra={"title": title, "text": body,
                           "subreddit": content.community or None})


def render_hackernews(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    """HN: no marketing language, no sales pitch, technical detail only.

    `body` is the *first comment* the author posts under their own submission, which
    is where the substance is expected to live. Per Show HN guidance the post itself
    is just a title + URL.
    """
    title = _truncate(content.title, 80)
    first = _clean(content.body)
    if content.proof:
        first += f"\n\n{content.proof}"
    first += (
        "\n\nHappy to answer questions about the implementation. "
        "This is a commercial service, so to be transparent about that up front."
    )
    return Rendered("hackernews", title, first, link=link, tags=[],
                    extra={"hn_title": title, "url": link, "first_comment": first,
                           "note": "Submit manually via news.ycombinator.com; "
                                   "the public API is read-only."})


def render_lobsters(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    first = _clean(content.body)
    if content.proof:
        first += f"\n\n{content.proof}"
    return Rendered("lobsters", _truncate(content.title, 100), first, link=link,
                    tags=(content.tags or svc.keywords)[:5],
                    extra={"title": _truncate(content.title, 100), "url": link,
                           "description": first, "tags": ["playnexus"]})


def render_github(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    body = _clean(content.body)
    if content.proof:
        body += f"\n\n> {content.proof}"
    body += f"\n\n{service_note(business)}"
    return Rendered("github", _truncate(content.title, 120), body, link=link,
                    extra={"title": _truncate(content.title, 120), "body": body})


def render_manual(content: Content, business: Business, svc: Service, link: str) -> Rendered:
    """Directory/listing form filler. Produces every field a form usually wants."""
    return Rendered(
        "manual",
        _truncate(content.title, 80),
        _truncate(_clean(content.body), 300),
        link=link,
        tags=(content.tags or svc.keywords)[:8],
        extra={
            "name": svc.name,
            "tagline": _truncate(svc.tagline, 120),
            "description": _truncate(content.body, 1000),
            "long_description": _truncate(content.body, 4000),
            "categories": svc.keywords[:5],
            "url": link,
            "contact": business.contact,
            "proof": content.proof,
            "price": svc.est_value,
            "proof_note": "Most directories want social proof. Have 1-2 real numbers "
                          "ready before submitting — 'high quality work' gets rejected.",
        },
    )


RENDERERS = {
    "bluesky": render_bluesky,
    "mastodon": render_mastodon,
    "telegram": render_telegram,
    "discord": render_discord,
    "devto": render_devto,
    "hashnode": render_hashnode,
    "reddit": render_reddit,
    "hackernews": render_hackernews,
    "lobsters": render_lobsters,
    "github": render_github,
    "manual": render_manual,
}


def render_for(channel_name: str, content: Content, business: Business,
               link: str = "") -> Rendered | None:
    fn = RENDERERS.get(channel_name)
    if fn is None:
        return None
    svc = service_for(business, content.service_slug)
    return fn(content, business, svc, link or link_for(business, svc, content))
