"""http.py — a small httpx wrapper with polite-pool identity and retry/backoff.

Retries 429/5xx with exponential backoff + jitter and honours ``Retry-After``.
``_sleep`` and ``_jitter`` are module-level so tests can
patch them to run instantly and deterministically.
"""

from __future__ import annotations

import time

import httpx

from ..config import Settings, get_settings

_RETRY_STATUS = {429, 500, 502, 503, 504}


def _sleep(seconds: float) -> None:  # patched in tests
    time.sleep(seconds)


def _jitter() -> float:  # patched in tests (avoids Math.random-style nondeterminism)
    return 0.1


def build_client(settings: Settings | None = None, **kwargs) -> httpx.Client:
    """Build an httpx.Client carrying the polite-pool User-Agent."""
    settings = settings or get_settings()
    headers = {"User-Agent": settings.user_agent, **kwargs.pop("headers", {})}
    timeout = kwargs.pop("timeout", 30.0)
    return httpx.Client(headers=headers, timeout=timeout, **kwargs)


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_retries: int = 4,
    base_delay: float = 0.5,
    **kwargs,
) -> httpx.Response:
    """Issue a request, retrying transient failures with backoff.

    Returns the final response (which may still be an error status if retries are
    exhausted); the caller decides how to treat 4xx like 404.
    """
    attempt = 0
    while True:
        try:
            resp = client.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt >= max_retries:
                raise
            _sleep(base_delay * (2**attempt) + _jitter())
            attempt += 1
            continue

        if resp.status_code in _RETRY_STATUS and attempt < max_retries:
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if (retry_after and retry_after.isdigit()) else (
                base_delay * (2**attempt) + _jitter()
            )
            _sleep(delay)
            attempt += 1
            continue
        return resp


__all__ = ["build_client", "request_with_retry"]
