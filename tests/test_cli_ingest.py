"""CLI `ingest` end-to-end over moto S3."""

from __future__ import annotations

import boto3
import orjson
import pytest
from moto import mock_aws
from typer.testing import CliRunner

from preprint_fulltext.cli import app
from preprint_fulltext.pipeline.ingest import manifest_path_for

from .factories import make_meca, read_fixture

runner = CliRunner()
SAMPLE_XML = read_fixture("jats_biorxiv_sample.xml")
ARR_XML = read_fixture("jats_biorxiv_arr.xml")
BUCKET = "biorxiv-src-monthly"


@pytest.fixture
def seeded_s3(monkeypatch):
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        client.put_object(Bucket=BUCKET, Key="Current_Content/January_2024/cc.meca",
                          Body=make_meca(SAMPLE_XML))
        client.put_object(Bucket=BUCKET, Key="Current_Content/February_2024/arr.meca",
                          Body=make_meca(ARR_XML))

        # Force the CLI's BiorxivS3 to use the moto client.
        import preprint_fulltext.sources.biorxiv_s3 as s3mod

        orig = s3mod.BiorxivS3

        def _factory(settings=None, client=client, cache=None):
            return orig(settings=settings, client=client, cache=cache)

        monkeypatch.setattr(s3mod, "BiorxivS3", _factory)
        yield client


def test_ingest_writes_jsonl_and_manifest(tmp_path, seeded_s3):
    out = tmp_path / "corpus.jsonl"
    r = runner.invoke(app, ["ingest", str(out), "--source", "s3", "--server", "biorxiv"])
    assert r.exit_code == 0, r.output
    chunk_lines = [orjson.loads(l) for l in out.read_bytes().splitlines() if l.strip()]
    assert chunk_lines and all(c["chunk_id"] for c in chunk_lines)
    manifest = manifest_path_for(out)
    rows = [orjson.loads(l) for l in manifest.read_bytes().splitlines() if l.strip()]
    assert len(rows) == 2  # two preprints
    assert "requester-pays" in r.output  # bytes reported


def test_ingest_redistribution_degrades_arr(tmp_path, seeded_s3):
    out = tmp_path / "corpus.jsonl"
    r = runner.invoke(
        app, ["ingest", str(out), "--source", "s3", "--server", "biorxiv", "--redistribution"]
    )
    assert r.exit_code == 0, r.output
    assert "1 degraded" in r.output
    # The ARR body ("Gadgets performed") must not be in the corpus.
    assert b"Gadgets performed" not in out.read_bytes()
    # The CC-BY body should be present.
    assert b"significantly more widgets" in out.read_bytes()


def test_ingest_since_filters_month(tmp_path, seeded_s3):
    out = tmp_path / "corpus.jsonl"
    r = runner.invoke(
        app, ["ingest", str(out), "--source", "s3", "--server", "biorxiv", "--since", "2024-02"]
    )
    assert r.exit_code == 0, r.output
    rows = [orjson.loads(l) for l in manifest_path_for(out).read_bytes().splitlines() if l.strip()]
    # Only the February (ARR) object survives the --since filter.
    assert len(rows) == 1
    assert rows[0]["doi"] == "10.1101/2024.02.20.999999"
