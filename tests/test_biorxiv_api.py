"""Tests for sources/biorxiv_api.py (respx-mocked)."""

from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest
import respx

from preprint_fulltext.config import Settings
from preprint_fulltext.core import http as http_mod
from preprint_fulltext.core.models import Server
from preprint_fulltext.sources.biorxiv_api import BASE, BiorxivAPI

from .factories import read_fixture

DETAILS = json.loads(read_fixture("biorxiv_details.json"))
DOI = "10.1101/2024.01.15.575000"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http_mod, "_sleep", lambda s: None)


def _api():
    return BiorxivAPI(settings=Settings(contact_email="t@example.org"))


@respx.mock
def test_get_metadata_parses_preprint():
    respx.get(f"{BASE}/details/biorxiv/{DOI}").mock(return_value=httpx.Response(200, json=DETAILS))
    p = _api().get_metadata(DOI, server="biorxiv")
    assert p.doi == DOI
    assert p.title == "A Test Preprint on Widgets"
    assert p.authors == ["Lovelace, A.", "Turing, A."]
    assert p.date == dt.date(2024, 1, 15)
    assert p.category == "neuroscience"
    assert p.abstract == "We study widgets."
    assert p.license.spdx_id == "CC-BY"
    assert p.published_doi == "10.1000/widgets.published"


@respx.mock
def test_get_metadata_tries_both_servers_when_unknown():
    # biorxiv 404s (empty), medrxiv returns the record.
    respx.get(f"{BASE}/details/biorxiv/{DOI}").mock(
        return_value=httpx.Response(200, json={"collection": []})
    )
    med = json.loads(json.dumps(DETAILS))
    med["collection"][0]["server"] = "medrxiv"
    respx.get(f"{BASE}/details/medrxiv/{DOI}").mock(return_value=httpx.Response(200, json=med))
    p = _api().get_metadata(DOI)
    assert p is not None
    assert p.server is Server.MEDRXIV


@respx.mock
def test_published_doi_helper():
    respx.get(f"{BASE}/details/biorxiv/{DOI}").mock(return_value=httpx.Response(200, json=DETAILS))
    assert _api().published_doi(DOI, server="biorxiv") == "10.1000/widgets.published"


@respx.mock
def test_published_na_becomes_none():
    d = json.loads(json.dumps(DETAILS))
    d["collection"][0]["published"] = "NA"
    respx.get(f"{BASE}/details/biorxiv/{DOI}").mock(return_value=httpx.Response(200, json=d))
    assert _api().get_metadata(DOI, server="biorxiv").published_doi is None


@respx.mock
def test_get_versions_and_latest():
    two = json.loads(json.dumps(DETAILS))
    two["collection"] = [
        {**DETAILS["collection"][0], "version": "1", "date": "2026-01-29"},
        {**DETAILS["collection"][0], "version": "2", "date": "2026-06-08"},
    ]
    respx.get(f"{BASE}/details/biorxiv/{DOI}").mock(return_value=httpx.Response(200, json=two))
    versions = _api().get_versions(DOI, server="biorxiv")
    assert [p.version for p in versions] == [1, 2]
    assert _api().latest_version(DOI, server="biorxiv") == 2
    assert _api().get_metadata(DOI, server="biorxiv").version == 2  # latest


@respx.mock
def test_iter_window_paginates():
    page = json.loads(json.dumps(DETAILS))
    page["messages"] = [{"status": "ok", "total": 1}]
    respx.get(url__regex=rf"{BASE}/details/biorxiv/2024-01-01/2024-01-31/0").mock(
        return_value=httpx.Response(200, json=page)
    )
    got = list(_api().iter_window("biorxiv", dt.date(2024, 1, 1), dt.date(2024, 1, 31)))
    assert len(got) == 1
    assert got[0].doi == DOI
