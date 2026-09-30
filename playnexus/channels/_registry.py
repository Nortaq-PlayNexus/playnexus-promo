"""Registry bootstrap.

Kept in its own module so the registration imports in `channels/__init__.py` are a
single explicit list. If a channel module fails to import, startup fails loudly
rather than the pipeline quietly not posting to that destination.
"""

from __future__ import annotations

from . import (  # noqa: F401
    bluesky,
    devto,
    discord,
    github,
    hackernews,
    hashnode,
    lobsters,
    manual,
    mastodon,
    reddit,
    telegram,
)

#: Channels where the platform itself expects a human, or where automation would
#: get the account banned. `doctor` reports these as MANUAL-ONLY regardless of config.
MANUAL_ONLY = {
    "hackernews",  # read-only public API; submission is a web form, by design
    "lobsters",    # invite-gated community; posting is manual
    "manual",      # directory forms, filled in by hand
}
