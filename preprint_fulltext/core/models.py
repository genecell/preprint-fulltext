"""Canonical data model (pydantic v2).

Every source adapter maps its payload *into* these models; the CLI, MCP server,
and embedding step read *out of* them. `Chunk` is the corpus record: one JSONL
line per chunk. All models serialize cleanly via ``model_dump(mode="json")``.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Server(StrEnum):
    """Preprint server hosting a paper."""

    BIORXIV = "biorxiv"
    MEDRXIV = "medrxiv"
    ARXIV = "arxiv"


class SectionKind(StrEnum):
    """Canonical section classification used by the chunker and exporters."""

    ABSTRACT = "abstract"
    INTRO = "intro"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    OTHER = "other"


class SourceName(StrEnum):
    """Provenance tag identifying which adapter produced a record."""

    OPENALEX = "openalex"
    EUROPEPMC = "europepmc"
    BIORXIV_API = "biorxiv_api"
    BIORXIV_S3 = "biorxiv_s3"
    BIORXIV_HTML = "biorxiv_html"
    ARXIV_API = "arxiv_api"
    ARXIV_HTML = "arxiv_html"


class License(BaseModel):
    """Author-selected license, mapped from a raw string by ``core.licenses``.

    ``redistributable`` is the compliance gate's sole input. Unknown or ambiguous
    licenses must be constructed as ``redistributable=False`` (fail safe) — that
    policy lives in ``core.licenses.parse_license``, not here.
    """

    model_config = ConfigDict(frozen=True)

    raw: str = Field(description="Original license string/URL as found in the source.")
    spdx_id: str | None = Field(
        default=None, description="SPDX identifier, e.g. 'CC-BY-4.0'; None if unmapped."
    )
    redistributable: bool = Field(
        default=False, description="May the body text be redistributed? Fail-safe default False."
    )
    requires_attribution: bool = Field(
        default=True, description="Does the license require attribution?"
    )


class Preprint(BaseModel):
    """Bibliographic record for one preprint version (abstract, never body)."""

    model_config = ConfigDict(extra="ignore")

    doi: str
    version: int | None = None
    server: Server
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    date: dt.date | None = None
    category: str | None = None
    abstract: str | None = None
    license: License | None = None
    published_doi: str | None = Field(
        default=None, description="DOI of the peer-reviewed version, if mapped."
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Free-form source provenance (source name, ids, urls)."
    )


class Section(BaseModel):
    """One logical section of full text. Nested JATS <sec> are flattened but keep
    document ``order`` and inherit their nearest titled parent's ``kind``."""

    id: str = Field(description="Stable within-document section id (e.g. the order index).")
    kind: SectionKind = SectionKind.OTHER
    title: str | None = None
    text: str = ""
    order: int
    role: str | None = None


class Figure(BaseModel):
    """A figure float extracted from JATS <fig> or bioRxiv HTML div.fig."""

    id: str | None = None
    label: str | None = None
    title: str | None = None
    caption: str = ""
    section_id: str | None = None
    image_url: str | None = None


class Table(BaseModel):
    """A table float extracted from JATS <table-wrap> or bioRxiv HTML div.table."""

    id: str | None = None
    label: str | None = None
    caption: str = ""
    section_id: str | None = None
    status: str = "parsed"
    header_rows: int = 0
    rows: list[list[str]] | None = None
    markdown: str | None = None
    footnotes: list[str] = Field(default_factory=list)
    source_url: str | None = None
    image_url: str | None = None


class Link(BaseModel):
    """An external hyperlink with character offsets into its section's text."""

    section_id: str
    start: int
    end: int
    text: str
    url: str


class Citation(BaseModel):
    """A bibliographic citation or citation group with offsets into its section's text."""

    section_id: str
    start: int
    end: int
    text: str
    ref_ids: list[str] = Field(default_factory=list)
    removed: bool = False


class Xref(BaseModel):
    """An in-text cross-reference (fig, table, sec, disp-formula, etc.) with offsets."""

    section_id: str
    start: int
    end: int
    text: str
    target: str | None = None
    type: str | None = None


class Formula(BaseModel):
    """An inline or display formula with character offsets into its section's text."""

    id: str | None = None
    section_id: str
    start: int
    end: int
    display: bool = False
    label: str | None = None
    tex: str | None = None
    mathml: str | None = None
    text: str | None = None
    image_url: str | None = None


class FullText(BaseModel):
    """A preprint plus its parsed sections — the output of ``get``."""

    preprint: Preprint
    sections: list[Section] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    xrefs: list[Xref] = Field(default_factory=list)
    formulas: list[Formula] = Field(default_factory=list)
    retrieved_from: SourceName
    raw_ref: str | None = Field(
        default=None, description="Cache key / URI / object key the raw XML came from."
    )
    text_format: str = "pf-text/2"
    text_options: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """The corpus record. One JSONL line per chunk. Carries its own License so the
    compliance gate can act on chunks independently of the parent FullText."""

    doi: str
    version: int | None = None
    chunk_id: str = Field(description="Deterministic: '{doi}:{version}:{section_order}:{idx}'.")
    section_kind: SectionKind
    text: str
    token_count: int
    char_start: int = Field(description="Inclusive start offset into the section text.")
    char_end: int = Field(description="Exclusive end offset into the section text.")
    license: License
    source: SourceName
    text_format: str = "pf-text/2"


class SearchHit(BaseModel):
    """A discovery/search result. Full text is not guaranteed to be retrievable."""

    title: str | None = None
    doi: str | None = None
    openalex_id: str | None = None
    score: float | None = None
    source: SourceName
    snippet: str | None = None
    oa_url: str | None = Field(default=None, description="Best open-access URL, if known.")
    has_fulltext: bool = False


__all__ = [
    "Chunk",
    "Citation",
    "Figure",
    "Formula",
    "FullText",
    "License",
    "Link",
    "Preprint",
    "SearchHit",
    "Section",
    "SectionKind",
    "Server",
    "SourceName",
    "Table",
    "Xref",
]
