"""Opt-in live tests. Skipped unless PREPRINT_FULLTEXT_LIVE=1.

S3 live is skipped even under LIVE (requester-pays cost); it needs the separate
PREPRINT_FULLTEXT_LIVE_S3=1 gate and hits a tiny single object.
"""

from __future__ import annotations

import os

import pytest

from preprint_fulltext.config import Settings
from preprint_fulltext.sources.base import DiscoverQuery

# A known open-access (CC-BY) bioRxiv preprint with retrievable full text on EPMC.
KNOWN_OA_DOI = "10.64898/2026.04.01.715781"


@pytest.mark.live
def test_live_epmc_fulltext_has_methods_and_results():
    from preprint_fulltext.sources.europepmc import EuropePMC

    email = os.environ.get("CONTACT_EMAIL")
    ft = EuropePMC(Settings(contact_email=email)).get_fulltext(KNOWN_OA_DOI)
    assert ft is not None, "expected retrievable OA full text"
    kinds = {s.kind.value for s in ft.sections}
    assert "methods" in kinds or "results" in kinds
    assert any(s.text.strip() for s in ft.sections)


@pytest.mark.live
def test_live_cc_no_preprint_epmc_none_but_metadata_and_html_work():
    """A real all-rights-reserved (cc_no) preprint: EPMC has no full text, the bioRxiv
    API returns metadata, and the opt-in HTML source can still retrieve the body."""
    from preprint_fulltext.sources.biorxiv_api import BiorxivAPI
    from preprint_fulltext.sources.biorxiv_html import BiorxivHTML
    from preprint_fulltext.sources.europepmc import EuropePMC

    cc_no_doi = "10.64898/2026.06.13.731750"
    s = Settings(contact_email=os.environ.get("CONTACT_EMAIL"))

    assert EuropePMC(s).get_fulltext(cc_no_doi) is None  # cc_no -> no retrievable full text
    meta = BiorxivAPI(s).get_metadata(cc_no_doi)
    assert meta is not None and meta.license.redistributable is False

    ft = BiorxivHTML(s).get_fulltext(cc_no_doi, server="biorxiv")
    assert ft is not None and any(s.text.strip() for s in ft.sections)


@pytest.mark.live
def test_live_default_is_latest_version_and_explicit_version_works():
    """DOI resolves to the latest version by default; an explicit version is honored."""
    from preprint_fulltext.pipeline.router import Router
    from preprint_fulltext.sources.biorxiv_api import BiorxivAPI

    two_version_doi = "10.64898/2026.01.29.702557"  # has v1 (Jan) and v2 (Jun)
    s = Settings(contact_email=os.environ.get("CONTACT_EMAIL"))
    latest = BiorxivAPI(s).latest_version(two_version_doi, "biorxiv")
    assert latest and latest >= 2

    default = Router(s).get_fulltext(two_version_doi)
    assert default.fulltext is not None
    assert default.fulltext.preprint.version == latest        # default == latest

    v1 = Router(s).get_fulltext(two_version_doi, version=1, source="html")
    assert v1.fulltext is not None
    assert v1.fulltext.preprint.version == 1                  # explicit older version


@pytest.mark.live
def test_live_medrxiv_metadata_and_html_fulltext():
    """medRxiv path: server detected as medrxiv, metadata via the JSON API, and the
    HTML source retrieves full text (EPMC full text is rare for medRxiv)."""
    from preprint_fulltext.sources.biorxiv_api import BiorxivAPI
    from preprint_fulltext.sources.biorxiv_html import BiorxivHTML
    from preprint_fulltext.sources.biorxiv_s3 import doi_posting_date
    import datetime as dt

    med_doi = "10.64898/2026.05.27.26354181"  # 8-digit suffix medRxiv preprint
    s = Settings(contact_email=os.environ.get("CONTACT_EMAIL"))

    # 8-digit openRxiv suffix parses to a posting date.
    assert doi_posting_date(med_doi) == dt.date(2026, 5, 27)

    meta = BiorxivAPI(s).get_metadata(med_doi, "medrxiv")
    assert meta is not None and meta.server.value == "medrxiv"

    ft = BiorxivHTML(s).get_fulltext(med_doi, server="medrxiv")
    assert ft is not None and ft.preprint.server.value == "medrxiv"
    assert any(sec.text.strip() for sec in ft.sections)


@pytest.mark.live
def test_live_arxiv_metadata_fulltext_and_search():
    """arXiv: metadata via the API, full text via LaTeXML HTML, and title search."""
    from preprint_fulltext.pipeline.router import Router
    from preprint_fulltext.sources.arxiv import ArxivAPI

    s = Settings(contact_email=os.environ.get("CONTACT_EMAIL"))
    aid = "1706.03762"  # Attention Is All You Need

    meta = ArxivAPI(s).get_metadata(aid)
    assert meta is not None and meta.server.value == "arxiv"
    assert meta.doi == "10.48550/arXiv.1706.03762"

    ft = Router(s).get_fulltext(f"arXiv:{aid}")
    assert ft.fulltext is not None
    assert ft.fulltext.retrieved_from.value == "arxiv_html"
    assert any(sec.text.strip() for sec in ft.fulltext.sections)

    hits = list(ArxivAPI(s).search("transformer", limit=3, field="title"))
    assert len(hits) >= 1 and all(h.doi.startswith("10.48550/arXiv.") for h in hits)


@pytest.mark.live
def test_live_openalex_discover_returns_hits():
    from preprint_fulltext.sources.openalex import OpenAlex

    key = os.environ.get("OPENALEX_API_KEY")
    if not key:
        pytest.skip("OPENALEX_API_KEY not set")
    oa = OpenAlex(Settings(openalex_api_key=key, contact_email=os.environ.get("CONTACT_EMAIL")))
    hits = list(oa.discover(DiscoverQuery(query="crispr", limit=3)))
    assert len(hits) >= 1


@pytest.mark.live_s3
def test_live_s3_single_object_fetch():
    import datetime as dt

    from preprint_fulltext.sources.biorxiv_s3 import BiorxivS3

    s3 = BiorxivS3(Settings())
    items = list(s3.iter_fulltext("biorxiv", since=dt.date(2024, 1, 1), max_items=1))
    assert len(items) == 1
    assert s3.bytes_downloaded > 0
