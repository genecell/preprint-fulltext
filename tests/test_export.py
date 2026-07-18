"""Tests for pipeline/export.py — the compliance gate."""

from __future__ import annotations

from preprint_fulltext.core.models import (
    FullText,
    License,
    Preprint,
    Section,
    SectionKind,
    Server,
    SourceName,
)
from preprint_fulltext.pipeline.export import ExportMode, Gate

CCBY = License(raw="cc-by", spdx_id="CC-BY-4.0", redistributable=True, requires_attribution=True)
ARR = License(raw="all rights reserved", spdx_id=None, redistributable=False)


def _ft(license_: License) -> FullText:
    return FullText(
        preprint=Preprint(doi="10.1101/x", server=Server.BIORXIV, title="T",
                          abstract="an abstract", license=license_),
        sections=[
            Section(id="1", kind=SectionKind.ABSTRACT, order=1, text="an abstract"),
            Section(id="2", kind=SectionKind.RESULTS, order=2, text="secret body text"),
        ],
        retrieved_from=SourceName.BIORXIV_S3,
        raw_ref="s3://bucket/key.meca",
    )


def test_analysis_mode_passes_through_and_reminds_once():
    seen = []
    gate = Gate(ExportMode.ANALYSIS, on_reminder=seen.append)
    r1 = gate.apply(_ft(ARR))
    r2 = gate.apply(_ft(CCBY))
    assert r1.degraded is False and r2.degraded is False
    assert r1.fulltext.sections[1].text == "secret body text"  # body preserved
    assert len(seen) == 1  # reminder printed exactly once


def test_redistribution_passes_ccby_with_body():
    gate = Gate(ExportMode.REDISTRIBUTION)
    r = gate.apply(_ft(CCBY))
    assert r.degraded is False
    assert any(s.text == "secret body text" for s in r.fulltext.sections)


def test_redistribution_degrades_arr_to_stub_no_body():
    gate = Gate(ExportMode.REDISTRIBUTION)
    r = gate.apply(_ft(ARR))
    assert r.degraded is True
    assert r.fulltext.sections == []  # NO body text
    assert r.fulltext.preprint.abstract is None
    assert r.fulltext.preprint.title == "T"  # metadata retained
    assert r.fulltext.preprint.doi == "10.1101/x"
    assert r.fulltext.preprint.provenance["oa_url"] == "s3://bucket/key.meca"


def test_unknown_license_is_degraded():
    gate = Gate(ExportMode.REDISTRIBUTION)
    unknown = License(raw="weird", spdx_id=None, redistributable=False)
    assert gate.apply(_ft(unknown)).degraded is True
