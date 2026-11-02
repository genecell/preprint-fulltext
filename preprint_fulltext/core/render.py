"""Shared inline and block renderer for JATS XML and bioRxiv HTML (pf-text/2).

Replaces the 0.1.0 "strip subtrees, then text_content()/itertext()" pattern with a
single-pass tree walker that:
  * Never mutates the input lxml tree (eliminating the D7 tail-reordering bug class).
  * Renders links inline ("visible (URL)" unless visible text is already the URL).
  * Drops citation groups cleanly (without leaving empty brackets) while keeping
    narrative "Author (Year)" citations.
  * Preserves cross-reference prose ("Figure 1e", "Table 1", "Section 1.4").
  * Formats superscripts with caret ("10^6") or Unicode ("10⁶") so exponents never
    merge into adjacent digits ("106").
  * Emits placeholders or linearised MathML/TeX for inline and display formulas.
  * Records side-channel items (links, citations, xrefs, formulas, figures, tables)
    with exact character offsets into the final normalised section text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urljoin

from lxml import etree

XLINK = "http://www.w3.org/1999/xlink"
TEXT_FORMAT = "pf-text/2"


@dataclass(frozen=True)
class TextOptions:
    links: Literal["inline", "text"] = "inline"
    citations: Literal["drop", "keep"] = "drop"
    scripts: Literal["caret", "unicode"] = "caret"
    subscripts: Literal["flat", "underscore"] = "flat"
    math: Literal["text", "tex", "placeholder"] = "text"
    paragraph_sep: str = " "
    legends_as_section: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "links": self.links,
            "citations": self.citations,
            "scripts": self.scripts,
            "subscripts": self.subscripts,
            "math": self.math,
            "paragraph_sep": self.paragraph_sep,
            "legends_as_section": self.legends_as_section,
        }


# --------------------------------------------------------------------------- #
# Pydantic-free intermediate records attached to ParsedArticle
# --------------------------------------------------------------------------- #
@dataclass
class ParsedFigure:
    id: str | None = None
    label: str | None = None
    title: str | None = None
    caption: str = ""
    section_order: int | None = None
    image_url: str | None = None


@dataclass
class ParsedTable:
    id: str | None = None
    label: str | None = None
    caption: str = ""
    section_order: int | None = None
    status: str = "parsed"
    header_rows: int = 0
    rows: list[list[str]] | None = None
    markdown: str | None = None
    footnotes: list[str] = field(default_factory=list)
    source_url: str | None = None
    image_url: str | None = None


@dataclass
class ParsedLink:
    section_order: int
    start: int
    end: int
    text: str
    url: str


@dataclass
class ParsedCitation:
    section_order: int
    start: int
    end: int
    text: str
    ref_ids: list[str] = field(default_factory=list)
    removed: bool = False


@dataclass
class ParsedXref:
    section_order: int
    start: int
    end: int
    text: str
    target: str | None = None
    type: str | None = None


@dataclass
class ParsedFormula:
    id: str | None = None
    section_order: int = 0
    start: int = 0
    end: int = 0
    display: bool = False
    label: str | None = None
    tex: str | None = None
    mathml: str | None = None
    text: str | None = None
    image_url: str | None = None


# --------------------------------------------------------------------------- #
# Section kind & role classification (§5.7)
# --------------------------------------------------------------------------- #
_NUM_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|[A-Za-z]\.|[IVXLC]+\.)\s+")

_KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("intro", re.compile(r"^(introduction|background|main)\b")),
    (
        "methods",
        re.compile(
            r"^((materials?|methods?|methodology)( and (materials?|methods?))?"
            r"|online methods|star\W*methods|experimental (procedures|section|methods)"
            r"|method details)\b"
        ),
    ),
    ("results", re.compile(r"^results?\b")),
    ("discussion", re.compile(r"^(discussion|conclusions?|concluding remarks)\b")),
]

_ROLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("acknowledgements", re.compile(r"^acknowledg")),
    ("author_contributions", re.compile(r"author contributions?")),
    ("competing_interests", re.compile(r"competing interests?|conflicts? of interest|declaration of interests?")),
    ("funding", re.compile(r"^(funding|financial support|funder information)")),
    ("ethics", re.compile(r"^ethics")),
    ("supplementary", re.compile(r"^(supplementary|supporting information|extended data)")),
    ("appendix", re.compile(r"^appendi(x|ces)\b")),
    ("footnotes", re.compile(r"^footnotes$")),
    ("abbreviations", re.compile(r"^(abbreviations|glossary)$")),
    ("figure_legends", re.compile(r"^figure legends$")),
    ("tables", re.compile(r"^tables$")),
]

_SEC_TYPE_KIND: list[tuple[str, str]] = [
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

_SEC_TYPE_ROLE: list[tuple[str, str]] = [
    ("data-availability", "data_availability"),
    ("data_availability", "data_availability"),
    ("code-availability", "code_availability"),
    ("code_availability", "code_availability"),
    ("availability", "data_availability"),
    ("ack", "acknowledgements"),
    ("author-contributions", "author_contributions"),
    ("competing-interest", "competing_interests"),
    ("conflict", "competing_interests"),
    ("funding", "funding"),
    ("financial-disclosure", "funding"),
    ("ethics", "ethics"),
    ("supplementary", "supplementary"),
    ("appendix", "appendix"),
    ("footnote", "footnotes"),
    ("glossary", "abbreviations"),
    ("abbreviations", "abbreviations"),
]


def _role_from_title(norm_title: str) -> str | None:
    if not norm_title:
        return None
    if "availability" in norm_title:
        if "code" in norm_title and "data" not in norm_title:
            return "code_availability"
        return "data_availability"
    for role, pat in _ROLE_PATTERNS:
        if pat.search(norm_title):
            return role
    return None


def _role_from_sec_type(sec_type: str | None) -> str | None:
    if not sec_type:
        return None
    st = sec_type.strip().lower()
    for needle, role in _SEC_TYPE_ROLE:
        if needle in st:
            return role
    return None


def _kind_from_sec_type(sec_type: str | None) -> str | None:
    if not sec_type:
        return None
    st = sec_type.strip().lower()
    for needle, kind in _SEC_TYPE_KIND:
        if needle in st:
            return kind
    return None


def classify_section(
    title: str | None,
    sec_type: str | None,
    parent_kind: str | None = None,
    parent_role: str | None = None,
) -> tuple[str, str | None]:
    """Return ``(kind, role)`` for a section given its title, ``@sec-type`` and parent."""
    norm_title = _NUM_PREFIX.sub("", (title or "")).strip().lower()
    role = _role_from_title(norm_title) or _role_from_sec_type(sec_type) or parent_role
    if role:
        return "other", role
    if sec_type and (k := _kind_from_sec_type(sec_type)):
        return k, None
    if parent_kind not in (None, "other"):
        return parent_kind, None
    for kind, pat in _KIND_PATTERNS:
        if pat.search(norm_title):
            return kind, None
    return "other", None


# --------------------------------------------------------------------------- #
# Superscripts, subscripts, links, MathML linearisation (§5.4 - §5.6)
# --------------------------------------------------------------------------- #
ORDINAL_RE = re.compile(r"^(st|nd|rd|th)$", re.IGNORECASE)
FLAT_SYMBOLS = set("°◦º′″'*†‡§¶®™")
SIMPLE_SCRIPT_RE = re.compile(r"^[+\-−–]?[0-9A-Za-zα-ωΑ-Ω.]+[+\-−]?$")

SUPERSCRIPT_MAP: dict[str, str] = {
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
    "+": "⁺",
    "-": "⁻",
    "−": "⁻",
    "–": "⁻",
    "=": "⁼",
    "(": "⁽",
    ")": "⁾",
    "n": "ⁿ",
    "i": "ⁱ",
}


def render_sup(inner: str, prev_char: str, mode: str) -> str:
    s = inner.strip()
    if not s:
        return ""
    if (ORDINAL_RE.match(s) and prev_char.isdigit()) or all(c in FLAT_SYMBOLS for c in s):
        return s
    if mode == "unicode" and all(c in SUPERSCRIPT_MAP for c in s):
        return "".join(SUPERSCRIPT_MAP[c] for c in s)
    return "^" + s if SIMPLE_SCRIPT_RE.match(s) else f"^({s})"


def render_sub(inner: str, mode: str) -> str:
    s = inner.strip()
    if not s:
        return ""
    if mode == "underscore":
        return "_" + s if SIMPLE_SCRIPT_RE.match(s) else f"_({s})"
    return s


def render_link(visible: str, href: str, mode: str) -> str:
    v = visible.strip()
    h = href.strip()
    if not v:
        return h
    if mode == "text" or h.rstrip("/") == v.rstrip("/") or h == "mailto:" + v:
        return v
    return f"{v} ({h})"


def _local(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    try:
        return etree.QName(tag).localname
    except ValueError:
        return tag.split("}")[-1] if "}" in tag else tag


def linearize_mathml(elem: etree._Element) -> str:
    """Linearise a MathML subtree into compact plain text."""
    name = _local(elem.tag)
    children = [c for c in elem if isinstance(c.tag, str)]

    if name in ("mi", "mn", "mo", "mtext", "ms"):
        return "".join(elem.itertext()).strip()
    if name == "msub" and len(children) >= 2:
        b = linearize_mathml(children[0])
        sub = linearize_mathml(children[1])
        sub_s = sub if SIMPLE_SCRIPT_RE.match(sub) else f"({sub})"
        return f"{b}_{sub_s}"
    if name == "msup" and len(children) >= 2:
        b = linearize_mathml(children[0])
        sup = linearize_mathml(children[1])
        sup_s = sup if SIMPLE_SCRIPT_RE.match(sup) else f"({sup})"
        return f"{b}^{sup_s}"
    if name == "msubsup" and len(children) >= 3:
        b = linearize_mathml(children[0])
        sub = linearize_mathml(children[1])
        sup = linearize_mathml(children[2])
        sub_s = sub if SIMPLE_SCRIPT_RE.match(sub) else f"({sub})"
        sup_s = sup if SIMPLE_SCRIPT_RE.match(sup) else f"({sup})"
        return f"{b}_{sub_s}^{sup_s}"
    if name == "mfrac" and len(children) >= 2:
        num = linearize_mathml(children[0])
        den = linearize_mathml(children[1])
        num_s = num if len(num) == 1 or num.isalnum() else f"({num})"
        den_s = den if len(den) == 1 or den.isalnum() else f"({den})"
        return f"{num_s}/{den_s}"
    if name == "msqrt":
        inner = "".join(linearize_mathml(c) for c in children)
        return f"√({inner})"
    if name in ("mover", "munder") and len(children) >= 1:
        return linearize_mathml(children[0])
    if name == "mfenced":
        open_b = elem.get("open", "(")
        close_b = elem.get("close", ")")
        sep = elem.get("separators", ",")
        inner = (sep + " ").join(linearize_mathml(c) for c in children)
        return f"{open_b}{inner}{close_b}"
    if name in ("annotation", "annotation-xml"):
        return ""
    return "".join(linearize_mathml(c) for c in children)


# --------------------------------------------------------------------------- #
# Citation & Sentinel Resolution Engine
# --------------------------------------------------------------------------- #
_WS_RE = re.compile(r"[ \t\r\n\xa0\u2009\u202f]+")
_NARRATIVE_YEAR_RE = re.compile(r"\(\s*\d{4}[a-z]?\s*\)\s*$")
_SUP_SEP_ONLY_RE = re.compile(r"^[\s,;–\-−]*(?:(?:and|&)[\s,;–\-−]*)*$")


@dataclass
class _RawCit:
    text: str
    ref_ids: list[str]
    is_narrative: bool
    is_sup_group: bool = False


class SectionAccumulator:
    """Collects paragraphs and inline side-channel records for one section."""

    def __init__(self, section_order: int, options: TextOptions):
        self.section_order = section_order
        self.options = options
        self._raw_cits: list[_RawCit] = []
        self._final_cits: list[tuple[str, list[str], bool]] = []  # (text, ref_ids, removed)
        self._links: list[tuple[str, str]] = []  # (visible_text, url)
        self._xrefs: list[tuple[str, str | None, str | None]] = []  # (text, target, type)
        self._formulas: list[ParsedFormula] = []
        self.paragraphs: list[str] = []

    def add_cit_sentinel(self, text: str, ref_ids: list[str], *, is_sup_group: bool = False) -> str:
        clean_t = _WS_RE.sub(" ", text).strip()
        is_narrative = (not is_sup_group) and bool(_NARRATIVE_YEAR_RE.search(clean_t))
        idx = len(self._raw_cits)
        self._raw_cits.append(
            _RawCit(text=clean_t, ref_ids=[r for r in ref_ids if r], is_narrative=is_narrative, is_sup_group=is_sup_group)
        )
        prefix = "G" if is_sup_group else "N" if is_narrative else "S"
        return f"\ue000{prefix}{idx}\ue001"

    def add_link_sentinel(self, visible: str, url: str) -> str:
        vis = _WS_RE.sub(" ", visible).strip()
        u = url.strip()
        rendered = render_link(vis, u, self.options.links)
        idx = len(self._links)
        self._links.append((vis or u, u))
        return f"\ue002L{idx}\ue003{rendered}\ue004"

    def add_xref_sentinel(self, text: str, target: str | None, xtype: str | None) -> str:
        t = _WS_RE.sub(" ", text).strip()
        if not t:
            return ""
        idx = len(self._xrefs)
        self._xrefs.append((t, target, xtype))
        return f"\ue002X{idx}\ue003{t}\ue004"

    def add_formula_sentinel(
        self,
        rendered: str,
        *,
        fid: str | None = None,
        display: bool = False,
        label: str | None = None,
        tex: str | None = None,
        mathml: str | None = None,
        linear_text: str | None = None,
        image_url: str | None = None,
    ) -> str:
        idx = len(self._formulas)
        self._formulas.append(
            ParsedFormula(
                id=fid,
                section_order=self.section_order,
                display=display,
                label=label,
                tex=tex,
                mathml=mathml,
                text=linear_text,
                image_url=image_url,
            )
        )
        return f"\ue002F{idx}\ue003{rendered}\ue004"

    def _register_final_cit(self, text: str, ref_ids: list[str], removed: bool, rendered: str) -> str:
        idx = len(self._final_cits)
        self._final_cits.append((text, ref_ids, removed))
        return f"\ue002C{idx}\ue003{rendered}\ue004"

    def resolve_paragraph(self, raw_para: str) -> str:
        """Resolve citation sentinels in a single paragraph and normalise whitespace."""
        if not raw_para:
            return ""
        s = _WS_RE.sub(" ", raw_para)
        drop = self.options.citations == "drop"

        # Pattern for a single removable non-superscript citation sentinel: \ue000S\d+\ue001
        s_tok = r"\ue000S\d+\ue001"
        sep_tok = r"(?:\s*(?:[,;–\-−]|and|&)\s*)"
        s_run_re = re.compile(f"{s_tok}(?:{sep_tok}{s_tok})*")

        def _extract_run_info(fragment: str) -> tuple[str, list[str]]:
            ref_ids: list[str] = []

            def _sub_one(m: re.Match[str]) -> str:
                rc = self._raw_cits[int(m.group(1))]
                ref_ids.extend(rc.ref_ids)
                return rc.text

            txt = re.sub(r"\ue000[SNG](\d+)\ue001", _sub_one, fragment)
            txt = _WS_RE.sub(" ", txt).strip()
            return txt, ref_ids

        # 1. Bracketed citation-only groups: (S; S) or [S-S]
        paren_group_re = re.compile(
            rf"\(\s*{s_tok}(?:{sep_tok}{s_tok})*\s*\)|\[\s*{s_tok}(?:{sep_tok}{s_tok})*\s*\]"
        )

        def _replace_bracket_group(m: re.Match[str]) -> str:
            full_frag = m.group(0)
            txt, ref_ids = _extract_run_info(full_frag)
            # Clean spaces just inside brackets in source_text
            txt = re.sub(r"^([(\[])\s+", r"\1", txt)
            txt = re.sub(r"\s+([)\]])$", r"\1", txt)
            if drop:
                return self._register_final_cit(txt, ref_ids, True, "")
            return self._register_final_cit(txt, ref_ids, False, txt)

        s = paren_group_re.sub(_replace_bracket_group, s)

        # 2. Trailing citation run at the right edge of a mixed parenthetical: (Fig. 1; Smith, 2020)
        right_edge_re = re.compile(rf"(\s*[,;]\s*)({s_tok}(?:{sep_tok}{s_tok})*)(?=\s*[)\]])")

        def _replace_right_edge(m: re.Match[str]) -> str:
            sep_str, run_frag = m.group(1), m.group(2)
            txt, ref_ids = _extract_run_info(run_frag)
            if drop:
                return self._register_final_cit(txt, ref_ids, True, "")
            return sep_str + self._register_final_cit(txt, ref_ids, False, txt)

        s = right_edge_re.sub(_replace_right_edge, s)

        # 3. Leading citation run at the left edge of a mixed parenthetical: (Smith, 2020; Fig. 1)
        left_edge_re = re.compile(rf"(?<=[(\[])(\s*)({s_tok}(?:{sep_tok}{s_tok})*)(\s*[,;]\s*)")

        def _replace_left_edge(m: re.Match[str]) -> str:
            lead_ws, run_frag, trail_sep = m.group(1), m.group(2), m.group(3)
            txt, ref_ids = _extract_run_info(run_frag)
            if drop:
                return self._register_final_cit(txt, ref_ids, True, "")
            return lead_ws + self._register_final_cit(txt, ref_ids, False, txt) + trail_sep

        s = left_edge_re.sub(_replace_left_edge, s)

        # 4. Superscript citation groups: \ue000G\d+\ue001
        sup_group_re = re.compile(r"\ue000G(\d+)\ue001")

        def _replace_sup_group(m: re.Match[str]) -> str:
            rc = self._raw_cits[int(m.group(1))]
            if drop:
                return self._register_final_cit(rc.text, rc.ref_ids, True, "")
            bracketed = f"[{rc.text}]"
            return " " + self._register_final_cit(bracketed, rc.ref_ids, False, bracketed)

        s = sup_group_re.sub(_replace_sup_group, s)

        # 5. Any remaining removable S runs (e.g. bare unbracketed citations)
        def _replace_bare_s_run(m: re.Match[str]) -> str:
            run_frag = m.group(0)
            txt, ref_ids = _extract_run_info(run_frag)
            if drop:
                return self._register_final_cit(txt, ref_ids, True, "")
            return self._register_final_cit(txt, ref_ids, False, txt)

        s = s_run_re.sub(_replace_bare_s_run, s)

        # 6. Narrative citations (\ue000N\d+\ue001) — always kept
        nav_re = re.compile(r"\ue000N(\d+)\ue001")

        def _replace_narrative(m: re.Match[str]) -> str:
            rc = self._raw_cits[int(m.group(1))]
            return self._register_final_cit(rc.text, rc.ref_ids, False, rc.text)

        s = nav_re.sub(_replace_narrative, s)

        # Normalise whitespace and punctuation around empty markers (\ue002C\d+\ue003\ue004)
        empty_cit = r"(?:\ue002C\d+\ue003\ue004)"
        # When whitespace appears on both sides of empty citation marker(s), keep the marker
        # attached to the left token and put a single space after it: "word \ue002C0\ue003\ue004 next" -> "word\ue002C0\ue003\ue004 next"
        s = re.sub(rf"[ \t]+({empty_cit}+)[ \t]+", r"\1 ", s)
        # Remove space before closing/sentence punctuation even across empty citation markers
        s = re.sub(rf"[ \t]+({empty_cit}*[,.;:)\]!?])", r"\1", s)
        # Remove space after opening bracket even across empty citation markers
        s = re.sub(rf"([(\[]{empty_cit}*)[ \t]+", r"\1", s)
        # Collapse any remaining multiple spaces
        s = re.sub(r"[ \t]{2,}", " ", s)
        # Strip leading/trailing spaces outside markers
        s = re.sub(rf"^[ \t]+({empty_cit}*)[ \t]*", r"\1", s)
        s = re.sub(rf"[ \t]*({empty_cit}*)[ \t]+$", r"\1", s)
        return s

    def add_paragraph(self, raw_para: str) -> None:
        resolved = self.resolve_paragraph(raw_para)
        # Only add if it has visible text (ignoring empty markers)
        vis = re.sub(r"\ue002[A-Z]\d+\ue003|\ue004", "", resolved).strip()
        if vis:
            self.paragraphs.append(resolved)

    def finalize(
        self,
    ) -> tuple[
        str,
        list[ParsedLink],
        list[ParsedCitation],
        list[ParsedXref],
        list[ParsedFormula],
    ]:
        """Join paragraphs with ``paragraph_sep``, strip markers, and compute exact offsets."""
        joined = self.options.paragraph_sep.join(self.paragraphs)
        out_chars: list[str] = []
        out_len = 0

        links: list[ParsedLink] = []
        citations: list[ParsedCitation] = []
        xrefs: list[ParsedXref] = []
        formulas: list[ParsedFormula] = []

        token_re = re.compile(r"\ue002([LXFC])(\d+)\ue003(.*?)\ue004", re.DOTALL)
        pos = 0
        for m in token_re.finditer(joined):
            if m.start() > pos:
                chunk = joined[pos : m.start()]
                out_chars.append(chunk)
                out_len += len(chunk)
            kind = m.group(1)
            idx = int(m.group(2))
            inner = m.group(3)
            start = out_len
            if inner:
                out_chars.append(inner)
                out_len += len(inner)
            end = out_len
            if kind == "L":
                vis, url = self._links[idx]
                links.append(
                    ParsedLink(
                        section_order=self.section_order,
                        start=start,
                        end=end,
                        text=vis,
                        url=url,
                    )
                )
            elif kind == "C":
                c_text, ref_ids, removed = self._final_cits[idx]
                citations.append(
                    ParsedCitation(
                        section_order=self.section_order,
                        start=start,
                        end=end,
                        text=c_text,
                        ref_ids=ref_ids,
                        removed=removed,
                    )
                )
            elif kind == "X":
                x_text, target, xtype = self._xrefs[idx]
                xrefs.append(
                    ParsedXref(
                        section_order=self.section_order,
                        start=start,
                        end=end,
                        text=x_text,
                        target=target,
                        type=xtype,
                    )
                )
            elif kind == "F":
                f_rec = self._formulas[idx]
                f_rec.start = start
                f_rec.end = end
                formulas.append(f_rec)
            pos = m.end()

        if pos < len(joined):
            out_chars.append(joined[pos:])

        return "".join(out_chars), links, citations, xrefs, formulas


# --------------------------------------------------------------------------- #
# Table helper functions (JATS & HTML)
# --------------------------------------------------------------------------- #
def rows_to_markdown(rows: list[list[str]], header_rows: int = 1) -> str | None:
    if not rows or not any( any(cell for cell in r) for r in rows ):
        return None
    n_cols = max(len(r) for r in rows)
    if n_cols == 0:
        return None
    padded = [r + [""] * (n_cols - len(r)) for r in rows]
    h_count = header_rows if header_rows > 0 else 1
    header = padded[:h_count]
    body = padded[h_count:]
    lines: list[str] = []
    for r in header:
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in r) + " |")
    lines.append("| " + " | ".join("---" for _ in range(n_cols)) + " |")
    for r in body:
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in r) + " |")
    return "\n".join(lines)


def parse_table_grid(
    table_el: etree._Element,
    render_cell_fn,
) -> tuple[list[list[str]], int]:
    """Parse an HTML or JATS ``<table>`` into a rectangular ``(rows, header_rows)`` grid."""
    thead_trs: list[etree._Element] = []
    body_trs: list[etree._Element] = []
    for child in table_el:
        cname = _local(child.tag)
        if cname == "thead":
            thead_trs.extend(c for c in child if _local(c.tag) == "tr")
        elif cname in ("tbody", "tfoot"):
            body_trs.extend(c for c in child if _local(c.tag) == "tr")
        elif cname == "tr":
            body_trs.append(child)

    all_trs = thead_trs + body_trs
    if not all_trs:
        return [], 0

    header_rows = len(thead_trs)
    if header_rows == 0 and all_trs:
        first_cells = [c for c in all_trs[0] if _local(c.tag) in ("th", "td")]
        if first_cells and all(_local(c.tag) == "th" for c in first_cells):
            header_rows = 1

    grid: dict[tuple[int, int], str] = {}
    max_col = 0
    n_rows = len(all_trs)

    for r_idx, tr in enumerate(all_trs):
        c_idx = 0
        for cell in tr:
            if _local(cell.tag) not in ("th", "td"):
                continue
            while (r_idx, c_idx) in grid:
                c_idx += 1
            text = render_cell_fn(cell)
            try:
                colspan = max(1, int(cell.get("colspan") or 1))
            except ValueError:
                colspan = 1
            try:
                rowspan = max(1, int(cell.get("rowspan") or 1))
            except ValueError:
                rowspan = 1
            for dr in range(rowspan):
                for dc in range(colspan):
                    rr = r_idx + dr
                    cc = c_idx + dc
                    if rr < n_rows:
                        grid[(rr, cc)] = text if (dr == 0 and dc == 0) else ""
                        max_col = max(max_col, cc + 1)
            c_idx += colspan

    rows: list[list[str]] = []
    for r_idx in range(n_rows):
        rows.append([grid.get((r_idx, c_idx), "") for c_idx in range(max_col)])
    return rows, header_rows


__all__ = [
    "TEXT_FORMAT",
    "ParsedCitation",
    "ParsedFigure",
    "ParsedFormula",
    "ParsedLink",
    "ParsedTable",
    "ParsedXref",
    "SectionAccumulator",
    "TextOptions",
    "classify_section",
    "linearize_mathml",
    "parse_table_grid",
    "render_link",
    "render_sub",
    "render_sup",
    "rows_to_markdown",
    "urljoin",
]
