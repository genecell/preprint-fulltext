# preprint-fulltext

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh.md">简体中文</a> |
  <a href="README.zht.md">繁體中文</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.de.md">Deutsch</a> |
  <b>Español</b> |
  <a href="README.fr.md">Français</a> |
  <a href="README.it.md">Italiano</a> |
  <a href="README.ja.md">日本語</a>
</p>

[![PyPI](https://img.shields.io/pypi/v/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![Python](https://img.shields.io/pypi/pyversions/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](LICENSE)
[![CI](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml/badge.svg)](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml)

Obtén el **texto completo** de preprints de bioRxiv / medRxiv / **arXiv** como datos limpios,
estructurados y listos para *embeddings* — desde una CLI, una biblioteca de Python o un servidor MCP.

`preprint-fulltext` convierte un DOI (o una búsqueda) en secciones estructuradas
(resumen / introducción / métodos / resultados / discusión), un único documento JSON/Markdown,
o un corpus JSONL/Parquet fragmentado y listo para *embeddings* y RAG. El cumplimiento de los
términos de minería de textos y datos (TDM) de openRxiv se aplica de forma estructural, no queda
a criterio del usuario.

> **«Listo para *embeddings*» significa que la salida son fragmentos limpios, conscientes de las
> secciones y acotados por tokens — listos para alimentar a *tu* modelo de embeddings. Calcular los
> embeddings es un último paso opcional que tú controlas; esta herramienta no incluye un modelo de embeddings.**

---

## Por qué

El texto completo de los preprints está disperso en canales incompatibles: Europe PMC ofrece
JATS XML para el subconjunto de acceso abierto, los buckets S3 de openRxiv contienen el corpus
`.meca` autoritativo (con pago del solicitante), OpenAlex es un catálogo con búsqueda de texto
completo solo por n-gramas, y los sitios web de bioRxiv/medRxiv renderizan HTML.
`preprint-fulltext` los unifica tras un único modelo de datos canónico y **un único analizador
JATS compartido**, de modo que obtienes la misma salida estructurada sin importar de dónde
provenga el documento.

## Para quién es

- **Investigadores de ML / NLP** que construyen corpus de embeddings o sistemas RAG sobre la
  literatura de preprints.
- **Bioinformáticos y laboratorios** que necesitan los métodos/resultados de un artículo como
  texto limpio para análisis, extracción o *pipelines* con LLM.
- **Agentes de programación** (vía el servidor MCP / `SKILL.md`) que necesitan obtener el texto
  completo de un preprint o buscar en la literatura durante una tarea.
- Cualquiera que quiera **las secciones de un preprint a partir de un DOI** sin analizar JATS a
  mano ni hacer *scraping* de HTML.

## Texto completo para la ciencia impulsada por IA

Los modelos de lenguaje y los agentes razonan de forma mucho más fiable sobre los **métodos y
resultados** de un artículo que sobre su resumen — la mayoría de las afirmaciones científicas,
protocolos, cantidades y salvedades están en el cuerpo. `preprint-fulltext` entrega ese cuerpo a
Claude, Codex y otros agentes como texto limpio, etiquetado por sección y con etiquetas de
procedencia y licencia, que es el sustrato para un **razonamiento científico fundamentado y la
investigación profunda**:

- **Investigación profunda de la literatura** — leer el texto completo de muchos artículos, no solo resúmenes.
- **Extracción de métodos / protocolos** — obtener procedimientos, parámetros y conjuntos de datos exactos.
- **Verificación de afirmaciones** — contrastar un resultado enunciado con la sección de Resultados real.
- **Reproducibilidad y metaanálisis** — comparar métodos y cifras entre estudios.
- **RAG sobre tu propio corpus** — fragmentos conscientes de las secciones, acotados por tokens y con citas.

Como cada `Section`/`Chunk` lleva su `kind` (métodos / resultados / …), su `source` y su
`license`, un agente puede **citar con precisión** (qué sección de qué artículo/versión) y
mantenerse **dentro de la licencia** mientras razona. El texto completo es recuperación, no
memorización: el modelo fundamenta su razonamiento en la fuente primaria en lugar de recordar un
resumen posiblemente desactualizado.

## Características

- **`get <id>`** — el texto completo de un preprint como JSON o Markdown estructurado.
  bioRxiv/medRxiv se enrutan por Europe PMC → S3 (con HTML opcional de reserva); los id de
  **arXiv** se enrutan al texto completo LaTeXML de arXiv (HTML nativo → ar5iv). Por defecto la
  última versión; `--version` selecciona una.
- **`search` / `discover`** — búsqueda por palabra clave, título, resumen o autor en Europe PMC,
  OpenAlex y **arXiv**; descubrimiento por tema/categoría/fecha.
- **`ingest`** — ingesta masiva reanudable e incremental desde los buckets S3 de openRxiv hacia un
  corpus fragmentado (JSONL o Parquet) con un manifiesto adjunto.
- **Servidor MCP** — las mismas capacidades como herramientas para agentes de programación.
- **Cumplimiento integrado** — una compuerta de exportación degrada las obras no redistribuibles a
  *stubs* de enlace de retorno; las licencias desconocidas se tratan como no redistribuibles (a prueba de fallos).
- **Un único analizador JATS** compartido por las rutas de Europe PMC y S3; fragmentación
  consciente de tokens y secciones, con identificadores de fragmento deterministas e idempotentes.

## Instalación

```bash
pip install preprint-fulltext                       # CLI + Python library + MCP server
pip install "preprint-fulltext[parquet,openalex]"   # + Parquet output, pyalex
```

El **servidor MCP viene integrado** — sin instalación extra ni marco MCP de terceros. Es un
servidor stdio JSON-RPC 2.0 pequeño y autónomo, así que `preprint-fulltext-mcp` funciona de
inmediato solo con las dependencias del núcleo.

Configura un correo de contacto para los *polite pools* de Europe PMC / OpenAlex (recomendado), y
una clave de API de OpenAlex si usas OpenAlex (obligatoria en OpenAlex desde el 2026-02-13):

```bash
export CONTACT_EMAIL="you@example.org"
export OPENALEX_API_KEY="..."            # only needed for OpenAlex discover/search
```

## Inicio rápido (CLI)

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

`get` emite un documento `FullText` (JSON) o Markdown (`--markdown`). `search` / `discover`
transmiten un `SearchHit` por línea (JSONL). `ingest` escribe un `Chunk` por línea más un
archivo adjunto `<out>_manifest.jsonl` para auditoría y reanudación.

## Flujos de trabajo típicos

**1. Leer los métodos/resultados de un artículo como texto.**

```bash
preprint-fulltext get 10.64898/2026.01.29.702557 --markdown > paper.md
# -> # Title / ## Abstract / ## Introduction / ## Methods / ## Results / ## Discussion
```

**2. Construir un corpus listo para embeddings sobre un tema (gratis, sin AWS).**

```bash
# CC/open-access subset via Europe PMC — one Chunk per JSONL line
preprint-fulltext ingest cortex.jsonl --source europepmc --query "cortical interneurons" -n 500
# cortex.jsonl          -> {doi, version, chunk_id, section_kind, text, token_count, license, ...}
# cortex_manifest.jsonl -> one row per preprint (doi, version, license, n_chunks, status)
```

**3. Construir el corpus completo de un mes desde S3 (con pago del solicitante).**

```bash
export AWS_PROFILE=...           # needs AWS credentials; ~$0.09/GB
preprint-fulltext ingest 2025-06.jsonl --source s3 --server both --since 2025-06 --format parquet
# resumable: rerun after an interruption and it skips finished preprints (no duplicates)
```

**4. Encontrar artículos por autor o título y luego obtenerlos.**

```bash
preprint-fulltext search "Min Dai" --field author -n 20 > hits.jsonl
preprint-fulltext get "$(head -1 hits.jsonl | python -c 'import sys,json;print(json.load(sys.stdin)["doi"])')" --markdown
```

**5. Dar a un agente de programación acceso a la literatura** — ejecuta `preprint-fulltext-mcp` y
apunta tu agente hacia él (consulta [`skills/preprint-fulltext/SKILL.md`](skills/preprint-fulltext/SKILL.md)).

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

## Servidor MCP

Da a un agente de programación acceso en vivo a los preprints. El servidor expone cuatro
herramientas — `search_preprints`, `get_fulltext`, `get_metadata`, `resolve` — por stdio.
(La ingesta masiva `ingest` **no** es una herramienta a propósito: es de larga duración e incurre
en costes de pago del solicitante.)

`mcp-name: io.github.genecell/preprint-fulltext`

Es un servidor **stdio local**, por lo que funciona en Claude Code / Cursor / VS Code / Windsurf /
Zed / Codex / Cline — pero no en la aplicación web claude.ai (allí, usa el
[Skill](skills/preprint-fulltext/SKILL.md) en su lugar).

### Recomendado: ejecutar con `uvx` (sin instalación)

[uv](https://docs.astral.sh/uv/) ejecuta el paquete publicado bajo demanda — no hay nada que
`pip install` ni que mantener en el PATH. Instala uv una vez:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# or:  pipx install uv  |  pip install --user uv  |  brew install uv  |  winget install astral-sh.uv
```

El comando de arranque es `uvx --from preprint-fulltext preprint-fulltext-mcp` (el `--from` es
necesario porque el comando de ejecución difiere del nombre del paquete). El primer arranque
descarga el paquete (~30 s); los siguientes usan la caché.

<details>
<summary><b>Claude Code</b> — clave <code>mcpServers</code></summary>

```bash
claude mcp add preprint-fulltext --scope user -- uvx --from preprint-fulltext preprint-fulltext-mcp
# uvx not on PATH? use its absolute path:
claude mcp add preprint-fulltext --scope user -- "$(which uvx)" --from preprint-fulltext preprint-fulltext-mcp
claude mcp get preprint-fulltext        # verify → Status: ✔ Connected
```

O edita `~/.claude.json` (usuario) / el `.mcp.json` del proyecto:

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>Cursor / Windsurf / Cline / Continue</b> — clave <code>mcpServers</code> (misma forma)</summary>

Cursor: `~/.cursor/mcp.json` (global) o `.cursor/mcp.json` (proyecto). Windsurf:
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
<summary><b>VS Code</b> (GitHub Copilot, modo Agente) — clave <code>servers</code> + <code>type</code></summary>

`.vscode/mcp.json` (del espacio de trabajo) o el `settings.json` de usuario bajo `"mcp"`:

```json
{ "servers": { "preprint-fulltext": {
  "type": "stdio",
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
} } }
```

O de una sola vez: `code --add-mcp '{"name":"preprint-fulltext","command":"uvx","args":["--from","preprint-fulltext","preprint-fulltext-mcp"]}'`
</details>

<details>
<summary><b>Zed</b> — clave <code>context_servers</code> (forma diferente)</summary>

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
<summary><b>Codex</b> (OpenAI Codex CLI) — TOML, no JSON</summary>

`~/.codex/config.toml`:

```toml
[mcp_servers.preprint-fulltext]
command = "uvx"
args = ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
# env = { CONTACT_EMAIL = "you@example.org" }
```

O: `codex mcp add preprint-fulltext -- uvx --from preprint-fulltext preprint-fulltext-mcp`
</details>

### Alternativa: instalar con pip

Si ya hiciste `pip install preprint-fulltext`, el servidor está en tu PATH como
`preprint-fulltext-mcp` — usa `"command": "preprint-fulltext-mcp"` (sin `args`) en cualquiera de
las configuraciones anteriores.

> **Variables de entorno:** configura `CONTACT_EMAIL` (polite pools de Europe PMC / OpenAlex) y
> `OPENALEX_API_KEY` (solo para búsqueda/descubrimiento en OpenAlex) mediante el bloque `env` de la
> configuración, o en tu shell antes de lanzar el cliente. Consulta
> [`SKILL.md`](skills/preprint-fulltext/SKILL.md) para la referencia completa de herramientas orientada a agentes.

## Fuentes de datos y enrutamiento

| Verbo       | Fuente por defecto    | Notas                                             |
|-------------|-----------------------|---------------------------------------------------|
| `get`       | auto (Europe PMC → S3, o arXiv) | bioRxiv/medRxiv: EPMC (subconjunto CC/OA) → S3 (completo, requiere credenciales AWS), `--html` como reserva opcional. **id de arXiv** → texto completo LaTeXML de arXiv (HTML nativo → ar5iv). |
| `search`    | Europe PMC            | Ranking de relevancia real; `--source openalex\|arxiv`. |
| `discover`  | OpenAlex              | Más de 250 M de obras, ubicaciones OA, filtros por tema/fecha; `--source arxiv`. |
| `ingest`    | S3 (o Europe PMC)     | S3 = corpus completo; Europe PMC = subconjunto CC gratuito. La ingesta masiva de arXiv está fuera de alcance (usa el propio bucket S3 de LaTeX de arXiv). |

## Configuración

Mediante variables de entorno (con el prefijo `PREPRINT_FULLTEXT_` o los nombres simples de abajo),
un archivo `.env`, o un `preprint-fulltext.toml`:

| Ajuste | Por defecto | Propósito |
|---|---|---|
| `CONTACT_EMAIL` | – | Identidad de *polite pool* para Europe PMC / OpenAlex |
| `OPENALEX_API_KEY` | – | Obligatoria en OpenAlex desde el 2026-02-13 |
| `AWS_REGION` | `us-east-1` | Región de los buckets openRxiv con pago del solicitante |
| `PREPRINT_FULLTEXT_CACHE_DIR` | `~/.cache/preprint-fulltext` | Caché con direccionamiento por contenido |
| `PREPRINT_FULLTEXT_CHUNK_TOKENS` | `512` | Máximo de tokens por fragmento |
| `PREPRINT_FULLTEXT_CHUNK_OVERLAP` | `64` | Solapamiento de tokens dentro de una sección |

## Cumplimiento

Los corpus son para la minería de textos y datos del propio operador bajo los términos TDM de
openRxiv. `preprint-fulltext` **no** vuelve a alojar ni redistribuye el texto completo de los
preprints. Cada `FullText`/`Chunk` lleva su licencia; la compuerta de exportación tiene dos modos:

- **analysis** (por defecto): paso directo para tu propia minería.
- **redistribution** (`--redistribution`): las obras cuya licencia permite la redistribución pasan
  sin cambios; el resto se degrada a un **stub de enlace de retorno** (metadatos + URL, sin texto
  del cuerpo). Las licencias desconocidas/ambiguas se tratan como no redistribuibles.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest              # offline suite (HTTP mocked with respx, S3 with moto)
ruff check preprint_fulltext/
```

Las pruebas en vivo son opcionales (acceden a las API públicas reales — Europe PMC, arXiv y la
API JSON de bioRxiv/medRxiv):

```bash
PREPRINT_FULLTEXT_LIVE=1 CONTACT_EMAIL=you@example.org pytest -m live   # EPMC / arXiv / medRxiv / versions
PREPRINT_FULLTEXT_LIVE_S3=1 pytest -m live_s3    # requester-pays S3 (small; needs AWS creds)
```

La misma prueba de humo en vivo se ejecuta en CI bajo demanda (Actions → **live-smoke**) y
semanalmente, para detectar cambios en las API externas; el flujo de trabajo `test` por defecto
permanece totalmente sin conexión.

Los documentos para agentes (`AGENTS.md`, `llms.txt`, `.cursor/rules/…`,
`.github/copilot-instructions.md`) se generan a partir de `skills/preprint-fulltext/SKILL.md`:

```bash
python scripts/build_agent_docs.py
```

## Contacto

**Min Dai** — <dai@broadinstitute.org> ([Gord Fishell Lab](https://fishelllab.hms.harvard.edu),
Harvard Medical School / Broad Institute). Se agradecen *issues* y *pull requests* en
<https://github.com/genecell/preprint-fulltext>.

## Licencia

BSD-3-Clause (consulta [`LICENSE`](LICENSE)). Cubre únicamente el **software** — el contenido de
los preprints obtenidos permanece bajo la licencia elegida por su autor.
