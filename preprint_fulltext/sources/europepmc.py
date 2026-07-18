"""europepmc.py — interactive full-text retrieval + relevance search.

Europe PMC indexes many sources; retrievable full-text XML exists only for the
open-access subset. For bioRxiv/medRxiv that is (broadly) the CC-licensed
preprints, so a 404 on ``fullTextXML`` is normal and means "fall back to S3", not
an error. We only ever call ``fullTextXML`` for ``PPR`` ids.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..config import Settings, get_settings
from ..core.assemble import build_fulltext
from ..core.http import build_client, request_with_retry
from ..core.jats import parse_jats
from ..core.models import FullText, SearchHit, Server, SourceName
from .base import DiscoverQuery

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"

_MEDRXIV_RE = re.compile(rb"medrxiv", re.IGNORECASE)


def _detect_server(xml: bytes) -> Server:
    """bioRxiv and medRxiv share the 10.1101 DOI prefix; disambiguate from the
    JATS front matter (journal-id/publisher), defaulting to bioRxiv."""
    head = xml[:4000]
    return Server.MEDRXIV if _MEDRXIV_RE.search(head) else Server.BIORXIV


class EuropePMC:
    name = "europepmc"

    def __init__(self, settings: Settings | None = None, client=None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.settings)
        return self._client

    # --- resolution -----------------------------------------------------------
    def resolve_ppr_id(self, doi: str) -> str | None:
        """DOI -> Europe PMC PPR id via search."""
        params = {
            "query": f'DOI:"{doi}" AND SRC:PPR',
            "format": "json",
            "resultType": "lite",
            "pageSize": "1",
        }
        resp = request_with_retry(self.client, "GET", f"{BASE}/search", params=params)
        if resp.status_code != 200:
            return None
        results = resp.json().get("resultList", {}).get("result", [])
        for r in results:
            if r.get("source") == "PPR" and r.get("id"):
                return r["id"]
        return None

    # --- full text ------------------------------------------------------------
    def get_fulltext(self, doi: str, version: int | None = None) -> FullText | None:
        ppr = self.resolve_ppr_id(doi)
        if not ppr:
            return None
        # NB: the id already carries its source prefix (PPR…/PMC…); the endpoint is
        # /{id}/fullTextXML, NOT /{source}/{id}/fullTextXML (the latter 404s).
        url = f"{BASE}/{ppr}/fullTextXML"
        resp = request_with_retry(self.client, "GET", url)
        if resp.status_code == 404:
            return None  # not OA -> router falls back to S3
        if resp.status_code != 200:
            return None
        xml = resp.content
        parsed = parse_jats(xml)
        if not parsed.sections and not parsed.abstract:
            return None
        return build_fulltext(
            parsed,
            doi=doi,
            server=_detect_server(xml),
            source=SourceName.EUROPEPMC,
            version=version,
            raw_ref=url,
            provenance={"source": "europepmc", "europepmc_id": ppr},
        )

    # --- search / discover ----------------------------------------------------
    def _paginate(self, query: str, limit: int) -> Iterator[dict]:
        cursor = "*"
        fetched = 0
        page_size = min(100, max(1, limit))
        while fetched < limit:
            params = {
                "query": query,
                "format": "json",
                "resultType": "lite",
                "pageSize": str(page_size),
                "cursorMark": cursor,
            }
            resp = request_with_retry(self.client, "GET", f"{BASE}/search", params=params)
            if resp.status_code != 200:
                return
            data = resp.json()
            results = data.get("resultList", {}).get("result", [])
            if not results:
                return
            for r in results:
                yield r
                fetched += 1
                if fetched >= limit:
                    return
            next_cursor = data.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor

    @staticmethod
    def _to_hit(r: dict) -> SearchHit:
        return SearchHit(
            title=r.get("title"),
            doi=r.get("doi"),
            source=SourceName.EUROPEPMC,
            has_fulltext=(r.get("inEPMC") == "Y" or r.get("hasTextMinedTerms") == "Y"),
            snippet=None,
        )

    @staticmethod
    def _field_query(query: str, field: str) -> str:
        """Build a Europe PMC field-scoped query.

        title/abstract → each term ANDed within the field (so multi-word topical
        queries match titles containing all the words, not an exact phrase);
        author → a quoted name phrase; fulltext → the raw query.
        """
        field = (field or "fulltext").lower()
        if field == "author":
            return f'AUTH:"{query}"'
        if field in ("title", "abstract"):
            tag = "TITLE" if field == "title" else "ABSTRACT"
            terms = [t for t in query.split() if t]
            if len(terms) <= 1:
                return f'{tag}:"{query}"'
            return "(" + " AND ".join(f'{tag}:"{t}"' for t in terms) + ")"
        return query  # fulltext

    def search(self, query: str, limit: int = 25, field: str = "fulltext") -> Iterator[SearchHit]:
        scoped = self._field_query(query, field)
        full_query = scoped if "SRC:PPR" in scoped.upper() else f"({scoped}) AND SRC:PPR"
        for r in self._paginate(full_query, limit):
            yield self._to_hit(r)

    def discover(self, query: DiscoverQuery) -> Iterator[SearchHit]:
        parts = ["SRC:PPR"]
        if query.query:
            parts.append(f"({query.query})")
        if query.category:
            parts.append(f'KW:"{query.category}"')
        if query.from_date or query.to_date:
            lo = query.from_date.isoformat() if query.from_date else "1900-01-01"
            hi = query.to_date.isoformat() if query.to_date else "3000-01-01"
            parts.append(f"FIRST_PDATE:[{lo} TO {hi}]")
        return self.search(" AND ".join(parts), query.limit)


__all__ = ["EuropePMC"]
