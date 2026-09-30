"""Minimal HTTP client: urllib + retry/backoff + rate-limit header awareness.

Deliberately not `requests`. Nothing here needs a dependency, and the whole point of
the pipeline is that it runs on a bare Python install in three years.

Two behaviours that matter for compliance:

1. **We never lie about our identity.** `user_agent` is built from a real config
   string. Reddit explicitly throttles generic agents like `Python/urllib/3.x`.
2. **Server rate-limit headers are ground truth.** `RateLimit-*` (Bluesky, Mastodon)
   and `X-Ratelimit-*` (Reddit) are recorded so the scheduler backs off instead of
   guessing.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_UA = "playnexus-promo/1.0 (+https://github.com/playnexus)"


class HttpError(Exception):
    def __init__(self, status: int, body: str, url: str, headers: dict[str, str] | None = None):
        super().__init__(f"HTTP {status} for {url}: {body[:300]}")
        self.status = status
        self.body = body
        self.url = url
        self.headers = headers or {}


@dataclass
class Response:
    status: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as e:
            raise HttpError(self.status, f"non-JSON body: {self.body[:200]}", "", self.headers) from e


def _header_map(headers: Any) -> dict[str, str]:
    return {k.lower(): v for k, v in (headers.items() if headers else [])}


def extract_rate_limit(headers: dict[str, str]) -> dict[str, float]:
    """Pull whichever rate-limit signal the server sent, normalised to floats."""
    out: dict[str, float] = {}
    pairs = [
        ("remaining", ("x-ratelimit-remaining", "ratelimit-remaining", "x-rate-limit-remaining")),
        ("limit", ("x-ratelimit-limit", "ratelimit-limit", "x-rate-limit-limit")),
        ("reset", ("x-ratelimit-reset", "ratelimit-reset", "x-rate-limit-reset", "retry-after")),
        ("used", ("x-ratelimit-used", "ratelimit-used")),
    ]
    for name, keys in pairs:
        for k in keys:
            if k in headers:
                try:
                    out[name] = float(headers[k])
                except ValueError:
                    pass
                break
    return out


def _is_retryable(status: int) -> bool:
    return status in (408, 425, 429, 500, 502, 503, 504, 522, 524)


class Client:
    def __init__(self, user_agent: str = DEFAULT_UA, timeout: int = 30,
                 max_retries: int = 4, min_interval: float = 0.0):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self._last_call = 0.0
        self.last_rate_limit: dict[str, float] = {}

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        delta = time.monotonic() - self._last_call
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last_call = time.monotonic()

    def request(self, method: str, url: str, *, headers: dict[str, str] | None = None,
                json_body: Any = None, form: dict[str, Any] | None = None,
                allow_redirects: bool = True) -> Response:
        hdrs = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        hdrs.update(headers or {})

        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        elif form is not None:
            data = urllib.parse.urlencode(
                {k: v for k, v in form.items() if v is not None}, doseq=True
            ).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
            opener_handlers = []
            if not allow_redirects:
                opener_handlers.append(_NoRedirect())
            opener = urllib.request.build_opener(*opener_handlers)
            try:
                with opener.open(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", "replace")
                    h = _header_map(resp.headers)
                    rl = extract_rate_limit(h)
                    if rl:
                        self.last_rate_limit = rl
                    return Response(status=resp.status, body=body, headers=h)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace") if e.fp else ""
                h = _header_map(e.headers)
                rl = extract_rate_limit(h)
                if rl:
                    self.last_rate_limit = rl
                if _is_retryable(e.code) and attempt < self.max_retries:
                    delay = self._backoff(attempt, h)
                    last_exc = HttpError(e.code, body, url, h)
                    time.sleep(delay)
                    continue
                raise HttpError(e.code, body, url, h) from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_exc = e
                if attempt < self.max_retries:
                    time.sleep(self._backoff(attempt, {}))
                    continue
                raise HttpError(0, f"transport error: {e}", url) from e
        raise HttpError(0, f"exhausted retries: {last_exc}", url)

    @staticmethod
    def _backoff(attempt: int, headers: dict[str, str]) -> float:
        """Honour Retry-After, else exponential backoff with full jitter."""
        ra = headers.get("retry-after")
        if ra:
            try:
                return min(float(ra), 300.0)
            except ValueError:
                pass
        return min(2 ** attempt + random.random(), 60.0)

    # convenience verbs
    def get(self, url: str, **kw: Any) -> Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> Response:
        return self.request("POST", url, **kw)

    def patch(self, url: str, **kw: Any) -> Response:
        return self.request("PATCH", url, **kw)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        return None
