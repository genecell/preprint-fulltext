"""cache.py — content-addressed local cache of fetched bytes (.meca/XML).

Keyed by ``sha256(source | id | version)`` so re-runs skip S3/EPMC. Sharded into
256 subdirectories to keep any one directory small.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from ..config import Settings, get_settings


class Cache:
    def __init__(self, cache_dir: Path | str | None = None, settings: Settings | None = None):
        settings = settings or get_settings()
        self.dir = Path(cache_dir or settings.cache_dir)

    @staticmethod
    def key(*parts: object) -> str:
        raw = "|".join("" if p is None else str(p) for p in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.dir / key[:2] / key

    def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)  # atomic within the same filesystem

    def get_or_fetch(self, key: str, fetch_fn: Callable[[], bytes]) -> bytes:
        cached = self.get(key)
        if cached is not None:
            return cached
        data = fetch_fn()
        self.put(key, data)
        return data


__all__ = ["Cache"]
