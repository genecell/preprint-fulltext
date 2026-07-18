"""arxiv_html.py — arXiv full text via LaTeXML HTML (native arXiv HTML → ar5iv fallback).

arXiv has no JATS; it renders LaTeX to HTML with LaTeXML (``ltx_*`` classes). Both the
native ``arxiv.org/html/<id>`` pages (2023+) and ``ar5iv`` (historical) use the same
LaTeXML structure, so one parser serves both. It emits a :class:`ParsedArticle` — the same
shape the JATS parser produces — so ``assemble``/``chunk``/the compliance gate are shared.

Single-document only (interactive full text), like the bioRxiv HTML source; arXiv bulk
belongs on arXiv's own S3 LaTeX-source channel, not HTML scraping.
"""

from __future__ import annotations

import re

from lxml import html as lxml_html

from ..config import Settings, get_settings
from ..core.assemble import build_fulltext
from ..core.http import build_client, request_with_retry
from ..core.ids import arxiv_doi, normalize_arxiv_id
from ..core.jats import ParsedArticle, ParsedSection, _classify, _norm
from ..core.models import FullText, Server, SourceName

# Section-number prefix in LaTeXML headings, e.g. "3.1 Methods".
_SEC_NUM = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)\s+")
# Subtrees whose text wrecks embedding signal (mirror the JATS strip policy).
_STRIP_XPATH = (
    ".//math | .//cite "
    "| .//*[contains(@class,'ltx_figure') or contains(@class,'ltx_table') "
    "or contains(@class,'ltx_tabular') or contains(@class,'ltx_Math') "
    "or contains(@class,'ltx_equation') or contains(@class,'ltx_bibliography') "
    "or contains(@class,'ltx_tag_section') or contains(@class,'ltx_tag_subsection')]"
)


def _heading(sec_el) -> str | None:
    for h in sec_el.xpath("./h1 | ./h2 | ./h3 | ./h4 | ./h5 | ./h6"):
        if "ltx_title" in (h.get("class") or ""):
            return _SEC_NUM.sub("", _norm(h.text_content()))
    return None


def _direct_paras(sec_el) -> str:
    """Text of ltx_p paragraphs belonging directly to this section (not nested sections)."""
    parts: list[str] = []

    def walk(node):
        for child in node:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag == "section":
                continue  # nested section -> its own ParsedSection
            cls = child.get("class") or ""
            if tag == "p" and "ltx_p" in cls:
                parts.append(_norm(child.text_content()))
            else:
                walk(child)

    walk(sec_el)
    return _norm(" ".join(p for p in parts if p))


def _strip_junk(root) -> None:
    for junk in root.xpath(_STRIP_XPATH):
        parent = junk.getparent()
        if parent is None:
            continue
        tail = junk.tail
        if tail:  # keep prose that follows an inline citation/math
            prev = junk.getprevious()
            if prev is not None:
                prev.tail = (prev.tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail
        parent.remove(junk)


def parse_latexml_html(html_bytes: bytes) -> ParsedArticle:
    """Parse a LaTeXML HTML page (native arXiv HTML or ar5iv) into a :class:`ParsedArticle`."""
    art = ParsedArticle()
    try:
        root = lxml_html.fromstring(html_bytes)
    except Exception:
        return art

    title = root.xpath('//h1[contains(@class,"ltx_title_document")]')
    if title:
        art.title = _norm(title[0].text_content())
    art.authors = [
        _norm(a.text_content())
        for a in root.xpath('//*[contains(@class,"ltx_personname")]')
        if _norm(a.text_content())
    ][:200]

    _strip_junk(root)

    abstract = root.xpath('//*[contains(@class,"ltx_abstract")]')
    if abstract:
        paras = [_norm(p.text_content()) for p in abstract[0].xpath('.//p[contains(@class,"ltx_p")]')]
        art.abstract = _norm(" ".join(p for p in paras if p)) or None

    counter = [0]
    for sec in root.xpath('//section[contains(@class,"ltx_section")]'):
        _walk_section(sec, art, counter, inherited=None)
    for i, s in enumerate(art.sections, start=1):
        s.order = i
    return art


def _walk_section(sec_el, art: ParsedArticle, counter, inherited) -> None:
    if "ltx_bibliography" in (sec_el.get("class") or ""):
        return
    title = _heading(sec_el)
    kind = _classify(None, title, inherited)
    text = _direct_paras(sec_el)
    if text or title:
        counter[0] += 1
        art.sections.append(ParsedSection(order=counter[0], kind=kind, title=title, text=text))
    for child in sec_el:
        if isinstance(child.tag, str) and child.tag == "section":
            _walk_section(child, art, counter, inherited=kind)


class ArxivHTML:
    name = "arxiv_html"

    def __init__(self, settings: Settings | None = None, client=None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.settings)
        return self._client

    def _fetch(self, url: str):
        resp = request_with_retry(self.client, "GET", url, follow_redirects=True)
        if resp.status_code != 200:
            return None
        parsed = parse_latexml_html(resp.content)
        if not parsed.sections and not parsed.abstract:
            return None
        return resp, parsed

    def _license_raw(self, arxiv_id: str) -> dict | None:
        """Best-effort: scan the arXiv abs page for a Creative Commons license link."""
        try:
            resp = request_with_retry(
                self.client, "GET", f"https://arxiv.org/abs/{arxiv_id}", follow_redirects=True
            )
            if resp.status_code == 200:
                m = re.search(rb"creativecommons\.org/(licenses|publicdomain)/[a-z0-9./-]+",
                              resp.content)
                if m:
                    return {"href": "https://" + m.group(0).decode("ascii"), "text": None}
        except Exception:
            pass
        return None

    def get_fulltext(
        self, arxiv_id: str, version: int | None = None, server: Server | str | None = None
    ) -> FullText | None:
        aid = normalize_arxiv_id(arxiv_id) or arxiv_id
        native = f"{self.settings.arxiv_html_base}/{aid}" + (f"v{version}" if version else "")
        got = self._fetch(native)
        backend = "native"
        if got is None:  # fall back to ar5iv (LaTeXML for historical papers)
            got = self._fetch(f"{self.settings.ar5iv_base}/{aid}")
            backend = "ar5iv"
        if got is None:
            return None
        resp, parsed = got
        final_url = str(resp.url)

        # Enrich license + metadata best-effort (arXiv HTML lacks license/date reliably).
        parsed.license_raw = parsed.license_raw or self._license_raw(aid)
        meta = None
        try:
            from .arxiv import ArxivAPI

            meta = ArxivAPI(self.settings).get_metadata(aid, version=version)
        except Exception:
            meta = None
        if meta is not None and not parsed.authors:
            parsed.authors = meta.authors

        return build_fulltext(
            parsed,
            doi=arxiv_doi(aid),
            server=Server.ARXIV,
            source=SourceName.ARXIV_HTML,
            version=version if version is not None else (meta.version if meta else None),
            raw_ref=final_url,
            date=(meta.date if meta else None),
            category=(meta.category if meta else None),
            published_doi=(meta.published_doi if meta else None),
            provenance={"source": "arxiv_html", "arxiv_id": aid, "url": final_url, "backend": backend},
        )


__all__ = ["ArxivHTML", "parse_latexml_html"]
