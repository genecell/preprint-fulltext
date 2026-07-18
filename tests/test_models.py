"""Tests for the canonical data model."""

from __future__ import annotations

import datetime as dt

import orjson
import pytest

from preprint_fulltext.core.models import (
    Chunk,
    FullText,
    License,
    Preprint,
    SearchHit,
    Section,
    SectionKind,
    Server,
    SourceName,
)


def _make_license(**kw) -> License:
    base = dict(raw="cc-by", spdx_id="CC-BY-4.0", redistributable=True, requires_attribution=True)
    base.update(kw)
    return License(**base)


def test_license_defaults_fail_safe():
    lic = License(raw="???")
    assert lic.redistributable is False
    assert lic.requires_attribution is True
    assert lic.spdx_id is None


def test_license_is_frozen():
    lic = _make_license()
    with pytest.raises(Exception):
        lic.redistributable = False  # type: ignore[misc]


def test_preprint_roundtrips_to_jsonl():
    p = Preprint(
        doi="10.1101/2024.01.01.123456",
        version=2,
        server=Server.BIORXIV,
        title="A study",
        authors=["Ada Lovelace", "Alan Turing"],
        date=dt.date(2024, 1, 1),
        category="neuroscience",
        abstract="We did science.",
        license=_make_license(),
        published_doi="10.1000/xyz",
        provenance={"source": "biorxiv_api"},
    )
    dumped = p.model_dump(mode="json")
    # A JSONL line must survive an orjson round-trip unchanged.
    line = orjson.dumps(dumped)
    back = orjson.loads(line)
    assert back == dumped
    assert back["date"] == "2024-01-01"  # date serialized as ISO string
    assert back["server"] == "biorxiv"
    reloaded = Preprint.model_validate(back)
    assert reloaded == p


def test_preprint_minimal_requires_only_doi_and_server():
    p = Preprint(doi="10.1101/x", server="medrxiv")
    assert p.server is Server.MEDRXIV
    assert p.authors == []
    assert p.license is None


def test_chunk_roundtrips_to_jsonl():
    c = Chunk(
        doi="10.1101/2024.01.01.123456",
        version=1,
        chunk_id="10.1101/2024.01.01.123456:1:3:0",
        section_kind=SectionKind.METHODS,
        text="We used a microscope.",
        token_count=5,
        char_start=0,
        char_end=21,
        license=_make_license(),
        source=SourceName.EUROPEPMC,
    )
    dumped = c.model_dump(mode="json")
    back = orjson.loads(orjson.dumps(dumped))
    assert back == dumped
    assert back["section_kind"] == "methods"
    assert back["source"] == "europepmc"
    assert Chunk.model_validate(back) == c


def test_section_defaults():
    s = Section(id="1", order=1)
    assert s.kind is SectionKind.OTHER
    assert s.text == ""
    assert s.title is None


def test_fulltext_composition():
    p = Preprint(doi="10.1101/x", server=Server.BIORXIV)
    ft = FullText(
        preprint=p,
        sections=[
            Section(id="1", kind=SectionKind.ABSTRACT, order=1, text="abs"),
            Section(id="2", kind=SectionKind.INTRO, title="Introduction", order=2, text="intro"),
        ],
        retrieved_from=SourceName.EUROPEPMC,
        raw_ref="sha256:deadbeef",
    )
    dumped = ft.model_dump(mode="json")
    assert dumped["retrieved_from"] == "europepmc"
    assert [s["kind"] for s in dumped["sections"]] == ["abstract", "intro"]
    assert FullText.model_validate(dumped) == ft


def test_searchhit_optional_ids():
    hit = SearchHit(title="T", source=SourceName.OPENALEX, has_fulltext=True, score=1.5)
    assert hit.doi is None
    assert hit.openalex_id is None
    dumped = hit.model_dump(mode="json")
    assert dumped["source"] == "openalex"
    assert dumped["has_fulltext"] is True


def test_enum_values_are_stable_strings():
    # These string values are the on-disk contract for JSONL corpora.
    assert [k.value for k in SectionKind] == [
        "abstract",
        "intro",
        "methods",
        "results",
        "discussion",
        "other",
    ]
    assert [s.value for s in Server] == ["biorxiv", "medrxiv", "arxiv"]
    assert set(x.value for x in SourceName) == {
        "openalex",
        "europepmc",
        "biorxiv_api",
        "biorxiv_s3",
        "biorxiv_html",
        "arxiv_api",
        "arxiv_html",
    }
