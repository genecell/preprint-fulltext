"""Tests for core/ids.py — DOI / URL normalization."""

from __future__ import annotations

import pytest

from preprint_fulltext.core.ids import normalize_doi, split_doi_version

NEW = "10.64898/2026.06.13.731750"
OLD = "10.1101/2024.01.15.575000"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (NEW, NEW),
        (f"https://doi.org/{NEW}", NEW),
        (f"http://dx.doi.org/{NEW}", NEW),
        (f"https://www.biorxiv.org/content/{NEW}v1.full", NEW),
        (f"https://www.biorxiv.org/content/{NEW}v2", NEW),
        (f"https://www.medrxiv.org/content/{OLD}v1.full-text", OLD),
        (f"  {NEW}  ", NEW),
    ],
)
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected


def test_split_doi_version():
    assert split_doi_version(f"https://www.biorxiv.org/content/{NEW}v3.full") == (NEW, 3)
    assert split_doi_version(NEW) == (NEW, None)
    assert split_doi_version(f"https://doi.org/{NEW}") == (NEW, None)


def test_empty():
    assert normalize_doi("") == ""
    assert split_doi_version("") == ("", None)


# --- arXiv --------------------------------------------------------------------
from preprint_fulltext.core.ids import arxiv_doi, identify, split_arxiv_id  # noqa: E402


@pytest.mark.parametrize(
    "raw,expected_id,expected_ver",
    [
        ("2401.10515", "2401.10515", None),
        ("2401.10515v2", "2401.10515", 2),
        ("arXiv:2401.10515", "2401.10515", None),
        ("https://arxiv.org/abs/2401.10515v3", "2401.10515", 3),
        ("https://arxiv.org/pdf/2401.10515", "2401.10515", None),
        ("https://arxiv.org/html/2401.10515v2", "2401.10515", 2),
        ("https://ar5iv.labs.arxiv.org/html/2401.10515", "2401.10515", None),
        ("10.48550/arXiv.2401.10515", "2401.10515", None),
        ("hep-th/9901001", "hep-th/9901001", None),
        ("arXiv:hep-th/9901001v2", "hep-th/9901001", 2),
    ],
)
def test_split_arxiv_id(raw, expected_id, expected_ver):
    assert split_arxiv_id(raw) == (expected_id, expected_ver)


def test_non_arxiv_inputs_are_not_arxiv():
    assert split_arxiv_id("10.64898/2026.06.13.731750") == (None, None)
    assert split_arxiv_id("just some text") == (None, None)
    # A bare old-style "a/1234567" without arxiv context is NOT treated as arXiv.
    assert split_arxiv_id("foo/1234567") == (None, None)


def test_arxiv_doi():
    assert arxiv_doi("2401.10515") == "10.48550/arXiv.2401.10515"


def test_identify_routes():
    assert identify("2401.10515v2") == ("arxiv", "2401.10515", 2)
    assert identify("https://arxiv.org/abs/2401.10515") == ("arxiv", "2401.10515", None)
    assert identify("10.48550/arXiv.2401.10515") == ("arxiv", "2401.10515", None)
    assert identify("10.64898/2026.06.13.731750") == ("openrxiv", "10.64898/2026.06.13.731750", None)
    assert identify("https://www.biorxiv.org/content/10.1101/2024.01.15.575000v2.full")[0] == "openrxiv"
