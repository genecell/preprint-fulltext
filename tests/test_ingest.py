"""Ingest resumability + idempotency (critical)."""

from __future__ import annotations

import orjson
import pytest

from preprint_fulltext.config import Settings
from preprint_fulltext.core.models import (
    FullText,
    License,
    Preprint,
    Section,
    SectionKind,
    Server,
    SourceName,
)
from preprint_fulltext.pipeline.export import ExportMode
from preprint_fulltext.pipeline.ingest import Ingest, Target, manifest_path_for

CCBY = License(raw="cc-by", spdx_id="CC-BY-4.0", redistributable=True, requires_attribution=True)
ARR = License(raw="arr", spdx_id=None, redistributable=False)
SETTINGS = Settings(chunk_tokens=16, chunk_overlap=4)


def _ft(i: int, license_: License = CCBY) -> FullText:
    body = " ".join(f"doc{i}word{j}" for j in range(60))
    return FullText(
        preprint=Preprint(doi=f"10.1101/doc{i}", version=1, server=Server.BIORXIV, license=license_),
        sections=[Section(id="1", kind=SectionKind.RESULTS, order=1, text=body)],
        retrieved_from=SourceName.BIORXIV_S3,
    )


def _targets(n: int, fail_at: int | None = None):
    for i in range(n):
        def load(i=i):
            if fail_at is not None and i == fail_at:
                raise RuntimeError("simulated kill")
            return _ft(i)

        yield Target(id=f"t{i}", load=load)


def _read_chunk_ids(path):
    return [orjson.loads(l)["chunk_id"] for l in path.read_bytes().splitlines() if l.strip()]


def test_resume_after_kill_no_duplicates(tmp_path):
    out = tmp_path / "corpus.jsonl"

    # First run: dies while processing the 3rd target (index 2).
    with pytest.raises(RuntimeError):
        Ingest(out, settings=SETTINGS).run(_targets(5, fail_at=2))

    manifest = manifest_path_for(out)
    rows = [orjson.loads(l) for l in manifest.read_bytes().splitlines() if l.strip()]
    assert len(rows) == 2  # only t0, t1 committed before the kill
    first_ids = set(_read_chunk_ids(out))

    # Rerun with the same targets: skips t0/t1, completes t2..t4.
    report = Ingest(out, settings=SETTINGS).run(_targets(5))
    assert report.skipped == 2
    assert report.processed == 3

    all_rows = [orjson.loads(l) for l in manifest.read_bytes().splitlines() if l.strip()]
    assert len(all_rows) == 5
    assert {r["target_id"] for r in all_rows} == {f"t{i}" for i in range(5)}

    chunk_ids = _read_chunk_ids(out)
    assert len(chunk_ids) == len(set(chunk_ids))  # NO duplicates
    assert first_ids.issubset(set(chunk_ids))  # early work preserved


def test_idempotent_full_rerun_zero_new_work(tmp_path):
    out = tmp_path / "corpus.jsonl"
    Ingest(out, settings=SETTINGS).run(_targets(3))
    chunks_before = _read_chunk_ids(out)

    report = Ingest(out, settings=SETTINGS).run(_targets(3))
    assert report.processed == 0
    assert report.skipped == 3
    assert _read_chunk_ids(out) == chunks_before  # unchanged


def test_not_found_records_manifest_row(tmp_path):
    out = tmp_path / "corpus.jsonl"
    targets = [Target(id="miss", load=lambda: None), Target(id="hit", load=lambda: _ft(0))]
    report = Ingest(out, settings=SETTINGS).run(iter(targets))
    assert report.not_found == 1 and report.processed == 1
    rows = {orjson.loads(l)["target_id"]: orjson.loads(l)
            for l in manifest_path_for(out).read_bytes().splitlines() if l.strip()}
    assert rows["miss"]["status"] == "not_found"


def test_redistribution_mode_degrades_and_counts(tmp_path):
    out = tmp_path / "corpus.jsonl"
    targets = [Target(id="cc", load=lambda: _ft(0, CCBY)),
               Target(id="arr", load=lambda: _ft(1, ARR))]
    report = Ingest(out, mode=ExportMode.REDISTRIBUTION, settings=SETTINGS).run(iter(targets))
    assert report.degraded == 1
    rows = {orjson.loads(l)["target_id"]: orjson.loads(l)
            for l in manifest_path_for(out).read_bytes().splitlines() if l.strip()}
    assert rows["arr"]["status"] == "degraded" and rows["arr"]["n_chunks"] == 0
    assert rows["cc"]["status"] == "ok" and rows["cc"]["n_chunks"] > 0
    # The ARR body text must never appear in the corpus.
    assert b"doc1word" not in out.read_bytes()


def test_valid_jsonl_chunks_written(tmp_path):
    out = tmp_path / "corpus.jsonl"
    Ingest(out, settings=SETTINGS).run(_targets(2))
    for line in out.read_bytes().splitlines():
        rec = orjson.loads(line)
        assert rec["chunk_id"] and rec["section_kind"] == "results"
        assert rec["token_count"] <= SETTINGS.chunk_tokens
