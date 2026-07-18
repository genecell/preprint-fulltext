---
name: preprint-fulltext
description: >-
  Retrieve full text of bioRxiv/medRxiv/arXiv preprints as structured sections to ground
  scientific reasoning and deep research (methods/results, not just abstracts), or build
  embedding-ready corpora. Use when a task needs a preprint's full text or sections
  from a DOI/arXiv id/URL; to verify a claim against a paper's Results; to extract methods
  or parameters; keyword/title/author search over preprints; discovery by topic/date; or a
  chunked JSONL/Parquet corpus for embeddings/RAG. Triggers on: bioRxiv, medRxiv, arXiv,
  openRxiv, preprint full text, JATS, a 10.1101/ or 10.64898/ DOI, an arXiv id (2401.10515),
  "get the methods/results section", "what does this paper actually do", "search preprints".
---

# preprint-fulltext

A CLI + Python library + MCP server for retrieving bioRxiv/medRxiv preprint full text
and turning it into structured, embedding-ready data. One canonical model and one
shared JATS parser back every path.

## When to use

- The user gives a **preprint DOI or bioRxiv/medRxiv URL** and wants the full text or
  a specific section (methods, results, …).
- The user wants to **search** preprints by keyword, **title**, **abstract**, or
  **author**, or **discover** them by topic/category/date.
- The user wants a **corpus** of preprint full text chunked for embeddings/RAG.

Do NOT use for published-journal full text in general (this is preprint-scoped), and
do not scrape the bioRxiv website in bulk — use `ingest --source s3` for corpora.

## Why full text (for grounded reasoning)

Prefer full text over abstracts when the task needs real evidence: methods, quantities,
protocols, datasets, and results live in the body. `get_fulltext` returns section-labeled
text (`kind` = methods / results / discussion / …) with `source`, `version`, and `license`,
so you can:
- **cite precisely** — quote/attribute the exact section of a specific paper + version;
- **verify claims** — check an assertion against the paper's Results, not its abstract;
- **extract methods/parameters** — read the Methods section directly;
- **stay within-license** — each Section/Chunk carries its license and a link-back source.
This grounds reasoning in the primary source rather than a recalled (possibly stale) summary.

## CLI

```bash
# One preprint -> structured sections (Europe PMC -> S3 router). Accepts DOI, doi.org
# URL, or a bioRxiv/medRxiv content URL. --markdown for readable output; default JSON.
preprint-fulltext get <DOI|URL> [--markdown] [--version N] [--source europepmc|s3|html] [--html]

# Search -> one SearchHit per line (JSONL). --field scopes the query.
preprint-fulltext search "<query>" [--field fulltext|title|abstract|author] [--source europepmc|openalex] [-n N]

# Discover by topic/category/date -> SearchHit JSONL (OpenAlex by default).
preprint-fulltext discover [--query Q] [--category C] [--since YYYY-MM] [--to YYYY-MM-DD] [-n N]

# Bulk corpus -> Chunk JSONL/Parquet + <out>_manifest.jsonl (resumable, incremental).
preprint-fulltext ingest <out.jsonl> --source s3|europepmc [--server biorxiv|medrxiv|both]
    [--since YYYY-MM] [--redistribution] [--format jsonl|parquet] [-n N]
```

Notes for agents:
- **arXiv:** `get` accepts an arXiv id (`2401.10515`), `arXiv:` prefix, an arxiv.org URL, or
  the `10.48550/arXiv.*` DOI, and returns full text from arXiv's LaTeXML HTML (native →
  ar5iv). `search --source arxiv` / `discover --source arxiv` query the arXiv API. arXiv is
  **not** available in `ingest` (single-document only).
- **Versions:** a DOI resolves to the **latest version by default** (openRxiv semantics).
  Pass `--version N` for a specific one. Europe PMC only serves the latest indexed
  version, so an explicit older version is fetched via the HTML source (`--source html
  --version 1`) or S3. The retrieved version is reported in `preprint.version`.
- `get` with no `--source` tries Europe PMC, then S3 (if AWS creds), and only tries the
  public HTML page if you pass `--html`. Europe PMC full text exists for the **CC /
  open-access subset**; all-rights-reserved preprints need S3 or `--html`.
- `--field title`/`abstract` match **all terms** (not an exact phrase); `--field author`
  matches an author name. For topical multi-word queries prefer `--field fulltext`.
- `ingest --source s3` is **requester-pays** (needs AWS credentials and costs money;
  ~$0.09/GB). `ingest --source europepmc` is free but only covers the CC subset.
- `--redistribution` degrades non-redistributable works to metadata-only stubs.

## Python

```python
from preprint_fulltext.pipeline.router import Router
from preprint_fulltext.core.chunk import chunk_fulltext

result = Router().get_fulltext("10.1101/2024.01.15.575000")  # -> GetResult
ft = result.fulltext                     # FullText | None (result.reason if None)
chunks = chunk_fulltext(ft)              # list[Chunk], embedding-ready
```

## MCP tools

Run `preprint-fulltext-mcp` (stdio). Tools:
- `search_preprints(query, source?, limit?)` → list of hits
- `get_fulltext(doi, as_markdown?)` → structured sections (or Markdown)
- `get_metadata(doi)` → bibliographic metadata (abstract only)
- `resolve(doi_or_openalex_id)` → cross-identifier resolution

Bulk `ingest` is intentionally not an MCP tool.

## Data model (what you get back)

- `FullText`: `preprint` + ordered `sections` (`kind` ∈ abstract|intro|methods|results|
  discussion|other) + `retrieved_from`.
- `Chunk` (the corpus record): `doi, version, chunk_id, section_kind, text,
  token_count, char_start, char_end, license, source`. One JSONL line per chunk.
- `SearchHit`: `title, doi?, openalex_id?, score?, source, snippet?, oa_url?, has_fulltext`.

## Gotchas

- openRxiv DOIs use prefix **`10.64898`** since 2025-12 (legacy **`10.1101`** before).
- OpenAlex requires an API key (`OPENALEX_API_KEY`) since 2026-02-13; missing → HTTP 409.
- Set `CONTACT_EMAIL` for the Europe PMC / OpenAlex polite pools.
- Retrieved content keeps its own license; corpora are for your own TDM, not re-hosting.
