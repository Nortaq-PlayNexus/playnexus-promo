"""GitHub. The most under-used free channel for a dev-services business.

Two automatable surfaces, both officially free at this rate:
  * profile README  (needs a repo named <username>/<username>) — evergreen landing page
  * repo topics     — this is literally how people discover "discord bot developer"
  * repo pinned description in the README

Writing a README is a filesystem write; syncing topics is a REST call. Both here.
"""

from __future__ import annotations

from typing import Any

from .base import Channel, ChannelError, register
from ..http import HttpError
from ..render import Rendered

API = "https://api.github.com"


@register
class GitHubChannel(Channel):
    name = "github"
    supports_auto = True

    def verify(self) -> tuple[bool, str]:
        for k in ("token", "username"):
            if not self.secret(k):
                return False, f"set secrets.github.{k}"
        return True, "ok"

    def endpoint(self) -> str:
        return f"{API}/user"

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret('token')}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def build_payload(self, rendered: Rendered) -> dict[str, Any]:
        """Not a publish payload. `push_topic` is what actually runs here."""
        return {"repo": self.channel_cfg.config.get("repo", ""),
                "topics": rendered.tags or []}

    def publish(self, rendered: Rendered) -> dict[str, str]:
        raise ChannelError(
            "github: use `pnx gh topics` to sync topics, or "
            f"`pnx gh readme {self.secret('username')}` to write the profile README. "
            "Writing a file into someone's repo is not something a scheduler should "
            "do unattended."
        )

    # -- topics ---------------------------------------------------------

    def set_topics(self, repo: str, topics: list[str]) -> dict[str, str]:
        """PUT /repos/{owner}/{repo}/topics. Idempotent, cheap, and genuinely useful."""
        topics = [t.strip().lower().replace(" ", "-") for t in topics if t.strip()][:20]
        if not topics:
            raise ChannelError("github: no topics to set")
        try:
            resp = self.client.put(
                f"{API}/repos/{repo}/topics",
                json_body={"names": topics},
                headers=self.headers(),
            )
        except HttpError as e:
            raise ChannelError(f"github: {e}") from e
        return {"id": repo, "url": f"https://github.com/{repo}/topics"}

    def profile_readme_path(self) -> str:
        user = self.secret("username")
        return f"C:/Users/natha/projects/playnexus-promo/out/github/{user}/{user}.md"

    def render_profile_readme(self, business: Any) -> str:
        """Build the profile README content for review. Not written automatically."""
        services = "\n".join(
            f"### {s.name}\n{s.tagline}"
            + (f"  \n_{s.detail}_" if s.detail else "")
            + (f"  \n{s.est_value}" if s.est_value else "")
            + (f"  \n[{s.name}]({business.url}{s.page})" if s.page and business.url else "")
            + "\n"
            for s in business.services
        )
        return f"""# {business.name}

{business.tagline}

{services}
---

**Contact:** {business.contact or business.url}

<sub>Written by the PlayNexus promo pipeline. Edit
`config/business.json` and regenerate, or edit the file directly — the pipeline will
not overwrite this file without `--force`.</sub>
"""
