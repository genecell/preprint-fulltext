"""Tests for sources/biorxiv_s3.py (moto-mocked)."""

from __future__ import annotations

import datetime as dt

import boto3
import pytest
from moto import mock_aws

from preprint_fulltext.config import Settings
from preprint_fulltext.core.models import Server, SourceName
from preprint_fulltext.sources.base import SourceError
from preprint_fulltext.sources.biorxiv_s3 import (
    BiorxivS3,
    doi_posting_date,
    extract_article_xml,
    month_folder,
    parse_month_folder,
)

from .factories import make_meca, read_fixture

SAMPLE_XML = read_fixture("jats_biorxiv_sample.xml")
DOI = "10.1101/2024.01.15.575000"
BUCKET = "biorxiv-src-monthly"
KEY = "Current_Content/January_2024/abc-123.meca"


class RecordingClient:
    """Wrap a boto3 S3 client and record kwargs so tests can assert RequestPayer."""

    def __init__(self, inner):
        self._inner = inner
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def wrapper(*args, **kwargs):
            self.calls.append((name, kwargs))
            return attr(*args, **kwargs)

        return wrapper


@pytest.fixture
def s3_env():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        client.put_object(Bucket=BUCKET, Key=KEY, Body=make_meca(SAMPLE_XML))
        rec = RecordingClient(client)
        src = BiorxivS3(settings=Settings(), client=rec)
        yield src, rec


# --- pure helpers -------------------------------------------------------------
def test_month_folder_roundtrip():
    assert month_folder(dt.date(2025, 6, 3)) == "June_2025"
    assert parse_month_folder("June_2025") == dt.date(2025, 6, 1)
    assert parse_month_folder("Batch_07") is None


def test_doi_posting_date():
    assert doi_posting_date(DOI) == dt.date(2024, 1, 15)
    assert doi_posting_date("10.1101/nonsense") is None


def test_doi_posting_date_new_openrxiv_prefix():
    # openRxiv prefix (since 2025-12) with an 8-digit suffix must also parse.
    assert doi_posting_date("10.64898/2026.06.13.731750") == dt.date(2026, 6, 13)
    assert doi_posting_date("10.64898/2026.01.01.12345678") == dt.date(2026, 1, 1)


def test_extract_article_xml_via_manifest():
    meca = make_meca(SAMPLE_XML, article_name="content/main.xml")
    xml = extract_article_xml(meca)
    assert b"A Test Preprint on" in xml


def test_extract_article_xml_fallback_without_manifest():
    meca = make_meca(SAMPLE_XML, include_manifest=False)
    xml = extract_article_xml(meca)
    assert b"A Test Preprint on" in xml


# --- S3 behaviour -------------------------------------------------------------
def test_iter_keys_passes_request_payer(s3_env):
    src, rec = s3_env
    keys = list(src.iter_keys("biorxiv"))
    assert KEY in keys
    list_calls = [kw for name, kw in rec.calls if name == "list_objects_v2"]
    assert list_calls and all(kw.get("RequestPayer") == "requester" for kw in list_calls)


def test_fetch_meca_passes_request_payer_and_counts_bytes(s3_env):
    src, rec = s3_env
    data = src.fetch_meca("biorxiv", KEY)
    assert data[:2] == b"PK"  # zip magic
    get_calls = [kw for name, kw in rec.calls if name == "get_object"]
    assert get_calls and all(kw.get("RequestPayer") == "requester" for kw in get_calls)
    assert src.bytes_downloaded == len(data)


def test_parse_meca_to_fulltext(s3_env):
    src, _ = s3_env
    ft = src.parse_meca(src.fetch_meca("biorxiv", KEY), "biorxiv", KEY)
    assert ft.preprint.doi == DOI
    assert ft.retrieved_from is SourceName.BIORXIV_S3
    assert ft.sections[0].kind.value == "abstract"
    assert ft.raw_ref == f"s3://{BUCKET}/{KEY}"


def test_get_fulltext_scans_month_and_matches_doi(s3_env):
    src, _ = s3_env
    ft = src.get_fulltext(DOI, server="biorxiv")
    assert ft is not None and ft.preprint.doi == DOI


def test_since_filter_excludes_older_months(s3_env):
    src, _ = s3_env
    # Ask for >= Feb 2024; the January object must be excluded.
    keys = list(src.iter_keys("biorxiv", since=dt.date(2024, 2, 1)))
    assert KEY not in keys


def test_iter_fulltext_yields_and_counts(s3_env):
    src, _ = s3_env
    items = list(src.iter_fulltext("biorxiv"))
    assert len(items) == 1
    assert items[0].preprint.doi == DOI
    assert src.bytes_downloaded > 0


def test_missing_credentials_raises(monkeypatch):
    class _NoCreds:
        def get_credentials(self):
            return None

    monkeypatch.setattr(boto3, "Session", lambda *a, **k: _NoCreds())
    src = BiorxivS3(settings=Settings())
    with pytest.raises(SourceError) as ei:
        _ = src.client
    assert "credentials" in str(ei.value).lower()
