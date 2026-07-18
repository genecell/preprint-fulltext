"""Typer CLI — thin frontend over the core library.

Subcommands: `get` (single full text), `discover`/`search` (SearchHit JSONL),
`ingest` (bulk chunked corpus). All heavy lifting lives in the core library and
`pipeline/`; this module only parses args, calls the router/pipeline, and formats.
"""

from __future__ import annotations

import datetime as dt
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Optional

import orjson
import typer

from .config import get_settings
from .core.models import FullText, SearchHit

app = typer.Typer(
    name="preprint-fulltext",
    help="Retrieve full text of bioRxiv/medRxiv preprints into embedding-ready corpora.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _main() -> None:
    """preprint-fulltext — CLI frontend over the shared core library."""


def _dumps(obj) -> bytes:
    return orjson.dumps(obj, option=orjson.OPT_INDENT_2)


def _write_hits_jsonl(hits: Iterable[SearchHit], out: Optional[Path], limit: int) -> int:
    """Stream SearchHit records as one JSON object per line; returns the count."""
    fh = out.open("wb") if out else sys.stdout.buffer
    n = 0
    try:
        for hit in hits:
            fh.write(orjson.dumps(hit.model_dump(mode="json")))
            fh.write(b"\n")
            n += 1
            if n >= limit:
                break
    finally:
        if out:
            fh.close()
    return n


def _since_to_date(since: Optional[str]) -> Optional[dt.date]:
    """Accept YYYY-MM or YYYY-MM-DD; map YYYY-MM to the first of the month."""
    if not since:
        return None
    parts = since.split("-")
    if len(parts) == 2:
        return dt.date(int(parts[0]), int(parts[1]), 1)
    return dt.date.fromisoformat(since)


def _render_markdown(ft: FullText) -> str:
    p = ft.preprint
    lines = [f"# {p.title or p.doi}", ""]
    meta = [f"**DOI:** {p.doi}", f"**Server:** {p.server.value}"]
    if p.version is not None:
        meta.append(f"**Version:** {p.version}")
    if p.authors:
        meta.append(f"**Authors:** {', '.join(p.authors)}")
    if p.license:
        lic = p.license.spdx_id or p.license.raw or "unknown"
        meta.append(f"**License:** {lic} (redistributable={p.license.redistributable})")
    meta.append(f"**Retrieved from:** {ft.retrieved_from.value}")
    lines.append("  \n".join(meta))
    lines.append("")
    for s in ft.sections:
        heading = s.title or s.kind.value.capitalize()
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(s.text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


@app.command()
def version() -> None:
    """Print the installed version."""
    from . import __version__

    typer.echo(__version__)


@app.command()
def get(
    doi: str = typer.Argument(..., help="DOI, arXiv id, or a doi.org/bioRxiv/arxiv.org URL."),
    version: Optional[int] = typer.Option(None, "--version", "-v", help="Specific version."),
    source: Optional[str] = typer.Option(
        None, "--source", help="Force a source: europepmc | s3 | html | arxiv (default: auto)."
    ),
    server: Optional[str] = typer.Option(None, "--server", help="biorxiv | medrxiv (hint for S3/HTML)."),
    html: bool = typer.Option(
        False, "--html", help="Allow the public HTML page as a last-resort fallback (interactive only)."
    ),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Render sections as markdown."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write to file instead of stdout."),
) -> None:
    """Retrieve one preprint's full text as structured JSON (default) or markdown.

    Accepts a bioRxiv/medRxiv DOI or content URL, a https://doi.org/… URL, or an arXiv id
    / arxiv.org URL / 10.48550/arXiv.* DOI (routed to arXiv's LaTeXML full text).
    """
    from .pipeline.router import Router

    result = Router(get_settings()).get_fulltext(
        doi, version=version, source=source, server=server, allow_html=html
    )
    if result.fulltext is None:
        typer.secho(
            f"No full text for {doi} (tried: {', '.join(result.tried) or 'none'}). "
            f"{result.reason or ''}".strip(),
            err=True,
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=2)

    if markdown:
        payload = _render_markdown(result.fulltext).encode("utf-8")
    else:
        payload = _dumps(result.fulltext.model_dump(mode="json"))

    if out:
        out.write_bytes(payload)
        typer.secho(f"wrote {out}", err=True, fg=typer.colors.GREEN)
    else:
        sys.stdout.buffer.write(payload)
        if not payload.endswith(b"\n"):
            sys.stdout.buffer.write(b"\n")


@app.command()
def search(
    query: str = typer.Argument(..., help="Keyword query."),
    field: str = typer.Option("fulltext", "--field", help="fulltext | title | abstract | author."),
    source: str = typer.Option("europepmc", "--source", help="europepmc | openalex | arxiv."),
    limit: int = typer.Option(25, "--limit", "-n", help="Max hits."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write JSONL to file."),
) -> None:
    """Keyword search → SearchHit JSONL. --field scopes to title/abstract/author/fulltext."""
    settings = get_settings()
    if source == "europepmc":
        from .sources.europepmc import EuropePMC

        hits: Iterator[SearchHit] = EuropePMC(settings).search(query, limit, field=field)
    elif source == "openalex":
        from .sources.openalex import OpenAlex

        hits = OpenAlex(settings).search(query, limit, field=field)
    elif source == "arxiv":
        from .sources.arxiv import ArxivAPI

        hits = ArxivAPI(settings).search(query, limit, field=field)
    else:
        typer.secho(f"unknown source {source!r} (europepmc|openalex|arxiv)", err=True, fg="red")
        raise typer.Exit(code=2)
    _run_hits(hits, out, limit)


@app.command()
def discover(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Free-text topic."),
    category: Optional[str] = typer.Option(None, "--category", help="Subject/concept."),
    since: Optional[str] = typer.Option(None, "--since", help="From date (YYYY-MM or YYYY-MM-DD)."),
    to: Optional[str] = typer.Option(None, "--to", help="To date (YYYY-MM-DD)."),
    source: str = typer.Option("openalex", "--source", help="openalex | europepmc | arxiv."),
    limit: int = typer.Option(100, "--limit", "-n", help="Max hits."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write JSONL to file."),
) -> None:
    """Discover preprints by topic/category/date window → SearchHit JSONL."""
    from .sources.base import DiscoverQuery

    settings = get_settings()
    dq = DiscoverQuery(
        query=query, category=category,
        from_date=_since_to_date(since), to_date=_since_to_date(to), limit=limit,
    )
    if source == "openalex":
        from .sources.openalex import OpenAlex

        hits: Iterator[SearchHit] = OpenAlex(settings).discover(dq)
    elif source == "europepmc":
        from .sources.europepmc import EuropePMC

        hits = EuropePMC(settings).discover(dq)
    elif source == "arxiv":
        from .sources.arxiv import ArxivAPI

        hits = ArxivAPI(settings).discover(dq)
    else:
        typer.secho(f"unknown source {source!r} (openalex|europepmc|arxiv)", err=True, fg="red")
        raise typer.Exit(code=2)
    _run_hits(hits, out, limit)


@app.command()
def ingest(
    out: Path = typer.Argument(..., help="Output corpus path (JSONL, or .parquet with --format parquet)."),
    source: str = typer.Option("s3", "--source", help="s3 | europepmc."),
    server: str = typer.Option("biorxiv", "--server", help="biorxiv | medrxiv | both (s3)."),
    since: Optional[str] = typer.Option(None, "--since", help="From month YYYY-MM (Current_Content only)."),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="EPMC query (source=europepmc)."),
    include_back_content: bool = typer.Option(
        False, "--include-back-content", help="Also ingest undated S3 Back_Content batches."
    ),
    redistribution: bool = typer.Option(
        False, "--redistribution", help="Gate for a shareable corpus (degrade non-CC to stubs)."
    ),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max preprints (testing/sampling)."),
    fmt: str = typer.Option("jsonl", "--format", help="jsonl | parquet."),
) -> None:
    """Bulk full text → chunked corpus JSONL/Parquet. Resumable and incremental."""
    from .pipeline.export import ExportMode
    from .pipeline.ingest import Ingest, Target

    settings = get_settings()
    mode = ExportMode.REDISTRIBUTION if redistribution else ExportMode.ANALYSIS
    since_date = _since_to_date(since)

    targets: Iterator[Target]
    bytes_source = None
    if source == "s3":
        from .core.models import Server
        from .sources.biorxiv_s3 import BiorxivS3

        s3 = BiorxivS3(settings)
        bytes_source = s3
        servers = [Server.BIORXIV, Server.MEDRXIV] if server == "both" else [Server(server)]

        def _s3_targets() -> Iterator[Target]:
            count = 0
            for srv in servers:
                for key in s3.iter_keys(srv, since=since_date, include_back_content=include_back_content):
                    yield Target(
                        id=f"{srv.value}:{key}",
                        load=lambda srv=srv, key=key: s3.parse_meca(s3.fetch_meca(srv, key), srv, key),
                    )
                    count += 1
                    if limit and count >= limit:
                        return

        targets = _s3_targets()
    elif source == "europepmc":
        from .sources.europepmc import EuropePMC

        epmc = EuropePMC(settings)
        q = query or "*"

        def _epmc_targets() -> Iterator[Target]:
            for i, hit in enumerate(epmc.search(q, limit or 1000)):
                if not hit.doi:
                    continue
                yield Target(id=f"doi:{hit.doi}", load=lambda doi=hit.doi: epmc.get_fulltext(doi))
                if limit and i + 1 >= limit:
                    return

        targets = _epmc_targets()
    elif source == "arxiv":
        typer.secho(
            "arXiv bulk ingest is not supported (arXiv full text is HTML, single-document). "
            "Use `get`/`search` for arXiv, or arXiv's own S3 LaTeX-source bucket for bulk.",
            err=True, fg="red",
        )
        raise typer.Exit(code=2)
    else:
        typer.secho(f"unknown source {source!r} (s3|europepmc)", err=True, fg="red")
        raise typer.Exit(code=2)

    ing = Ingest(out, mode=mode, settings=settings,
                 on_reminder=lambda m: typer.secho(m, err=True, fg="yellow"),
                 bytes_source=bytes_source)
    report = ing.run(targets)

    if fmt == "parquet":
        _to_parquet(out)

    typer.secho(
        f"ingest done: {report.processed} processed, {report.skipped} skipped, "
        f"{report.degraded} degraded, {report.not_found} not-found, "
        f"{report.n_chunks} chunks, {report.bytes_downloaded} bytes (requester-pays).",
        err=True, fg="green",
    )


def _to_parquet(jsonl_out: Path) -> None:
    """Convert the durable JSONL corpus to Parquet (best-effort, needs pyarrow)."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        typer.secho("pyarrow not installed; keeping JSONL only", err=True, fg="yellow")
        return
    rows = [orjson.loads(line) for line in jsonl_out.read_bytes().splitlines() if line.strip()]
    if not rows:
        return
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, str(jsonl_out.with_suffix(".parquet")))


def _run_hits(hits: Iterator[SearchHit], out: Optional[Path], limit: int) -> None:
    from .sources.base import SourceError

    try:
        n = _write_hits_jsonl(hits, out, limit)
    except SourceError as e:
        typer.secho(str(e), err=True, fg="red")
        raise typer.Exit(code=2)
    typer.secho(f"{n} hit(s)" + (f" → {out}" if out else ""), err=True, fg="green")


if __name__ == "__main__":  # pragma: no cover
    app()
