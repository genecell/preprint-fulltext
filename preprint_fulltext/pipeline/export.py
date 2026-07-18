"""export.py — the compliance gate. The ONLY way body text reaches a corpus.

`analysis` (default): pass-through, plus a one-time TDM-terms reminder.
`redistribution`: works with ``license.redistributable == True`` pass unchanged;
all others are degraded to a **link-back stub** (metadata + oa_url, no body text).
Unknown license → non-redistributable (enforced upstream in ``core.licenses``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..core.models import FullText, Preprint

_TDM_REMINDER = (
    "[preprint-fulltext] TDM terms: this corpus is for your own text/data mining. "
    "Do not re-host or redistribute openRxiv full text; tools built on it must link "
    "back to the openRxiv-hosted text. Use --redistribution to gate a shareable corpus."
)


class ExportMode(StrEnum):
    ANALYSIS = "analysis"
    REDISTRIBUTION = "redistribution"


@dataclass
class GateResult:
    fulltext: FullText  # body-stripped when degraded
    degraded: bool


class Gate:
    """Stateful gate so the analysis-mode reminder prints only once per run."""

    def __init__(self, mode: ExportMode | str = ExportMode.ANALYSIS, *, on_reminder=None):
        self.mode = ExportMode(mode)
        self._reminded = False
        self._on_reminder = on_reminder

    def _remind_once(self) -> None:
        if not self._reminded:
            self._reminded = True
            if self._on_reminder:
                self._on_reminder(_TDM_REMINDER)

    def apply(self, ft: FullText) -> GateResult:
        if self.mode is ExportMode.ANALYSIS:
            self._remind_once()
            return GateResult(ft, degraded=False)

        lic = ft.preprint.license
        if lic is not None and lic.redistributable:
            return GateResult(ft, degraded=False)
        return GateResult(_link_back_stub(ft), degraded=True)


def _link_back_stub(ft: FullText) -> FullText:
    """A body-free stub: keep bibliographic metadata + link-back, drop all sections."""
    p = ft.preprint
    oa_url = (p.provenance or {}).get("oa_url") or ft.raw_ref
    stub_preprint = Preprint(
        doi=p.doi,
        version=p.version,
        server=p.server,
        title=p.title,
        authors=p.authors,
        date=p.date,
        category=p.category,
        abstract=None,  # abstract is body-adjacent; omit from a redistribution stub
        license=p.license,
        published_doi=p.published_doi,
        provenance={**(p.provenance or {}), "degraded": True, "oa_url": oa_url},
    )
    return FullText(
        preprint=stub_preprint,
        sections=[],  # NO body text
        retrieved_from=ft.retrieved_from,
        raw_ref=ft.raw_ref,
    )


__all__ = ["Gate", "GateResult", "ExportMode"]
