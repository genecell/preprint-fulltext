"""assemble.py — map a pydantic-free :class:`ParsedArticle` into the canonical model.

This is the single seam between the shared JATS parser and the canonical model,
used by BOTH the Europe PMC and S3 paths so their `FullText` is byte-for-byte
identical for the same document. The abstract is emitted as an
``abstract``-kind :class:`Section` so the chunker treats it uniformly; sections
are renumbered from 1 with ``id = str(order)``.
"""

from __future__ import annotations

import datetime as dt

from .jats import ParsedArticle
from .licenses import parse_license
from .models import FullText, Preprint, Section, SectionKind, Server, SourceName


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
    order = 0
    if parsed.abstract:
        order += 1
        sections.append(
            Section(id=str(order), kind=SectionKind.ABSTRACT, title="Abstract",
                    text=parsed.abstract, order=order)
        )
    for ps in parsed.sections:
        order += 1
        sections.append(
            Section(id=str(order), kind=SectionKind(ps.kind), title=ps.title,
                    text=ps.text, order=order)
        )

    return FullText(
        preprint=preprint,
        sections=sections,
        retrieved_from=SourceName(source),
        raw_ref=raw_ref,
    )


__all__ = ["build_fulltext"]
