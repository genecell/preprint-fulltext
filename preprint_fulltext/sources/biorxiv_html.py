"""biorxiv_html.py — OPT-IN, interactive-only, single-document HTML fallback.

Why this exists: for a brand-new or non-CC (e.g. ``cc_no``) preprint, Europe PMC has
no retrievable full text and S3 needs AWS credentials + requester-pays cost (and lags
until the month closes). The public ``…​.full`` HTML page is then the only free
full-text route. This is defensible for personal analysis/reading of a single paper.

GUARDRAILS (deliberate):
  * NEVER wired into bulk ``ingest`` — single-document only.
  * Polite User-Agent + ``mailto`` (our UA is not in bioRxiv's robots blocklist).
  * Emits a :class:`ParsedArticle` — the SAME shape the JATS parser produces — so
    ``assemble``/``chunk``/the compliance ``gate`` are shared and identical. Only the
    parser differs from the JATS path.
  * License is enriched best-effort from the bioRxiv JSON API; unknown → the gate's
    fail-safe (non-redistributable) still applies.
"""

from __future__ import annotations

import re

from lxml import html as lxml_html

from ..config import Settings, get_settings
from ..core.assemble import build_fulltext
from ..core.http import build_client, request_with_retry
from ..core.jats import ParsedArticle, ParsedSection, _classify, _norm
from ..core.models import FullText, Server, SourceName

# Section-level classes to drop entirely (references, footnotes, acknowledgements-as-refs).
_SKIP_SECTION_CLASSES = ("ref-list", "fn-group", "copyright")
# Inline/blocks whose text wrecks embedding signal (mirror the JATS strip policy).
_STRIP_XPATH = (
    ".//a | .//cite "
    "| .//*[contains(@class,'fig') or contains(@class,'table') "
    "or contains(@class,'formula') or contains(@class,'disp-formula') "
    "or contains(@class,'supplementary') or contains(@class,'ref-list')]"
)


def _has_class(el, needle: str) -> bool:
    return needle in (el.get("class") or "")


def _direct_prose(section_el) -> str:
    """Text of <p> that belong directly to this section (not to a nested sub-section)."""
    parts: list[str] = []

    def walk(node):
        for child in node:
            cls = child.get("class") or ""
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag == "div" and ("subsection" in cls or "section" in cls):
                continue  # nested section handled separately
            if tag == "p":
                parts.append(_norm(child.text_content()))
            else:
                walk(child)  # descend through wrappers (section-content etc.)

    walk(section_el)
    return _norm(" ".join(p for p in parts if p))


def parse_biorxiv_html(html_bytes: bytes) -> ParsedArticle:
    """Parse a bioRxiv/medRxiv ``…​.full`` HTML page into a :class:`ParsedArticle`."""
    art = ParsedArticle()
    try:
        root = lxml_html.fromstring(html_bytes)
    except Exception:
        return art

    def meta(name: str) -> str | None:
        vals = root.xpath(f'//meta[@name="{name}"]/@content')
        return vals[0].strip() if vals else None

    def meta_all(name: str) -> list[str]:
        return [v.strip() for v in root.xpath(f'//meta[@name="{name}"]/@content') if v.strip()]

    art.title = meta("citation_title")
    art.doi = meta("citation_doi")
    art.authors = meta_all("citation_author")

    views = root.xpath('//div[contains(@class,"fulltext-view")]')
    if not views:
        return art
    view = views[0]

    # Strip citation links, figures, tables and formulae up front, PRESERVING tail
    # text (the prose that follows an inline <a> citation) so it isn't lost.
    for junk in view.xpath(_STRIP_XPATH):
        parent = junk.getparent()
        if parent is None:
            continue
        tail = junk.tail
        if tail:
            prev = junk.getprevious()
            if prev is not None:
                prev.tail = (prev.tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail
        parent.remove(junk)

    counter = [0]
    for sec in view.xpath('./div[contains(@class,"section")]'):
        _walk_section(sec, art, counter, inherited=None)

    # Abstract: prefer the dedicated section; fall back to the citation meta tag.
    for s in list(art.sections):
        if s.title and s.title.strip().lower() == "abstract":
            art.abstract = s.text
            art.sections.remove(s)
            break
    if art.abstract is None:
        art.abstract = meta("citation_abstract")
    # Re-number remaining body sections from 1 (abstract is added at assembly).
    for i, s in enumerate(art.sections, start=1):
        s.order = i
    return art


def _walk_section(sec_el, art: ParsedArticle, counter, inherited) -> None:
    cls = sec_el.get("class") or ""
    if any(skip in cls for skip in _SKIP_SECTION_CLASSES):
        return
    heading = sec_el.xpath("./h2 | ./h3 | ./h4 | ./h5")
    title = _norm(heading[0].text_content()) if heading else None
    kind = _classify(None, title, inherited)

    text = _direct_prose(sec_el)
    if text or title:
        counter[0] += 1
        art.sections.append(ParsedSection(order=counter[0], kind=kind, title=title, text=text))

    for child in sec_el.xpath('./div[contains(@class,"subsection") or contains(@class,"section")]'):
        _walk_section(child, art, counter, inherited=kind)


class BiorxivHTML:
    name = "biorxiv_html"

    def __init__(self, settings: Settings | None = None, client=None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.settings)
        return self._client

    def _host(self, server: Server) -> str:
        return "www.medrxiv.org" if server is Server.MEDRXIV else "www.biorxiv.org"

    def get_fulltext(
        self, doi: str, version: int | None = None, server: Server | str | None = None
    ) -> FullText | None:
        srv = Server(server) if server else Server.BIORXIV
        host = self._host(srv)
        # version given -> that exact version; otherwise the un-versioned URL, which the
        # site redirects to the LATEST version (openRxiv DOI semantics).
        url = (
            f"https://{host}/content/{doi}v{version}.full"
            if version is not None
            else f"https://{host}/content/{doi}.full"
        )
        resp = request_with_retry(self.client, "GET", url, follow_redirects=True)
        if resp.status_code != 200:
            return None
        parsed = parse_biorxiv_html(resp.content)
        if not parsed.sections and not parsed.abstract:
            return None
        # Record the version actually served (parsed from the final, possibly-redirected URL).
        final_url = str(resp.url)
        m = re.search(r"/content/[^\s]*?v(\d+)", final_url)
        fetched_version = version if version is not None else (int(m.group(1)) if m else None)
        provenance = {"source": "biorxiv_html", "url": final_url, "version": fetched_version}
        # Best-effort license/metadata enrichment from the JSON API (gate needs license).
        try:
            from .biorxiv_api import BiorxivAPI

            meta = BiorxivAPI(self.settings).get_metadata(parsed.doi or doi, server=srv)
        except Exception:
            meta = None
        if meta is not None and meta.license is not None and not parsed.license_raw:
            parsed.license_raw = {"href": None, "text": meta.license.raw}
        return build_fulltext(
            parsed,
            doi=parsed.doi or doi,
            server=srv,
            source=SourceName.BIORXIV_HTML,
            version=fetched_version,
            raw_ref=final_url,
            date=(meta.date if meta else None),
            category=(meta.category if meta else None),
            published_doi=(meta.published_doi if meta else None),
            provenance=provenance,
        )


__all__ = ["BiorxivHTML", "parse_biorxiv_html"]
