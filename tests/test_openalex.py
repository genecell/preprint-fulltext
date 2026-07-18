"""Tests for sources/openalex.py (respx-mocked)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from preprint_fulltext.config import Settings
from preprint_fulltext.core import http as http_mod
from preprint_fulltext.sources.base import SourceError
from preprint_fulltext.sources.openalex import BASE, OpenAlex, reconstruct_abstract

from .factories import read_fixture

SEARCH = json.loads(read_fixture("openalex_search.json"))
WORK = json.loads(read_fixture("openalex_work.json"))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http_mod, "_sleep", lambda s: None)


def _oa(key="k-123", email="t@example.org"):
    return OpenAlex(settings=Settings(openalex_api_key=key, contact_email=email))


def test_reconstruct_abstract():
    inv = {"Hello": [0], "world": [1], "again": [2, 4], "world!": [3]}
    assert reconstruct_abstract(inv) == "Hello world again world! again"
    assert reconstruct_abstract(None) is None
    assert reconstruct_abstract({}) is None


def test_missing_key_raises_with_hint():
    oa = OpenAlex(settings=Settings(openalex_api_key=None))
    with pytest.raises(SourceError) as ei:
        list(oa.search("widgets"))
    assert "2026-02-13" in str(ei.value)


@respx.mock
def test_search_parses_hits_and_has_fulltext():
    route = respx.get(f"{BASE}/works").mock(return_value=httpx.Response(200, json=SEARCH))
    hits = list(_oa().search("widgets", limit=25))
    assert [h.openalex_id for h in hits] == ["W111", "W222"]
    assert hits[0].doi == "10.1101/2024.01.15.575000"
    assert hits[0].has_fulltext is True
    assert hits[1].has_fulltext is False
    assert hits[0].oa_url.endswith(".full.pdf")
    assert hits[0].snippet == "We study widgets here"
    # api_key sent as a param.
    assert "api_key=k-123" in str(route.calls[0].request.url)


@respx.mock
def test_search_sends_mailto_and_search_param():
    route = respx.get(f"{BASE}/works").mock(return_value=httpx.Response(200, json=SEARCH))
    list(_oa().search("crispr", limit=1))
    url = str(route.calls[0].request.url)
    assert "mailto=t%40example.org" in url or "mailto=t@example.org" in url
    assert "search=crispr" in url


@respx.mock
def test_409_raises_key_hint():
    respx.get(f"{BASE}/works").mock(return_value=httpx.Response(409, json={"error": "auth"}))
    with pytest.raises(SourceError):
        list(_oa().search("x"))


@respx.mock
def test_get_metadata_uses_singleton_and_reconstructs_abstract():
    route = respx.get(url__regex=rf"{BASE}/works/https").mock(
        return_value=httpx.Response(200, json=WORK)
    )
    p = _oa().get_metadata("10.1101/2024.01.15.575000")
    assert p.abstract == "Widgets are studied carefully"
    assert p.provenance["openalex_id"] == "W111"
    assert "/works/https://doi.org/" in str(route.calls[0].request.url)


@respx.mock
def test_search_field_title_uses_filter():
    route = respx.get(f"{BASE}/works").mock(return_value=httpx.Response(200, json=SEARCH))
    list(_oa().search("satb2", limit=1, field="title"))
    url = str(route.calls[0].request.url)
    assert "title.search%3Asatb2" in url or "title.search:satb2" in url
    assert "search=satb2" not in url  # title field must NOT use the free search param


@respx.mock
def test_discover_builds_date_filter():
    import datetime as dt

    from preprint_fulltext.sources.base import DiscoverQuery

    route = respx.get(f"{BASE}/works").mock(return_value=httpx.Response(200, json=SEARCH))
    list(_oa().discover(DiscoverQuery(query="widgets", from_date=dt.date(2024, 1, 1), limit=1)))
    url = str(route.calls[0].request.url)
    assert "from_publication_date%3A2024-01-01" in url or "from_publication_date:2024-01-01" in url
