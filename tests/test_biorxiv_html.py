"""Tests for sources/biorxiv_html.py — opt-in HTML parser + source (respx-mocked)."""

from __future__ import annotations

import httpx
import pytest
import respx

from preprint_fulltext.config import Settings
from preprint_fulltext.core import http as http_mod
from preprint_fulltext.core.models import Server, SourceName
from preprint_fulltext.sources.biorxiv_api import BASE as API_BASE
from preprint_fulltext.sources.biorxiv_html import BiorxivHTML, parse_biorxiv_html

from .factories import read_fixture

PAGE = read_fixture("biorxiv_page.html")
DOI = "10.64898/2026.06.13.731750"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http_mod, "_sleep", lambda s: None)


# --- pure parser --------------------------------------------------------------
def test_parse_metadata_from_citation_meta():
    art = parse_biorxiv_html(PAGE)
    assert art.title == "Cognitive function depends upon Satb2 gene dosage"
    assert art.doi == DOI
    assert art.authors == ["Thomas S. Finn", "Min Dai"]


def test_parse_sections_and_kinds():
    art = parse_biorxiv_html(PAGE)
    by_title = {s.title: s.kind for s in art.sections}
    assert by_title["Introduction"] == "intro"
    assert by_title["Results"] == "results"
    assert by_title["Method Details"] == "methods"
    assert by_title["SATB2 binds promoters"] == "results"  # subsection inherits parent kind


def test_abstract_extracted_from_section_not_meta():
    art = parse_biorxiv_html(PAGE)
    assert art.abstract.startswith("SATB2 dosage matters")
    assert "Meta-tag abstract fallback" not in art.abstract


def test_citation_links_figures_and_refs_stripped():
    art = parse_biorxiv_html(PAGE)
    blob = (art.abstract or "") + " ".join(s.text for s in art.sections)
    assert "FIGURE_CAPTION_SHOULD_BE_DROPPED" not in blob
    assert "REFERENCE_TEXT_SHOULD_BE_STRIPPED" not in blob
    # The inline citation marker text ("1", "2" from <a class="xref-bibr">) is gone.
    assert "SATB2 dosage matters for cognition." in art.abstract


def test_orders_renumbered_contiguously():
    art = parse_biorxiv_html(PAGE)
    assert [s.order for s in art.sections] == list(range(1, len(art.sections) + 1))


# --- source (network mocked) --------------------------------------------------
def _details_cc_no():
    return {
        "messages": [{"status": "ok", "total": 1}],
        "collection": [{"doi": DOI, "title": "T", "authors": "Finn, T.",
                        "date": "2026-06-16", "version": "1", "license": "cc_no",
                        "published": "NA", "server": "biorxiv"}],
    }


@respx.mock
def test_get_fulltext_defaults_to_latest_unversioned_url():
    # No version -> the un-versioned URL (which the site redirects to the latest version).
    url = f"https://www.biorxiv.org/content/{DOI}.full"
    respx.get(url).mock(return_value=httpx.Response(200, content=PAGE))
    respx.get(f"{API_BASE}/details/biorxiv/{DOI}").mock(
        return_value=httpx.Response(200, json=_details_cc_no())
    )
    ft = BiorxivHTML(Settings(contact_email="t@example.org")).get_fulltext(DOI, server="biorxiv")
    assert ft is not None
    assert ft.retrieved_from is SourceName.BIORXIV_HTML
    assert ft.preprint.server is Server.BIORXIV
    assert ft.raw_ref == url
    # cc_no -> non-redistributable (fail-safe holds via the JATS/text license path).
    assert ft.preprint.license.redistributable is False
    assert ft.sections[0].kind.value == "abstract"


@respx.mock
def test_get_fulltext_specific_version_uses_versioned_url_and_records_it():
    url = f"https://www.biorxiv.org/content/{DOI}v2.full"
    respx.get(url).mock(return_value=httpx.Response(200, content=PAGE))
    respx.get(f"{API_BASE}/details/biorxiv/{DOI}").mock(
        return_value=httpx.Response(200, json=_details_cc_no())
    )
    ft = BiorxivHTML(Settings()).get_fulltext(DOI, version=2, server="biorxiv")
    assert ft is not None
    assert ft.preprint.version == 2
    assert ft.raw_ref == url


@respx.mock
def test_get_fulltext_404_returns_none():
    url = f"https://www.biorxiv.org/content/{DOI}.full"
    respx.get(url).mock(return_value=httpx.Response(404))
    assert BiorxivHTML(Settings()).get_fulltext(DOI) is None
