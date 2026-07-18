"""Tests for core/jats.py — the shared parser (highest priority)."""

from __future__ import annotations

from preprint_fulltext.core.jats import parse_jats

from .factories import read_fixture

SAMPLE = read_fixture("jats_biorxiv_sample.xml")
ARR = read_fixture("jats_biorxiv_arr.xml")


def test_parses_title_authors_abstract():
    art = parse_jats(SAMPLE)
    assert art.title == "A Test Preprint on Widgets"
    assert art.authors == ["Ada Lovelace", "Alan Turing"]
    assert art.abstract is not None
    assert "widgets" in art.abstract.lower()


def test_graphical_abstract_is_skipped():
    art = parse_jats(SAMPLE)
    assert "GRAPHICAL_ABSTRACT_SHOULD_BE_SKIPPED" not in (art.abstract or "")


def test_xref_stripped_from_abstract():
    art = parse_jats(SAMPLE)
    # The [1] citation marker (an <xref>) must be gone, and no dangling space.
    assert "[1]" not in art.abstract
    assert "Our approach works" in art.abstract


def test_sections_present_and_order_monotonic():
    art = parse_jats(SAMPLE)
    orders = [s.order for s in art.sections]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)  # unique
    titles = [s.title for s in art.sections]
    assert "Introduction" in titles
    assert "Sample preparation" in titles  # nested sec flattened


def test_kind_mapping_from_sectype_and_title():
    art = parse_jats(SAMPLE)
    by_title = {s.title: s.kind for s in art.sections}
    assert by_title["Introduction"] == "intro"
    assert by_title["Materials and Methods"] == "methods"
    assert by_title["Results"] == "results"
    assert by_title["Discussion and Conclusion"] == "discussion"


def test_nested_sec_inherits_parent_kind():
    art = parse_jats(SAMPLE)
    prep = next(s for s in art.sections if s.title == "Sample preparation")
    assert prep.kind == "methods"  # inherited; its own title has no keyword


def test_formulae_and_xref_dropped_from_body_by_default():
    art = parse_jats(SAMPLE)
    results = next(s for s in art.sections if s.title == "Results")
    assert "DISP_FORMULA_SHOULD_BE_DROPPED" not in results.text
    assert "INLINE_FORMULA_DROPPED" not in results.text
    assert "effect size was large" in results.text


def test_tables_dropped_by_default_kept_with_flag():
    default = parse_jats(SAMPLE)
    methods_default = next(s for s in default.sections if s.title == "Materials and Methods")
    assert "TABLE_CELL_TEXT_42" not in methods_default.text

    kept = parse_jats(SAMPLE, keep_tables=True)
    methods_kept = next(s for s in kept.sections if s.title == "Materials and Methods")
    assert "TABLE_CELL_TEXT_42" in methods_kept.text


def test_reference_list_stripped():
    art = parse_jats(SAMPLE)
    blob = " ".join(s.text for s in art.sections) + (art.abstract or "")
    assert "REFERENCE_TEXT_SHOULD_BE_STRIPPED" not in blob


def test_license_extracted_ccby():
    art = parse_jats(SAMPLE)
    assert art.license_raw is not None
    assert art.license_raw["href"] == "http://creativecommons.org/licenses/by/4.0/"
    assert "Attribution" in art.license_raw["text"]


def test_license_extracted_all_rights_reserved():
    art = parse_jats(ARR)
    assert art.license_raw is not None
    assert art.license_raw["href"] is None  # no xlink:href on ARR license
    assert "No reuse allowed" in art.license_raw["text"]


def test_xlink_namespace_read_correctly():
    # href lives in the xlink namespace; the parser must not hardcode a prefix.
    art = parse_jats(SAMPLE)
    assert art.license_raw["href"].startswith("http://creativecommons.org/")


def test_malformed_xml_does_not_raise():
    truncated = SAMPLE[: len(SAMPLE) // 2]
    art = parse_jats(truncated)  # must not raise
    # recover mode yields partial structure; title should still be there.
    assert art.title == "A Test Preprint on Widgets"


def test_empty_and_garbage_inputs():
    assert parse_jats(b"").sections == []
    assert parse_jats(b"not xml at all").sections == []
    assert parse_jats(b"<article></article>").title is None


def test_body_missing_returns_no_sections_no_crash():
    xml = b"<article><front><article-meta><title-group>" \
          b"<article-title>Only Front</article-title></title-group></article-meta></front></article>"
    art = parse_jats(xml)
    assert art.title == "Only Front"
    assert art.sections == []
