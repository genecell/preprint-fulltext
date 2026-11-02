"""router.py — verb + flags -> concrete Source. `--source` overrides.

`get_fulltext` embodies the coverage rule: Europe PMC has retrievable full text for
bioRxiv only when ``inEPMC == "Y"``; otherwise S3 (requester-pays) or the opt-in
public HTML page (``--html`` / ``--source html``) is used.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings, get_settings
from ..core.models import FullText, Server
from ..core.render import TextOptions
from ..sources.base import SourceError
from ..sources.europepmc import EuropePMC


@dataclass
class GetResult:
    """Outcome of a full-text `get`, with a reason when nothing was retrieved."""

    fulltext: FullText | None
    tried: list[str]
    reason: str | None = None


def _have_aws_credentials() -> bool:
    try:
        import boto3

        return boto3.Session().get_credentials() is not None
    except Exception:  # noqa: BLE001
        return False


def _call_source(fn, *args, **kwargs):
    """Invoke a source's ``get_fulltext``, dropping optional kwargs if a test double omits them."""
    active_kw = {k: v for k, v in kwargs.items() if v is not None and v is not False}
    try:
        return fn(*args, **active_kw)
    except TypeError:
        return fn(*args)


class Router:
    _biorxiv_web_blocked: bool = False

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._epmc: EuropePMC | None = None
        self._last_versions: list = []

    @property
    def epmc(self) -> EuropePMC:
        if self._epmc is None:
            self._epmc = EuropePMC(self.settings)
        return self._epmc

    def _s3(self):
        # Imported lazily: boto3 client construction is deferred and S3 is optional.
        from ..sources.biorxiv_s3 import BiorxivS3

        return BiorxivS3(self.settings)

    def _html(self):
        from ..sources.biorxiv_html import BiorxivHTML

        return BiorxivHTML(self.settings)

    def _arxiv_html(self):
        from ..sources.arxiv_html import ArxivHTML

        return ArxivHTML(self.settings)

    def _resolve_meta(self, doi: str, server):
        """Best-effort bioRxiv-API metadata (all versions). Never fails the request."""
        self._last_versions = []
        try:
            from ..sources.biorxiv_api import BiorxivAPI

            versions = BiorxivAPI(self.settings).get_versions(doi, server)
            self._last_versions = versions
            meta = versions[-1] if versions else None
            return meta, (meta.version if meta else None)
        except Exception:  # noqa: BLE001
            return None, None

    @staticmethod
    def _enrich(ft: FullText, meta, resolved_version: int | None) -> None:
        """Fill version/date/category/published_doi on the result when the source left
        them blank (e.g. Europe PMC JATS lacks the version and posting date)."""
        p = ft.preprint
        if p.version is None and resolved_version is not None:
            p.version = resolved_version
        if meta is not None:
            p.date = p.date or meta.date
            p.category = p.category or meta.category
            p.published_doi = p.published_doi or meta.published_doi

    def get_fulltext(
        self,
        doi: str,
        *,
        version: int | None = None,
        source: str | None = None,
        server: Server | str | None = None,
        allow_html: bool = False,
        options: TextOptions | None = None,
        fetch_tables: bool = False,
    ) -> GetResult:
        """Route a single-DOI full-text request. The DOI resolves to the LATEST
        version by default; pass ``version`` for a specific one.

        Default chain: Europe PMC → S3 (if creds). The bioRxiv HTML fallback is
        OPT-IN (``allow_html=True`` or ``source="html"``) — interactive only, never bulk.
        Europe PMC only serves the latest indexed version, so an explicit request for a
        non-latest version skips it in favour of S3/HTML (which can target a version).
        arXiv inputs (ids, arxiv.org URLs, 10.48550/arXiv.* DOIs) route to arXiv's LaTeXML
        full text; ``--source arxiv`` forces it.
        """
        from ..core.ids import identify

        tried: list[str] = []
        notes: list[str] = []

        # arXiv path: full text is LaTeXML HTML (native arXiv HTML → ar5iv), never openRxiv.
        kind, ident, id_version = identify(doi)
        if source == "arxiv" or (source is None and kind == "arxiv"):
            tried.append("arxiv_html")
            ft = self._arxiv_html().get_fulltext(ident, version=version or id_version)
            return GetResult(ft, tried, None if ft else "arXiv full text (HTML/ar5iv) not available")
        if kind == "openrxiv":
            doi = ident  # normalize openRxiv URLs/DOIs
            if version is None:
                version = id_version

        # Best-effort version + metadata resolution (free, abstract-only bioRxiv API call).
        self._last_versions = []
        meta, latest = self._resolve_meta(doi, server)
        versions = getattr(self, "_last_versions", []) or ([meta] if meta else [])
        target_meta = (
            next((v for v in versions if v.version == version), meta)
            if version is not None
            else meta
        )
        candidate_dates = [v.date for v in versions if getattr(v, "date", None)]
        epmc_ok = version is None or latest is None or version == latest

        def finish(ft: FullText | None, reason: str | None = None) -> GetResult:
            if ft is not None:
                self._enrich(ft, target_meta or meta, version if version is not None else latest)
            return GetResult(ft, tried, reason if ft is None else None)

        # Forced HTML source.
        if source == "html":
            tried.append("biorxiv_html")
            html_src = self._html()
            ft = _call_source(
                html_src.get_fulltext,
                doi,
                version=version,
                server=server,
                options=options,
                fetch_tables=fetch_tables,
            )
            err = getattr(html_src, "last_error", None)
            reason = f"biorxiv_html: {err}" if err else "no full-text HTML page found"
            return finish(ft, reason)

        if source in (None, "europepmc") and epmc_ok:
            tried.append("europepmc")
            ft = _call_source(self.epmc.get_fulltext, doi, version=version, options=options)
            if ft is not None:
                return finish(ft)
            epmc_err = getattr(self.epmc, "last_error", None) or "not-in-epmc"
            notes.append(f"not in Europe PMC ({epmc_err})")
            if source == "europepmc":
                return GetResult(None, tried, f"not open-access on Europe PMC ({epmc_err})")

        # Tier 2: Direct JATS XML URL (`*.source.xml`) advertised by api.biorxiv.org when
        # interactive web access (`allow_html=True`) is enabled and Cloudflare hasn't blocked us.
        jatsxml_url = (
            (target_meta.provenance or {}).get("jatsxml")
            if target_meta is not None and getattr(target_meta, "provenance", None)
            else None
        )
        if source is None and allow_html and jatsxml_url and not self._biorxiv_web_blocked:
            html_src = self._html()
            if hasattr(html_src, "get_jats_xml"):
                tried.append("biorxiv_jats_xml")
                ft, blocked = html_src.get_jats_xml(
                    jatsxml_url,
                    doi,
                    version=version,
                    server=server or (target_meta.server if target_meta else None),
                    options=options,
                    meta=target_meta,
                )
                if blocked:
                    Router._biorxiv_web_blocked = True
                if ft is not None:
                    return finish(ft)
                j_err = getattr(html_src, "last_error", None) or "jatsxml unavailable"
                notes.append(f"biorxiv_jats_xml: {j_err}")

        if source in (None, "s3"):
            if _have_aws_credentials():
                tried.append("biorxiv_s3")
                try:
                    ft = _call_source(
                        self._s3().get_fulltext,
                        doi,
                        version=version,
                        server=server or (target_meta.server if target_meta else None),
                        options=options,
                        candidate_dates=candidate_dates or None,
                    )
                except SourceError as e:
                    ft = None
                    notes.append(f"biorxiv_s3: {e}")
                    if source == "s3":
                        return GetResult(None, tried, str(e))
                if ft is not None:
                    return finish(ft)
                notes.append("S3 had no match")
                if source == "s3":
                    return GetResult(None, tried, "not found in S3")
            else:
                notes.append("no AWS credentials for S3")
                if source == "s3":
                    return GetResult(None, tried, "S3 requested but no AWS credentials found")

        # Opt-in HTML last resort (interactive get only).
        if allow_html and not self._biorxiv_web_blocked:
            tried.append("biorxiv_html")
            html_src = self._html()
            ft = _call_source(
                html_src.get_fulltext,
                doi,
                version=version,
                server=server or (target_meta.server if target_meta else None),
                options=options,
                fetch_tables=fetch_tables,
            )
            if ft is not None:
                return finish(ft)
            html_err = getattr(html_src, "last_error", None) or "no full-text HTML page found"
            notes.append(f"biorxiv_html: {html_err}")

        if source not in (None, "europepmc", "s3", "html"):
            return GetResult(None, tried, f"unknown source {source!r}")

        if meta is not None and meta.license is not None and not meta.license.redistributable:
            notes.append(f"license={meta.license.raw}")
        if not allow_html:
            notes.append("pass --html to try the public HTML page")
        return GetResult(None, tried, "; ".join(notes))


__all__ = ["GetResult", "Router"]
