"""arxiv.py — arXiv metadata + search via the arXiv API (Atom).

Metadata/search only; full text (LaTeXML HTML) is handled by ``arxiv_html.py``.
arXiv IDs map to their DataCite DOI (``10.48550/arXiv.<id>``) in the canonical model.
The arXiv API is polite-pool friendly but has no key; it returns Atom XML.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

from lxml import etree

from ..config import Settings, get_settings
from ..core.http import build_client, request_with_retry
from ..core.ids import arxiv_doi, normalize_arxiv_id
from ..core.models import Preprint, SearchHit, Server, SourceName
from .base import DiscoverQuery

_ATOM = "http://www.w3.org/2005/Atom"
_ARXIV = "http://arxiv.org/schemas/atom"
_OS = "http://a9.com/-/spec/opensearch/1.1/"

# arXiv search field prefixes for --field.
_FIELD_PREFIX = {"fulltext": "all", "title": "ti", "abstract": "abs", "author": "au"}


def _text(el, path: str) -> str | None:
    found = el.find(path)
    return found.text.strip() if found is not None and found.text else None


def _parse_id(raw_id: str) -> tuple[str, int | None]:
    """'http://arxiv.org/abs/2401.10515v2' -> ('2401.10515', 2)."""
    tail = raw_id.rsplit("/", 1)[-1]
    ver = None
    if "v" in tail:
        base, _, v = tail.rpartition("v")
        if v.isdigit():
            return base, int(v)
    return tail, ver


def _entry_to_preprint(entry) -> Preprint:
    raw_id = _text(entry, f"{{{_ATOM}}}id") or ""
    aid, version = _parse_id(raw_id)
    authors = [
        n.text.strip()
        for n in entry.findall(f"{{{_ATOM}}}author/{{{_ATOM}}}name")
        if n.text and n.text.strip()
    ]
    date = None
    published = _text(entry, f"{{{_ATOM}}}published")
    if published:
        try:
            date = dt.date.fromisoformat(published[:10])
        except ValueError:
            date = None
    prim = entry.find(f"{{{_ARXIV}}}primary_category")
    category = prim.get("term") if prim is not None else None
    journal_doi = _text(entry, f"{{{_ARXIV}}}doi")  # published-version DOI, if any
    title = _text(entry, f"{{{_ATOM}}}title")
    summary = _text(entry, f"{{{_ATOM}}}summary")
    return Preprint(
        doi=arxiv_doi(aid),
        version=version,
        server=Server.ARXIV,
        title=" ".join(title.split()) if title else None,
        authors=authors,
        date=date,
        category=category,
        abstract=" ".join(summary.split()) if summary else None,
        published_doi=journal_doi,
        provenance={"source": "arxiv_api", "arxiv_id": aid},
    )


class ArxivAPI:
    name = "arxiv_api"

    def __init__(self, settings: Settings | None = None, client=None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.settings)
        return self._client

    def _query(self, params: dict) -> list:
        resp = request_with_retry(self.client, "GET", self.settings.arxiv_api_base, params=params)
        if resp.status_code != 200:
            return []
        try:
            root = etree.fromstring(resp.content, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            return []
        return root.findall(f"{{{_ATOM}}}entry") if root is not None else []

    def get_metadata(self, arxiv_id: str, version: int | None = None) -> Preprint | None:
        aid = normalize_arxiv_id(arxiv_id) or arxiv_id
        id_arg = f"{aid}v{version}" if version else aid
        entries = self._query({"id_list": id_arg, "max_results": "1"})
        return _entry_to_preprint(entries[0]) if entries else None

    def latest_version(self, arxiv_id: str) -> int | None:
        p = self.get_metadata(arxiv_id)
        return p.version if p else None

    def _search_query(self, search_query: str, limit: int) -> Iterator[SearchHit]:
        fetched = 0
        page = min(100, max(1, limit))
        while fetched < limit:
            entries = self._query({
                "search_query": search_query,
                "start": str(fetched),
                "max_results": str(page),
                "sortBy": "relevance",
            })
            if not entries:
                return
            for e in entries:
                p = _entry_to_preprint(e)
                aid = (p.provenance or {}).get("arxiv_id")
                yield SearchHit(
                    title=p.title,
                    doi=p.doi,
                    source=SourceName.ARXIV_API,
                    snippet=p.abstract[:300] if p.abstract else None,
                    oa_url=f"https://arxiv.org/abs/{aid}" if aid else None,
                    has_fulltext=True,  # arXiv HTML/ar5iv is broadly available
                )
                fetched += 1
                if fetched >= limit:
                    return
            if len(entries) < page:
                return

    @staticmethod
    def _field_query(query: str, field: str) -> str:
        """Scope a query to an arXiv field. Multi-word title/abstract/fulltext queries are
        term-ANDed within the field (a bare space would otherwise unscope later words);
        author is a quoted name."""
        prefix = _FIELD_PREFIX.get(field, "all")
        if field == "author":
            return f'au:"{query}"'
        terms = [t for t in query.split() if t]
        if len(terms) <= 1:
            return f"{prefix}:{query}"
        return "(" + " AND ".join(f"{prefix}:{t}" for t in terms) + ")"

    def search(self, query: str, limit: int = 25, field: str = "fulltext") -> Iterator[SearchHit]:
        return self._search_query(self._field_query(query, field), limit)

    def discover(self, query: DiscoverQuery) -> Iterator[SearchHit]:
        parts = []
        if query.query:
            parts.append(f"all:{query.query}")
        if query.category:
            parts.append(f"cat:{query.category}")
        return self._search_query(" AND ".join(parts) if parts else "all:*", query.limit)


__all__ = ["ArxivAPI"]
