# preprint-fulltext

<p align="center">
  <a href="README.md">English</a> |
  <b>简体中文</b> |
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

以干净、结构化、可直接用于向量化（embedding）的形式，获取 bioRxiv / medRxiv / **arXiv**
预印本的**全文**——支持命令行（CLI）、Python 库以及 MCP 服务器三种方式。

`preprint-fulltext` 能把一个 DOI（或一次检索）转换为结构化的章节（摘要 / 引言 / 方法 /
结果 / 讨论）、单个 JSON/Markdown 文档，或一个已分块、可直接用于向量化与 RAG 的
JSONL/Parquet 语料。openRxiv 的文本与数据挖掘（TDM）合规性由结构本身强制保证，而非依赖用户自觉。

> **“可直接用于向量化”指的是：输出是干净、按章节切分、受 token 上限约束的文本块——
> 可直接送入*你自己的*向量化模型。计算向量是一个由你掌控的可选最后步骤；本工具不内置向量化模型。**

---

## 为什么需要它

预印本全文散落在互不兼容的多个渠道：Europe PMC 为开放获取子集提供 JATS XML，openRxiv
的 S3 存储桶保存着权威的 `.meca` 语料（请求方付费），OpenAlex 是一个仅支持 n-gram 全文检索的
目录，而 bioRxiv/medRxiv 网站只渲染 HTML。`preprint-fulltext` 用一个统一的规范化数据模型和
**一个共享的 JATS 解析器**把它们整合起来——无论文档来自哪个渠道，你都得到相同的结构化输出。

## 适用人群

- **机器学习 / NLP 研究者**——需要在预印本文献上构建向量化语料或 RAG 系统。
- **生物信息学研究者与实验室**——需要将论文的方法/结果作为干净文本用于分析、抽取或 LLM 流水线。
- **编程智能体（Coding agents）**——通过 MCP 服务器 / `SKILL.md`，在任务中拉取预印本全文或检索文献。
- 任何想要**从一个 DOI 得到某篇预印本的结构化章节**、又不愿手动解析 JATS 或抓取 HTML 的人。

## 面向 AI 科研的全文

相比仅凭摘要，大语言模型与智能体在论文的**方法与结果**上的推理要可靠得多——绝大多数科学论断、
实验方案、数值与注意事项都藏在正文里。`preprint-fulltext` 把正文以干净、带章节标注、带来源与许可证
标签的文本形式交给 Claude、Codex 等智能体，这正是**有据可依的科学推理与深度研究**的基础：

- **文献深度研究**——跨多篇论文阅读全文，而不只是摘要。
- **方法 / 实验方案抽取**——精确提取步骤、参数与数据集。
- **论断核验**——将某个陈述与真正的“结果”章节对照检查。
- **可复现性与元分析**——跨研究比较方法与数值。
- **在你自己的语料上做 RAG**——按章节切分、受 token 上限约束、带引用出处的文本块。

由于每个 `Section`/`Chunk` 都携带其 `kind`（方法 / 结果 / …）、`source` 与 `license`，
智能体可以**精确引用**（哪一篇论文/版本的哪个章节），并在推理时**遵守许可证边界**。
全文是检索而非记忆：模型将推理建立在原始文献之上，而不是依赖可能已过时的摘要式记忆。

## 功能特性

- **`get <id>`**——将一篇预印本的全文输出为结构化 JSON 或 Markdown。bioRxiv/medRxiv 走
  Europe PMC → S3（可选 HTML 回退）；**arXiv** id 走 arXiv 的 LaTeXML 全文（原生 HTML → ar5iv）。
  默认取最新版本，可用 `--version` 指定。
- **`search` / `discover`**——在 Europe PMC、OpenAlex 与 **arXiv** 上按关键词、标题、摘要或
  作者检索；以及按主题/类别/日期发现。
- **`ingest`**——从 openRxiv S3 存储桶进行可断点续传、增量式的批量导入，生成分块语料
  （JSONL 或 Parquet）并附带清单（manifest）。
- **MCP 服务器**——将上述能力作为工具提供给编程智能体。
- **内置合规**——导出关卡会将不可再分发的作品降级为“回链存根（link-back stub）”；未知许可证
  一律按不可再分发处理（安全兜底）。
- **一个 JATS 解析器**——被 Europe PMC 与 S3 路径共享；分块过程感知 token 与章节边界，
  且 chunk id 是确定性、幂等的。

## 安装

```bash
pip install preprint-fulltext                       # CLI + Python library + MCP server
pip install "preprint-fulltext[parquet,openalex]"   # + Parquet output, pyalex
```

**MCP 服务器已内置**——无需额外安装，也不依赖任何第三方 MCP 框架。它是一个小巧、自包含的
JSON-RPC 2.0 stdio 服务器，因此 `preprint-fulltext-mcp` 仅凭核心依赖即可开箱即用。

请设置一个联系邮箱以使用 Europe PMC / OpenAlex 的礼貌访问池（推荐），若使用 OpenAlex，
还需设置其 API key（OpenAlex 自 2026-02-13 起要求）：

```bash
export CONTACT_EMAIL="you@example.org"
export OPENALEX_API_KEY="..."            # only needed for OpenAlex discover/search
```

## 快速上手（CLI）

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

`get` 输出一个 `FullText` 文档（JSON）或 Markdown（`--markdown`）。`search` / `discover`
以每行一条 `SearchHit`（JSONL）的形式流式输出。`ingest` 每行写入一个 `Chunk`，并附带一个
`<out>_manifest.jsonl` 用于审计与断点续传。

## 典型工作流

**1. 将一篇论文的方法/结果作为文本阅读。**

```bash
preprint-fulltext get 10.64898/2026.01.29.702557 --markdown > paper.md
# -> # Title / ## Abstract / ## Introduction / ## Methods / ## Results / ## Discussion
```

**2. 就某个主题构建可向量化的语料（免费，无需 AWS）。**

```bash
# CC/open-access subset via Europe PMC — one Chunk per JSONL line
preprint-fulltext ingest cortex.jsonl --source europepmc --query "cortical interneurons" -n 500
# cortex.jsonl          -> {doi, version, chunk_id, section_kind, text, token_count, license, ...}
# cortex_manifest.jsonl -> one row per preprint (doi, version, license, n_chunks, status)
```

**3. 从 S3 构建某一个月的完整语料（请求方付费）。**

```bash
export AWS_PROFILE=...           # needs AWS credentials; ~$0.09/GB
preprint-fulltext ingest 2025-06.jsonl --source s3 --server both --since 2025-06 --format parquet
# resumable: rerun after an interruption and it skips finished preprints (no duplicates)
```

**4. 按作者或标题查找论文，然后获取全文。**

```bash
preprint-fulltext search "Min Dai" --field author -n 20 > hits.jsonl
preprint-fulltext get "$(head -1 hits.jsonl | python -c 'import sys,json;print(json.load(sys.stdin)["doi"])')" --markdown
```

**5. 让编程智能体访问文献**——运行 `preprint-fulltext-mcp` 并让你的智能体连接它
（参见 [`skills/preprint-fulltext/SKILL.md`](skills/preprint-fulltext/SKILL.md)）。

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

## MCP 服务器

让编程智能体实时访问预印本。该服务器通过 stdio 暴露四个工具——`search_preprints`、
`get_fulltext`、`get_metadata`、`resolve`。（批量 `ingest` 有意**不**作为工具提供：它耗时较长
且会产生请求方付费成本。）

`mcp-name: io.github.genecell/preprint-fulltext`

它是一个**本地 stdio** 服务器，因此可用于 Claude Code / Cursor / VS Code / Windsurf /
Zed / Codex / Cline——但不能用于 claude.ai 网页版（网页版请改用
[Skill](skills/preprint-fulltext/SKILL.md)）。

### 推荐：通过 `uvx` 运行（无需安装）

[uv](https://docs.astral.sh/uv/) 会按需运行已发布的软件包——无需 `pip install`，也不必挂到
PATH 上。只需安装一次 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# or:  pipx install uv  |  pip install --user uv  |  brew install uv  |  winget install astral-sh.uv
```

启动命令是 `uvx --from preprint-fulltext preprint-fulltext-mcp`（需要 `--from`，因为运行命令
与包名不同）。首次启动会下载软件包（约 30 秒），之后的启动都会走缓存。

<details>
<summary><b>Claude Code</b> — 键 <code>mcpServers</code></summary>

```bash
claude mcp add preprint-fulltext --scope user -- uvx --from preprint-fulltext preprint-fulltext-mcp
# uvx not on PATH? use its absolute path:
claude mcp add preprint-fulltext --scope user -- "$(which uvx)" --from preprint-fulltext preprint-fulltext-mcp
claude mcp get preprint-fulltext        # verify → Status: ✔ Connected
```

或编辑 `~/.claude.json`（用户级）/ 项目级 `.mcp.json`：

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>Cursor / Windsurf / Cline / Continue</b> — 键 <code>mcpServers</code>（结构相同）</summary>

Cursor：`~/.cursor/mcp.json`（全局）或 `.cursor/mcp.json`（项目级）。Windsurf：
`~/.codeium/windsurf/mcp_config.json`。Cline：*MCP Servers → Configure*。Continue：
`~/.continue/config`。

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>VS Code</b>（GitHub Copilot，Agent 模式）— 键 <code>servers</code> + <code>type</code></summary>

`.vscode/mcp.json`（工作区）或用户 `settings.json` 中的 `"mcp"`：

```json
{ "servers": { "preprint-fulltext": {
  "type": "stdio",
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
} } }
```

或一行搞定：`code --add-mcp '{"name":"preprint-fulltext","command":"uvx","args":["--from","preprint-fulltext","preprint-fulltext-mcp"]}'`
</details>

<details>
<summary><b>Zed</b> — 键 <code>context_servers</code>（结构不同）</summary>

`~/.config/zed/settings.json`：

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
<summary><b>Codex</b>（OpenAI Codex CLI）— TOML，而非 JSON</summary>

`~/.codex/config.toml`：

```toml
[mcp_servers.preprint-fulltext]
command = "uvx"
args = ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
# env = { CONTACT_EMAIL = "you@example.org" }
```

或：`codex mcp add preprint-fulltext -- uvx --from preprint-fulltext preprint-fulltext-mcp`
</details>

### 备选：用 pip 安装

如果你已经 `pip install preprint-fulltext`，那么服务器会作为 `preprint-fulltext-mcp` 出现在
你的 PATH 上——在上面任意配置中改用 `"command": "preprint-fulltext-mcp"`（无需 `args`）即可。

> **环境变量：** 通过配置中的 `env` 块（或在启动客户端前于 shell 中）设置 `CONTACT_EMAIL`
> （Europe PMC / OpenAlex 礼貌访问池）与 `OPENALEX_API_KEY`（仅 OpenAlex 检索/发现时需要）。
> 完整的面向智能体的工具说明见 [`SKILL.md`](skills/preprint-fulltext/SKILL.md)。

## 数据源与路由

| 命令        | 默认数据源            | 说明                                             |
|-------------|-----------------------|---------------------------------------------------|
| `get`       | 自动（Europe PMC → S3，或 arXiv） | bioRxiv/medRxiv：EPMC（CC/OA 子集）→ S3（完整，需 AWS 凭证），`--html` 为可选回退。**arXiv id** → arXiv LaTeXML 全文（原生 HTML → ar5iv）。 |
| `search`    | Europe PMC            | 真正的相关性排序；`--source openalex\|arxiv`。 |
| `discover`  | OpenAlex              | 2.5 亿+ 作品、OA 位置、主题/日期过滤；`--source arxiv`。 |
| `ingest`    | S3（或 Europe PMC）   | S3 = 完整语料；Europe PMC = 免费的 CC 子集。arXiv 批量不在范围内（请用 arXiv 自己的 S3 LaTeX 存储桶）。 |

## 配置

可通过环境变量（前缀 `PREPRINT_FULLTEXT_`，或下方的裸名）、`.env` 文件，或
`preprint-fulltext.toml` 进行配置：

| 设置项 | 默认值 | 用途 |
|---|---|---|
| `CONTACT_EMAIL` | – | Europe PMC / OpenAlex 礼貌访问池的身份标识 |
| `OPENALEX_API_KEY` | – | OpenAlex 自 2026-02-13 起要求 |
| `AWS_REGION` | `us-east-1` | 请求方付费的 openRxiv 存储桶所在区域 |
| `PREPRINT_FULLTEXT_CACHE_DIR` | `~/.cache/preprint-fulltext` | 基于内容寻址的缓存 |
| `PREPRINT_FULLTEXT_CHUNK_TOKENS` | `512` | 每个块的最大 token 数 |
| `PREPRINT_FULLTEXT_CHUNK_OVERLAP` | `64` | 章节内块之间的 token 重叠 |

## 合规

语料仅供使用者自身在 openRxiv TDM 条款下进行文本与数据挖掘。`preprint-fulltext` **不会**
重新托管或再分发预印本全文。每个 `FullText`/`Chunk` 都携带其许可证；导出关卡有两种模式：

- **analysis**（默认）：直通，用于你自己的挖掘。
- **redistribution**（`--redistribution`）：许可证允许再分发的作品原样通过；其余一律降级为
  **回链存根**（元数据 + URL，无正文）。未知/含糊的许可证一律按不可再分发处理。

## 开发

```bash
pip install -e ".[dev]"
pytest              # offline suite (HTTP mocked with respx, S3 with moto)
ruff check preprint_fulltext/
```

联网测试为可选（它们会访问真实的公开 API——Europe PMC、arXiv 以及 bioRxiv/medRxiv 的 JSON API）：

```bash
PREPRINT_FULLTEXT_LIVE=1 CONTACT_EMAIL=you@example.org pytest -m live   # EPMC / arXiv / medRxiv / versions
PREPRINT_FULLTEXT_LIVE_S3=1 pytest -m live_s3    # requester-pays S3 (small; needs AWS creds)
```

同样的联网冒烟测试也会在 CI 中按需运行（Actions → **live-smoke**）并每周运行一次，以便及时
发现上游 API 的变动；默认的 `test` 工作流则保持完全离线。

面向智能体的文档（`AGENTS.md`、`llms.txt`、`.cursor/rules/…`、`.github/copilot-instructions.md`）
由 `skills/preprint-fulltext/SKILL.md` 生成：

```bash
python scripts/build_agent_docs.py
```

## 联系方式

**Min Dai** — <dai@broadinstitute.org>（[Gord Fishell Lab](https://fishelllab.hms.harvard.edu)，
哈佛医学院 / 布罗德研究所）。欢迎在
<https://github.com/genecell/preprint-fulltext> 提交 issue 与 pull request。

## 许可证

BSD-3-Clause（见 [`LICENSE`](LICENSE)）。该许可证仅覆盖**软件本身**——所获取的预印本内容仍
受其作者所选择的许可证约束。
