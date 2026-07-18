# preprint-fulltext

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh.md">简体中文</a> |
  <a href="README.zht.md">繁體中文</a> |
  <a href="README.ko.md">한국어</a> |
  <b>Deutsch</b> |
  <a href="README.es.md">Español</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.it.md">Italiano</a> |
  <a href="README.ja.md">日本語</a>
</p>

[![PyPI](https://img.shields.io/pypi/v/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![Python](https://img.shields.io/pypi/pyversions/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](LICENSE)
[![CI](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml/badge.svg)](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml)

Ruft den **Volltext** von bioRxiv-/medRxiv-/**arXiv**-Preprints als sauberes,
strukturiertes und embedding-fertiges Datenmaterial ab — über eine CLI, eine
Python-Bibliothek oder einen MCP-Server.

`preprint-fulltext` verwandelt eine DOI (oder eine Suche) in strukturierte Abschnitte
(Abstract / Einleitung / Methoden / Ergebnisse / Diskussion), ein einzelnes JSON-/Markdown-Dokument
oder einen in Chunks zerlegten JSONL-/Parquet-Korpus, der für Embeddings und RAG bereit ist.
Die Einhaltung der Text-and-Data-Mining-(TDM-)Bedingungen von openRxiv wird strukturell
erzwungen und nicht dem Nutzer überlassen.

> **„Embedding-fertig“ bedeutet: Die Ausgabe besteht aus sauberen, abschnittsbewussten,
> token-begrenzten Chunks — bereit, an *dein* Embedding-Modell übergeben zu werden. Die
> Berechnung der Embeddings ist ein optionaler letzter Schritt, den du kontrollierst; dieses
> Werkzeug bringt kein Embedding-Modell mit.**

---

## Warum

Der Volltext von Preprints ist über inkompatible Kanäle verstreut: Europe PMC liefert JATS-XML
für die Open-Access-Teilmenge, die openRxiv-S3-Buckets enthalten den maßgeblichen
`.meca`-Korpus (Requester-Pays), OpenAlex ist ein Katalog mit reiner n-Gramm-Volltextsuche,
und die bioRxiv-/medRxiv-Websites rendern HTML. `preprint-fulltext` vereint sie hinter einem
kanonischen Datenmodell und **einem gemeinsamen JATS-Parser**, sodass du dieselbe strukturierte
Ausgabe erhältst, ganz gleich, woher ein Dokument stammt.

## Für wen

- **ML-/NLP-Forschende**, die Embedding-Korpora oder RAG-Systeme über der Preprint-Literatur aufbauen.
- **Bioinformatiker:innen und Labore**, die die Methoden/Ergebnisse einer Arbeit als sauberen
  Text für Analyse, Extraktion oder LLM-Pipelines benötigen.
- **Coding-Agenten** (über den MCP-Server / `SKILL.md`), die während einer Aufgabe den Volltext
  eines Preprints abrufen oder die Literatur durchsuchen müssen.
- Alle, die **die Abschnitte eines Preprints aus einer DOI** wollen, ohne JATS von Hand zu
  parsen oder HTML zu scrapen.

## Volltext für KI-gestützte Wissenschaft

Sprachmodelle und Agenten schlussfolgern weit zuverlässiger über die **Methoden und Ergebnisse**
einer Arbeit als über deren Abstract allein — die meisten wissenschaftlichen Aussagen,
Protokolle, Größen und Einschränkungen stehen im Fließtext. `preprint-fulltext` liefert diesen
Fließtext an Claude, Codex und andere Agenten als sauberen, abschnittsbeschrifteten Text mit
Herkunfts- und Lizenz-Tags — das Fundament für **fundiertes wissenschaftliches Schlussfolgern
und tiefe Recherche**:

- **Tiefe Literaturrecherche** — den Volltext vieler Arbeiten lesen, nicht nur die Abstracts.
- **Extraktion von Methoden/Protokollen** — exakte Abläufe, Parameter und Datensätze gewinnen.
- **Aussagenprüfung** — ein behauptetes Ergebnis gegen den tatsächlichen Ergebnisteil abgleichen.
- **Reproduzierbarkeit & Metaanalyse** — Methoden und Zahlen über Studien hinweg vergleichen.
- **RAG über deinen eigenen Korpus** — abschnittsbewusste, token-begrenzte Chunks mit Zitaten.

Da jeder `Section`/`Chunk` seinen `kind` (Methoden / Ergebnisse / …), seine `source` und seine
`license` trägt, kann ein Agent **präzise zitieren** (welcher Abschnitt welcher Arbeit/Version)
und beim Schlussfolgern **innerhalb der Lizenz** bleiben. Volltext ist Abruf, nicht Auswendiglernen:
Das Modell gründet sein Schlussfolgern auf der Primärquelle statt auf einer womöglich veralteten Zusammenfassung.

## Funktionen

- **`get <id>`** — der Volltext eines Preprints als strukturiertes JSON oder Markdown.
  bioRxiv/medRxiv laufen über Europe PMC → S3 (optionaler HTML-Fallback); **arXiv**-IDs werden
  zum LaTeXML-Volltext von arXiv geleitet (natives HTML → ar5iv). Standardmäßig die neueste
  Version; `--version` wählt eine aus.
- **`search` / `discover`** — Suche nach Stichwort, Titel, Abstract oder Autor über Europe PMC,
  OpenAlex und **arXiv**; Entdeckung nach Thema/Kategorie/Datum.
- **`ingest`** — wiederaufnehmbare, inkrementelle Massenaufnahme aus den openRxiv-S3-Buckets in
  einen Chunk-Korpus (JSONL oder Parquet) mit begleitendem Manifest.
- **MCP-Server** — dieselben Fähigkeiten als Werkzeuge für Coding-Agenten.
- **Compliance eingebaut** — ein Export-Gate stuft nicht weiterverbreitbare Werke zu
  Link-Back-Stubs herab; unbekannte Lizenzen werden als nicht weiterverbreitbar behandelt (Fail-Safe).
- **Ein JATS-Parser**, gemeinsam für die Europe-PMC- und die S3-Pfade; token- und
  abschnittsbewusstes Chunking mit deterministischen, idempotenten Chunk-IDs.

## Installation

```bash
pip install preprint-fulltext                       # CLI + Python library + MCP server
pip install "preprint-fulltext[parquet,openalex]"   # + Parquet output, pyalex
```

Der **MCP-Server ist eingebaut** — keine zusätzliche Installation und kein MCP-Framework von
Dritten. Es ist ein kleiner, eigenständiger JSON-RPC-2.0-stdio-Server, sodass
`preprint-fulltext-mcp` allein mit den Kernabhängigkeiten sofort funktioniert.

Setze eine Kontakt-E-Mail für die Polite-Pools von Europe PMC / OpenAlex (empfohlen) und einen
OpenAlex-API-Schlüssel, falls du OpenAlex nutzt (bei OpenAlex seit 2026-02-13 erforderlich):

```bash
export CONTACT_EMAIL="you@example.org"
export OPENALEX_API_KEY="..."            # only needed for OpenAlex discover/search
```

## Schnellstart (CLI)

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

`get` gibt ein `FullText`-Dokument (JSON) oder Markdown (`--markdown`) aus. `search` / `discover`
streamen einen `SearchHit` pro Zeile (JSONL). `ingest` schreibt einen `Chunk` pro Zeile plus eine
begleitende `<out>_manifest.jsonl` für Audit und Wiederaufnahme.

## Typische Arbeitsabläufe

**1. Methoden/Ergebnisse einer Arbeit als Text lesen.**

```bash
preprint-fulltext get 10.64898/2026.01.29.702557 --markdown > paper.md
# -> # Title / ## Abstract / ## Introduction / ## Methods / ## Results / ## Discussion
```

**2. Einen embedding-fertigen Korpus zu einem Thema aufbauen (kostenlos, ohne AWS).**

```bash
# CC/open-access subset via Europe PMC — one Chunk per JSONL line
preprint-fulltext ingest cortex.jsonl --source europepmc --query "cortical interneurons" -n 500
# cortex.jsonl          -> {doi, version, chunk_id, section_kind, text, token_count, license, ...}
# cortex_manifest.jsonl -> one row per preprint (doi, version, license, n_chunks, status)
```

**3. Den vollständigen Korpus eines Monats aus S3 aufbauen (Requester-Pays).**

```bash
export AWS_PROFILE=...           # needs AWS credentials; ~$0.09/GB
preprint-fulltext ingest 2025-06.jsonl --source s3 --server both --since 2025-06 --format parquet
# resumable: rerun after an interruption and it skips finished preprints (no duplicates)
```

**4. Arbeiten nach Autor oder Titel finden und dann abrufen.**

```bash
preprint-fulltext search "Min Dai" --field author -n 20 > hits.jsonl
preprint-fulltext get "$(head -1 hits.jsonl | python -c 'import sys,json;print(json.load(sys.stdin)["doi"])')" --markdown
```

**5. Einem Coding-Agenten Literaturzugang geben** — starte `preprint-fulltext-mcp` und richte
deinen Agenten darauf aus (siehe [`skills/preprint-fulltext/SKILL.md`](skills/preprint-fulltext/SKILL.md)).

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

## MCP-Server

Gib einem Coding-Agenten Live-Zugriff auf Preprints. Der Server stellt vier Werkzeuge über stdio
bereit — `search_preprints`, `get_fulltext`, `get_metadata`, `resolve`. (Die Massenaufnahme
`ingest` ist bewusst **kein** Werkzeug: Sie ist langlaufend und verursacht Requester-Pays-Kosten.)

`mcp-name: io.github.genecell/preprint-fulltext`

Es ist ein **lokaler stdio**-Server und funktioniert daher in Claude Code / Cursor / VS Code /
Windsurf / Zed / Codex / Cline — aber nicht in der claude.ai-Web-App (dort stattdessen den
[Skill](skills/preprint-fulltext/SKILL.md) verwenden).

### Empfohlen: mit `uvx` ausführen (ohne Installation)

[uv](https://docs.astral.sh/uv/) führt das veröffentlichte Paket bei Bedarf aus — nichts zu
`pip install`, nichts auf dem PATH zu halten. uv einmalig installieren:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# or:  pipx install uv  |  pip install --user uv  |  brew install uv  |  winget install astral-sh.uv
```

Der Startbefehl lautet `uvx --from preprint-fulltext preprint-fulltext-mcp` (das `--from` ist
nötig, weil der Ausführungsbefehl vom Paketnamen abweicht). Der erste Start lädt das Paket
herunter (~30 s); spätere Starts sind gecacht.

<details>
<summary><b>Claude Code</b> — Schlüssel <code>mcpServers</code></summary>

```bash
claude mcp add preprint-fulltext --scope user -- uvx --from preprint-fulltext preprint-fulltext-mcp
# uvx not on PATH? use its absolute path:
claude mcp add preprint-fulltext --scope user -- "$(which uvx)" --from preprint-fulltext preprint-fulltext-mcp
claude mcp get preprint-fulltext        # verify → Status: ✔ Connected
```

Oder `~/.claude.json` (Benutzer) / projekteigenes `.mcp.json` bearbeiten:

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>Cursor / Windsurf / Cline / Continue</b> — Schlüssel <code>mcpServers</code> (gleiche Form)</summary>

Cursor: `~/.cursor/mcp.json` (global) oder `.cursor/mcp.json` (Projekt). Windsurf:
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
<summary><b>VS Code</b> (GitHub Copilot, Agent-Modus) — Schlüssel <code>servers</code> + <code>type</code></summary>

`.vscode/mcp.json` (Arbeitsbereich) oder Benutzer-`settings.json` unter `"mcp"`:

```json
{ "servers": { "preprint-fulltext": {
  "type": "stdio",
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
} } }
```

Oder in einem Schritt: `code --add-mcp '{"name":"preprint-fulltext","command":"uvx","args":["--from","preprint-fulltext","preprint-fulltext-mcp"]}'`
</details>

<details>
<summary><b>Zed</b> — Schlüssel <code>context_servers</code> (andere Form)</summary>

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
<summary><b>Codex</b> (OpenAI Codex CLI) — TOML, kein JSON</summary>

`~/.codex/config.toml`:

```toml
[mcp_servers.preprint-fulltext]
command = "uvx"
args = ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
# env = { CONTACT_EMAIL = "you@example.org" }
```

Oder: `codex mcp add preprint-fulltext -- uvx --from preprint-fulltext preprint-fulltext-mcp`
</details>

### Alternative: mit pip installieren

Wenn du bereits `pip install preprint-fulltext` ausgeführt hast, liegt der Server als
`preprint-fulltext-mcp` auf deinem PATH — verwende `"command": "preprint-fulltext-mcp"` (ohne
`args`) in einer der obigen Konfigurationen.

> **Umgebungsvariablen:** Setze `CONTACT_EMAIL` (Polite-Pools von Europe PMC / OpenAlex) und
> `OPENALEX_API_KEY` (nur für die OpenAlex-Suche/-Entdeckung) über den `env`-Block der
> Konfiguration oder in deiner Shell vor dem Start des Clients. Die vollständige, an Agenten
> gerichtete Werkzeugreferenz findest du in [`SKILL.md`](skills/preprint-fulltext/SKILL.md).

## Datenquellen & Routing

| Befehl      | Standardquelle        | Hinweise                                          |
|-------------|-----------------------|---------------------------------------------------|
| `get`       | auto (Europe PMC → S3, oder arXiv) | bioRxiv/medRxiv: EPMC (CC/OA-Teilmenge) → S3 (vollständig, AWS-Zugangsdaten nötig), `--html` als optionaler Fallback. **arXiv-IDs** → arXiv-LaTeXML-Volltext (natives HTML → ar5iv). |
| `search`    | Europe PMC            | Echtes Relevanz-Ranking; `--source openalex\|arxiv`. |
| `discover`  | OpenAlex              | 250 Mio.+ Werke, OA-Standorte, Themen-/Datumsfilter; `--source arxiv`. |
| `ingest`    | S3 (oder Europe PMC)  | S3 = vollständiger Korpus; Europe PMC = kostenlose CC-Teilmenge. arXiv-Massenaufnahme außerhalb des Umfangs (nutze arXivs eigenen S3-LaTeX-Bucket). |

## Konfiguration

Über Umgebungsvariablen (mit Präfix `PREPRINT_FULLTEXT_` oder den einfachen Namen unten), eine
`.env`-Datei oder eine `preprint-fulltext.toml`:

| Einstellung | Standard | Zweck |
|---|---|---|
| `CONTACT_EMAIL` | – | Polite-Pool-Identität für Europe PMC / OpenAlex |
| `OPENALEX_API_KEY` | – | Bei OpenAlex seit 2026-02-13 erforderlich |
| `AWS_REGION` | `us-east-1` | Region der Requester-Pays-openRxiv-Buckets |
| `PREPRINT_FULLTEXT_CACHE_DIR` | `~/.cache/preprint-fulltext` | Inhaltsadressierter Cache |
| `PREPRINT_FULLTEXT_CHUNK_TOKENS` | `512` | Maximale Tokens pro Chunk |
| `PREPRINT_FULLTEXT_CHUNK_OVERLAP` | `64` | Token-Überlappung innerhalb eines Abschnitts |

## Compliance

Korpora sind für das eigene Text- und Data-Mining des Betreibers gemäß den openRxiv-TDM-Bedingungen
bestimmt. `preprint-fulltext` hostet oder verbreitet den Volltext von Preprints **nicht** erneut.
Jeder `FullText`/`Chunk` trägt seine Lizenz; das Export-Gate hat zwei Modi:

- **analysis** (Standard): Durchreichen für dein eigenes Mining.
- **redistribution** (`--redistribution`): Werke, deren Lizenz die Weiterverbreitung erlaubt,
  laufen unverändert durch; alle anderen werden zu einem **Link-Back-Stub** herabgestuft
  (Metadaten + URL, kein Fließtext). Unbekannte/mehrdeutige Lizenzen gelten als nicht weiterverbreitbar.

## Entwicklung

```bash
pip install -e ".[dev]"
pytest              # offline suite (HTTP mocked with respx, S3 with moto)
ruff check preprint_fulltext/
```

Live-Tests sind optional (sie greifen auf die echten öffentlichen APIs zu — Europe PMC, arXiv und
die bioRxiv-/medRxiv-JSON-API):

```bash
PREPRINT_FULLTEXT_LIVE=1 CONTACT_EMAIL=you@example.org pytest -m live   # EPMC / arXiv / medRxiv / versions
PREPRINT_FULLTEXT_LIVE_S3=1 pytest -m live_s3    # requester-pays S3 (small; needs AWS creds)
```

Derselbe Live-Smoke läuft in der CI auf Abruf (Actions → **live-smoke**) und wöchentlich, um
Änderungen der Upstream-APIs zu erkennen; der Standard-`test`-Workflow bleibt vollständig offline.

Die Agenten-Dokumente (`AGENTS.md`, `llms.txt`, `.cursor/rules/…`,
`.github/copilot-instructions.md`) werden aus `skills/preprint-fulltext/SKILL.md` generiert:

```bash
python scripts/build_agent_docs.py
```

## Kontakt

**Min Dai** — <dai@broadinstitute.org> ([Gord Fishell Lab](https://fishelllab.hms.harvard.edu),
Harvard Medical School / Broad Institute). Issues und Pull Requests sind willkommen unter
<https://github.com/genecell/preprint-fulltext>.

## Lizenz

BSD-3-Clause (siehe [`LICENSE`](LICENSE)). Sie deckt nur die **Software** ab — die abgerufenen
Preprint-Inhalte bleiben unter der vom Autor gewählten Lizenz.
