"""ingest.py — resumable, idempotent, incremental bulk ingestion.

Each preprint is an atomic unit: buffer its chunks, write them, then append a
manifest row. Resume is driven by the manifest (``_manifest.jsonl``): processed
target ids are skipped on restart. Deterministic ``chunk_id`` plus a seen-set make
a mid-preprint crash idempotent — a re-run never writes a duplicate chunk line.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import orjson

from ..config import Settings, get_settings
from ..core.chunk import chunk_fulltext
from ..core.models import FullText
from .export import ExportMode, Gate


@dataclass
class Target:
    """A unit of work: a stable skip id plus a lazy loader (fetch happens in load)."""

    id: str
    load: Callable[[], FullText | None]


@dataclass
class IngestReport:
    processed: int = 0
    skipped: int = 0
    degraded: int = 0
    not_found: int = 0
    n_chunks: int = 0
    bytes_downloaded: int = 0
    errors: int = 0

    def as_dict(self) -> dict:
        return {
            "processed": self.processed,
            "skipped": self.skipped,
            "degraded": self.degraded,
            "not_found": self.not_found,
            "n_chunks": self.n_chunks,
            "bytes_downloaded": self.bytes_downloaded,
            "errors": self.errors,
        }


def manifest_path_for(out: Path) -> Path:
    return out.parent / f"{out.stem}_manifest.jsonl"


class Ingest:
    def __init__(
        self,
        out: Path | str,
        *,
        mode: ExportMode | str = ExportMode.ANALYSIS,
        settings: Settings | None = None,
        on_reminder: Callable[[str], None] | None = None,
        bytes_source=None,
    ):
        self.out = Path(out)
        self.manifest = manifest_path_for(self.out)
        self.settings = settings or get_settings()
        self.gate = Gate(mode, on_reminder=on_reminder)
        self.bytes_source = bytes_source  # e.g. the BiorxivS3 instance (for cost reporting)
        self._processed_ids: set[str] = set()
        self._seen_chunk_ids: set[str] = set()

    def _load_state(self) -> None:
        """Rebuild resume state from the manifest and existing corpus file."""
        self.out.parent.mkdir(parents=True, exist_ok=True)
        if self.manifest.exists():
            for line in self.manifest.read_bytes().splitlines():
                if not line.strip():
                    continue
                try:
                    row = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue
                if row.get("target_id"):
                    self._processed_ids.add(row["target_id"])
        if self.out.exists():
            for line in self.out.read_bytes().splitlines():
                if not line.strip():
                    continue
                try:
                    self._seen_chunk_ids.add(orjson.loads(line)["chunk_id"])
                except (orjson.JSONDecodeError, KeyError):
                    continue

    def run(self, targets: Iterable[Target]) -> IngestReport:
        """Process targets, skipping any already in the manifest. A raised exception
        from ``target.load`` (a kill) propagates after prior work is durably flushed."""
        self._load_state()
        report = IngestReport()

        with self.out.open("ab") as corpus, self.manifest.open("ab") as manifest:
            for target in targets:
                if target.id in self._processed_ids:
                    report.skipped += 1
                    continue

                ft = target.load()  # may raise -> simulates a kill; prior rows are flushed
                if ft is None:
                    self._write_manifest_row(
                        manifest, target_id=target.id, doi=None, version=None,
                        status="not_found", n_chunks=0, license=None, source=None,
                    )
                    self._processed_ids.add(target.id)
                    report.not_found += 1
                    continue

                gated = self.gate.apply(ft)
                chunks = chunk_fulltext(gated.fulltext, settings=self.settings)
                new = [c for c in chunks if c.chunk_id not in self._seen_chunk_ids]

                buf = b"".join(orjson.dumps(c.model_dump(mode="json")) + b"\n" for c in new)
                corpus.write(buf)
                corpus.flush()
                for c in new:
                    self._seen_chunk_ids.add(c.chunk_id)

                p = gated.fulltext.preprint
                self._write_manifest_row(
                    manifest, target_id=target.id, doi=p.doi, version=p.version,
                    status="degraded" if gated.degraded else "ok", n_chunks=len(new),
                    license=(p.license.spdx_id if p.license else None),
                    source=gated.fulltext.retrieved_from.value,
                )

                self._processed_ids.add(target.id)
                report.processed += 1
                report.n_chunks += len(new)
                if gated.degraded:
                    report.degraded += 1

        if self.bytes_source is not None:
            report.bytes_downloaded = getattr(self.bytes_source, "bytes_downloaded", 0)
        return report

    @staticmethod
    def _write_manifest_row(fh, **row) -> None:
        fh.write(orjson.dumps(row) + b"\n")
        fh.flush()


__all__ = ["Ingest", "Target", "IngestReport", "manifest_path_for"]
