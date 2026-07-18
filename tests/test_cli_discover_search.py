"""CLI `search` / `discover` — sources respx-mocked."""

from __future__ import annotations

import json

import httpx
import orjson
import respx
from typer.testing import CliRunner

from preprint_fulltext.cli import app
from preprint_fulltext.sources.europepmc import BASE as EPMC
from preprint_fulltext.sources.openalex import BASE as OA

from .factories import read_fixture

runner = CliRunner()
OA_SEARCH = json.loads(read_fixture("openalex_search.json"))
EPMC_PAGE = json.loads(read_fixture("epmc_search_page1.json"))


@respx.mock
def test_search_europepmc_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("PREPRINT_FULLTEXT_CONTACT_EMAIL", "t@example.org")
    respx.get(f"{EPMC}/search").mock(return_value=httpx.Response(200, json=EPMC_PAGE))
    out = tmp_path / "hits.jsonl"
    r = runner.invoke(app, ["search", "widgets", "--source", "europepmc", "-n", "2", "-o", str(out)])
    assert r.exit_code == 0, r.output
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 2
    rec = orjson.loads(lines[0])
    assert rec["source"] == "europepmc"
    assert rec["doi"] == "10.1101/2024.01.15.575000"


@respx.mock
def test_discover_openalex_streams_to_stdout(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "k-abc")
    respx.get(f"{OA}/works").mock(return_value=httpx.Response(200, json=OA_SEARCH))
    r = runner.invoke(app, ["discover", "-q", "widgets", "--since", "2024-01", "-n", "2"])
    assert r.exit_code == 0, r.output
    first = orjson.loads(r.stdout.strip().splitlines()[0])
    assert first["openalex_id"] == "W111"
    assert first["has_fulltext"] is True


def test_discover_openalex_missing_key_errors(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    r = runner.invoke(app, ["discover", "-q", "x", "--source", "openalex"])
    assert r.exit_code == 2
    assert "2026-02-13" in r.output


def test_search_unknown_source_errors():
    r = runner.invoke(app, ["search", "x", "--source", "nope"])
    assert r.exit_code == 2
