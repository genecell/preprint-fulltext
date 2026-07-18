# preprint-fulltext

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh.md">简体中文</a> |
  <a href="README.zht.md">繁體中文</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.es.md">Español</a> |
  <b>Français</b> |
  <a href="README.it.md">Italiano</a> |
  <a href="README.ja.md">日本語</a>
</p>

[![PyPI](https://img.shields.io/pypi/v/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![Python](https://img.shields.io/pypi/pyversions/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](LICENSE)
[![CI](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml/badge.svg)](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml)

Récupérez le **texte intégral** des preprints bioRxiv / medRxiv / **arXiv** sous forme de données
propres, structurées et prêtes pour l'*embedding* — depuis une CLI, une bibliothèque Python ou un serveur MCP.

`preprint-fulltext` transforme un DOI (ou une recherche) en sections structurées
(résumé / introduction / méthodes / résultats / discussion), en un unique document JSON/Markdown,
ou en un corpus JSONL/Parquet découpé en fragments et prêt pour l'*embedding* et le RAG. La
conformité aux conditions de fouille de textes et de données (TDM) d'openRxiv est imposée
structurellement, et non laissée à l'utilisateur.

> **« Prêt pour l'*embedding* » signifie que la sortie est constituée de fragments propres,
> conscients des sections et bornés en tokens — prêts à être fournis à *votre* modèle d'embedding.
> Le calcul des embeddings est une dernière étape facultative que vous maîtrisez ; cet outil
> n'embarque aucun modèle d'embedding.**

---

## Pourquoi

Le texte intégral des preprints est éparpillé sur des canaux incompatibles : Europe PMC fournit du
JATS XML pour le sous-ensemble en libre accès, les buckets S3 d'openRxiv hébergent le corpus
`.meca` de référence (payé par le demandeur), OpenAlex est un catalogue avec une recherche plein
texte uniquement par n-grammes, et les sites bioRxiv/medRxiv rendent du HTML. `preprint-fulltext`
les unifie derrière un unique modèle de données canonique et **un unique analyseur JATS partagé**,
de sorte que vous obtenez la même sortie structurée quelle que soit la provenance du document.

## À qui ça s'adresse

- **Chercheurs en ML / NLP** qui construisent des corpus d'embeddings ou des systèmes RAG sur la
  littérature des preprints.
- **Bio-informaticiens et laboratoires** qui ont besoin des méthodes/résultats d'un article sous
  forme de texte propre pour l'analyse, l'extraction ou des *pipelines* LLM.
- **Agents de programmation** (via le serveur MCP / `SKILL.md`) qui doivent récupérer le texte
  intégral d'un preprint ou fouiller la littérature en cours de tâche.
- Toute personne qui veut **les sections d'un preprint à partir d'un DOI** sans analyser le JATS à
  la main ni faire du *scraping* HTML.

## Le texte intégral pour la science pilotée par l'IA

Les modèles de langage et les agents raisonnent bien plus fiablement sur les **méthodes et
résultats** d'un article que sur son seul résumé — la plupart des affirmations scientifiques,
protocoles, quantités et réserves se trouvent dans le corps. `preprint-fulltext` fournit ce corps à
Claude, Codex et aux autres agents sous forme de texte propre, étiqueté par section et annoté de sa
provenance et de sa licence, ce qui constitue le socle d'un **raisonnement scientifique fondé et de
la recherche approfondie** :

- **Recherche documentaire approfondie** — lire le texte intégral de nombreux articles, pas seulement les résumés.
- **Extraction de méthodes / protocoles** — obtenir procédures, paramètres et jeux de données exacts.
- **Vérification des affirmations** — confronter un résultat annoncé à la véritable section « Résultats ».
- **Reproductibilité et méta-analyse** — comparer méthodes et chiffres entre études.
- **RAG sur votre propre corpus** — fragments conscients des sections, bornés en tokens et cités.

Comme chaque `Section`/`Chunk` porte son `kind` (méthodes / résultats / …), son `source` et sa
`license`, un agent peut **citer avec précision** (quelle section de quel article/version) et rester
**dans les limites de la licence** pendant qu'il raisonne. Le texte intégral relève de la
récupération, pas de la mémorisation : le modèle fonde son raisonnement sur la source primaire au
lieu de se rappeler un résumé potentiellement obsolète.

## Fonctionnalités

- **`get <id>`** — le texte intégral d'un preprint en JSON ou Markdown structuré. bioRxiv/medRxiv
  passent par Europe PMC → S3 (repli HTML facultatif) ; les id **arXiv** sont routés vers le texte
  intégral LaTeXML d'arXiv (HTML natif → ar5iv). Dernière version par défaut ; `--version` en choisit une.
- **`search` / `discover`** — recherche par mot-clé, titre, résumé ou auteur sur Europe PMC,
  OpenAlex et **arXiv** ; découverte par sujet/catégorie/date.
- **`ingest`** — ingestion en masse reprenable et incrémentale depuis les buckets S3 d'openRxiv vers
  un corpus fragmenté (JSONL ou Parquet) accompagné d'un manifeste.
- **Serveur MCP** — les mêmes capacités sous forme d'outils pour les agents de programmation.
- **Conformité intégrée** — une passerelle d'export rétrograde les œuvres non redistribuables en
  *stubs* de lien retour ; les licences inconnues sont traitées comme non redistribuables (par sécurité).
- **Un unique analyseur JATS** partagé par les chemins Europe PMC et S3 ; fragmentation consciente
  des tokens et des sections, avec des identifiants de fragment déterministes et idempotents.

## Installation

```bash
pip install preprint-fulltext                       # CLI + Python library + MCP server
pip install "preprint-fulltext[parquet,openalex]"   # + Parquet output, pyalex
```

Le **serveur MCP est intégré** — aucune installation supplémentaire ni framework MCP tiers. C'est un
serveur stdio JSON-RPC 2.0 petit et autonome, donc `preprint-fulltext-mcp` fonctionne
immédiatement avec les seules dépendances du cœur.

Définissez une adresse e-mail de contact pour les *polite pools* d'Europe PMC / OpenAlex
(recommandé), et une clé d'API OpenAlex si vous utilisez OpenAlex (obligatoire chez OpenAlex depuis
le 2026-02-13) :

```bash
export CONTACT_EMAIL="you@example.org"
export OPENALEX_API_KEY="..."            # only needed for OpenAlex discover/search
```

## Démarrage rapide (CLI)

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

`get` émet un document `FullText` (JSON) ou du Markdown (`--markdown`). `search` / `discover`
diffusent un `SearchHit` par ligne (JSONL). `ingest` écrit un `Chunk` par ligne, plus un fichier
`<out>_manifest.jsonl` d'audit et de reprise.

## Cas d'usage typiques

**1. Lire les méthodes/résultats d'un article sous forme de texte.**

```bash
preprint-fulltext get 10.64898/2026.01.29.702557 --markdown > paper.md
# -> # Title / ## Abstract / ## Introduction / ## Methods / ## Results / ## Discussion
```

**2. Construire un corpus prêt pour l'embedding sur un sujet (gratuit, sans AWS).**

```bash
# CC/open-access subset via Europe PMC — one Chunk per JSONL line
preprint-fulltext ingest cortex.jsonl --source europepmc --query "cortical interneurons" -n 500
# cortex.jsonl          -> {doi, version, chunk_id, section_kind, text, token_count, license, ...}
# cortex_manifest.jsonl -> one row per preprint (doi, version, license, n_chunks, status)
```

**3. Construire le corpus complet d'un mois depuis S3 (payé par le demandeur).**

```bash
export AWS_PROFILE=...           # needs AWS credentials; ~$0.09/GB
preprint-fulltext ingest 2025-06.jsonl --source s3 --server both --since 2025-06 --format parquet
# resumable: rerun after an interruption and it skips finished preprints (no duplicates)
```

**4. Trouver des articles par auteur ou titre, puis les récupérer.**

```bash
preprint-fulltext search "Min Dai" --field author -n 20 > hits.jsonl
preprint-fulltext get "$(head -1 hits.jsonl | python -c 'import sys,json;print(json.load(sys.stdin)["doi"])')" --markdown
```

**5. Donner à un agent de programmation l'accès à la littérature** — lancez `preprint-fulltext-mcp`
et pointez votre agent vers lui (voir [`skills/preprint-fulltext/SKILL.md`](skills/preprint-fulltext/SKILL.md)).

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

## Serveur MCP

Donnez à un agent de programmation un accès en direct aux preprints. Le serveur expose quatre
outils — `search_preprints`, `get_fulltext`, `get_metadata`, `resolve` — via stdio. (L'ingestion en
masse `ingest` **n'est** délibérément **pas** un outil : elle est longue et engendre des coûts payés
par le demandeur.)

`mcp-name: io.github.genecell/preprint-fulltext`

C'est un serveur **stdio local**, il fonctionne donc dans Claude Code / Cursor / VS Code / Windsurf
/ Zed / Codex / Cline — mais pas dans l'application web claude.ai (là, utilisez plutôt le
[Skill](skills/preprint-fulltext/SKILL.md)).

### Recommandé : lancer via `uvx` (sans installation)

[uv](https://docs.astral.sh/uv/) exécute le paquet publié à la demande — rien à `pip install` ni à
garder sur le PATH. Installez uv une fois :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# or:  pipx install uv  |  pip install --user uv  |  brew install uv  |  winget install astral-sh.uv
```

La commande de lancement est `uvx --from preprint-fulltext preprint-fulltext-mcp` (le `--from` est
nécessaire car la commande d'exécution diffère du nom du paquet). Le premier lancement télécharge le
paquet (~30 s) ; les suivants sont mis en cache.

<details>
<summary><b>Claude Code</b> — clé <code>mcpServers</code></summary>

```bash
claude mcp add preprint-fulltext --scope user -- uvx --from preprint-fulltext preprint-fulltext-mcp
# uvx not on PATH? use its absolute path:
claude mcp add preprint-fulltext --scope user -- "$(which uvx)" --from preprint-fulltext preprint-fulltext-mcp
claude mcp get preprint-fulltext        # verify → Status: ✔ Connected
```

Ou éditez `~/.claude.json` (utilisateur) / le `.mcp.json` du projet :

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>Cursor / Windsurf / Cline / Continue</b> — clé <code>mcpServers</code> (même forme)</summary>

Cursor : `~/.cursor/mcp.json` (global) ou `.cursor/mcp.json` (projet). Windsurf :
`~/.codeium/windsurf/mcp_config.json`. Cline : *MCP Servers → Configure*. Continue :
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
<summary><b>VS Code</b> (GitHub Copilot, mode Agent) — clé <code>servers</code> + <code>type</code></summary>

`.vscode/mcp.json` (espace de travail) ou le `settings.json` utilisateur sous `"mcp"` :

```json
{ "servers": { "preprint-fulltext": {
  "type": "stdio",
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
} } }
```

Ou en une fois : `code --add-mcp '{"name":"preprint-fulltext","command":"uvx","args":["--from","preprint-fulltext","preprint-fulltext-mcp"]}'`
</details>

<details>
<summary><b>Zed</b> — clé <code>context_servers</code> (forme différente)</summary>

`~/.config/zed/settings.json` :

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
<summary><b>Codex</b> (OpenAI Codex CLI) — TOML, pas JSON</summary>

`~/.codex/config.toml` :

```toml
[mcp_servers.preprint-fulltext]
command = "uvx"
args = ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
# env = { CONTACT_EMAIL = "you@example.org" }
```

Ou : `codex mcp add preprint-fulltext -- uvx --from preprint-fulltext preprint-fulltext-mcp`
</details>

### Alternative : installer avec pip

Si vous avez déjà fait `pip install preprint-fulltext`, le serveur est sur votre PATH sous le nom
`preprint-fulltext-mcp` — utilisez `"command": "preprint-fulltext-mcp"` (sans `args`) dans
n'importe quelle configuration ci-dessus.

> **Variables d'environnement :** définissez `CONTACT_EMAIL` (polite pools Europe PMC / OpenAlex) et
> `OPENALEX_API_KEY` (uniquement pour la recherche/découverte OpenAlex) via le bloc `env` de la
> configuration, ou dans votre shell avant de lancer le client. Voir
> [`SKILL.md`](skills/preprint-fulltext/SKILL.md) pour la référence complète des outils destinée aux agents.

## Sources de données et routage

| Verbe       | Source par défaut     | Notes                                             |
|-------------|-----------------------|---------------------------------------------------|
| `get`       | auto (Europe PMC → S3, ou arXiv) | bioRxiv/medRxiv : EPMC (sous-ensemble CC/OA) → S3 (complet, nécessite des identifiants AWS), repli facultatif `--html`. **id arXiv** → texte intégral LaTeXML d'arXiv (HTML natif → ar5iv). |
| `search`    | Europe PMC            | Classement par pertinence réel ; `--source openalex\|arxiv`. |
| `discover`  | OpenAlex              | Plus de 250 M d'œuvres, emplacements OA, filtres sujet/date ; `--source arxiv`. |
| `ingest`    | S3 (ou Europe PMC)    | S3 = corpus complet ; Europe PMC = sous-ensemble CC gratuit. L'ingestion en masse d'arXiv est hors périmètre (utilisez le propre bucket S3 LaTeX d'arXiv). |

## Configuration

Via des variables d'environnement (préfixées `PREPRINT_FULLTEXT_` ou les noms simples ci-dessous),
un fichier `.env`, ou un `preprint-fulltext.toml` :

| Paramètre | Défaut | Utilité |
|---|---|---|
| `CONTACT_EMAIL` | – | Identité de *polite pool* pour Europe PMC / OpenAlex |
| `OPENALEX_API_KEY` | – | Obligatoire chez OpenAlex depuis le 2026-02-13 |
| `AWS_REGION` | `us-east-1` | Région des buckets openRxiv payés par le demandeur |
| `PREPRINT_FULLTEXT_CACHE_DIR` | `~/.cache/preprint-fulltext` | Cache adressé par contenu |
| `PREPRINT_FULLTEXT_CHUNK_TOKENS` | `512` | Nombre maximal de tokens par fragment |
| `PREPRINT_FULLTEXT_CHUNK_OVERLAP` | `64` | Chevauchement de tokens au sein d'une section |

## Conformité

Les corpus sont destinés à la fouille de textes et de données par l'opérateur lui-même, selon les
conditions TDM d'openRxiv. `preprint-fulltext` ne réhéberge **pas** et ne redistribue **pas** le
texte intégral des preprints. Chaque `FullText`/`Chunk` porte sa licence ; la passerelle d'export a
deux modes :

- **analysis** (par défaut) : passage direct pour votre propre fouille.
- **redistribution** (`--redistribution`) : les œuvres dont la licence autorise la redistribution
  passent sans changement ; toutes les autres sont rétrogradées en **stub de lien retour**
  (métadonnées + URL, sans corps de texte). Les licences inconnues/ambiguës sont traitées comme non redistribuables.

## Développement

```bash
pip install -e ".[dev]"
pytest              # offline suite (HTTP mocked with respx, S3 with moto)
ruff check preprint_fulltext/
```

Les tests en direct sont facultatifs (ils sollicitent les véritables API publiques — Europe PMC,
arXiv et l'API JSON de bioRxiv/medRxiv) :

```bash
PREPRINT_FULLTEXT_LIVE=1 CONTACT_EMAIL=you@example.org pytest -m live   # EPMC / arXiv / medRxiv / versions
PREPRINT_FULLTEXT_LIVE_S3=1 pytest -m live_s3    # requester-pays S3 (small; needs AWS creds)
```

La même vérification à chaud s'exécute en CI à la demande (Actions → **live-smoke**) et chaque
semaine, afin de détecter les dérives des API en amont ; le workflow `test` par défaut reste
entièrement hors ligne.

Les docs pour agents (`AGENTS.md`, `llms.txt`, `.cursor/rules/…`,
`.github/copilot-instructions.md`) sont générées à partir de `skills/preprint-fulltext/SKILL.md` :

```bash
python scripts/build_agent_docs.py
```

## Contact

**Min Dai** — <dai@broadinstitute.org> ([Gord Fishell Lab](https://fishelllab.hms.harvard.edu),
Harvard Medical School / Broad Institute). Les *issues* et *pull requests* sont bienvenues sur
<https://github.com/genecell/preprint-fulltext>.

## Licence

BSD-3-Clause (voir [`LICENSE`](LICENSE)). Elle couvre uniquement le **logiciel** — le contenu des
preprints récupérés reste sous la licence choisie par son auteur.
