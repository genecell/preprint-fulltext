"""assemble.py — map a pydantic-free :class:`ParsedArticle` into the canonical model.

This is the single seam between the shared JATS/HTML parsers and the canonical model,
used by the Europe PMC, S3, and HTML paths so their `FullText` schema is identical.
The abstract is emitted as an ``abstract``-kind :class:`Section` so the chunker treats
it uniformly; sections are renumbered from 1 with ``id = str(order)``.
"""

from __future__ import annotations

import datetime as dt

from .jats import ParsedArticle
from .licenses import parse_license
from .models import (
    Citation,
    Figure,
    Formula,
    FullText,
    Link,
    Preprint,
    Section,
    SectionKind,
    Server,
    SourceName,
    Table,
    Xref,
)


def build_fulltext(
    parsed: ParsedArticle,
    *,
    doi: str,
    server: Server | str,
    source: SourceName | str,
    version: int | None = None,
    raw_ref: str | None = None,
    published_doi: str | None = None,
    date: dt.date | None = None,
    category: str | None = None,
    provenance: dict | None = None,
) -> FullText:
    """Assemble a :class:`FullText` from parser output plus caller-supplied metadata."""
    license_ = parse_license(parsed.license_raw)

    preprint = Preprint(
        doi=doi,
        version=version,
        server=Server(server),
        title=parsed.title,
        authors=list(parsed.authors),
        date=date,
        category=category,
        abstract=parsed.abstract,
        license=license_,
        published_doi=published_doi,
        provenance=provenance or {},
    )

    sections: list[Section] = []
    order_map: dict[int, str] = {}
    order = 0
    if parsed.abstract:
        order += 1
        sid = str(order)
        order_map[0] = sid
        sections.append(
            Section(
                id=sid,
                kind=SectionKind.ABSTRACT,
                title="Abstract",
                text=parsed.abstract,
                order=order,
                role=None,
            )
        )
    for ps in parsed.sections:
        order += 1
        sid = str(order)
        order_map[ps.order] = sid
        sections.append(
            Section(
                id=sid,
                kind=SectionKind(ps.kind),
                title=ps.title,
                text=ps.text,
                order=order,
                role=ps.role,
            )
        )

    default_sid = sections[0].id if sections else "1"

    def _sid(sec_order: int | None) -> str:
        if sec_order is None:
            return default_sid
        return order_map.get(sec_order, default_sid)

    figures = [
        Figure(
            id=f.id,
            label=f.label,
            title=f.title,
            caption=f.caption,
            section_id=_sid(f.section_order),
            image_url=f.image_url,
        )
        for f in parsed.figures
    ]
    tables = [
        Table(
            id=t.id,
            label=t.label,
            caption=t.caption,
            section_id=_sid(t.section_order),
            status=t.status,
            header_rows=t.header_rows,
            rows=t.rows,
            markdown=t.markdown,
            footnotes=list(t.footnotes),
            source_url=t.source_url,
            image_url=t.image_url,
        )
        for t in parsed.tables
    ]
    links = [
        Link(
            section_id=_sid(lnk.section_order),
            start=lnk.start,
            end=lnk.end,
            text=lnk.text,
            url=lnk.url,
        )
        for lnk in parsed.links
    ]
    citations = [
        Citation(
            section_id=_sid(c.section_order),
            start=c.start,
            end=c.end,
            text=c.text,
            ref_ids=list(c.ref_ids),
            removed=c.removed,
        )
        for c in parsed.citations
    ]
    xrefs = [
        Xref(
            section_id=_sid(x.section_order),
            start=x.start,
            end=x.end,
            text=x.text,
            target=x.target,
            type=x.type,
        )
        for x in parsed.xrefs
    ]
    formulas = [
        Formula(
            id=fm.id,
            section_id=_sid(fm.section_order),
            start=fm.start,
            end=fm.end,
            display=fm.display,
            label=fm.label,
            tex=fm.tex,
            mathml=fm.mathml,
            text=fm.text,
            image_url=fm.image_url,
        )
        for fm in parsed.formulas
    ]

    return FullText(
        preprint=preprint,
        sections=sections,
        figures=figures,
        tables=tables,
        links=links,
        citations=citations,
        xrefs=xrefs,
        formulas=formulas,
        retrieved_from=SourceName(source),
        raw_ref=raw_ref,
        text_format=parsed.text_format,
        text_options=dict(parsed.text_options),
    )


__all__ = ["build_fulltext"]
