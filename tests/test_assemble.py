"""Tests for core/assemble.py — parser output -> canonical FullText."""

from __future__ import annotations

from preprint_fulltext.core.assemble import build_fulltext
from preprint_fulltext.core.jats import parse_jats
from preprint_fulltext.core.models import SectionKind, SourceName

from .factories import read_fixture

SAMPLE = read_fixture("jats_biorxiv_sample.xml")
ARR = read_fixture("jats_biorxiv_arr.xml")


def _build(xml, **kw):
    parsed = parse_jats(xml)
    return build_fulltext(
        parsed, doi=kw.pop("doi", "10.1101/2024.01.15.575000"),
        server="biorxiv", source=SourceName.EUROPEPMC, version=1, **kw
    )


def test_abstract_becomes_first_section():
    ft = _build(SAMPLE)
    assert ft.sections[0].kind is SectionKind.ABSTRACT
    assert ft.sections[0].order == 1
    assert ft.sections[0].id == "1"


def test_orders_are_unique_and_contiguous():
    ft = _build(SAMPLE)
    orders = [s.order for s in ft.sections]
    assert orders == list(range(1, len(orders) + 1))
    assert [s.id for s in ft.sections] == [str(o) for o in orders]


def test_license_mapped_onto_preprint():
    ft = _build(SAMPLE)
    assert ft.preprint.license.spdx_id == "CC-BY-4.0"
    assert ft.preprint.license.redistributable is True


def test_arr_license_non_redistributable():
    ft = _build(ARR, doi="10.1101/2024.02.20.999999")
    assert ft.preprint.license.redistributable is False


def test_preprint_metadata_carried():
    ft = _build(SAMPLE, provenance={"source": "europepmc"})
    assert ft.preprint.title == "A Test Preprint on Widgets"
    assert ft.preprint.authors == ["Ada Lovelace", "Alan Turing"]
    assert ft.retrieved_from is SourceName.EUROPEPMC


def test_body_kinds_preserved():
    ft = _build(SAMPLE)
    kinds = [s.kind.value for s in ft.sections]
    assert kinds[0] == "abstract"
    assert "intro" in kinds and "methods" in kinds and "results" in kinds
