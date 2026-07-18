"""Tests for sources/europepmc.py (respx-mocked, offline)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from preprint_fulltext.config import Settings
from preprint_fulltext.core import http as http_mod
from preprint_fulltext.core.models import Server, SourceName
from preprint_fulltext.sources.europepmc import BASE, EuropePMC

from .factories import read_fixture

DOI = "10.1101/2024.01.15.575000"
RESOLVE = json.loads(read_fixture("epmc_resolve.json"))
SAMPLE_XML = read_fixture("jats_biorxiv_sample.xml")


@pytest.fixture
def epmc():
    return EuropePMC(settings=Settings(contact_email="test@example.org"))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http_mod, "_sleep", lambda s: None)


@respx.mock
def test_resolve_doi_to_ppr(epmc):
    respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=RESOLVE))
    assert epmc.resolve_ppr_id(DOI) == "PPR100001"


@respx.mock
def test_get_fulltext_returns_structured_sections(epmc):
    respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=RESOLVE))
    respx.get(f"{BASE}/PPR100001/fullTextXML").mock(
        return_value=httpx.Response(200, content=SAMPLE_XML)
    )
    ft = epmc.get_fulltext(DOI)
    assert ft is not None
    assert ft.retrieved_from is SourceName.EUROPEPMC
    assert ft.preprint.server is Server.BIORXIV
    assert ft.sections[0].kind.value == "abstract"
    assert any(s.kind.value == "methods" for s in ft.sections)
    assert ft.preprint.license.spdx_id == "CC-BY-4.0"


@respx.mock
def test_get_fulltext_404_returns_none(epmc):
    respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=RESOLVE))
    respx.get(f"{BASE}/PPR100001/fullTextXML").mock(return_value=httpx.Response(404))
    assert epmc.get_fulltext(DOI) is None


@respx.mock
def test_get_fulltext_unresolvable_doi_returns_none(epmc):
    respx.get(f"{BASE}/search").mock(
        return_value=httpx.Response(200, json={"resultList": {"result": []}})
    )
    assert epmc.get_fulltext("10.1101/does.not.exist") is None


@respx.mock
def test_search_cursor_pagination_advances(epmc):
    page1 = json.loads(read_fixture("epmc_search_page1.json"))
    page2 = json.loads(read_fixture("epmc_search_page2.json"))
    route = respx.get(f"{BASE}/search")
    route.side_effect = [
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ]
    hits = list(epmc.search("widgets", limit=3))
    assert [h.doi for h in hits] == [
        "10.1101/2024.01.15.575000",
        "10.1101/2024.03.03.111111",
        "10.1101/2024.04.04.222222",
    ]
    assert hits[0].has_fulltext is True
    assert hits[1].has_fulltext is False
    # Two pages were fetched (cursor advanced from '*' to CURSOR2).
    assert route.call_count == 2


@respx.mock
def test_429_is_retried_then_succeeds(epmc):
    calls = {"n": 0}

    def responder(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json=RESOLVE)

    respx.get(f"{BASE}/search").mock(side_effect=responder)
    assert epmc.resolve_ppr_id(DOI) == "PPR100001"
    assert calls["n"] == 2  # retried exactly once


@respx.mock
def test_search_field_title_builds_title_query(epmc):
    page = json.loads(read_fixture("epmc_search_page1.json"))
    route = respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=page))
    list(epmc.search("satb2", limit=1, field="title"))
    url = str(route.calls[0].request.url)
    assert "TITLE" in url and "SRC%3APPR" in url.replace("SRC:PPR", "SRC%3APPR")


@respx.mock
def test_search_field_author(epmc):
    page = json.loads(read_fixture("epmc_search_page1.json"))
    route = respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=page))
    list(epmc.search("Dai", limit=1, field="author"))
    assert "AUTH" in str(route.calls[0].request.url)


def test_field_query_semantics():
    # author -> quoted phrase; title multi-word -> term-AND; fulltext -> raw.
    assert EuropePMC._field_query("Gord Fishell", "author") == 'AUTH:"Gord Fishell"'
    assert EuropePMC._field_query("Fezf2", "title") == 'TITLE:"Fezf2"'
    assert EuropePMC._field_query("Fezf2 cortex", "title") == '(TITLE:"Fezf2" AND TITLE:"cortex")'
    assert EuropePMC._field_query("brain organoid", "abstract") == '(ABSTRACT:"brain" AND ABSTRACT:"organoid")'
    assert EuropePMC._field_query("crispr", "fulltext") == "crispr"


@respx.mock
def test_medrxiv_detected_from_xml(epmc):
    medxml = SAMPLE_XML.replace(b"bioRxiv", b"medRxiv")
    respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=RESOLVE))
    respx.get(f"{BASE}/PPR100001/fullTextXML").mock(
        return_value=httpx.Response(200, content=medxml)
    )
    ft = epmc.get_fulltext(DOI)
    assert ft.preprint.server is Server.MEDRXIV
