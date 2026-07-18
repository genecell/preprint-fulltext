"""Router fallback behaviour."""

from __future__ import annotations

import boto3
import httpx
import pytest
import respx
from moto import mock_aws

from preprint_fulltext.config import Settings
from preprint_fulltext.core import http as http_mod
from preprint_fulltext.pipeline.router import Router
from preprint_fulltext.sources.europepmc import BASE as EPMC

from .factories import make_meca, read_fixture

SAMPLE_XML = read_fixture("jats_biorxiv_sample.xml")
DOI = "10.1101/2024.01.15.575000"
BUCKET = "biorxiv-src-monthly"
KEY = "Current_Content/January_2024/abc.meca"
EMPTY = {"resultList": {"result": []}}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http_mod, "_sleep", lambda s: None)


@respx.mock
def test_epmc_hit_returns_without_touching_s3():
    resolve = {"resultList": {"result": [{"id": "PPR1", "source": "PPR", "doi": DOI}]}}
    respx.get(f"{EPMC}/search").mock(return_value=httpx.Response(200, json=resolve))
    respx.get(f"{EPMC}/PPR1/fullTextXML").mock(
        return_value=httpx.Response(200, content=SAMPLE_XML)
    )
    result = Router(Settings()).get_fulltext(DOI)
    assert result.fulltext is not None
    assert result.tried == ["europepmc"]


@respx.mock
def test_epmc_miss_falls_back_to_s3_when_creds_present():
    respx.get(f"{EPMC}/search").mock(return_value=httpx.Response(200, json=EMPTY))
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        client.put_object(Bucket=BUCKET, Key=KEY, Body=make_meca(SAMPLE_XML))

        router = Router(Settings())
        # Inject the moto-backed S3 source so the fallback uses the seeded bucket.
        from preprint_fulltext.sources.biorxiv_s3 import BiorxivS3

        router._s3 = lambda: BiorxivS3(Settings(), client=client)
        result = router.get_fulltext(DOI, server="biorxiv")
    assert result.fulltext is not None
    assert result.fulltext.preprint.doi == DOI
    assert "biorxiv_s3" in result.tried


def test_explicit_non_latest_version_skips_epmc(monkeypatch):
    # bioRxiv API resolves latest = v2; requesting v1 must NOT use Europe PMC (serves latest).
    class _NoCreds:
        def get_credentials(self):
            return None

    monkeypatch.setattr(boto3, "Session", lambda *a, **k: _NoCreds())

    router = Router(Settings())
    monkeypatch.setattr(router, "_resolve_meta", lambda doi, server: (None, 2))  # latest = 2
    called = {"epmc": False}

    def _boom(*a, **k):
        called["epmc"] = True
        raise AssertionError("Europe PMC must not be consulted for a non-latest version")

    monkeypatch.setattr(router.epmc, "get_fulltext", _boom)
    result = router.get_fulltext(DOI, version=1, server="biorxiv")
    assert called["epmc"] is False
    assert "europepmc" not in result.tried

    # Sanity: for the latest version (2), EPMC IS eligible.
    router2 = Router(Settings())
    monkeypatch.setattr(router2, "_resolve_meta", lambda doi, server: (None, 2))
    monkeypatch.setattr(router2.epmc, "get_fulltext", lambda doi, version=None: None)
    res2 = router2.get_fulltext(DOI, version=2, server="biorxiv")
    assert "europepmc" in res2.tried


def test_arxiv_id_routes_to_arxiv(monkeypatch):
    from preprint_fulltext.core.assemble import build_fulltext
    from preprint_fulltext.core.jats import ParsedArticle, ParsedSection
    from preprint_fulltext.core.models import SourceName

    router = Router(Settings())

    class _Arxiv:
        def get_fulltext(self, arxiv_id, version=None, server=None):
            assert arxiv_id == "2401.10515" and version == 2
            pa = ParsedArticle(title="T", sections=[ParsedSection(order=1, kind="results", title="R", text="x")])
            return build_fulltext(pa, doi="10.48550/arXiv.2401.10515", server="arxiv",
                                  source=SourceName.ARXIV_HTML, version=version)

    monkeypatch.setattr(router, "_arxiv_html", lambda: _Arxiv())
    result = router.get_fulltext("https://arxiv.org/abs/2401.10515v2")
    assert result.tried == ["arxiv_html"]
    assert result.fulltext.retrieved_from is SourceName.ARXIV_HTML
    assert result.fulltext.preprint.version == 2


@respx.mock
def test_epmc_miss_no_creds_reports_reason(monkeypatch):
    respx.get(f"{EPMC}/search").mock(return_value=httpx.Response(200, json=EMPTY))

    class _NoCreds:
        def get_credentials(self):
            return None

    monkeypatch.setattr(boto3, "Session", lambda *a, **k: _NoCreds())
    result = Router(Settings()).get_fulltext(DOI)
    assert result.fulltext is None
    assert "AWS credentials" in result.reason
    assert "--html" in result.reason  # nudges the user toward the opt-in HTML fallback


@respx.mock
def test_allow_html_falls_back_to_html(monkeypatch):
    # EPMC miss, no AWS creds, but --html allowed -> HTML source is tried and succeeds.
    respx.get(f"{EPMC}/search").mock(return_value=httpx.Response(200, json=EMPTY))

    class _NoCreds:
        def get_credentials(self):
            return None

    monkeypatch.setattr(boto3, "Session", lambda *a, **k: _NoCreds())

    from preprint_fulltext.core.assemble import build_fulltext
    from preprint_fulltext.core.jats import ParsedArticle, ParsedSection
    from preprint_fulltext.core.models import SourceName

    def _fake_html():
        class _HTML:
            def get_fulltext(self, doi, version=None, server=None):
                pa = ParsedArticle(title="T", doi=doi,
                                   sections=[ParsedSection(order=1, kind="results", title="Results", text="body")])
                return build_fulltext(pa, doi=doi, server="biorxiv", source=SourceName.BIORXIV_HTML)
        return _HTML()

    router = Router(Settings())
    router._html = _fake_html
    result = router.get_fulltext(DOI, allow_html=True)
    assert result.fulltext is not None
    assert result.fulltext.retrieved_from is SourceName.BIORXIV_HTML
    assert "biorxiv_html" in result.tried
