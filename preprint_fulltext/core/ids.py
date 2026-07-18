"""ids.py — identifier normalization (DOI / doi.org URL / bioRxiv content URL)."""

from __future__ import annotations

import re

# Grab the DOI from a bioRxiv/medRxiv content URL:
# https://www.biorxiv.org/content/10.64898/2026.06.13.731750v1[.full]
_CONTENT_URL_RE = re.compile(r"/content/(10\.\d+/[^\s?#]+?)(?:v\d+)?(?:\.full[^\s]*|\.article[^\s]*)?/?$")
_DOI_RE = re.compile(r"10\.\d+/\S+")


def normalize_doi(value: str) -> str:
    """Normalize a DOI, a ``doi.org`` URL, or a bioRxiv/medRxiv content URL to a bare DOI.

    Examples
    --------
    ``10.64898/2026.06.13.731750`` → unchanged
    ``https://doi.org/10.64898/2026.06.13.731750`` → ``10.64898/2026.06.13.731750``
    ``https://www.biorxiv.org/content/10.64898/2026.06.13.731750v1.full`` → same bare DOI
    """
    s = (value or "").strip()
    if not s:
        return s

    # doi.org / dx.doi.org resolver URLs.
    for marker in ("doi.org/",):
        if marker in s:
            return s.split(marker, 1)[1].strip().rstrip("/")

    # bioRxiv/medRxiv content URLs (strip version suffix and .full/.article tails).
    m = _CONTENT_URL_RE.search(s)
    if m:
        return m.group(1).strip().rstrip("/")

    # Bare DOI possibly with a version suffix appended (…v1) — strip a trailing vN.
    m = _DOI_RE.search(s)
    if m:
        doi = m.group(0).rstrip("/")
        return re.sub(r"v\d+$", "", doi)
    return s


def split_doi_version(value: str) -> tuple[str, int | None]:
    """Return (bare_doi, version) where version is parsed from a trailing ``vN`` if present."""
    s = (value or "").strip()
    version = None
    m = re.search(r"v(\d+)(?:\.full[^\s]*|\.article[^\s]*)?/?$", s)
    if m:
        version = int(m.group(1))
    return normalize_doi(s), version


# --- arXiv identifiers --------------------------------------------------------
# New-style: 2401.10515 (YYMM.NNNNN, 4-5 digits) optionally vN.
# Old-style: hep-th/9901001, math.GT/0309136 (archive[.subclass]/YYMMNNN) optionally vN.
_ARXIV_NEW = r"\d{4}\.\d{4,5}"
_ARXIV_OLD = r"[a-z-]+(?:\.[A-Z]{2})?/\d{7}"
_ARXIV_CORE_RE = re.compile(rf"({_ARXIV_NEW}|{_ARXIV_OLD})(v\d+)?", re.IGNORECASE)
# Known legacy arXiv archives, so a bare "hep-th/9901001" is recognized but "foo/1234567"
# is not (old-style ids are otherwise indistinguishable from an arbitrary path/number).
_ARXIV_ARCHIVES = frozenset({
    "acc-phys", "adap-org", "alg-geom", "ao-sci", "astro-ph", "atom-ph", "bayes-an",
    "chao-dyn", "chem-ph", "cmp-lg", "comp-gas", "cond-mat", "cs", "dg-ga", "econ",
    "eess", "funct-an", "gr-qc", "hep-ex", "hep-lat", "hep-ph", "hep-th", "math",
    "math-ph", "mtrl-th", "nlin", "nucl-ex", "nucl-th", "patt-sol", "physics",
    "plasm-ph", "q-alg", "q-bio", "q-fin", "quant-ph", "solv-int", "stat", "supr-con",
})
# arXiv DOI (DataCite): 10.48550/arXiv.2401.10515
_ARXIV_DOI_RE = re.compile(r"10\.48550/arxiv\.(.+)", re.IGNORECASE)


def split_arxiv_id(value: str) -> tuple[str | None, int | None]:
    """Extract (arxiv_id_without_version, version) from an id, arXiv:…, arxiv.org/ar5iv URL,
    or the 10.48550/arXiv.* DOI. Returns (None, None) if it is not an arXiv identifier."""
    s = (value or "").strip()
    if not s:
        return None, None

    dm = _ARXIV_DOI_RE.search(s)
    if dm:
        s = dm.group(1)

    # Only treat bare old-style ("archive/NNNNNNN") as arXiv, not arbitrary "a/b" strings:
    # require an arxiv context (arxiv:/arxiv.org/ar5iv/10.48550) OR a new-style id.
    low = s.lower()
    has_context = any(k in low for k in ("arxiv", "ar5iv", "10.48550"))
    m = _ARXIV_CORE_RE.search(s)
    if not m:
        return None, None
    core, ver = m.group(1), m.group(2)
    is_new = bool(re.fullmatch(_ARXIV_NEW, core))
    # Old-style: accept if it carries arxiv context OR its archive prefix is a real one.
    archive_ok = "/" in core and core.split("/", 1)[0].split(".", 1)[0].lower() in _ARXIV_ARCHIVES
    if not (is_new or has_context or archive_ok):
        return None, None
    version = int(ver[1:]) if ver else None
    return core, version


def normalize_arxiv_id(value: str) -> str | None:
    return split_arxiv_id(value)[0]


def arxiv_doi(arxiv_id: str) -> str:
    """arXiv id -> its registered DataCite DOI (10.48550/arXiv.<id>)."""
    return f"10.48550/arXiv.{arxiv_id}"


def identify(value: str) -> tuple[str, str, int | None]:
    """Classify an input and return (kind, canonical_id, version).

    kind is ``"arxiv"`` (canonical_id = bare arXiv id), ``"openrxiv"`` (canonical_id =
    bare DOI), or ``"unknown"``. Version is parsed from a trailing ``vN`` when present.
    """
    s = (value or "").strip()
    aid, aver = split_arxiv_id(s)
    if aid is not None:
        return "arxiv", aid, aver
    doi, ver = split_doi_version(s)
    if re.match(r"10\.\d+/", doi):
        return "openrxiv", doi, ver
    return "unknown", doi, ver


__all__ = [
    "normalize_doi",
    "split_doi_version",
    "split_arxiv_id",
    "normalize_arxiv_id",
    "arxiv_doi",
    "identify",
]
