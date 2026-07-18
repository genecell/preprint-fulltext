"""MCP server — interactive frontend over the same core.

A self-contained Model Context Protocol server over stdio, implemented directly on
JSON-RPC 2.0 with **no third-party MCP framework** — the tools-only surface is small
and stable, so we avoid the heavy FastMCP/uvicorn dependency tree and ship a working
`preprint-fulltext-mcp` with zero extra installs.

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio). Only JSON-RPC
is written to stdout; diagnostics go to stderr. Bulk ingest is intentionally NOT a tool.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional

import orjson

from .config import get_settings

# Protocol versions we understand; we echo the client's if we know it, else offer latest.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]


# --- tool implementation functions (also imported directly by tests) ---------
def get_fulltext_impl(
    doi: str,
    version: Optional[int] = None,
    source: Optional[str] = None,
    server: Optional[str] = None,
    as_markdown: bool = False,
):
    """Structured full text for a DOI (router: Europe PMC → S3; latest version by default)."""
    from .core.ids import split_doi_version
    from .pipeline.router import Router

    norm_doi, url_version = split_doi_version(doi)
    result = Router(get_settings()).get_fulltext(
        norm_doi, version=version or url_version, source=source, server=server
    )
    if result.fulltext is None:
        return {"error": result.reason or "not found", "tried": result.tried, "doi": norm_doi}
    if as_markdown:
        from .cli import _render_markdown

        return _render_markdown(result.fulltext)
    return result.fulltext.model_dump(mode="json")


def get_metadata_impl(doi: str):
    """Bibliographic metadata (abstract only) via the bioRxiv/medRxiv JSON API."""
    from .core.ids import normalize_doi
    from .sources.biorxiv_api import BiorxivAPI

    p = BiorxivAPI(get_settings()).get_metadata(normalize_doi(doi))
    return p.model_dump(mode="json") if p else {"error": "not found", "doi": doi}


def search_impl(query: str, source: str = "europepmc", limit: int = 25, field: str = "fulltext"):
    """Keyword search → list of SearchHit dicts. field: fulltext|title|abstract|author."""
    settings = get_settings()
    if source == "openalex":
        from .sources.openalex import OpenAlex

        hits = OpenAlex(settings).search(query, limit, field=field)
    elif source == "arxiv":
        from .sources.arxiv import ArxivAPI

        hits = ArxivAPI(settings).search(query, limit, field=field)
    else:
        from .sources.europepmc import EuropePMC

        hits = EuropePMC(settings).search(query, limit, field=field)
    out = []
    for i, h in enumerate(hits):
        out.append(h.model_dump(mode="json"))
        if i + 1 >= limit:
            break
    return out


def resolve_impl(doi_or_openalex_id: str):
    """Resolve between DOI / OpenAlex id / PPR id."""
    from .pipeline.resolve import resolve

    return resolve(doi_or_openalex_id, get_settings())


# --- tool registry -----------------------------------------------------------
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Any]

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


def _tools() -> list[Tool]:
    _str = {"type": "string"}
    return [
        Tool(
            "search_preprints",
            "Search preprint full text (Europe PMC relevance or OpenAlex n-gram). "
            "field scopes to fulltext|title|abstract|author.",
            {
                "type": "object",
                "properties": {
                    "query": _str,
                    "source": {"type": "string", "enum": ["europepmc", "openalex", "arxiv"]},
                    "field": {"type": "string", "enum": ["fulltext", "title", "abstract", "author"]},
                    "limit": {"type": "integer", "minimum": 1},
                },
                "required": ["query"],
            },
            lambda query, source="europepmc", field="fulltext", limit=25: search_impl(
                query, source=source, limit=limit, field=field
            ),
        ),
        Tool(
            "get_fulltext",
            "Retrieve structured full-text sections for a preprint DOI (or URL). Resolves to "
            "the latest version by default; pass version for a specific one.",
            {
                "type": "object",
                "properties": {
                    "doi": _str,
                    "version": {"type": "integer"},
                    "as_markdown": {"type": "boolean"},
                },
                "required": ["doi"],
            },
            lambda doi, version=None, as_markdown=False: get_fulltext_impl(
                doi, version=version, as_markdown=as_markdown
            ),
        ),
        Tool(
            "get_metadata",
            "Retrieve bibliographic metadata (abstract only) for a preprint DOI.",
            {"type": "object", "properties": {"doi": _str}, "required": ["doi"]},
            lambda doi: get_metadata_impl(doi),
        ),
        Tool(
            "resolve",
            "Resolve between a DOI, an OpenAlex id, and a Europe PMC PPR id.",
            {
                "type": "object",
                "properties": {"doi_or_openalex_id": _str},
                "required": ["doi_or_openalex_id"],
            },
            lambda doi_or_openalex_id: resolve_impl(doi_or_openalex_id),
        ),
    ]


# --- JSON-RPC / MCP server ---------------------------------------------------
class MCPServer:
    def __init__(self, name: str, version: str, tools: list[Tool]):
        self.name = name
        self.version = version
        self.tools = {t.name: t for t in tools}

    @staticmethod
    def _ok(id_, result) -> dict:
        return {"jsonrpc": "2.0", "id": id_, "result": result}

    @staticmethod
    def _err(id_, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}

    def dispatch(self, msg: dict) -> Optional[dict]:
        """Handle one JSON-RPC message. Returns a response dict, or None for notifications."""
        method = msg.get("method")
        id_ = msg.get("id")
        is_notification = "id" not in msg
        params = msg.get("params") or {}

        if method == "initialize":
            requested = params.get("protocolVersion")
            proto = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
            return self._ok(id_, {
                "protocolVersion": proto,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.name, "version": self.version},
            })
        if method in ("notifications/initialized", "notifications/cancelled"):
            return None
        if method == "ping":
            return self._ok(id_, {})
        if method == "tools/list":
            return self._ok(id_, {"tools": [t.spec() for t in self.tools.values()]})
        if method == "tools/call":
            return self._call_tool(id_, params)

        if is_notification:
            return None
        return self._err(id_, -32601, f"Method not found: {method}")

    def _call_tool(self, id_, params: dict) -> dict:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        tool = self.tools.get(name)
        if tool is None:
            return self._err(id_, -32602, f"Unknown tool: {name}")
        try:
            result = tool.handler(**arguments)
        except TypeError as e:
            return self._err(id_, -32602, f"Invalid arguments for {name}: {e}")
        except Exception as e:  # tool execution error -> reported in-band with isError
            return self._ok(id_, {
                "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                "isError": True,
            })
        return self._ok(id_, self._wrap_result(result))

    @staticmethod
    def _wrap_result(result) -> dict:
        if isinstance(result, str):
            text = result
            structured = None
        else:
            text = orjson.dumps(result).decode("utf-8")
            structured = result
        is_error = isinstance(result, dict) and "error" in result
        out = {"content": [{"type": "text", "text": text}], "isError": is_error}
        if structured is not None:
            out["structuredContent"] = structured if isinstance(structured, dict) else {"result": structured}
        return out

    def serve(self, stdin=None, stdout=None) -> None:
        """Read newline-delimited JSON-RPC from stdin, write responses to stdout."""
        stdin = stdin if stdin is not None else sys.stdin.buffer
        stdout = stdout if stdout is not None else sys.stdout.buffer
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = orjson.loads(line)
            except orjson.JSONDecodeError:
                self._write(stdout, self._err(None, -32700, "Parse error"))
                continue
            response = self.dispatch(msg)
            if response is not None:
                self._write(stdout, response)

    @staticmethod
    def _write(stdout, obj: dict) -> None:
        stdout.write(orjson.dumps(obj))
        stdout.write(b"\n")
        stdout.flush()


def build_server() -> MCPServer:
    """Construct the MCP server with the four interactive tools registered."""
    from . import __version__

    return MCPServer("preprint-fulltext", __version__, _tools())


def main() -> None:  # pragma: no cover
    build_server().serve()


if __name__ == "__main__":  # pragma: no cover
    main()
