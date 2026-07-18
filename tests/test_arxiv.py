"""Tests for sources/arxiv.py (ArxivAPI) + sources/arxiv_html.py (respx-mocked)."""

from __future__ import annotations

import httpx
import pytest
import respx

from preprint_fulltext.config import Settings
from preprint_fulltext.core import http as http_mod
from preprint_fulltext.core.models import Server, SourceName
from preprint_fulltext.sources.arxiv import ArxivAPI
from preprint_fulltext.sources.arxiv_html import ArxivHTML, parse_latexml_html

from .factories import read_fixture

ATOM = read_fixture("arxiv_api.xml")
PAGE = read_fixture("arxiv_latexml.html")
AID = "2401.10515"
API = "https://export.arxiv.org/api/query"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http_mod, "_sleep", lambda s: None)


def _api():
    return ArxivAPI(Settings(contact_email="t@example.org"))


# --- ArxivAPI -----------------------------------------------------------------
@respx.mock
def test_get_metadata_parses_atom():
    respx.get(API).mock(return_value=httpx.Response(200, content=ATOM))
    p = _api().get_metadata(AID)
    assert p.doi == "10.48550/arXiv.2401.10515"
    assert p.server is Server.ARXIV
    assert p.version == 2                      # from <id>…v2</id>
    assert p.authors == ["Ada Lovelace", "Alan Turing"]
    assert p.category == "cs.NE"
    assert p.published_doi == "10.1000/journal.widgets.2024"
    assert "coevolutionary" in p.abstract.lower()


@respx.mock
def test_latest_version():
    respx.get(API).mock(return_value=httpx.Response(200, content=ATOM))
    assert _api().latest_version(AID) == 2


@respx.mock
def test_search_builds_field_prefix_and_parses_hits():
    route = respx.get(API).mock(return_value=httpx.Response(200, content=ATOM))
    hits = list(_api().search("widgets", limit=1, field="title"))
    assert len(hits) == 1
    assert hits[0].source is SourceName.ARXIV_API
    assert hits[0].doi == "10.48550/arXiv.2401.10515"
    assert hits[0].has_fulltext is True
    assert "search_query=ti%3Awidgets" in str(route.calls[0].request.url)


# --- LaTeXML parser -----------------------------------------------------------
def test_parse_latexml_sections_and_kinds():
    art = parse_latexml_html(PAGE)
    assert art.title == "Coevolutionary Computation for Widget Optimization"
    by_title = {s.title: s.kind for s in art.sections}
    assert by_title["Introduction"] == "intro"
    assert by_title["Methods"] == "methods"
    assert by_title["Results"] == "results"
    assert by_title["Sample preparation"] == "methods"   # subsection inherits parent kind


def test_parse_latexml_strips_math_figures_refs_and_section_numbers():
    art = parse_latexml_html(PAGE)
    blob = (art.abstract or "") + " ".join(s.text for s in art.sections)
    assert "MATH_SHOULD_DROP" not in blob
    assert "FIGURE_CAPTION_DROP" not in blob
    assert "REFERENCE_TEXT_SHOULD_BE_STRIPPED" not in blob
    assert all(not s.title[0].isdigit() for s in art.sections if s.title)  # numbers stripped


def test_parse_latexml_abstract_and_citation_tail_preserved():
    art = parse_latexml_html(PAGE)
    assert art.abstract.startswith("We present a coevolutionary")
    # the <cite> marker is dropped but the following prose ("that scales…") is kept
    assert "that scales across conditions" in art.abstract


# --- ArxivHTML source ---------------------------------------------------------
@respx.mock
def test_get_fulltext_native_html():
    respx.get(f"https://arxiv.org/html/{AID}").mock(return_value=httpx.Response(200, content=PAGE))
    respx.get(f"https://arxiv.org/abs/{AID}").mock(return_value=httpx.Response(200, content=b"no license here"))
    respx.get(API).mock(return_value=httpx.Response(200, content=ATOM))
    ft = ArxivHTML(Settings()).get_fulltext(AID)
    assert ft is not None
    assert ft.retrieved_from is SourceName.ARXIV_HTML
    assert ft.preprint.doi == "10.48550/arXiv.2401.10515"
    assert ft.preprint.version == 2                       # enriched from the API
    assert ft.preprint.provenance["backend"] == "native"
    assert any(s.kind.value == "results" for s in ft.sections)


@respx.mock
def test_get_fulltext_falls_back_to_ar5iv():
    respx.get(f"https://arxiv.org/html/{AID}").mock(return_value=httpx.Response(404))
    respx.get(f"https://ar5iv.labs.arxiv.org/html/{AID}").mock(
        return_value=httpx.Response(200, content=PAGE)
    )
    respx.get(f"https://arxiv.org/abs/{AID}").mock(return_value=httpx.Response(200, content=b"x"))
    respx.get(API).mock(return_value=httpx.Response(200, content=ATOM))
    ft = ArxivHTML(Settings()).get_fulltext(AID)
    assert ft is not None
    assert ft.preprint.provenance["backend"] == "ar5iv"


def test_field_query_semantics():
    assert ArxivAPI._field_query("diffusion model", "title") == "(ti:diffusion AND ti:model)"
    assert ArxivAPI._field_query("brain", "abstract") == "abs:brain"
    assert ArxivAPI._field_query("Yann LeCun", "author") == 'au:"Yann LeCun"'
    assert ArxivAPI._field_query("crispr", "fulltext") == "all:crispr"


@respx.mock
def test_cli_get_arxiv_id_routes_to_arxiv():
    from typer.testing import CliRunner

    from preprint_fulltext.cli import app

    respx.get(f"https://arxiv.org/html/{AID}").mock(return_value=httpx.Response(200, content=PAGE))
    respx.get(f"https://arxiv.org/abs/{AID}").mock(return_value=httpx.Response(200, content=b"x"))
    respx.get(API).mock(return_value=httpx.Response(200, content=ATOM))
    r = CliRunner().invoke(app, ["get", "arXiv:2401.10515", "--markdown"])
    assert r.exit_code == 0, r.output
    assert "## Introduction" in r.output and "## Results" in r.output


@respx.mock
def test_get_fulltext_license_detected_from_abs_page():
    respx.get(f"https://arxiv.org/html/{AID}").mock(return_value=httpx.Response(200, content=PAGE))
    respx.get(f"https://arxiv.org/abs/{AID}").mock(return_value=httpx.Response(
        200, content=b'<a href="http://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>'))
    respx.get(API).mock(return_value=httpx.Response(200, content=ATOM))
    ft = ArxivHTML(Settings()).get_fulltext(AID)
    assert ft.preprint.license.spdx_id == "CC-BY-4.0"
    assert ft.preprint.license.redistributable is True
