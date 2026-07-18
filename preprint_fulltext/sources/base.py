"""base.py — the Source port. Adapters map their payloads into the canonical model.

Sources implement only what they support; unsupported verbs raise
:class:`NotSupported` so the router can react.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from ..core.models import FullText, Preprint, SearchHit, Server


class NotSupported(Exception):
    """Raised when a source is asked for a verb it does not implement."""


class SourceError(Exception):
    """A recoverable, reportable source failure (e.g. missing credentials/key)."""


class DiscoverQuery(BaseModel):
    """Structured discovery query (topic/category/date window)."""

    query: str | None = None
    category: str | None = None
    server: Server | None = None
    from_date: dt.date | None = None
    to_date: dt.date | None = None
    limit: int = 100


@runtime_checkable
class Source(Protocol):
    name: str

    def discover(self, query: DiscoverQuery) -> Iterator[SearchHit]: ...
    def search(self, query: str, limit: int) -> Iterator[SearchHit]: ...
    def get_fulltext(self, doi: str, version: int | None = None) -> FullText | None: ...
    def get_metadata(self, doi: str) -> Preprint | None: ...


__all__ = ["Source", "DiscoverQuery", "NotSupported", "SourceError"]
