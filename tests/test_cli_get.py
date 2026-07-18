"""CLI `get` end-to-end — EPMC mocked with respx."""

from __future__ import annotations

import json

import httpx
import orjson
import pytest
import respx
from typer.testing import CliRunner

from preprint_fulltext.cli import app
from preprint_fulltext.sources.europepmc import BASE

from .factories import read_fixture

DOI = "10.1101/2024.01.15.575000"
RESOLVE = json.loads(read_fixture("epmc_resolve.json"))
SAMPLE_XML = read_fixture("jats_biorxiv_sample.xml")
runner = CliRunner()


@pytest.fixture(autouse=True)
def _mock_epmc():
    with respx.mock:
        respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=RESOLVE))
        respx.get(f"{BASE}/PPR100001/fullTextXML").mock(
            return_value=httpx.Response(200, content=SAMPLE_XML)
        )
        yield


def test_get_markdown_prints_sections_as_h2():
    result = runner.invoke(app, ["get", DOI, "--markdown", "--source", "europepmc"])
    assert result.exit_code == 0, result.output
    assert "## Introduction" in result.output
    assert "## Results" in result.output
    assert result.output.startswith("# A Test Preprint on Widgets")


def test_get_json_is_valid_fulltext():
    result = runner.invoke(app, ["get", DOI, "--source", "europepmc"])
    assert result.exit_code == 0, result.output
    data = orjson.loads(result.stdout)
    assert data["preprint"]["doi"] == DOI
    assert data["retrieved_from"] == "europepmc"
    assert data["sections"][0]["kind"] == "abstract"


def test_get_writes_to_out_file(tmp_path):
    out = tmp_path / "doc.json"
    result = runner.invoke(app, ["get", DOI, "--source", "europepmc", "--out", str(out)])
    assert result.exit_code == 0, result.output
    data = orjson.loads(out.read_bytes())
    assert data["preprint"]["title"] == "A Test Preprint on Widgets"


def test_get_source_europepmc_404_exits_nonzero():
    with respx.mock:
        respx.get(f"{BASE}/search").mock(
            return_value=httpx.Response(200, json={"resultList": {"result": []}})
        )
        result = runner.invoke(app, ["get", "10.1101/nope", "--source", "europepmc"])
    assert result.exit_code == 2
    assert "No full text" in result.output
