"""router.py — verb + flags -> concrete Source. `--source` overrides.

`get_fulltext` embodies the key coverage rule from the addendum: Europe PMC has
retrievable full text for bioRxiv only for CC-licensed preprints, so for an
all-rights-reserved preprint EPMC returns None and S3 is the *only* full-text
source. Without AWS credentials that full text is simply unavailable, and we say so.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings, get_settings
from ..core.models import FullText, Server
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
    except Exception:
        return False


class Router:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._epmc: EuropePMC | None = None

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
        """Best-effort bioRxiv-API metadata (latest version). Never fails the request."""
        try:
            from ..sources.biorxiv_api import BiorxivAPI

            meta = BiorxivAPI(self.settings).get_metadata(doi, server)
            return meta, (meta.version if meta else None)
        except Exception:
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
        meta, latest = self._resolve_meta(doi, server)
        epmc_ok = version is None or latest is None or version == latest

        def finish(ft: FullText | None, reason: str | None = None) -> GetResult:
            if ft is not None:
                self._enrich(ft, meta, version if version is not None else latest)
            return GetResult(ft, tried, reason if ft is None else None)

        # Forced HTML source.
        if source == "html":
            tried.append("biorxiv_html")
            return finish(self._html().get_fulltext(doi, version=version, server=server),
                          "no full-text HTML page found")

        if source in (None, "europepmc") and epmc_ok:
            tried.append("europepmc")
            ft = self.epmc.get_fulltext(doi, version=version)
            if ft is not None:
                return finish(ft)
            if source == "europepmc":
                return GetResult(None, tried, "not open-access on Europe PMC")

        if source in (None, "s3"):
            if _have_aws_credentials():
                tried.append("biorxiv_s3")
                try:
                    ft = self._s3().get_fulltext(doi, version=version, server=server)
                except SourceError as e:
                    ft = None
                    if source == "s3":
                        return GetResult(None, tried, str(e))
                if ft is not None:
                    return finish(ft)
                if source == "s3":
                    return GetResult(None, tried, "not found in S3")
            elif source == "s3":
                return GetResult(None, tried, "S3 requested but no AWS credentials found")

        # Opt-in HTML last resort (interactive get only).
        if allow_html:
            tried.append("biorxiv_html")
            ft = self._html().get_fulltext(doi, version=version, server=server)
            if ft is not None:
                return finish(ft)

        if source not in (None, "europepmc", "s3", "html"):
            return GetResult(None, tried, f"unknown source {source!r}")
        reason = (
            "not on Europe PMC (likely non-CC/all-rights-reserved); "
            + ("S3 had no match" if _have_aws_credentials() else "no AWS credentials for S3")
            + ("" if allow_html else "; pass --html to try the public HTML page")
        )
        return GetResult(None, tried, reason)


__all__ = ["Router", "GetResult"]
