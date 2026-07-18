"""openalex.py — discovery / search / OA-location only.

OpenAlex is a catalog + signpost, **never a full-text store**: its full text is
n-gram search (not retrievable), so we surface `has_fulltext` and hand off the OA
URL but never attempt to fetch body text here. API key required since 2026-02-13
(missing key → HTTP 409); single-work-by-DOI lookups are free, list/search cost
credits, so `get_metadata` uses the free singleton endpoint.
"""

from __future__ import annotations

from collections.abc import Iterator

from ..config import Settings, get_settings
from ..core.http import build_client, request_with_retry
from ..core.models import Preprint, SearchHit, Server, SourceName
from .base import DiscoverQuery, SourceError

BASE = "https://api.openalex.org"

_KEY_HINT = (
    "OpenAlex API key required since 2026-02-13 (requests without a key return HTTP 409 "
    "after a small free-credit grace). Set OPENALEX_API_KEY (free at openalex.org/settings/api)."
)


def reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Rebuild plaintext from OpenAlex's abstract_inverted_index (position -> word)."""
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    if not positions:
        return None
    positions.sort()
    return " ".join(word for _, word in positions)


def _short_id(openalex_id: str | None) -> str | None:
    if not openalex_id:
        return None
    return openalex_id.rsplit("/", 1)[-1]  # https://openalex.org/W123 -> W123


def _clean_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.replace("https://doi.org/", "").replace("http://doi.org/", "")


class OpenAlex:
    name = "openalex"

    def __init__(self, settings: Settings | None = None, client=None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.settings)
        return self._client

    def _require_key(self) -> str:
        key = self.settings.openalex_api_key
        if not key:
            raise SourceError(_KEY_HINT)
        return key

    def _base_params(self) -> dict:
        params = {"api_key": self._require_key()}
        if self.settings.contact_email:
            params["mailto"] = self.settings.contact_email
        return params

    @staticmethod
    def _work_to_hit(w: dict) -> SearchHit:
        best = w.get("best_oa_location") or {}
        oa_url = best.get("pdf_url") or best.get("landing_page_url") or w.get("best_oa_url")
        return SearchHit(
            title=w.get("title") or w.get("display_name"),
            doi=_clean_doi(w.get("doi")),
            openalex_id=_short_id(w.get("id")),
            score=w.get("relevance_score"),
            source=SourceName.OPENALEX,
            snippet=reconstruct_abstract(w.get("abstract_inverted_index")),
            oa_url=oa_url,
            has_fulltext=bool(w.get("has_fulltext")),
        )

    def _paginate(self, params: dict, limit: int) -> Iterator[dict]:
        cursor = "*"
        fetched = 0
        per_page = min(200, max(1, limit))
        while fetched < limit:
            page_params = {**params, "per-page": str(per_page), "cursor": cursor}
            resp = request_with_retry(self.client, "GET", f"{BASE}/works", params=page_params)
            if resp.status_code == 409:
                raise SourceError(_KEY_HINT)
            if resp.status_code != 200:
                return
            data = resp.json()
            results = data.get("results", [])
            if not results:
                return
            for w in results:
                yield w
                fetched += 1
                if fetched >= limit:
                    return
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                return

    # OpenAlex field-scoped search: title/abstract/author use filters, else free search=.
    _FILTER_FIELD = {
        "title": "title.search",
        "abstract": "abstract.search",
        "author": "raw_author_name.search",
    }

    def search(self, query: str, limit: int = 25, field: str = "fulltext") -> Iterator[SearchHit]:
        params = {**self._base_params()}
        filter_key = self._FILTER_FIELD.get(field)
        if filter_key:
            params["filter"] = f"{filter_key}:{query}"
        else:
            params["search"] = query
        for w in self._paginate(params, limit):
            yield self._work_to_hit(w)

    def discover(self, query: DiscoverQuery) -> Iterator[SearchHit]:
        filters = []
        if query.from_date:
            filters.append(f"from_publication_date:{query.from_date.isoformat()}")
        if query.to_date:
            filters.append(f"to_publication_date:{query.to_date.isoformat()}")
        if query.category:
            filters.append(f"concepts.display_name.search:{query.category}")
        params = {**self._base_params()}
        if filters:
            params["filter"] = ",".join(filters)
        if query.query:
            params["search"] = query.query
        for w in self._paginate(params, query.limit):
            yield self._work_to_hit(w)

    def get_metadata(self, doi: str) -> Preprint | None:
        """Free singleton lookup by DOI. Abstract reconstructed; no body text."""
        params = self._base_params()
        resp = request_with_retry(
            self.client, "GET", f"{BASE}/works/https://doi.org/{doi}", params=params
        )
        if resp.status_code == 409:
            raise SourceError(_KEY_HINT)
        if resp.status_code != 200:
            return None
        w = resp.json()
        return Preprint(
            doi=_clean_doi(w.get("doi")) or doi,
            server=Server.BIORXIV,
            title=w.get("title") or w.get("display_name"),
            abstract=reconstruct_abstract(w.get("abstract_inverted_index")),
            provenance={"source": "openalex", "openalex_id": _short_id(w.get("id"))},
        )


__all__ = ["OpenAlex", "reconstruct_abstract"]
