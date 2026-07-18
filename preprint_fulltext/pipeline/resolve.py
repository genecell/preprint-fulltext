"""resolve.py — doi <-> openalex_id <-> PPR id helpers (MCP `resolve` + internal use)."""

from __future__ import annotations

from ..config import Settings, get_settings


def resolve(identifier: str, settings: Settings | None = None) -> dict:
    """Best-effort cross-identifier resolution. Returns whatever could be resolved.

    - a DOI (``10.…``) → attach its Europe PMC PPR id (if OA) and bioRxiv metadata
    - an OpenAlex id (``W…``) or URL → attach the DOI via the free singleton lookup
    """
    settings = settings or get_settings()
    ident = identifier.strip()
    out: dict = {"input": ident, "doi": None, "openalex_id": None, "ppr_id": None, "server": None}

    short = ident.rsplit("/", 1)[-1]
    if ident.startswith("10.") or "doi.org/" in ident:
        doi = short if "doi.org/" in ident else ident
        out["doi"] = doi
        from ..sources.biorxiv_api import BiorxivAPI
        from ..sources.europepmc import EuropePMC

        out["ppr_id"] = EuropePMC(settings).resolve_ppr_id(doi)
        meta = BiorxivAPI(settings).get_metadata(doi)
        if meta:
            out["server"] = meta.server.value
            if meta.published_doi:
                out["published_doi"] = meta.published_doi
    elif short.upper().startswith("W"):
        out["openalex_id"] = short
        from ..sources.openalex import BASE, OpenAlex
        from ..core.http import build_client, request_with_retry

        oa = OpenAlex(settings)
        resp = request_with_retry(build_client(settings), "GET", f"{BASE}/works/{short}",
                                  params=oa._base_params())
        if resp.status_code == 200:
            doi = (resp.json().get("doi") or "").replace("https://doi.org/", "") or None
            out["doi"] = doi
    return out


__all__ = ["resolve"]
