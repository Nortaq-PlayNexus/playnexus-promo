"""Channel registry.

Adding a channel = add a module to `_registry.py` + a block in config/channels.json.
The registry is explicit rather than import-scanning, because a typo in a channel
name should be a startup error, not a silently missing destination.
"""

from __future__ import annotations

from .base import Channel, ChannelError, register, registered
from ._registry import MANUAL_ONLY  # noqa: F401  (triggers module registration)


def get(name: str) -> type[Channel] | None:
    return registered().get(name)


def known() -> list[str]:
    return sorted(registered())


def build(cfg, name: str, client) -> Channel | None:
    cls = get(name)
    if cls is None or name not in cfg.channels:
        return None
    return cls(cfg, client)


def build_all(cfg, client) -> dict[str, Channel]:
    out: dict[str, Channel] = {}
    for name in sorted(cfg.channels):
        inst = build(cfg, name, client)
        if inst is not None:
            out[name] = inst
    return out


__all__ = [
    "Channel", "ChannelError", "register", "get", "known", "build", "build_all",
    "MANUAL_ONLY",
]
