"""MCP frontend: identical section structure to CLI `get`."""

from __future__ import annotations

import json

import httpx
import orjson
import pytest
import respx
from typer.testing import CliRunner

from preprint_fulltext import mcp_server
from preprint_fulltext.cli import app
from preprint_fulltext.core import http as http_mod
from preprint_fulltext.sources.europepmc import BASE

from .factories import read_fixture

DOI = "10.1101/2024.01.15.575000"
RESOLVE = json.loads(read_fixture("epmc_resolve.json"))
SAMPLE_XML = read_fixture("jats_biorxiv_sample.xml")
runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http_mod, "_sleep", lambda s: None)


@pytest.fixture
def _mock_epmc():
    with respx.mock:
        respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=RESOLVE))
        respx.get(f"{BASE}/PPR100001/fullTextXML").mock(
            return_value=httpx.Response(200, content=SAMPLE_XML)
        )
        yield


def test_mcp_get_fulltext_matches_cli_get(_mock_epmc):
    mcp_doc = mcp_server.get_fulltext_impl(DOI, source="europepmc")

    with respx.mock:
        respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=RESOLVE))
        respx.get(f"{BASE}/PPR100001/fullTextXML").mock(
            return_value=httpx.Response(200, content=SAMPLE_XML)
        )
        cli_res = runner.invoke(app, ["get", DOI, "--source", "europepmc"])
    cli_doc = orjson.loads(cli_res.stdout)

    # The single-parser guarantee: identical section structure.
    assert mcp_doc["sections"] == cli_doc["sections"]
    assert mcp_doc["preprint"]["doi"] == cli_doc["preprint"]["doi"]
    assert mcp_doc["retrieved_from"] == cli_doc["retrieved_from"]


def test_mcp_get_fulltext_markdown(_mock_epmc):
    md = mcp_server.get_fulltext_impl(DOI, source="europepmc", as_markdown=True)
    assert isinstance(md, str)
    assert "## Introduction" in md


def test_mcp_get_fulltext_miss_returns_error():
    with respx.mock:
        respx.get(f"{BASE}/search").mock(
            return_value=httpx.Response(200, json={"resultList": {"result": []}})
        )
        doc = mcp_server.get_fulltext_impl("10.1101/nope", source="europepmc")
    assert "error" in doc


def test_mcp_search(_mock_epmc):
    page = json.loads(read_fixture("epmc_search_page1.json"))
    with respx.mock:
        respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=page))
        hits = mcp_server.search_impl("widgets", limit=2)
    assert len(hits) == 2
    assert hits[0]["source"] == "europepmc"


def test_build_server_registers_tools():
    server = mcp_server.build_server()
    assert set(server.tools) == {"search_preprints", "get_fulltext", "get_metadata", "resolve"}


# --- self-contained JSON-RPC / MCP protocol (no third-party framework) --------
def test_mcp_initialize_handshake():
    server = mcp_server.build_server()
    resp = server.dispatch({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}},
    })
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2025-06-18"      # echoes a supported version
    assert "tools" in resp["result"]["capabilities"]
    assert resp["result"]["serverInfo"]["name"] == "preprint-fulltext"


def test_mcp_initialize_unknown_version_falls_back_to_latest():
    server = mcp_server.build_server()
    resp = server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "1999-01-01"}})
    assert resp["result"]["protocolVersion"] == mcp_server.LATEST_PROTOCOL_VERSION


def test_mcp_notifications_get_no_response():
    server = mcp_server.build_server()
    assert server.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_mcp_tools_list_shape():
    server = mcp_server.build_server()
    resp = server.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = resp["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == {"search_preprints", "get_fulltext", "get_metadata", "resolve"}
    for t in tools:  # every tool advertises a JSON-Schema object
        assert t["inputSchema"]["type"] == "object"
    gf = next(t for t in tools if t["name"] == "get_fulltext")
    assert gf["inputSchema"]["required"] == ["doi"]


def test_mcp_tools_call_get_fulltext_via_protocol(_mock_epmc):
    server = mcp_server.build_server()
    resp = server.dispatch({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "get_fulltext", "arguments": {"doi": DOI}},
    })
    result = resp["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["preprint"]["doi"] == DOI
    # unstructured text content mirrors the structured content (round-trips as JSON)
    assert orjson.loads(result["content"][0]["text"])["retrieved_from"] == "europepmc"


def test_mcp_tools_call_unknown_tool_is_protocol_error():
    server = mcp_server.build_server()
    resp = server.dispatch({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                            "params": {"name": "nope", "arguments": {}}})
    assert resp["error"]["code"] == -32602


def test_mcp_unknown_method_is_method_not_found():
    server = mcp_server.build_server()
    resp = server.dispatch({"jsonrpc": "2.0", "id": 5, "method": "frobnicate"})
    assert resp["error"]["code"] == -32601


def test_mcp_serve_over_streams_end_to_end():
    """Feed newline-delimited JSON-RPC through serve() and read framed responses."""
    import io

    server = mcp_server.build_server()
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},   # no response expected
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    stdin = io.BytesIO(b"\n".join(orjson.dumps(r) for r in requests))
    stdout = io.BytesIO()
    server.serve(stdin=stdin, stdout=stdout)
    lines = [orjson.loads(x) for x in stdout.getvalue().splitlines() if x.strip()]
    assert len(lines) == 2                       # initialize + tools/list (notification silent)
    assert lines[0]["id"] == 1 and lines[1]["id"] == 2
