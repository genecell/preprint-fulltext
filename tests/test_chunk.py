"""Tests for core/chunk.py."""

from __future__ import annotations

import pytest

from preprint_fulltext.config import Settings
from preprint_fulltext.core.chunk import chunk_fulltext
from preprint_fulltext.core.models import (
    FullText,
    License,
    Preprint,
    Section,
    SectionKind,
    Server,
    SourceName,
)

CCBY = License(raw="cc-by", spdx_id="CC-BY-4.0", redistributable=True, requires_attribution=True)


def _toklen(text: str, spec: str = "tiktoken:cl100k_base") -> int:
    import tiktoken

    return len(tiktoken.get_encoding(spec.split(":")[1]).encode(text))


def _ft(sections: list[Section], version: int | None = 1) -> FullText:
    return FullText(
        preprint=Preprint(doi="10.1101/x", version=version, server=Server.BIORXIV, license=CCBY),
        sections=sections,
        retrieved_from=SourceName.EUROPEPMC,
    )


def _settings(**kw) -> Settings:
    base = dict(chunk_tokens=20, chunk_overlap=5)
    base.update(kw)
    return Settings(**base)


def test_never_exceeds_chunk_tokens():
    long = " ".join(f"word{i}" for i in range(500))
    ft = _ft([Section(id="1", kind=SectionKind.RESULTS, order=1, text=long)])
    chunks = chunk_fulltext(ft, settings=_settings(chunk_tokens=20, chunk_overlap=5))
    assert len(chunks) > 1
    for c in chunks:
        assert c.token_count <= 20
        assert _toklen(c.text) <= 20


def test_char_offsets_slice_back_to_section_text():
    text = " ".join(f"token{i}" for i in range(120))
    section = Section(id="1", kind=SectionKind.METHODS, order=1, text=text)
    ft = _ft([section])
    for c in chunk_fulltext(ft, settings=_settings()):
        assert c.text == text[c.char_start:c.char_end]


def test_no_chunk_crosses_section_boundary_by_default():
    s1 = Section(id="1", kind=SectionKind.INTRO, order=1, text=" ".join(["aaa"] * 60))
    s2 = Section(id="2", kind=SectionKind.RESULTS, order=2, text=" ".join(["bbb"] * 60))
    chunks = chunk_fulltext(_ft([s1, s2]), settings=_settings())
    for c in chunks:
        assert not ("aaa" in c.text and "bbb" in c.text)
    kinds = {c.section_kind for c in chunks}
    assert kinds == {SectionKind.INTRO, SectionKind.RESULTS}


def test_overlap_within_section_only():
    text = " ".join(f"w{i}" for i in range(100))
    ft = _ft([Section(id="1", kind=SectionKind.RESULTS, order=1, text=text)])
    chunks = chunk_fulltext(ft, settings=_settings(chunk_tokens=20, chunk_overlap=5))
    # Consecutive chunks should overlap in characters (end of one > start of next).
    for a, b in zip(chunks, chunks[1:]):
        assert b.char_start < a.char_end  # overlapping window


def test_chunk_id_deterministic_and_stable():
    text = " ".join(f"w{i}" for i in range(80))
    ft = _ft([Section(id="1", kind=SectionKind.RESULTS, order=3, text=text)])
    ids1 = [c.chunk_id for c in chunk_fulltext(ft, settings=_settings())]
    ids2 = [c.chunk_id for c in chunk_fulltext(ft, settings=_settings())]
    assert ids1 == ids2
    assert ids1[0] == "10.1101/x:1:3:0"
    assert len(set(ids1)) == len(ids1)


def test_version_none_renders_na_in_id():
    ft = _ft([Section(id="1", kind=SectionKind.RESULTS, order=1, text="hello world foo bar")], version=None)
    c = chunk_fulltext(ft, settings=_settings())[0]
    assert c.chunk_id.startswith("10.1101/x:na:1:0")


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_empty_or_whitespace_section_yields_no_chunks(text):
    ft = _ft([Section(id="1", kind=SectionKind.OTHER, order=1, text=text)])
    assert chunk_fulltext(ft, settings=_settings()) == []


def test_license_and_source_copied_onto_each_chunk():
    ft = _ft([Section(id="1", kind=SectionKind.RESULTS, order=1, text="a b c d e f g")])
    for c in chunk_fulltext(ft, settings=_settings()):
        assert c.license == CCBY
        assert c.source is SourceName.EUROPEPMC


def test_cross_section_true_can_span_sections():
    s1 = Section(id="1", kind=SectionKind.INTRO, order=1, text=" ".join(["aaa"] * 8))
    s2 = Section(id="2", kind=SectionKind.RESULTS, order=2, text=" ".join(["bbb"] * 8))
    chunks = chunk_fulltext(_ft([s1, s2]), settings=_settings(chunk_tokens=40, chunk_overlap=0, cross_section=True))
    # With a big window, one chunk should contain text from both sections.
    assert any("aaa" in c.text and "bbb" in c.text for c in chunks)
