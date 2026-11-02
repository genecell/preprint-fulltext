"""Shared test helpers for text-extraction fidelity tests (pf-text/2)."""

from __future__ import annotations

import re

from preprint_fulltext.core.assemble import build_fulltext
from preprint_fulltext.core.jats import parse_jats
from preprint_fulltext.core.render import TextOptions
from preprint_fulltext.sources.biorxiv_html import parse_biorxiv_html

EMPTY_BRACKETS = re.compile(r"\(\s*[,;–\-\s]*\)|\[\s*[,;–\-\s]*\]")


def html_page(sections_html: str, *, meta_charset: bool = True) -> bytes:
    head = (
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />'
        if meta_charset
        else ""
    )
    return (
        "<html><head>"
        + head
        + '<meta name="citation_title" content="T">'
        '<meta name="citation_doi" content="10.1101/2099.01.01.000001"></head><body>'
        '<div class="article fulltext-view ">'
        + sections_html
        + "</div></body></html>"
    ).encode("utf-8")


def jats_doc(body: str, back: str = "", abstract: str = "") -> bytes:
    return (
        '<article xmlns:xlink="http://www.w3.org/1999/xlink" '
        'xmlns:mml="http://www.w3.org/1998/Math/MathML">'
        "<front><article-meta><title-group><article-title>T</article-title></title-group>"
        + abstract
        + "</article-meta></front><body>"
        + body
        + "</body>"
        + (f"<back>{back}</back>" if back else "")
        + "</article>"
    ).encode("utf-8")


def html(sections_html: str, **kw):
    return parse_biorxiv_html(html_page(sections_html), **kw)


def jats(body: str, back: str = "", abstract: str = "", **kw):
    return parse_jats(jats_doc(body, back, abstract), **kw)


def section(art, title: str):
    return next(s for s in art.sections if s.title == title)


def text_of(art, title: str) -> str:
    return section(art, title).text


def fulltext(art, source: str = "biorxiv_html"):
    return build_fulltext(art, doi="10.1101/2099.01.01.000001", server="biorxiv", source=source)


__all__ = [
    "EMPTY_BRACKETS",
    "TextOptions",
    "html_page",
    "jats_doc",
    "html",
    "jats",
    "section",
    "text_of",
    "fulltext",
]
