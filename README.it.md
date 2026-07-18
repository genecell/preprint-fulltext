# preprint-fulltext

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh.md">简体中文</a> |
  <a href="README.zht.md">繁體中文</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.es.md">Español</a> |
  <a href="README.fr.md">Français</a> |
  <b>Italiano</b> |
  <a href="README.ja.md">日本語</a>
</p>

[![PyPI](https://img.shields.io/pypi/v/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![Python](https://img.shields.io/pypi/pyversions/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](LICENSE)
[![CI](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml/badge.svg)](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml)

Recupera il **testo completo** dei preprint di bioRxiv / medRxiv / **arXiv** come dati puliti,
strutturati e pronti per gli *embedding* — da una CLI, una libreria Python o un server MCP.

`preprint-fulltext` trasforma un DOI (o una ricerca) in sezioni strutturate
(abstract / introduzione / metodi / risultati / discussione), in un singolo documento
JSON/Markdown, o in un corpus JSONL/Parquet suddiviso in chunk e pronto per embedding e RAG.
La conformità ai termini di text and data mining (TDM) di openRxiv è imposta strutturalmente,
non lasciata all'utente.

> **«Pronto per gli *embedding*» significa che l'output è costituito da chunk puliti, consapevoli
> delle sezioni e limitati nei token — pronti per essere dati in pasto al *tuo* modello di
> embedding. Calcolare gli embedding è un ultimo passaggio facoltativo che controlli tu; questo
> strumento non include alcun modello di embedding.**

---

## Perché

Il testo completo dei preprint è disperso in canali incompatibili: Europe PMC fornisce JATS XML
per il sottoinsieme ad accesso aperto, i bucket S3 di openRxiv contengono il corpus `.meca`
autorevole (a carico del richiedente), OpenAlex è un catalogo con ricerca full-text solo per
n-grammi, e i siti bioRxiv/medRxiv restituiscono HTML. `preprint-fulltext` li unifica dietro un
unico modello di dati canonico e **un unico parser JATS condiviso**, così ottieni lo stesso
output strutturato indipendentemente dall'origine del documento.

## A chi è rivolto

- **Ricercatori di ML / NLP** che costruiscono corpus di embedding o sistemi RAG sulla
  letteratura dei preprint.
- **Bioinformatici e laboratori** che hanno bisogno dei metodi/risultati di un articolo come
  testo pulito per analisi, estrazione o *pipeline* con LLM.
- **Agenti di programmazione** (tramite il server MCP / `SKILL.md`) che devono recuperare il testo
  completo di un preprint o cercare nella letteratura durante un'attività.
- Chiunque voglia **le sezioni di un preprint a partire da un DOI** senza analizzare il JATS a
  mano né fare *scraping* dell'HTML.

## Testo completo per la scienza guidata dall'IA

I modelli linguistici e gli agenti ragionano in modo molto più affidabile sui **metodi e
risultati** di un articolo che sul solo abstract — la maggior parte delle affermazioni
scientifiche, dei protocolli, delle quantità e delle riserve si trova nel corpo. `preprint-fulltext`
fornisce quel corpo a Claude, Codex e agli altri agenti come testo pulito, etichettato per sezione
e con tag di provenienza e licenza, che è il substrato per un **ragionamento scientifico fondato e
la ricerca approfondita**:

- **Ricerca bibliografica approfondita** — leggere il testo completo di molti articoli, non solo gli abstract.
- **Estrazione di metodi / protocolli** — ottenere procedure, parametri e dataset esatti.
- **Verifica delle affermazioni** — confrontare un risultato dichiarato con la reale sezione dei Risultati.
- **Riproducibilità e meta-analisi** — confrontare metodi e numeri tra studi.
- **RAG sul tuo corpus** — chunk consapevoli delle sezioni, limitati nei token e con citazioni.

Poiché ogni `Section`/`Chunk` porta il proprio `kind` (metodi / risultati / …), la propria
`source` e la propria `license`, un agente può **citare con precisione** (quale sezione di quale
articolo/versione) e restare **entro i limiti della licenza** mentre ragiona. Il testo completo è
recupero, non memorizzazione: il modello fonda il proprio ragionamento sulla fonte primaria invece
di ricordare un riassunto potenzialmente obsoleto.

## Funzionalità

- **`get <id>`** — il testo completo di un preprint come JSON o Markdown strutturato.
  bioRxiv/medRxiv vengono instradati tramite Europe PMC → S3 (fallback HTML facoltativo); gli id
  **arXiv** vengono instradati al testo completo LaTeXML di arXiv (HTML nativo → ar5iv). Ultima
  versione per impostazione predefinita; `--version` ne seleziona una.
- **`search` / `discover`** — ricerca per parola chiave, titolo, abstract o autore su Europe PMC,
  OpenAlex e **arXiv**; scoperta per tema/categoria/data.
- **`ingest`** — ingestione massiva riprendibile e incrementale dai bucket S3 di openRxiv verso un
  corpus a chunk (JSONL o Parquet) con un manifesto allegato.
- **Server MCP** — le stesse capacità come strumenti per gli agenti di programmazione.
- **Conformità integrata** — un gate di esportazione degrada le opere non ridistribuibili a *stub*
  di rimando; le licenze sconosciute sono trattate come non ridistribuibili (a prova di errore).
- **Un unico parser JATS** condiviso dai percorsi Europe PMC e S3; suddivisione in chunk
  consapevole di token e sezioni, con id di chunk deterministici e idempotenti.

## Installazione

```bash
pip install preprint-fulltext                       # CLI + Python library + MCP server
pip install "preprint-fulltext[parquet,openalex]"   # + Parquet output, pyalex
```

Il **server MCP è integrato** — nessuna installazione aggiuntiva né framework MCP di terze parti.
È un server stdio JSON-RPC 2.0 piccolo e autonomo, quindi `preprint-fulltext-mcp` funziona subito
con le sole dipendenze di base.

Imposta un'e-mail di contatto per i *polite pool* di Europe PMC / OpenAlex (consigliato) e una
chiave API OpenAlex se usi OpenAlex (obbligatoria su OpenAlex dal 2026-02-13):

```bash
export CONTACT_EMAIL="you@example.org"
export OPENALEX_API_KEY="..."            # only needed for OpenAlex discover/search
```

## Avvio rapido (CLI)

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

`get` emette un documento `FullText` (JSON) o Markdown (`--markdown`). `search` / `discover`
trasmettono un `SearchHit` per riga (JSONL). `ingest` scrive un `Chunk` per riga più un file
`<out>_manifest.jsonl` di audit e ripresa.

## Flussi di lavoro tipici

**1. Leggere i metodi/risultati di un articolo come testo.**

```bash
preprint-fulltext get 10.64898/2026.01.29.702557 --markdown > paper.md
# -> # Title / ## Abstract / ## Introduction / ## Methods / ## Results / ## Discussion
```

**2. Costruire un corpus pronto per gli embedding su un tema (gratis, senza AWS).**

```bash
# CC/open-access subset via Europe PMC — one Chunk per JSONL line
preprint-fulltext ingest cortex.jsonl --source europepmc --query "cortical interneurons" -n 500
# cortex.jsonl          -> {doi, version, chunk_id, section_kind, text, token_count, license, ...}
# cortex_manifest.jsonl -> one row per preprint (doi, version, license, n_chunks, status)
```

**3. Costruire il corpus completo di un mese da S3 (a carico del richiedente).**

```bash
export AWS_PROFILE=...           # needs AWS credentials; ~$0.09/GB
preprint-fulltext ingest 2025-06.jsonl --source s3 --server both --since 2025-06 --format parquet
# resumable: rerun after an interruption and it skips finished preprints (no duplicates)
```

**4. Trovare articoli per autore o titolo, poi recuperarli.**

```bash
preprint-fulltext search "Min Dai" --field author -n 20 > hits.jsonl
preprint-fulltext get "$(head -1 hits.jsonl | python -c 'import sys,json;print(json.load(sys.stdin)["doi"])')" --markdown
```

**5. Dare a un agente di programmazione l'accesso alla letteratura** — avvia `preprint-fulltext-mcp`
e punta il tuo agente su di esso (vedi [`skills/preprint-fulltext/SKILL.md`](skills/preprint-fulltext/SKILL.md)).

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

## Server MCP

Dai a un agente di programmazione l'accesso in tempo reale ai preprint. Il server espone quattro
strumenti — `search_preprints`, `get_fulltext`, `get_metadata`, `resolve` — via stdio.
(L'ingestione massiva `ingest` **non** è uno strumento di proposito: è a lunga esecuzione e
comporta costi a carico del richiedente.)

`mcp-name: io.github.genecell/preprint-fulltext`

È un server **stdio locale**, quindi funziona in Claude Code / Cursor / VS Code / Windsurf / Zed /
Codex / Cline — ma non nell'app web claude.ai (lì, usa invece lo
[Skill](skills/preprint-fulltext/SKILL.md)).

### Consigliato: eseguire con `uvx` (senza installazione)

[uv](https://docs.astral.sh/uv/) esegue il pacchetto pubblicato su richiesta — niente da
`pip install` né da tenere nel PATH. Installa uv una volta:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# or:  pipx install uv  |  pip install --user uv  |  brew install uv  |  winget install astral-sh.uv
```

Il comando di avvio è `uvx --from preprint-fulltext preprint-fulltext-mcp` (il `--from` serve
perché il comando di esecuzione differisce dal nome del pacchetto). Il primo avvio scarica il
pacchetto (~30 s); gli avvii successivi sono in cache.

<details>
<summary><b>Claude Code</b> — chiave <code>mcpServers</code></summary>

```bash
claude mcp add preprint-fulltext --scope user -- uvx --from preprint-fulltext preprint-fulltext-mcp
# uvx not on PATH? use its absolute path:
claude mcp add preprint-fulltext --scope user -- "$(which uvx)" --from preprint-fulltext preprint-fulltext-mcp
claude mcp get preprint-fulltext        # verify → Status: ✔ Connected
```

Oppure modifica `~/.claude.json` (utente) / il `.mcp.json` del progetto:

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>Cursor / Windsurf / Cline / Continue</b> — chiave <code>mcpServers</code> (stessa forma)</summary>

Cursor: `~/.cursor/mcp.json` (globale) o `.cursor/mcp.json` (progetto). Windsurf:
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
<summary><b>VS Code</b> (GitHub Copilot, modalità Agent) — chiave <code>servers</code> + <code>type</code></summary>

`.vscode/mcp.json` (workspace) o il `settings.json` utente sotto `"mcp"`:

```json
{ "servers": { "preprint-fulltext": {
  "type": "stdio",
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
} } }
```

Oppure in un colpo solo: `code --add-mcp '{"name":"preprint-fulltext","command":"uvx","args":["--from","preprint-fulltext","preprint-fulltext-mcp"]}'`
</details>

<details>
<summary><b>Zed</b> — chiave <code>context_servers</code> (forma diversa)</summary>

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
<summary><b>Codex</b> (OpenAI Codex CLI) — TOML, non JSON</summary>

`~/.codex/config.toml`:

```toml
[mcp_servers.preprint-fulltext]
command = "uvx"
args = ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
# env = { CONTACT_EMAIL = "you@example.org" }
```

Oppure: `codex mcp add preprint-fulltext -- uvx --from preprint-fulltext preprint-fulltext-mcp`
</details>

### Alternativa: installare con pip

Se hai già fatto `pip install preprint-fulltext`, il server è nel tuo PATH come
`preprint-fulltext-mcp` — usa `"command": "preprint-fulltext-mcp"` (senza `args`) in una qualsiasi
delle configurazioni sopra.

> **Variabili d'ambiente:** imposta `CONTACT_EMAIL` (polite pool di Europe PMC / OpenAlex) e
> `OPENALEX_API_KEY` (solo per ricerca/scoperta OpenAlex) tramite il blocco `env` della
> configurazione, o nella tua shell prima di avviare il client. Consulta
> [`SKILL.md`](skills/preprint-fulltext/SKILL.md) per il riferimento completo degli strumenti destinato agli agenti.

## Fonti di dati e instradamento

| Verbo       | Fonte predefinita     | Note                                              |
|-------------|-----------------------|---------------------------------------------------|
| `get`       | auto (Europe PMC → S3, o arXiv) | bioRxiv/medRxiv: EPMC (sottoinsieme CC/OA) → S3 (completo, richiede credenziali AWS), `--html` come fallback facoltativo. **id arXiv** → testo completo LaTeXML di arXiv (HTML nativo → ar5iv). |
| `search`    | Europe PMC            | Ranking di rilevanza reale; `--source openalex\|arxiv`. |
| `discover`  | OpenAlex              | Oltre 250 mln di opere, posizioni OA, filtri per tema/data; `--source arxiv`. |
| `ingest`    | S3 (o Europe PMC)     | S3 = corpus completo; Europe PMC = sottoinsieme CC gratuito. L'ingestione massiva di arXiv è fuori ambito (usa il bucket S3 LaTeX di arXiv). |

## Configurazione

Tramite variabili d'ambiente (con prefisso `PREPRINT_FULLTEXT_` o i nomi semplici sotto), un file
`.env`, o un `preprint-fulltext.toml`:

| Impostazione | Predefinito | Scopo |
|---|---|---|
| `CONTACT_EMAIL` | – | Identità di *polite pool* per Europe PMC / OpenAlex |
| `OPENALEX_API_KEY` | – | Obbligatoria su OpenAlex dal 2026-02-13 |
| `AWS_REGION` | `us-east-1` | Regione dei bucket openRxiv a carico del richiedente |
| `PREPRINT_FULLTEXT_CACHE_DIR` | `~/.cache/preprint-fulltext` | Cache a indirizzamento per contenuto |
| `PREPRINT_FULLTEXT_CHUNK_TOKENS` | `512` | Numero massimo di token per chunk |
| `PREPRINT_FULLTEXT_CHUNK_OVERLAP` | `64` | Sovrapposizione di token all'interno di una sezione |

## Conformità

I corpus sono destinati al text and data mining dell'operatore stesso secondo i termini TDM di
openRxiv. `preprint-fulltext` **non** riospita né ridistribuisce il testo completo dei preprint.
Ogni `FullText`/`Chunk` porta la propria licenza; il gate di esportazione ha due modalità:

- **analysis** (predefinita): passaggio diretto per il tuo mining.
- **redistribution** (`--redistribution`): le opere la cui licenza consente la ridistribuzione
  passano invariate; tutte le altre vengono degradate a uno **stub di rimando** (metadati + URL,
  senza corpo del testo). Le licenze sconosciute/ambigue sono trattate come non ridistribuibili.

## Sviluppo

```bash
pip install -e ".[dev]"
pytest              # offline suite (HTTP mocked with respx, S3 with moto)
ruff check preprint_fulltext/
```

I test dal vivo sono facoltativi (accedono alle vere API pubbliche — Europe PMC, arXiv e l'API
JSON di bioRxiv/medRxiv):

```bash
PREPRINT_FULLTEXT_LIVE=1 CONTACT_EMAIL=you@example.org pytest -m live   # EPMC / arXiv / medRxiv / versions
PREPRINT_FULLTEXT_LIVE_S3=1 pytest -m live_s3    # requester-pays S3 (small; needs AWS creds)
```

Lo stesso smoke test dal vivo viene eseguito in CI su richiesta (Actions → **live-smoke**) e
settimanalmente, per rilevare cambiamenti nelle API a monte; il flusso di lavoro `test`
predefinito resta completamente offline.

I documenti per agenti (`AGENTS.md`, `llms.txt`, `.cursor/rules/…`,
`.github/copilot-instructions.md`) sono generati da `skills/preprint-fulltext/SKILL.md`:

```bash
python scripts/build_agent_docs.py
```

## Contatti

**Min Dai** — <dai@broadinstitute.org> ([Gord Fishell Lab](https://fishelllab.hms.harvard.edu),
Harvard Medical School / Broad Institute). Issue e pull request sono benvenute su
<https://github.com/genecell/preprint-fulltext>.

## Licenza

BSD-3-Clause (vedi [`LICENSE`](LICENSE)). Copre solo il **software** — il contenuto dei preprint
recuperati resta sotto la licenza scelta dal suo autore.
