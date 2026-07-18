# preprint-fulltext

<p align="center">
  <b>English</b> |
  <a href="README.zh.md">简体中文</a> |
  <a href="README.zht.md">繁體中文</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.es.md">Español</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.it.md">Italiano</a> |
  <a href="README.ja.md">日本語</a>
</p>

[![PyPI](https://img.shields.io/pypi/v/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![Python](https://img.shields.io/pypi/pyversions/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](LICENSE)
[![CI](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml/badge.svg)](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml)

Retrieve the **full text** of bioRxiv / medRxiv / **arXiv** preprints as clean,
structured, embedding-ready data — from a CLI, a Python library, or an MCP server.

`preprint-fulltext` turns a DOI (or a search) into structured sections
(abstract / introduction / methods / results / discussion), a single JSON/Markdown
document, or a chunked JSONL/Parquet corpus ready for embeddings and RAG. openRxiv
text-and-data-mining (TDM) compliance is enforced structurally, not left to the user.

> **"Embedding-ready" means the output is clean, section-aware, token-bounded chunks —
> ready to feed to *your* embedding model. Computing embeddings is an optional last step
> you own; this tool does not bundle an embedding model.**

## Contents

- [Why](#why) · [Who it's for](#who-its-for) · [Full text for AI-driven science](#full-text-for-ai-driven-science)
- [Features](#features) · [Install](#install) · [Quickstart (CLI)](#quickstart-cli) · [Typical workflows](#typical-workflows)
- [Python library](#python) · [**MCP server (coding agents)**](#mcp-server) · [Data sources & routing](#data-sources--routing)
- [Configuration](#configuration) · [Compliance](#compliance) · [Development](#development) · [Contact](#contact) · [License](#license)

---

## Why

Preprint full text is scattered across incompatible channels: Europe PMC serves JATS
XML for the open-access subset, the openRxiv S3 buckets hold the authoritative
`.meca` corpus (requester-pays), OpenAlex is a catalog with n-gram-only full-text
search, and the bioRxiv/medRxiv websites render HTML. `preprint-fulltext` unifies
them behind one canonical data model and **one shared JATS parser**, so you get the
same structured output no matter where a document came from.

## Who it's for

- **ML / NLP researchers** building embedding corpora or RAG systems over the
  preprint literature.
- **Bioinformaticians and labs** who need a paper's methods/results as clean text for
  analysis, extraction, or LLM pipelines.
- **Coding agents** (via the MCP server / `SKILL.md`) that need to pull a preprint's
  full text or search the literature mid-task.
- Anyone who wants **one preprint's sections from a DOI** without hand-parsing JATS or
  scraping HTML.

## Full text for AI-driven science

Language models and agents reason far more reliably over a paper's **methods and results**
than over its abstract alone — most scientific claims, protocols, quantities, and caveats
live in the body. `preprint-fulltext` gives Claude, Codex, and other agents that body as
clean, section-labeled, provenance- and license-tagged text, which is the substrate for
**grounded scientific reasoning and deep research**:

- **Literature deep-research** — read across many papers' full text, not just abstracts.
- **Methods / protocol extraction** — pull exact procedures, parameters, and datasets.
- **Claim verification** — check a stated result against the actual Results section.
- **Reproducibility & meta-analysis** — compare methods and numbers across studies.
- **RAG over your own corpus** — section-aware, token-bounded chunks with citations.

Because every `Section`/`Chunk` carries its `kind` (methods / results / …), `source`, and
`license`, an agent can **cite precisely** (which section of which paper/version) and stay
**within-license** while it reasons. Full text is retrieval, not memorization: the model
grounds its reasoning in the primary source instead of recalling a possibly-stale summary.

## Features

- **`get <id>`** — one preprint's full text as structured JSON or Markdown. bioRxiv/
  medRxiv route Europe PMC → S3 (opt-in HTML fallback); **arXiv** ids route to arXiv's
  LaTeXML full text (native HTML → ar5iv). Latest version by default; `--version` selects one.
- **`search` / `discover`** — keyword, title, abstract, or author search across Europe PMC,
  OpenAlex, and **arXiv**; topic/category/date discovery.
- **`ingest`** — resumable, incremental bulk ingestion from the openRxiv S3 buckets
  into a chunked corpus (JSONL or Parquet) with a sidecar manifest.
- **MCP server** — the same capabilities as tools for coding agents.
- **Compliance built in** — an export gate degrades non-redistributable works to
  link-back stubs; unknown licenses are treated as non-redistributable (fail-safe).
- **One JATS parser** shared by the Europe PMC and S3 paths; token- and
  section-aware chunking with deterministic, idempotent chunk ids.

## Install

```bash
pip install preprint-fulltext                       # CLI + Python library + MCP server
pip install "preprint-fulltext[parquet,openalex]"   # + Parquet output, pyalex
```

The **MCP server is built in** — no extra install and no third-party MCP framework. It's a
small, self-contained JSON-RPC 2.0 stdio server, so `preprint-fulltext-mcp` works out of the
box with only the core dependencies.

Set a contact email for the Europe PMC / OpenAlex polite pools (recommended), and an
OpenAlex API key if you use OpenAlex (required by OpenAlex since 2026-02-13):

```bash
export CONTACT_EMAIL="you@example.org"
export OPENALEX_API_KEY="..."            # only needed for OpenAlex discover/search
```

## Quickstart (CLI)

```bash
# Structured full text for one preprint (Europe PMC → S3 router)
preprint-fulltext get 10.1101/2024.01.15.575000 --markdown

# Accepts a DOI, a doi.org URL, or a bioRxiv/medRxiv content URL
preprint-fulltext get https://www.biorxiv.org/content/10.64898/2026.06.13.731750v1.full --html --markdown

# Versions: the DOI resolves to the latest version by default; --version selects one
preprint-fulltext get 10.64898/2026.01.29.702557 --version 1 --source html --markdown

# arXiv: id, arxiv.org URL, or 10.48550/arXiv.* DOI — routed to arXiv LaTeXML full text
preprint-fulltext get arXiv:1706.03762 --markdown
preprint-fulltext get https://arxiv.org/abs/2401.10515 --markdown

# Search: keyword, title, or author (add --source arxiv to search arXiv)
preprint-fulltext search "cortical interneurons" -n 20
preprint-fulltext search "Fezf2" --field title
preprint-fulltext search "Min Dai" --field author
preprint-fulltext search "diffusion model" --field title --source arxiv

# Discover by topic + date window (OpenAlex)
preprint-fulltext discover --query "spatial transcriptomics" --since 2025-01 -n 100

# Bulk corpus from S3 (requester-pays; needs AWS credentials)
preprint-fulltext ingest corpus.jsonl --source s3 --server biorxiv --since 2025-06

# A free, no-AWS corpus of the open-access (CC) subset via Europe PMC
preprint-fulltext ingest corpus.jsonl --source europepmc --query "long covid"
```

`get` emits a `FullText` document (JSON) or Markdown (`--markdown`). `search` /
`discover` stream one `SearchHit` per line (JSONL). `ingest` writes one `Chunk` per
line plus a `<out>_manifest.jsonl` audit/resume sidecar.

## Typical workflows

**1. Read one paper's methods/results as text.**

```bash
preprint-fulltext get 10.64898/2026.01.29.702557 --markdown > paper.md
# -> # Title / ## Abstract / ## Introduction / ## Methods / ## Results / ## Discussion
```

**2. Build an embedding-ready corpus on a topic (free, no AWS).**

```bash
# CC/open-access subset via Europe PMC — one Chunk per JSONL line
preprint-fulltext ingest cortex.jsonl --source europepmc --query "cortical interneurons" -n 500
# cortex.jsonl          -> {doi, version, chunk_id, section_kind, text, token_count, license, ...}
# cortex_manifest.jsonl -> one row per preprint (doi, version, license, n_chunks, status)
```

**3. Build the complete corpus for a month from S3 (requester-pays).**

```bash
export AWS_PROFILE=...           # needs AWS credentials; ~$0.09/GB
preprint-fulltext ingest 2025-06.jsonl --source s3 --server both --since 2025-06 --format parquet
# resumable: rerun after an interruption and it skips finished preprints (no duplicates)
```

**4. Find papers by author or title, then fetch.**

```bash
preprint-fulltext search "Min Dai" --field author -n 20 > hits.jsonl
preprint-fulltext get "$(head -1 hits.jsonl | python -c 'import sys,json;print(json.load(sys.stdin)["doi"])')" --markdown
```

**5. Give a coding agent literature access** — run `preprint-fulltext-mcp` and point your
agent at it (see [`skills/preprint-fulltext/SKILL.md`](skills/preprint-fulltext/SKILL.md)).

## Python

```python
from preprint_fulltext.pipeline.router import Router

result = Router().get_fulltext("10.1101/2024.01.15.575000")
if result.fulltext:
    for section in result.fulltext.sections:
        print(section.kind, section.title)

from preprint_fulltext.core.chunk import chunk_fulltext
chunks = chunk_fulltext(result.fulltext)   # embedding-ready Chunk records
```

## MCP server

Give a coding agent live preprint access. The server exposes four tools —
`search_preprints`, `get_fulltext`, `get_metadata`, `resolve` — over stdio. (Bulk `ingest`
is intentionally **not** a tool: it is long-running and incurs requester-pays cost.)

`mcp-name: io.github.genecell/preprint-fulltext`

It's a **local stdio** server, so it works in Claude Code / Cursor / VS Code / Windsurf /
Zed / Codex / Cline — but not the claude.ai web app (there, use the
[Skill](skills/preprint-fulltext/SKILL.md) instead).

### Recommended: run via `uvx` (no install)

[uv](https://docs.astral.sh/uv/) runs the published package on demand — nothing to
`pip install` or keep on a PATH. Install uv once:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# or:  pipx install uv  |  pip install --user uv  |  brew install uv  |  winget install astral-sh.uv
```

The launch command is `uvx --from preprint-fulltext preprint-fulltext-mcp` (the `--from` is
needed because the run command differs from the package name). First launch downloads the
package (~30 s); later launches are cached.

<details>
<summary><b>Claude Code</b> — key <code>mcpServers</code></summary>

```bash
claude mcp add preprint-fulltext --scope user -- uvx --from preprint-fulltext preprint-fulltext-mcp
# uvx not on PATH? use its absolute path:
claude mcp add preprint-fulltext --scope user -- "$(which uvx)" --from preprint-fulltext preprint-fulltext-mcp
claude mcp get preprint-fulltext        # verify → Status: ✔ Connected
```

Or edit `~/.claude.json` (user) / project `.mcp.json`:

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>Cursor / Windsurf / Cline / Continue</b> — key <code>mcpServers</code> (same shape)</summary>

Cursor: `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project). Windsurf:
`~/.codeium/windsurf/mcp_config.json`. Cline: *MCP Servers → Configure*. Continue:
`~/.continue/config`.

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>VS Code</b> (GitHub Copilot, Agent mode) — key <code>servers</code> + <code>type</code></summary>

`.vscode/mcp.json` (workspace) or user `settings.json` under `"mcp"`:

```json
{ "servers": { "preprint-fulltext": {
  "type": "stdio",
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
} } }
```

Or one-shot: `code --add-mcp '{"name":"preprint-fulltext","command":"uvx","args":["--from","preprint-fulltext","preprint-fulltext-mcp"]}'`
</details>

<details>
<summary><b>Zed</b> — key <code>context_servers</code> (different shape)</summary>

`~/.config/zed/settings.json`:

```json
{ "context_servers": { "preprint-fulltext": {
  "source": "custom",
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": {}
} } }
```
</details>

<details>
<summary><b>Codex</b> (OpenAI Codex CLI) — TOML, not JSON</summary>

`~/.codex/config.toml`:

```toml
[mcp_servers.preprint-fulltext]
command = "uvx"
args = ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
# env = { CONTACT_EMAIL = "you@example.org" }
```

Or: `codex mcp add preprint-fulltext -- uvx --from preprint-fulltext preprint-fulltext-mcp`
</details>

### Alternative: install with pip

If you already `pip install preprint-fulltext`, the server is on your PATH as
`preprint-fulltext-mcp` — use `"command": "preprint-fulltext-mcp"` (no `args`) in any config
above.

> **Env vars:** set `CONTACT_EMAIL` (Europe PMC / OpenAlex polite pools) and
> `OPENALEX_API_KEY` (only for OpenAlex search/discover) via the config's `env` block, or in
> your shell before launching the client. See [`SKILL.md`](skills/preprint-fulltext/SKILL.md)
> for the full agent-facing tool reference.

## Data sources & routing

| Verb        | Default source        | Notes                                             |
|-------------|-----------------------|---------------------------------------------------|
| `get`       | auto (Europe PMC → S3, or arXiv) | bioRxiv/medRxiv: EPMC (CC/OA subset) → S3 (complete, needs AWS creds), `--html` opt-in fallback. **arXiv ids** → arXiv LaTeXML full text (native HTML → ar5iv). |
| `search`    | Europe PMC            | Real relevance ranking; `--source openalex\|arxiv`. |
| `discover`  | OpenAlex              | 250M+ works, OA locations, topic/date; `--source arxiv`. |
| `ingest`    | S3 (or Europe PMC)    | S3 = complete corpus; Europe PMC = free CC subset. arXiv bulk is out of scope (use arXiv's own S3 LaTeX bucket). |

## Configuration

Via environment variables (prefixed `PREPRINT_FULLTEXT_` or the bare names below),
a `.env` file, or a `preprint-fulltext.toml`:

| Setting | Default | Purpose |
|---|---|---|
| `CONTACT_EMAIL` | – | Polite-pool identity for Europe PMC / OpenAlex |
| `OPENALEX_API_KEY` | – | Required by OpenAlex since 2026-02-13 |
| `AWS_REGION` | `us-east-1` | Region for the requester-pays openRxiv buckets |
| `PREPRINT_FULLTEXT_CACHE_DIR` | `~/.cache/preprint-fulltext` | Content-addressed cache |
| `PREPRINT_FULLTEXT_CHUNK_TOKENS` | `512` | Max tokens per chunk |
| `PREPRINT_FULLTEXT_CHUNK_OVERLAP` | `64` | Token overlap within a section |

## Compliance

Corpora are for the operator's own text/data mining under the openRxiv TDM terms.
`preprint-fulltext` does **not** re-host or redistribute preprint full text. Every
`FullText`/`Chunk` carries its license; the export gate has two modes:

- **analysis** (default): pass-through for your own mining.
- **redistribution** (`--redistribution`): works whose license permits redistribution
  pass unchanged; all others are degraded to a **link-back stub** (metadata + URL,
  no body text). Unknown/ambiguous licenses are treated as non-redistributable.

## Development

```bash
pip install -e ".[dev]"
pytest              # offline suite (HTTP mocked with respx, S3 with moto)
ruff check preprint_fulltext/
```

Live tests are opt-in (they hit the real public APIs — Europe PMC, arXiv, and the
bioRxiv/medRxiv JSON API):

```bash
PREPRINT_FULLTEXT_LIVE=1 CONTACT_EMAIL=you@example.org pytest -m live   # EPMC / arXiv / medRxiv / versions
PREPRINT_FULLTEXT_LIVE_S3=1 pytest -m live_s3    # requester-pays S3 (small; needs AWS creds)
```

The same live smoke runs in CI on demand (Actions → **live-smoke**) and weekly, to catch
upstream API drift; the default `test` workflow stays fully offline.

Agent docs (`AGENTS.md`, `llms.txt`, `.cursor/rules/…`, `.github/copilot-instructions.md`)
are generated from `skills/preprint-fulltext/SKILL.md`:

```bash
python scripts/build_agent_docs.py
```

## Contact

**Min Dai** — <dai@broadinstitute.org> ([Gord Fishell Lab](https://fishelllab.hms.harvard.edu),
Harvard Medical School / Broad Institute). Issues and pull requests welcome at
<https://github.com/genecell/preprint-fulltext>.

## License

BSD-3-Clause (see [`LICENSE`](LICENSE)). This covers the **software** only —
retrieved preprint content remains under its author-selected license.
