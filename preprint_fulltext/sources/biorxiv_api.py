"""biorxiv_api.py — cheap metadata / recency / published mapping.

Abstract only, never body text. Backed by api.biorxiv.org
(`/details/{server}/{doi}` and the date-window form; the `published` field maps a
preprint to its peer-reviewed DOI).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

from ..config import Settings, get_settings
from ..core.http import build_client, request_with_retry
from ..core.licenses import parse_license
from ..core.models import Preprint, Server

BASE = "https://api.biorxiv.org"


def _parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def _authors(raw: str | None) -> list[str]:
    # bioRxiv returns "Surname, F.; Other, A." — keep as-is, split on ';'.
    if not raw:
        return []
    return [a.strip() for a in raw.split(";") if a.strip()]


def _entry_to_preprint(e: dict, server: Server) -> Preprint:
    published = e.get("published")
    published_doi = published if published and published not in ("NA", "na") else None
    return Preprint(
        doi=e.get("doi", ""),
        version=int(e["version"]) if str(e.get("version", "")).isdigit() else None,
        server=server,
        title=e.get("title") or None,
        authors=_authors(e.get("authors")),
        date=_parse_date(e.get("date")),
        category=e.get("category") or None,
        abstract=e.get("abstract") or None,
        license=parse_license(e.get("license")),
        published_doi=published_doi,
        provenance={"source": "biorxiv_api", "server": server.value},
    )


class BiorxivAPI:
    name = "biorxiv_api"

    def __init__(self, settings: Settings | None = None, client=None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.settings)
        return self._client

    def get_versions(self, doi: str, server: Server | str | None = None) -> list[Preprint]:
        """All versions of a preprint (ascending), one Preprint per version row.

        The bioRxiv/medRxiv details endpoint returns every version; the DOI always
        resolves to the latest, so ``get_versions(...)[-1]`` is the latest version.
        """
        servers = [Server(server)] if server else [Server.BIORXIV, Server.MEDRXIV]
        for srv in servers:
            resp = request_with_retry(self.client, "GET", f"{BASE}/details/{srv.value}/{doi}")
            if resp.status_code != 200:
                continue
            coll = resp.json().get("collection", [])
            if coll:
                return [_entry_to_preprint(e, srv) for e in coll]
        return []

    def get_metadata(self, doi: str, server: Server | str | None = None) -> Preprint | None:
        """DOI -> Preprint (latest version). Tries both servers if none given."""
        versions = self.get_versions(doi, server)
        return versions[-1] if versions else None

    def latest_version(self, doi: str, server: Server | str | None = None) -> int | None:
        """Latest version number, or None if unknown."""
        p = self.get_metadata(doi, server)
        return p.version if p else None

    def iter_window(
        self, server: Server | str, from_date: dt.date, to_date: dt.date
    ) -> Iterator[Preprint]:
        """Enumerate preprints deposited in a date window (recency), paginated."""
        srv = Server(server)
        cursor = 0
        seen = 0
        while True:
            url = f"{BASE}/details/{srv.value}/{from_date.isoformat()}/{to_date.isoformat()}/{cursor}"
            resp = request_with_retry(self.client, "GET", url)
            if resp.status_code != 200:
                return
            data = resp.json()
            coll = data.get("collection", [])
            if not coll:
                return
            for e in coll:
                yield _entry_to_preprint(e, srv)
            seen += len(coll)
            messages = data.get("messages", [{}])
            total = int(messages[0].get("total", 0)) if messages else 0
            if total and seen >= total:
                return
            cursor += len(coll)

    def published_doi(self, doi: str, server: Server | str | None = None) -> str | None:
        p = self.get_metadata(doi, server)
        return p.published_doi if p else None


__all__ = ["BiorxivAPI"]
