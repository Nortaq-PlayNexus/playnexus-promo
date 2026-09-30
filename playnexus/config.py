"""Config loading and validation.

Four files, all JSON (stdlib has no YAML):
  business.json   brand, services, links, tone
  channels.json   per-channel mode / limits / hours / rules
  hooks.json      the angles to write about
  secrets.json    credentials (gitignored)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Channel, ChannelRules, Hook, Mode, Service

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


class ConfigError(Exception):
    pass


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is None:
            raise ConfigError(f"missing required file: {path}")
        return default
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        if default is None:
            raise ConfigError(f"empty required file: {path}")
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path.name}: invalid JSON at line {e.lineno}: {e.msg}") from e


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@dataclass
class Business:
    name: str
    tagline: str
    url: str
    contact: str
    discord_invite: str
    tone: str
    forbidden: list[str]
    hashtags: list[str]
    languages: list[str]
    services: list[Service]
    timezone: str = "UTC"
    utm_source: str = "playnexus"
    utm_medium: str = "promo"
    rules_note: str = ""

    def service(self, slug: str) -> Service:
        for s in self.services:
            if s.slug == slug:
                return s
        raise ConfigError(f"unknown service slug: {slug!r}")


@dataclass
class Config:
    business: Business
    channels: dict[str, Channel]
    hooks: list[Hook]
    secrets: dict[str, Any] = field(default_factory=dict)
    config_dir: Path = CONFIG_DIR
    data_dir: Path = DATA_DIR

    def secret(self, channel: str, key: str, default: Any = None) -> Any:
        return self.secrets.get(channel, {}).get(key, default)

    def has_secrets(self, channel: str) -> bool:
        ch = self.channels.get(channel)
        if ch is None:
            return False
        return all(self.secret(channel, k) not in (None, "") for k in ch.secret_keys)

    def active_channels(self) -> list[Channel]:
        return [
            c for c in self.channels.values()
            if c.enabled and c.mode is not Mode.OFF
        ]


def load(config_dir: Path | None = None) -> Config:
    cdir = Path(config_dir) if config_dir else CONFIG_DIR

    b = _read_json(cdir / "business.json")
    biz = Business(
        name=b["name"],
        tagline=b.get("tagline", ""),
        url=b.get("url", "").rstrip("/"),
        contact=b.get("contact", ""),
        discord_invite=b.get("discord_invite", ""),
        tone=b.get("tone", "direct, technical, no hype"),
        forbidden=b.get("forbidden_words", []),
        hashtags=b.get("hashtags", []),
        languages=b.get("languages", ["en"]),
        timezone=b.get("timezone", "UTC"),
        utm_source=b.get("utm_source", "playnexus"),
        utm_medium=b.get("utm_medium", "promo"),
        rules_note=b.get("rules_note", ""),
        services=[
            Service(
                slug=s["slug"],
                name=s["name"],
                tagline=s["tagline"],
                detail=s.get("detail", ""),
                keywords=s.get("keywords", []),
                page=s.get("page", ""),
                proof=s.get("proof", ""),
                cta=s.get("cta", ""),
                est_value=s.get("est_value", ""),
                audience=s.get("audience", ""),
            )
            for s in b.get("services", [])
        ],
    )
    if not biz.services:
        raise ConfigError("business.json: 'services' must not be empty")

    ch_raw = _read_json(cdir / "channels.json", default={})
    channels: dict[str, Channel] = {}
    for name, c in ch_raw.get("channels", {}).items():
        if "rules" not in c:
            raise ConfigError(
                f"channels.json: channel {name!r} has no 'rules' block. "
                "Every channel must declare its own compliance rules."
            )
        r = c["rules"]
        channels[name] = Channel(
            name=name,
            mode=Mode(c.get("mode", "off")),
            enabled=bool(c.get("enabled", False)),
            rate_per_day=int(c.get("rate_per_day", 1)),
            min_gap_minutes=int(c.get("min_gap_minutes", 240)),
            active_hours=c.get("active_hours", list(range(24))),
            weekdays=c.get("weekdays", [0, 1, 2, 3, 4, 5, 6]),
            weight=int(c.get("weight", 1)),
            notes=c.get("notes", ""),
            config={k: v for k, v in c.items() if k not in {
                "mode", "enabled", "rate_per_day", "min_gap_minutes",
                "active_hours", "weekdays", "rules", "weight", "notes",
            }},
            rules=ChannelRules(
                max_title=int(r.get("max_title", 300)),
                max_body=int(r.get("max_body", 4000)),
                min_body=int(r.get("min_body", 0)),
                max_tags=int(r.get("max_tags", 0)),
                link_allowed=bool(r.get("link_allowed", True)),
                link_required=bool(r.get("link_required", False)),
                banned=r.get("banned", []),
                required=r.get("required", []),
                min_value_ratio=float(r.get("min_value_ratio", 0.0)),
                no_ad_tone=bool(r.get("no_ad_tone", False)),
                link_in_profile_only=bool(r.get("link_in_profile_only", False)),
                community=bool(r.get("community", False)),
            ),
        )

    hooks_raw = _read_json(cdir / "hooks.json", default={})
    hooks = [
        Hook(
            id=h["id"],
            service=h["service"],
            angle=h.get("angle", ""),
            title=h["title"],
            body=h["body"],
            proof=h.get("proof", ""),
            cta=h.get("cta", ""),
            tags=h.get("tags", []),
            link=h.get("link", ""),
            community=h.get("community", ""),
        )
        for h in hooks_raw.get("hooks", [])
    ]

    known = {s.slug for s in biz.services}
    for h in hooks:
        if h.service not in known:
            raise ConfigError(
                f"hooks.json: hook {h.id!r} targets unknown service {h.service!r}. "
                f"known: {sorted(known)}"
            )

    secrets = _read_json(cdir / "secrets.json", default={})
    return Config(business=biz, channels=channels, hooks=hooks, secrets=secrets,
                  config_dir=cdir, data_dir=DATA_DIR)


def save_secrets(cfg: Config, channel: str, values: dict[str, Any]) -> None:
    cfg.secrets.setdefault(channel, {}).update(values)
    _write_json(cfg.config_dir / "secrets.json", cfg.secrets)


def all_urls() -> list[str]:
    return [
        u for u in [
            os.environ.get("PLAYNEXUS_URL"),
        ] if u
    ]


_url_re = re.compile(r"https?://[^\s<>\"')]+")


def find_urls(text: str) -> list[str]:
    return _url_re.findall(text or "")
