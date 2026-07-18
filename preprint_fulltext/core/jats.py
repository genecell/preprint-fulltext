"""jats.py — the ONE shared JATS parser (correctness-critical).

Serves both the Europe PMC path (``fullTextXML``) and the S3 path (the JATS XML
inside each ``.meca``'s ``content/`` folder), because both return JATS. Ported
from a reference implementation; kept pydantic-free and dependency-light (only
``lxml``) so it stays identical for both paths and is trivially testable. The
mapping into the canonical model happens in :mod:`preprint_fulltext.core.assemble`.

Design notes (the non-obvious, correctness-critical bits):
  * JATS main elements are NOT namespaced; only attributes like ``xlink:href`` are.
    So element lookups use plain local tags; only attribute reads use the xlink NS.
  * We parse defensively (``recover=True``, no network, no DTD load) — bioRxiv JATS
    drifts across versions and some payloads are slightly malformed. Never crash;
    on failure return whatever partial structure we have.
  * Each ``<sec>`` (including nested) becomes ONE ``ParsedSection`` holding only its
    *direct* paragraph-level text — descendant ``<sec>`` content is emitted as its
    own section, so text is never duplicated. ``order`` follows document order.
  * ``kind`` comes from ``@sec-type`` first, then the ``<title>`` text, then inherited
    from the nearest ancestor with a known kind, else ``"other"``. Kind strings match
    :class:`preprint_fulltext.core.models.SectionKind` values exactly.
  * Reference lists live in ``<back>`` and are simply never walked. Figures, tables,
    xrefs and formulae are stripped from prose by default (they wreck embedding
    signal); ``keep_tables=True`` retains table text.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field

from lxml import etree

XLINK = "http://www.w3.org/1999/xlink"

# Elements whose textual content we drop from section/abstract prose by default.
_STRIP_TAGS = {
    "xref", "fig", "fig-group", "disp-formula", "inline-formula",
    "graphic", "media", "supplementary-material", "label",
}
_STRIP_TABLES = {"table-wrap", "table-wrap-group", "table", "array"}

# Substring rules mapping @sec-type / title text -> canonical kind. First match wins.
# The right-hand values MUST match SectionKind string values.
_KIND_RULES = [
    ("intro", "intro"),
    ("background", "intro"),
    ("method", "methods"),
    ("material", "methods"),
    ("procedure", "methods"),
    ("result", "results"),
    ("finding", "results"),
    ("discussion", "discussion"),
    ("conclusion", "discussion"),
]

_WS = re.compile(r"\s+")
# After stripping inline citation markers ("[1]"), prose is often left with a
# space before punctuation ("review , creating"). Tidy the common cases.
_DESPACE = re.compile(r"\s+([,.;:)\]!?])")
_OPENSPACE = re.compile(r"([(\[])\s+")


@dataclass
class ParsedSection:
    """One <sec>'s direct prose. Pydantic-free; mapped to models.Section at assembly."""

    order: int
    kind: str  # intro | methods | results | discussion | other  (never 'abstract' here)
    title: str | None
    text: str


@dataclass
class ParsedArticle:
    """Everything the parser can pull from a JATS document, dependency-light."""

    title: str | None = None
    doi: str | None = None
    authors: list[str] = field(default_factory=list)
    abstract: str | None = None
    license_raw: dict | None = None  # {"href": ..., "text": ...} -> licenses.parse_license
    sections: list[ParsedSection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _norm(text: str | None) -> str:
    s = _WS.sub(" ", (text or "")).strip()
    s = _DESPACE.sub(r"\1", s)
    s = _OPENSPACE.sub(r"\1", s)
    return s


def _local(tag) -> str:
    try:
        return etree.QName(tag).localname
    except ValueError:
        return ""


def _deepcopy_stripped(elem: etree._Element, keep_tables: bool) -> etree._Element:
    clone = deepcopy(elem)
    strip = set(_STRIP_TAGS) if keep_tables else set(_STRIP_TAGS) | _STRIP_TABLES
    # etree.strip_elements would remove the elements AND their tail text; we want
    # to keep tail text (surrounding prose), so remove nodes manually.
    for node in clone.iter():
        for child in list(node):
            if _local(child.tag) in strip:
                tail = child.tail
                node.remove(child)
                if tail:  # preserve tail so adjacent prose isn't glued together
                    prev = child.getprevious()
                    if prev is not None:
                        prev.tail = (prev.tail or "") + tail
                    else:
                        node.text = (node.text or "") + tail
    return clone


def _clean_text(elem: etree._Element, keep_tables: bool) -> str:
    """Text of `elem` with unwanted subtrees removed. Operates on a copy."""
    clone = _deepcopy_stripped(elem, keep_tables)
    return _norm("".join(clone.itertext()))


def _classify(sec_type: str | None, title: str | None, inherited: str | None) -> str:
    hay = f"{sec_type or ''} {title or ''}".lower()
    for needle, kind in _KIND_RULES:
        if needle in hay:
            return kind
    return inherited or "other"


def _direct_prose(sec: etree._Element, keep_tables: bool) -> str:
    """Concatenate direct paragraph-level children of a <sec>, excluding nested
    <sec> (those become their own section) and reference material."""
    parts: list[str] = []
    for child in sec:
        name = _local(child.tag)
        if name == "sec":
            continue  # handled as its own section
        if name in ("p", "list", "disp-quote", "statement", "boxed-text"):
            parts.append(_clean_text(child, keep_tables))
        elif name == "table-wrap" and keep_tables:
            parts.append(_clean_text(child, keep_tables))
    return _norm(" ".join(p for p in parts if p))


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def parse_jats(xml: bytes | str, *, keep_tables: bool = False) -> ParsedArticle:
    """Parse JATS XML into a :class:`ParsedArticle`. Never raises on malformed input."""
    if isinstance(xml, str):
        xml = xml.encode("utf-8")

    parser = etree.XMLParser(
        recover=True, resolve_entities=False, load_dtd=False, no_network=True,
        huge_tree=True,
    )
    try:
        root = etree.fromstring(xml, parser=parser)
    except etree.XMLSyntaxError:
        return ParsedArticle()
    if root is None:
        return ParsedArticle()

    art = ParsedArticle()
    meta = root.find(".//article-meta")

    t = root.find(".//article-meta/title-group/article-title")
    if t is not None:
        art.title = _norm("".join(t.itertext()))

    doi_el = root.find(".//article-meta/article-id[@pub-id-type='doi']")
    if doi_el is not None and doi_el.text:
        art.doi = doi_el.text.strip()

    if meta is not None:
        for name in meta.iterfind(".//contrib[@contrib-type='author']/name"):
            surname = name.findtext("surname")
            given = name.findtext("given-names")
            full = _norm(" ".join(x for x in (given, surname) if x))
            if full:
                art.authors.append(full)

    # abstract (skip graphical/teaser variants that carry an abstract-type)
    for ab in root.iterfind(".//article-meta/abstract"):
        if ab.get("abstract-type"):
            continue
        art.abstract = _clean_text(ab, keep_tables)
        break

    # license -> raw dict for licenses.parse_license
    lic = root.find(".//article-meta/permissions/license")
    if lic is not None:
        art.license_raw = {
            "href": lic.get(f"{{{XLINK}}}href"),
            "text": _norm("".join(lic.itertext())) or None,
        }

    # body sections (document order, nested flattened)
    body = root.find(".//body")
    if body is not None:
        counter = [0]
        for sec in body.findall("sec"):
            _walk_sec(sec, art.sections, counter, inherited=None, keep_tables=keep_tables)

    return art


def _walk_sec(sec, out: list[ParsedSection], counter, inherited, keep_tables) -> None:
    title_el = sec.find("title")
    title = _norm("".join(title_el.itertext())) if title_el is not None else None
    kind = _classify(sec.get("sec-type"), title, inherited)

    text = _direct_prose(sec, keep_tables)
    if text or title:
        counter[0] += 1
        out.append(ParsedSection(order=counter[0], kind=kind, title=title, text=text))

    for child in sec.findall("sec"):
        _walk_sec(child, out, counter, inherited=kind, keep_tables=keep_tables)


__all__ = ["ParsedArticle", "ParsedSection", "parse_jats"]


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "jats_biorxiv_sample.xml"
    with open(path, "rb") as fh:
        print(json.dumps(parse_jats(fh.read()).to_dict(), indent=2, ensure_ascii=False))
