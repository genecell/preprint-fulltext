"""jats.py — the ONE shared JATS parser (correctness-critical).

Serves both the Europe PMC path (``fullTextXML``) and the S3 path (the JATS XML
inside each ``.meca``'s ``content/`` folder), because both return JATS. Kept
pydantic-free and dependency-light (only ``lxml``) so it stays identical for both
paths and is trivially testable. The mapping into the canonical model happens in
:mod:`preprint_fulltext.core.assemble`.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import asdict, dataclass, field
from typing import Any

from lxml import etree

from .render import (
     _SUP_SEP_ONLY_RE,
    TEXT_FORMAT,
    XLINK,
    ParsedCitation,
    ParsedFigure,
    ParsedFormula,
    ParsedLink,
    ParsedTable,
    ParsedXref,
    SectionAccumulator,
    TextOptions,
    classify_section,
    linearize_mathml,
    parse_table_grid,
    render_sub,
    render_sup,
    rows_to_markdown,
)

_WS = re.compile(r"\s+")
_DESPACE = re.compile(r"\s+([,.;:)\]!?])")
_OPENSPACE = re.compile(r"([(\[])\s+")


@dataclass
class ParsedSection:
    """One <sec>'s direct prose. Pydantic-free; mapped to models.Section at assembly."""

    order: int
    kind: str  # intro | methods | results | discussion | other  (never 'abstract' here)
    title: str | None
    text: str
    role: str | None = None


@dataclass
class ParsedArticle:
    """Everything the parser can pull from a JATS or HTML document, dependency-light."""

    title: str | None = None
    doi: str | None = None
    authors: list[str] = field(default_factory=list)
    abstract: str | None = None
    license_raw: dict | None = None  # {"href": ..., "text": ...} -> licenses.parse_license
    sections: list[ParsedSection] = field(default_factory=list)
    figures: list[ParsedFigure] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    links: list[ParsedLink] = field(default_factory=list)
    citations: list[ParsedCitation] = field(default_factory=list)
    xrefs: list[ParsedXref] = field(default_factory=list)
    formulas: list[ParsedFormula] = field(default_factory=list)
    text_format: str = TEXT_FORMAT
    text_options: dict[str, Any] = field(default_factory=lambda: TextOptions().as_dict())

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


def _local(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    try:
        return etree.QName(tag).localname
    except ValueError:
        return tag.split("}")[-1] if "}" in tag else tag


def _classify(sec_type: str | None, title: str | None, inherited: str | None) -> str:
    """Backwards-compatible helper returning only ``kind``."""
    kind, _ = classify_section(title, sec_type, inherited, None)
    return kind


def _is_sup_citation_group(sup_el: etree._Element) -> tuple[bool, str, list[str]]:
    """Check whether a ``<sup>`` contains only bibliographic ``<xref>`` citations and separators."""
    children = [c for c in sup_el if isinstance(c.tag, str)]
    if not children:
        return False, "", []
    if not all(_local(c.tag) == "xref" and (c.get("ref-type") or "bibr") == "bibr" for c in children):
        return False, "", []
    if sup_el.text and not _SUP_SEP_ONLY_RE.match(sup_el.text):
        return False, "", []
    ref_ids: list[str] = []
    for c in children:
        if c.tail and not _SUP_SEP_ONLY_RE.match(c.tail):
            return False, "", []
        rid = (c.get("rid") or "").strip()
        if rid:
            ref_ids.extend(rid.split())
    group_text = _WS.sub(" ", "".join(sup_el.itertext())).strip()
    if not group_text:
        return False, "", []
    return True, group_text, ref_ids


def _render_inline_formula(elem: etree._Element, acc: SectionAccumulator) -> str:
    fid = elem.get("id")
    tex_el = elem.find(".//tex-math")
    tex = _WS.sub(" ", "".join(tex_el.itertext())).strip() if tex_el is not None else None
    mml_el = next((e for e in elem.iter() if _local(e.tag) == "math"), None)
    mathml_str = etree.tostring(mml_el, encoding="unicode", with_tail=False) if mml_el is not None else None
    linear = _WS.sub(" ", linearize_mathml(mml_el)).strip() if mml_el is not None else None

    mode = acc.options.math
    if mode == "placeholder":
        rendered = "[formula]"
    elif mode == "tex":
        cand = tex or linear
        rendered = cand if (cand and len(cand) <= 80) else "[formula]"
    else:
        cand = linear or tex
        rendered = cand if (cand and len(cand) <= 80) else "[formula]"

    return acc.add_formula_sentinel(
        rendered,
        fid=fid,
        display=False,
        tex=tex,
        mathml=mathml_str,
        linear_text=linear,
    )


def _render_disp_formula(elem: etree._Element, acc: SectionAccumulator) -> str:
    fid = elem.get("id")
    lbl_el = elem.find("label")
    label = _WS.sub(" ", "".join(lbl_el.itertext())).strip() if lbl_el is not None else None
    tex_el = elem.find(".//tex-math")
    tex = _WS.sub(" ", "".join(tex_el.itertext())).strip() if tex_el is not None else None
    mml_el = next((e for e in elem.iter() if _local(e.tag) == "math"), None)
    mathml_str = etree.tostring(mml_el, encoding="unicode", with_tail=False) if mml_el is not None else None
    linear = _WS.sub(" ", linearize_mathml(mml_el)).strip() if mml_el is not None else None

    if label:
        lbl_fmt = label if (label.startswith("(") and label.endswith(")")) else f"({label})"
        rendered = f"[equation {lbl_fmt}]"
    else:
        rendered = "[equation]"

    return acc.add_formula_sentinel(
        rendered,
        fid=fid,
        display=True,
        label=label,
        tex=tex,
        mathml=mathml_str,
        linear_text=linear,
    )


def _render_inline_children(
    elem: etree._Element,
    acc: SectionAccumulator,
    art: ParsedArticle | None,
    sec_order: int,
    keep_tables: bool,
    opts: TextOptions,
    supp_items: list[str] | None,
) -> str:
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)

    for child in elem:
        if not isinstance(child.tag, str):
            if child.tail:
                parts.append(child.tail)
            continue
        prev_str = "".join(parts)
        prev_char = prev_str[-1] if prev_str else ""
        cname = _local(child.tag)

        if cname == "xref":
            ref_type = (child.get("ref-type") or "").strip().lower()
            rid = (child.get("rid") or "").strip() or None
            inner_txt = _WS.sub(" ", "".join(child.itertext())).strip()
            if ref_type in ("fn", "table-fn"):
                pass
            elif ref_type == "bibr" or not ref_type:
                # Default untyped xref in JATS body is bibr if rid starts with c/ref/bib, else keep text
                if ref_type == "bibr" or (rid and rid[:1].lower() in ("c", "b", "r") and inner_txt[:1].isdigit()):
                    parts.append(acc.add_cit_sentinel(inner_txt, rid.split() if rid else []))
                else:
                    parts.append(acc.add_xref_sentinel(inner_txt, rid, ref_type or None))
            else:
                parts.append(acc.add_xref_sentinel(inner_txt, rid, ref_type))
        elif cname in ("ext-link", "uri"):
            href = (child.get(f"{{{XLINK}}}href") or child.get("href") or "").strip()
            vis = _WS.sub(" ", _render_inline_children(child, acc, art, sec_order, keep_tables, opts, supp_items)).strip()
            if not href:
                href = vis
            if href:
                parts.append(acc.add_link_sentinel(vis, href))
            else:
                parts.append(vis)
        elif cname == "sup":
            is_cit, g_txt, ref_ids = _is_sup_citation_group(child)
            if is_cit:
                parts.append(acc.add_cit_sentinel(g_txt, ref_ids, is_sup_group=True))
            else:
                inner_sup = _WS.sub(
                    " ",
                    _render_inline_children(child, acc, art, sec_order, keep_tables, opts, supp_items),
                ).strip()
                parts.append(render_sup(inner_sup, prev_char, opts.scripts))
        elif cname == "sub":
            inner_sub = _WS.sub(
                " ",
                _render_inline_children(child, acc, art, sec_order, keep_tables, opts, supp_items),
            ).strip()
            parts.append(render_sub(inner_sub, opts.subscripts))
        elif cname == "inline-formula":
            parts.append(_render_inline_formula(child, acc))
        elif cname == "disp-formula":
            parts.append(" " + _render_disp_formula(child, acc) + " ")
        elif cname == "break":
            parts.append(" ")
        elif cname == "list":
            parts.append(" " + _render_list(child, acc, art, sec_order, keep_tables, opts, supp_items) + " ")
        elif cname == "def-list":
            parts.append(" " + _render_def_list(child, acc, art, sec_order, keep_tables, opts, supp_items) + " ")
        elif cname == "fig":
            if art is not None:
                fig = _extract_jats_fig(child, sec_order, opts)
                if fig:
                    art.figures.append(fig)
        elif cname == "fig-group":
            if art is not None:
                for f in child.findall("fig"):
                    fig = _extract_jats_fig(f, sec_order, opts)
                    if fig:
                        art.figures.append(fig)
        elif cname == "table-wrap":
            if art is not None:
                tab = _extract_jats_table(child, sec_order, opts)
                if tab:
                    art.tables.append(tab)
                    if keep_tables:
                        parts.append(" " + _table_to_inline_text(tab) + " ")
        elif cname == "table-wrap-group":
            if art is not None:
                for tw in child.findall("table-wrap"):
                    tab = _extract_jats_table(tw, sec_order, opts)
                    if tab:
                        art.tables.append(tab)
                        if keep_tables:
                            parts.append(" " + _table_to_inline_text(tab) + " ")
        elif cname == "supplementary-material":
            if supp_items is not None:
                s_txt = _extract_jats_supplementary(child, opts)
                if s_txt:
                    supp_items.append(s_txt)
        elif cname in ("graphic", "media", "label"):
            pass
        else:
            parts.append(_render_inline_children(child, acc, art, sec_order, keep_tables, opts, supp_items))

        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


def _render_list(
    list_el: etree._Element,
    acc: SectionAccumulator,
    art: ParsedArticle | None,
    sec_order: int,
    keep_tables: bool,
    opts: TextOptions,
    supp_items: list[str] | None,
) -> str:
    items: list[str] = []
    for li in list_el:
        if _local(li.tag) != "list-item":
            continue
        li_parts: list[str] = []
        lbl = li.find("label")
        if lbl is not None:
            l_txt = _WS.sub(" ", "".join(lbl.itertext())).strip()
            if l_txt:
                li_parts.append(l_txt)
        for sub in li:
            sname = _local(sub.tag)
            if sname == "label":
                continue
            elif sname == "list":
                li_parts.append(_render_list(sub, acc, art, sec_order, keep_tables, opts, supp_items))
            else:
                li_parts.append(_render_inline_children(sub, acc, art, sec_order, keep_tables, opts, supp_items))
        if not li_parts and li.text:
            li_parts.append(li.text)
        joined = " ".join(p.strip() for p in li_parts if p and p.strip())
        if joined:
            items.append(joined)
    return " ".join(items)


def _render_def_list(
    dl_el: etree._Element,
    acc: SectionAccumulator,
    art: ParsedArticle | None,
    sec_order: int,
    keep_tables: bool,
    opts: TextOptions,
    supp_items: list[str] | None,
) -> str:
    items: list[str] = []
    for di in dl_el:
        if _local(di.tag) != "def-item":
            continue
        term_el = di.find("term")
        def_el = di.find("def")
        t_str = (
            _render_inline_children(term_el, acc, art, sec_order, keep_tables, opts, supp_items).strip()
            if term_el is not None
            else ""
        )
        d_str = (
            _render_inline_children(def_el, acc, art, sec_order, keep_tables, opts, supp_items).strip()
            if def_el is not None
            else ""
        )
        if t_str and d_str:
            items.append(f"{t_str}: {d_str}")
        elif t_str or d_str:
            items.append(t_str or d_str)
    return " ".join(items)


def _render_isolated_text(elem: etree._Element, opts: TextOptions) -> str:
    """Render an element (such as a caption paragraph or table cell) into clean text."""
    tmp_acc = SectionAccumulator(0, opts)
    raw = _render_inline_children(elem, tmp_acc, None, 0, False, opts, None)
    tmp_acc.add_paragraph(raw)
    text, _, _, _, _ = tmp_acc.finalize()
    return text


def _extract_jats_fig(fig_el: etree._Element, sec_order: int, opts: TextOptions) -> ParsedFigure | None:
    fid = fig_el.get("id")
    lbl_el = fig_el.find("label")
    label = _norm("".join(lbl_el.itertext())).rstrip(":.") if lbl_el is not None else None
    if label == "":
        label = None

    cap_el = fig_el.find("caption")
    title: str | None = None
    cap_parts: list[str] = []
    if cap_el is not None:
        t_el = cap_el.find("title")
        if t_el is not None:
            title = _render_isolated_text(t_el, opts) or None
            if title:
                cap_parts.append(title)
        for p_el in cap_el.findall("p"):
            p_txt = _render_isolated_text(p_el, opts)
            if p_txt:
                cap_parts.append(p_txt)
        if not cap_parts:
            fallback = _render_isolated_text(cap_el, opts)
            if fallback:
                cap_parts.append(fallback)

    graphic_el = fig_el.find(".//graphic")
    image_url = None
    if graphic_el is not None:
        image_url = (graphic_el.get(f"{{{XLINK}}}href") or graphic_el.get("href") or "").strip() or None

    caption = " ".join(cap_parts).strip()
    if not (fid or label or title or caption or image_url):
        return None
    return ParsedFigure(
        id=fid,
        label=label,
        title=title,
        caption=caption,
        section_order=sec_order,
        image_url=image_url,
    )


def _extract_jats_table(tw_el: etree._Element, sec_order: int, opts: TextOptions) -> ParsedTable | None:
    tid = tw_el.get("id")
    lbl_el = tw_el.find("label")
    label = _norm("".join(lbl_el.itertext())).rstrip(":.") if lbl_el is not None else None
    if label == "":
        label = None

    cap_el = tw_el.find("caption")
    cap_parts: list[str] = []
    if cap_el is not None:
        t_el = cap_el.find("title")
        if t_el is not None:
            t_txt = _render_isolated_text(t_el, opts)
            if t_txt:
                cap_parts.append(t_txt)
        for p_el in cap_el.findall("p"):
            p_txt = _render_isolated_text(p_el, opts)
            if p_txt:
                cap_parts.append(p_txt)
        if not cap_parts:
            fallback = _render_isolated_text(cap_el, opts)
            if fallback:
                cap_parts.append(fallback)
    caption = " ".join(cap_parts).strip()

    footnotes: list[str] = []
    foot_el = tw_el.find("table-wrap-foot")
    if foot_el is not None:
        for fn in foot_el:
            if _local(fn.tag) in ("fn", "p", "fn-group"):
                fn_txt = _render_isolated_text(fn, opts)
                if fn_txt:
                    footnotes.append(fn_txt)

    table_el = tw_el.find(".//table")
    rows: list[list[str]] | None = None
    header_rows = 0
    md: str | None = None
    status = "parsed"
    image_url: str | None = None

    if table_el is not None:
        parsed_rows, header_rows = parse_table_grid(table_el, lambda cell: _render_isolated_text(cell, opts))
        rows = parsed_rows
        md = rows_to_markdown(rows, header_rows)
    else:
        graphic_el = tw_el.find(".//graphic")
        if graphic_el is not None:
            image_url = (graphic_el.get(f"{{{XLINK}}}href") or graphic_el.get("href") or "").strip() or None
            status = "image_only"
        else:
            status = "not_in_page"

    return ParsedTable(
        id=tid,
        label=label,
        caption=caption,
        section_order=sec_order,
        status=status,
        header_rows=header_rows,
        rows=rows,
        markdown=md,
        footnotes=footnotes,
        source_url=None,
        image_url=image_url,
    )


def _table_to_inline_text(tab: ParsedTable) -> str:
    parts: list[str] = []
    if tab.caption:
        parts.append(tab.caption)
    if tab.rows:
        parts.append("; ".join(" | ".join(r) for r in tab.rows))
    if tab.footnotes:
        parts.extend(tab.footnotes)
    return " ".join(parts)


def _extract_jats_supplementary(supp_el: etree._Element, opts: TextOptions) -> str:
    lbl_el = supp_el.find("label")
    label = _norm("".join(lbl_el.itertext())).rstrip(":.") if lbl_el is not None else ""
    cap_el = supp_el.find("caption")
    cap = _render_isolated_text(cap_el, opts) if cap_el is not None else ""
    if not cap:
        # Check for direct <p> children outside <caption>
        ps = [_render_isolated_text(p, opts) for p in supp_el.findall("p")]
        cap = " ".join(p for p in ps if p)
    if label and cap:
        return f"{label}: {cap}"
    return label or cap


def _process_block_children(
    container: etree._Element,
    acc: SectionAccumulator,
    art: ParsedArticle,
    sec_order: int,
    keep_tables: bool,
    opts: TextOptions,
    supp_items: list[str],
) -> None:
    for child in container:
        cname = _local(child.tag)
        if cname in ("sec", "title", "label", "app"):
            continue
        if cname in ("p", "disp-quote", "statement", "boxed-text"):
            if cname != "p" and child.findall("p"):
                for sub in child:
                    if _local(sub.tag) in ("p", "title"):
                        acc.add_paragraph(
                            _render_inline_children(sub, acc, art, sec_order, keep_tables, opts, supp_items)
                        )
            else:
                acc.add_paragraph(
                    _render_inline_children(child, acc, art, sec_order, keep_tables, opts, supp_items)
                )
        elif cname == "list":
            acc.add_paragraph(_render_list(child, acc, art, sec_order, keep_tables, opts, supp_items))
        elif cname == "def-list":
            acc.add_paragraph(_render_def_list(child, acc, art, sec_order, keep_tables, opts, supp_items))
        elif cname == "disp-formula":
            acc.add_paragraph(_render_disp_formula(child, acc))
        elif cname == "fig":
            fig = _extract_jats_fig(child, sec_order, opts)
            if fig:
                art.figures.append(fig)
        elif cname == "fig-group":
            for f in child.findall("fig"):
                fig = _extract_jats_fig(f, sec_order, opts)
                if fig:
                    art.figures.append(fig)
        elif cname == "table-wrap":
            tab = _extract_jats_table(child, sec_order, opts)
            if tab:
                art.tables.append(tab)
                if keep_tables:
                    acc.add_paragraph(_table_to_inline_text(tab))
        elif cname == "table-wrap-group":
            for tw in child.findall("table-wrap"):
                tab = _extract_jats_table(tw, sec_order, opts)
                if tab:
                    art.tables.append(tab)
                    if keep_tables:
                        acc.add_paragraph(_table_to_inline_text(tab))
        elif cname == "supplementary-material":
            s_txt = _extract_jats_supplementary(child, opts)
            if s_txt:
                supp_items.append(s_txt)


def _walk_sec(
    sec: etree._Element,
    art: ParsedArticle,
    counter: list[int],
    parent_kind: str | None,
    parent_role: str | None,
    keep_tables: bool,
    opts: TextOptions,
    supp_items: list[str],
    *,
    default_title: str | None = None,
) -> None:
    lbl_el = sec.find("label")
    title_el = sec.find("title")
    lbl_str = _norm("".join(lbl_el.itertext())) if lbl_el is not None else ""
    title_str = _norm("".join(title_el.itertext())) if title_el is not None else ""
    if lbl_str and title_str:
        title: str | None = f"{lbl_str} {title_str}" if not title_str.startswith(lbl_str) else title_str
    elif title_str:
        title = title_str
    elif lbl_str:
        title = lbl_str
    else:
        title = default_title

    kind, role = classify_section(title, sec.get("sec-type"), parent_kind, parent_role)

    provisional_order = counter[0] + 1
    acc = SectionAccumulator(provisional_order, opts)
    figs_before = len(art.figures)
    tabs_before = len(art.tables)

    _process_block_children(sec, acc, art, provisional_order, keep_tables, opts, supp_items)
    text, links, cits, xrefs, formulas = acc.finalize()

    if text or title:
        counter[0] += 1
        art.sections.append(
            ParsedSection(order=counter[0], kind=kind, title=title, text=text, role=role)
        )
        art.links.extend(links)
        art.citations.extend(cits)
        art.xrefs.extend(xrefs)
        art.formulas.extend(formulas)
    else:
        fallback_order = counter[0] if counter[0] > 0 else 1
        for f in art.figures[figs_before:]:
            f.section_order = fallback_order
        for t in art.tables[tabs_before:]:
            t.section_order = fallback_order

    for child in sec:
        if _local(child.tag) in ("sec", "app"):
            _walk_sec(
                child,
                art,
                counter,
                parent_kind=kind,
                parent_role=role,
                keep_tables=keep_tables,
                opts=opts,
                supp_items=supp_items,
            )


def _render_abstract(ab_el: etree._Element, art: ParsedArticle, keep_tables: bool, opts: TextOptions) -> str:
    acc = SectionAccumulator(0, opts)
    supp_items: list[str] = []

    secs = ab_el.findall("sec")
    if secs:
        for s in secs:
            t_el = s.find("title")
            sec_title = _norm("".join(t_el.itertext())).rstrip(":") if t_el is not None else ""
            sub_acc = SectionAccumulator(0, opts)
            _process_block_children(s, sub_acc, art, 0, keep_tables, opts, supp_items)
            if sub_acc.paragraphs:
                if sec_title:
                    sub_acc.paragraphs[0] = f"{sec_title}: {sub_acc.paragraphs[0]}"
                for p_raw in sub_acc.paragraphs:
                    # Transfer raw paragraphs/records via acc directly by rendering on acc
                    pass
        # Render structured abstract directly into `acc` so offsets are unified:
        acc = SectionAccumulator(0, opts)
        for s in secs:
            t_el = s.find("title")
            sec_title = _norm("".join(t_el.itertext())).rstrip(":") if t_el is not None else ""
            first = True
            for child in s:
                cname = _local(child.tag)
                if cname in ("title", "label"):
                    continue
                raw_p = _render_inline_children(child, acc, art, 0, keep_tables, opts, supp_items)
                if first and sec_title:
                    raw_p = f"{sec_title}: {raw_p}"
                    first = False
                acc.add_paragraph(raw_p)
    else:
        _process_block_children(ab_el, acc, art, 0, keep_tables, opts, supp_items)
        if not acc.paragraphs:
            raw = _render_inline_children(ab_el, acc, art, 0, keep_tables, opts, supp_items)
            acc.add_paragraph(raw)

    text, links, cits, xrefs, formulas = acc.finalize()
    art.links.extend(links)
    art.citations.extend(cits)
    art.xrefs.extend(xrefs)
    art.formulas.extend(formulas)
    return text


def _walk_back(
    back: etree._Element,
    art: ParsedArticle,
    counter: list[int],
    keep_tables: bool,
    opts: TextOptions,
    supp_items: list[str],
) -> None:
    for child in back:
        cname = _local(child.tag)
        if cname == "ref-list":
            continue
        elif cname == "ack":
            _walk_sec(
                child,
                art,
                counter,
                parent_kind="other",
                parent_role="acknowledgements",
                keep_tables=keep_tables,
                opts=opts,
                supp_items=supp_items,
                default_title="Acknowledgements",
            )
        elif cname == "sec":
            _walk_sec(
                child,
                art,
                counter,
                parent_kind="other",
                parent_role=None,
                keep_tables=keep_tables,
                opts=opts,
                supp_items=supp_items,
            )
        elif cname == "app-group":
            for app in child:
                if _local(app.tag) in ("app", "sec"):
                    _walk_sec(
                        app,
                        art,
                        counter,
                        parent_kind="other",
                        parent_role="appendix",
                        keep_tables=keep_tables,
                        opts=opts,
                        supp_items=supp_items,
                    )
        elif cname == "app":
            _walk_sec(
                child,
                art,
                counter,
                parent_kind="other",
                parent_role="appendix",
                keep_tables=keep_tables,
                opts=opts,
                supp_items=supp_items,
            )
        elif cname == "notes":
            _walk_sec(
                child,
                art,
                counter,
                parent_kind="other",
                parent_role=None,
                keep_tables=keep_tables,
                opts=opts,
                supp_items=supp_items,
            )
        elif cname == "fn-group":
            t_el = child.find("title")
            fn_title = _norm("".join(t_el.itertext())) if t_el is not None else "Footnotes"
            sec_order = counter[0] + 1
            acc = SectionAccumulator(sec_order, opts)
            for fn in child.findall("fn"):
                _process_block_children(fn, acc, art, sec_order, keep_tables, opts, supp_items)
            text, links, cits, xrefs, formulas = acc.finalize()
            if text:
                counter[0] += 1
                art.sections.append(
                    ParsedSection(
                        order=counter[0],
                        kind="other",
                        title=fn_title or "Footnotes",
                        text=text,
                        role="footnotes",
                    )
                )
                art.links.extend(links)
                art.citations.extend(cits)
                art.xrefs.extend(xrefs)
                art.formulas.extend(formulas)
        elif cname == "glossary":
            t_el = child.find("title")
            gl_title = _norm("".join(t_el.itertext())) if t_el is not None else "Abbreviations"
            sec_order = counter[0] + 1
            acc = SectionAccumulator(sec_order, opts)
            _process_block_children(child, acc, art, sec_order, keep_tables, opts, supp_items)
            text, links, cits, xrefs, formulas = acc.finalize()
            if text:
                counter[0] += 1
                art.sections.append(
                    ParsedSection(
                        order=counter[0],
                        kind="other",
                        title=gl_title or "Abbreviations",
                        text=text,
                        role="abbreviations",
                    )
                )
                art.links.extend(links)
                art.citations.extend(cits)
                art.xrefs.extend(xrefs)
                art.formulas.extend(formulas)


def append_legends_sections(art: ParsedArticle, counter: list[int], opts: TextOptions) -> None:
    """Append 'Figure legends' and 'Tables' sections when ``opts.legends_as_section`` is True."""
    if not opts.legends_as_section:
        return
    if art.figures:
        lines = [
            f"{f.label}: {f.caption}" if (f.label and f.caption) else (f.label or f.caption)
            for f in art.figures
            if f.label or f.caption
        ]
        if lines:
            counter[0] += 1
            art.sections.append(
                ParsedSection(
                    order=counter[0],
                    kind="other",
                    title="Figure legends",
                    text=opts.paragraph_sep.join(lines),
                    role="figure_legends",
                )
            )
    if art.tables:
        t_lines: list[str] = []
        for t in art.tables:
            head = f"{t.label}: {t.caption}" if (t.label and t.caption) else (t.label or t.caption or "")
            if t.markdown:
                head = f"{head}\n{t.markdown}" if head else t.markdown
            if head:
                t_lines.append(head)
        if t_lines:
            counter[0] += 1
            art.sections.append(
                ParsedSection(
                    order=counter[0],
                    kind="other",
                    title="Tables",
                    text=opts.paragraph_sep.join(t_lines),
                    role="tables",
                )
            )


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def parse_jats(
    xml: bytes | str,
    *,
    keep_tables: bool = False,
    options: TextOptions | None = None,
) -> ParsedArticle:
    """Parse JATS XML into a :class:`ParsedArticle`. Never raises on malformed input."""
    if keep_tables:
        warnings.warn(
            "keep_tables is deprecated; read FullText.tables instead.",
            DeprecationWarning,
            stacklevel=2,
        )
    opts = options or TextOptions()
    if isinstance(xml, str):
        xml = xml.encode("utf-8")

    parser = etree.XMLParser(
        recover=True,
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=True,
    )
    try:
        root = etree.fromstring(xml, parser=parser)
    except etree.XMLSyntaxError:
        return ParsedArticle(text_options=opts.as_dict())
    if root is None:
        return ParsedArticle(text_options=opts.as_dict())

    art = ParsedArticle(text_options=opts.as_dict())
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
        art.abstract = _render_abstract(ab, art, keep_tables, opts)
        break

    # license -> raw dict for licenses.parse_license
    lic = root.find(".//article-meta/permissions/license")
    if lic is not None:
        art.license_raw = {
            "href": lic.get(f"{{{XLINK}}}href"),
            "text": _norm("".join(lic.itertext())) or None,
        }

    counter = [0]
    supp_items: list[str] = []

    # body sections + body-level blocks outside <sec>
    body = root.find(".//body")
    if body is not None:
        pending_blocks: list[etree._Element] = []

        def _flush_pending() -> None:
            if not pending_blocks:
                return
            sec_order = counter[0] + 1
            acc = SectionAccumulator(sec_order, opts)
            dummy = etree.Element("sec")
            for b in pending_blocks:
                dummy.append(b)
            pending_blocks.clear()
            _process_block_children(dummy, acc, art, sec_order, keep_tables, opts, supp_items)
            text, links, cits, xrefs, formulas = acc.finalize()
            if text:
                counter[0] += 1
                art.sections.append(
                    ParsedSection(order=counter[0], kind="other", title=None, text=text, role=None)
                )
                art.links.extend(links)
                art.citations.extend(cits)
                art.xrefs.extend(xrefs)
                art.formulas.extend(formulas)

        for child in list(body):
            if _local(child.tag) == "sec":
                _flush_pending()
                _walk_sec(
                    child,
                    art,
                    counter,
                    parent_kind=None,
                    parent_role=None,
                    keep_tables=keep_tables,
                    opts=opts,
                    supp_items=supp_items,
                )
            else:
                pending_blocks.append(child)
        _flush_pending()

    # back matter (<ack>, <sec>, <app-group>, <fn-group>, <glossary>; skip <ref-list>)
    back = root.find(".//back")
    if back is not None:
        _walk_back(back, art, counter, keep_tables, opts, supp_items)

    # trailing supplementary material section if any block <supplementary-material> was collected
    if supp_items:
        counter[0] += 1
        art.sections.append(
            ParsedSection(
                order=counter[0],
                kind="other",
                title="Supplementary material",
                text=opts.paragraph_sep.join(supp_items),
                role="supplementary",
            )
        )

    append_legends_sections(art, counter, opts)
    return art


__all__ = ["ParsedArticle", "ParsedSection", "parse_jats", "_classify", "_norm", "append_legends_sections"]


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "jats_biorxiv_sample.xml"
    with open(path, "rb") as fh:
        print(json.dumps(parse_jats(fh.read()).to_dict(), indent=2, ensure_ascii=False))
