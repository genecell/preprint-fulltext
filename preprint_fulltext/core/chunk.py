"""chunk.py — turn a :class:`FullText` into corpus :class:`Chunk` records.

Token- and section-aware:
  * Tokenize with the configured tokenizer (default ``tiktoken`` cl100k_base).
  * Greedy-pack to ``chunk_tokens`` with ``chunk_overlap`` overlap **within a
    section**; never cross a section boundary unless ``cross_section=True``.
  * ``chunk_id = "{doi}:{version}:{section_order}:{idx}"`` — deterministic, so a
    re-run reproduces identical ids (idempotency / resumable ingest).
  * ``char_start``/``char_end`` slice back into the *original* section text.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from ..config import Settings, get_settings
from .models import Chunk, FullText, License, Section, SourceName


class _Tokenizer:
    """Thin wrapper over a tiktoken encoding, resolved from a 'tiktoken:<enc>' spec."""

    def __init__(self, spec: str):
        provider, _, name = spec.partition(":")
        if provider != "tiktoken":
            raise ValueError(f"unsupported tokenizer spec {spec!r} (only 'tiktoken:<enc>')")
        import tiktoken

        self._enc = tiktoken.get_encoding(name or "cl100k_base")

    def encode(self, text: str) -> list[int]:
        return self._enc.encode(text)

    def decode(self, tokens: list[int]) -> str:
        return self._enc.decode(tokens)


@lru_cache(maxsize=8)
def _get_tokenizer(spec: str) -> _Tokenizer:
    return _Tokenizer(spec)


def _pack_section(
    text: str, tok: _Tokenizer, chunk_tokens: int, overlap: int
) -> Iterator[tuple[int, int, int]]:
    """Yield (char_start, char_end, token_count) windows over one section's text.

    Windows are token-bounded (never more than ``chunk_tokens``) with ``overlap``
    tokens shared between neighbours; char offsets are derived from decoded-prefix
    lengths so the caller can slice the original text back out.
    """
    toks = tok.encode(text)
    n = len(toks)
    if n == 0:
        return
    step = max(1, chunk_tokens - overlap)
    i = 0
    while i < n:
        end = min(i + chunk_tokens, n)
        char_start = len(tok.decode(toks[:i]))
        char_end = len(tok.decode(toks[:end]))
        yield char_start, char_end, end - i
        if end == n:
            break
        i += step


def chunk_section(
    section: Section,
    *,
    doi: str,
    version: int | None,
    license: License,
    source: SourceName,
    settings: Settings,
) -> list[Chunk]:
    """Chunk a single :class:`Section` into ordered :class:`Chunk` records."""
    tok = _get_tokenizer(settings.tokenizer)
    text = section.text or ""
    if not text.strip():
        return []
    ver = "na" if version is None else str(version)
    out: list[Chunk] = []
    for idx, (cstart, cend, tcount) in enumerate(
        _pack_section(text, tok, settings.chunk_tokens, settings.chunk_overlap)
    ):
        out.append(
            Chunk(
                doi=doi,
                version=version,
                chunk_id=f"{doi}:{ver}:{section.order}:{idx}",
                section_kind=section.kind,
                text=text[cstart:cend],
                token_count=tcount,
                char_start=cstart,
                char_end=cend,
                license=license,
                source=source,
            )
        )
    return out


def chunk_fulltext(ft: FullText, *, settings: Settings | None = None) -> list[Chunk]:
    """Chunk every section of a :class:`FullText` into corpus records.

    With ``cross_section=True`` sections are concatenated (blank-line separated)
    and chunked as one stream, tagging each chunk with the section kind that
    contains its start offset.
    """
    settings = settings or get_settings()
    p = ft.preprint
    license_ = p.license or License(raw="", redistributable=False)
    source = ft.retrieved_from

    if not settings.cross_section:
        chunks: list[Chunk] = []
        for section in ft.sections:
            chunks.extend(
                chunk_section(section, doi=p.doi, version=p.version,
                              license=license_, source=source, settings=settings)
            )
        return chunks
    return _chunk_cross_section(ft, license_, settings)


def _chunk_cross_section(ft: FullText, license_: License, settings: Settings) -> list[Chunk]:
    p = ft.preprint
    tok = _get_tokenizer(settings.tokenizer)
    sep = "\n\n"
    # Build the concatenated stream and remember each section's [start,end) span.
    spans: list[tuple[int, int, Section]] = []
    parts: list[str] = []
    pos = 0
    for s in ft.sections:
        if not (s.text or "").strip():
            continue
        if parts:
            pos += len(sep)
            parts.append(sep)
        start = pos
        parts.append(s.text)
        pos += len(s.text)
        spans.append((start, pos, s))
    doc = "".join(parts)
    if not doc.strip():
        return []

    def kind_at(offset: int):
        for start, end, s in spans:
            if start <= offset < end:
                return s.kind, s.order
        return ft.sections[0].kind, ft.sections[0].order

    ver = "na" if p.version is None else str(p.version)
    out: list[Chunk] = []
    for idx, (cstart, cend, tcount) in enumerate(
        _pack_section(doc, tok, settings.chunk_tokens, settings.chunk_overlap)
    ):
        kind, order = kind_at(cstart)
        out.append(
            Chunk(doi=p.doi, version=p.version, chunk_id=f"{p.doi}:{ver}:x:{idx}",
                  section_kind=kind, text=doc[cstart:cend], token_count=tcount,
                  char_start=cstart, char_end=cend, license=license_, source=ft.retrieved_from)
        )
    return out


__all__ = ["chunk_fulltext", "chunk_section"]
