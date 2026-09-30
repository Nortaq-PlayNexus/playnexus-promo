"""Attribution. Every post gets a link you can actually measure.

A post to a subreddit that doesn't route traffic to a page you own is a wasted post.
This module is how you find out which ones are wasted.
"""

from __future__ import annotations

import hashlib
import urllib.parse

from .config import Business


def utm_link(base: str, path: str, source: str, medium: str = "promo",
             campaign: str = "", content: str = "", term: str = "") -> str:
    """Append UTM parameters to a URL. Idempotent-ish: replaces existing utm_*."""
    if not base:
        return ""
    p = urllib.parse.urlsplit(base)
    q = dict(urllib.parse.parse_qsl(p.query, keep_blank_values=True))
    q.update({
        "utm_source": source,
        "utm_medium": medium,
    })
    if campaign:
        q["utm_campaign"] = campaign
    if content:
        q["utm_content"] = content
    if term:
        q["utm_term"] = term
    return urllib.parse.urlunsplit(
        (p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), p.fragment)
    )


def tracked(business: Business, path: str, channel: str, hook_id: str = "") -> str:
    """The canonical tracked link for a (service page, channel, hook) triple."""
    short = hashlib.sha1(f"{channel}:{hook_id}".encode()).hexdigest()[:6]
    return utm_link(
        business.url + path if path else business.url,
        "", source=channel or business.utm_source,
        medium=business.utm_medium,
        campaign="playnexus",
        content=short,
    )


def service_path(business: Business, service_slug: str) -> str:
    svc = business.service(service_slug)
    return svc.page or f"/{svc.slug}"


def short_hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:6]
