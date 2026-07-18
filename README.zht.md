# preprint-fulltext

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh.md">简体中文</a> |
  <b>繁體中文</b> |
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

以乾淨、結構化、可直接用於向量化（embedding）的形式，取得 bioRxiv / medRxiv / **arXiv**
預印本的**全文**——支援命令列（CLI）、Python 函式庫，以及 MCP 伺服器三種方式。

`preprint-fulltext` 能把一個 DOI（或一次檢索）轉換為結構化的章節（摘要 / 引言 / 方法 /
結果 / 討論）、單一 JSON/Markdown 文件，或一個已分塊、可直接用於向量化與 RAG 的
JSONL/Parquet 語料。openRxiv 的文字與資料探勘（TDM）合規性由結構本身強制保證，而非仰賴使用者自覺。

> **「可直接用於向量化」指的是：輸出是乾淨、依章節切分、受 token 上限約束的文字區塊——
> 可直接送入*你自己的*向量化模型。計算向量是一個由你掌控的可選最後步驟；本工具不內建向量化模型。**

---

## 為什麼需要它

預印本全文散落在互不相容的多個管道：Europe PMC 為開放取用子集提供 JATS XML，openRxiv 的
S3 儲存桶保存著權威的 `.meca` 語料（請求方付費），OpenAlex 是一個僅支援 n-gram 全文檢索的
目錄，而 bioRxiv/medRxiv 網站只渲染 HTML。`preprint-fulltext` 用一個統一的規範化資料模型和
**一個共用的 JATS 解析器**把它們整合起來——無論文件來自哪個管道，你都能得到相同的結構化輸出。

## 適用對象

- **機器學習 / NLP 研究者**——需要在預印本文獻上建立向量化語料或 RAG 系統。
- **生物資訊研究者與實驗室**——需要將論文的方法/結果作為乾淨文字，用於分析、抽取或 LLM 流程。
- **程式設計代理（Coding agents）**——透過 MCP 伺服器 / `SKILL.md`，在任務中拉取預印本全文或檢索文獻。
- 任何想要**從一個 DOI 得到某篇預印本的結構化章節**、又不願手動解析 JATS 或抓取 HTML 的人。

## 面向 AI 科研的全文

相較於僅憑摘要，大型語言模型與代理在論文的**方法與結果**上的推理要可靠得多——絕大多數科學論斷、
實驗方案、數值與注意事項都藏在正文裡。`preprint-fulltext` 把正文以乾淨、帶章節標註、帶來源與授權
標籤的文字形式交給 Claude、Codex 等代理，這正是**有據可依的科學推理與深度研究**的基礎：

- **文獻深度研究**——跨多篇論文閱讀全文，而不只是摘要。
- **方法 / 實驗方案抽取**——精確擷取步驟、參數與資料集。
- **論斷核驗**——將某個陳述與真正的「結果」章節對照檢查。
- **可重現性與統合分析**——跨研究比較方法與數值。
- **在你自己的語料上做 RAG**——依章節切分、受 token 上限約束、帶引用出處的文字區塊。

由於每個 `Section`/`Chunk` 都攜帶其 `kind`（方法 / 結果 / …）、`source` 與 `license`，
代理可以**精確引用**（哪一篇論文/版本的哪個章節），並在推理時**遵守授權邊界**。
全文是檢索而非記憶：模型將推理建立在原始文獻之上，而不是依賴可能已過時的摘要式記憶。

## 功能特色

- **`get <id>`**——將一篇預印本的全文輸出為結構化 JSON 或 Markdown。bioRxiv/medRxiv 走
  Europe PMC → S3（可選 HTML 回退）；**arXiv** id 走 arXiv 的 LaTeXML 全文（原生 HTML → ar5iv）。
  預設取最新版本，可用 `--version` 指定。
- **`search` / `discover`**——在 Europe PMC、OpenAlex 與 **arXiv** 上依關鍵字、標題、摘要或
  作者檢索；以及依主題/類別/日期探索。
- **`ingest`**——從 openRxiv S3 儲存桶進行可續傳、增量式的批次匯入，產生分塊語料
  （JSONL 或 Parquet）並附帶清單（manifest）。
- **MCP 伺服器**——將上述能力作為工具提供給程式設計代理。
- **內建合規**——匯出關卡會將不可再散布的作品降級為「回鏈存根（link-back stub）」；未知授權
  一律按不可再散布處理（安全兜底）。
- **一個 JATS 解析器**——被 Europe PMC 與 S3 路徑共用；分塊過程感知 token 與章節邊界，
  且 chunk id 是確定性、冪等的。

## 安裝

```bash
pip install preprint-fulltext                       # CLI + Python library + MCP server
pip install "preprint-fulltext[parquet,openalex]"   # + Parquet output, pyalex
```

**MCP 伺服器已內建**——無需額外安裝，也不依賴任何第三方 MCP 框架。它是一個小巧、自足的
JSON-RPC 2.0 stdio 伺服器，因此 `preprint-fulltext-mcp` 僅憑核心相依套件即可開箱即用。

請設定一個聯絡信箱以使用 Europe PMC / OpenAlex 的禮貌存取池（建議），若使用 OpenAlex，
還需設定其 API key（OpenAlex 自 2026-02-13 起要求）：

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

`get` 輸出一個 `FullText` 文件（JSON）或 Markdown（`--markdown`）。`search` / `discover`
以每行一筆 `SearchHit`（JSONL）的形式串流輸出。`ingest` 每行寫入一個 `Chunk`，並附帶一個
`<out>_manifest.jsonl` 用於稽核與續傳。

## 典型工作流程

**1. 將一篇論文的方法/結果作為文字閱讀。**

```bash
preprint-fulltext get 10.64898/2026.01.29.702557 --markdown > paper.md
# -> # Title / ## Abstract / ## Introduction / ## Methods / ## Results / ## Discussion
```

**2. 就某個主題建立可向量化的語料（免費，無需 AWS）。**

```bash
# CC/open-access subset via Europe PMC — one Chunk per JSONL line
preprint-fulltext ingest cortex.jsonl --source europepmc --query "cortical interneurons" -n 500
# cortex.jsonl          -> {doi, version, chunk_id, section_kind, text, token_count, license, ...}
# cortex_manifest.jsonl -> one row per preprint (doi, version, license, n_chunks, status)
```

**3. 從 S3 建立某一個月的完整語料（請求方付費）。**

```bash
export AWS_PROFILE=...           # needs AWS credentials; ~$0.09/GB
preprint-fulltext ingest 2025-06.jsonl --source s3 --server both --since 2025-06 --format parquet
# resumable: rerun after an interruption and it skips finished preprints (no duplicates)
```

**4. 依作者或標題尋找論文，然後取得全文。**

```bash
preprint-fulltext search "Min Dai" --field author -n 20 > hits.jsonl
preprint-fulltext get "$(head -1 hits.jsonl | python -c 'import sys,json;print(json.load(sys.stdin)["doi"])')" --markdown
```

**5. 讓程式設計代理存取文獻**——執行 `preprint-fulltext-mcp` 並讓你的代理連接它
（參見 [`skills/preprint-fulltext/SKILL.md`](skills/preprint-fulltext/SKILL.md)）。

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

## MCP 伺服器

讓程式設計代理即時存取預印本。該伺服器透過 stdio 公開四個工具——`search_preprints`、
`get_fulltext`、`get_metadata`、`resolve`。（批次 `ingest` 有意**不**作為工具提供：它耗時較長
且會產生請求方付費成本。）

`mcp-name: io.github.genecell/preprint-fulltext`

它是一個**本機 stdio** 伺服器，因此可用於 Claude Code / Cursor / VS Code / Windsurf /
Zed / Codex / Cline——但不能用於 claude.ai 網頁版（網頁版請改用
[Skill](skills/preprint-fulltext/SKILL.md)）。

### 建議：透過 `uvx` 執行（無需安裝）

[uv](https://docs.astral.sh/uv/) 會按需執行已發佈的套件——無需 `pip install`，也不必掛到
PATH 上。只需安裝一次 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# or:  pipx install uv  |  pip install --user uv  |  brew install uv  |  winget install astral-sh.uv
```

啟動指令是 `uvx --from preprint-fulltext preprint-fulltext-mcp`（需要 `--from`，因為執行指令
與套件名稱不同）。首次啟動會下載套件（約 30 秒），之後的啟動都會走快取。

<details>
<summary><b>Claude Code</b> — 鍵 <code>mcpServers</code></summary>

```bash
claude mcp add preprint-fulltext --scope user -- uvx --from preprint-fulltext preprint-fulltext-mcp
# uvx not on PATH? use its absolute path:
claude mcp add preprint-fulltext --scope user -- "$(which uvx)" --from preprint-fulltext preprint-fulltext-mcp
claude mcp get preprint-fulltext        # verify → Status: ✔ Connected
```

或編輯 `~/.claude.json`（使用者層級）/ 專案層級 `.mcp.json`：

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>Cursor / Windsurf / Cline / Continue</b> — 鍵 <code>mcpServers</code>（結構相同）</summary>

Cursor：`~/.cursor/mcp.json`（全域）或 `.cursor/mcp.json`（專案層級）。Windsurf：
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
<summary><b>VS Code</b>（GitHub Copilot，Agent 模式）— 鍵 <code>servers</code> + <code>type</code></summary>

`.vscode/mcp.json`（工作區）或使用者 `settings.json` 中的 `"mcp"`：

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
<summary><b>Zed</b> — 鍵 <code>context_servers</code>（結構不同）</summary>

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

### 備選：以 pip 安裝

如果你已經 `pip install preprint-fulltext`，那麼伺服器會作為 `preprint-fulltext-mcp` 出現在
你的 PATH 上——在上面任意設定中改用 `"command": "preprint-fulltext-mcp"`（無需 `args`）即可。

> **環境變數：** 透過設定中的 `env` 區塊（或在啟動用戶端前於 shell 中）設定 `CONTACT_EMAIL`
> （Europe PMC / OpenAlex 禮貌存取池）與 `OPENALEX_API_KEY`（僅 OpenAlex 檢索/探索時需要）。
> 完整的面向代理的工具說明見 [`SKILL.md`](skills/preprint-fulltext/SKILL.md)。

## 資料來源與路由

| 指令        | 預設資料來源          | 說明                                             |
|-------------|-----------------------|---------------------------------------------------|
| `get`       | 自動（Europe PMC → S3，或 arXiv） | bioRxiv/medRxiv：EPMC（CC/OA 子集）→ S3（完整，需 AWS 憑證），`--html` 為可選回退。**arXiv id** → arXiv LaTeXML 全文（原生 HTML → ar5iv）。 |
| `search`    | Europe PMC            | 真正的相關性排序；`--source openalex\|arxiv`。 |
| `discover`  | OpenAlex              | 2.5 億+ 作品、OA 位置、主題/日期過濾；`--source arxiv`。 |
| `ingest`    | S3（或 Europe PMC）   | S3 = 完整語料；Europe PMC = 免費的 CC 子集。arXiv 批次不在範圍內（請用 arXiv 自己的 S3 LaTeX 儲存桶）。 |

## 設定

可透過環境變數（前綴 `PREPRINT_FULLTEXT_`，或下方的裸名）、`.env` 檔案，或
`preprint-fulltext.toml` 進行設定：

| 設定項 | 預設值 | 用途 |
|---|---|---|
| `CONTACT_EMAIL` | – | Europe PMC / OpenAlex 禮貌存取池的身分識別 |
| `OPENALEX_API_KEY` | – | OpenAlex 自 2026-02-13 起要求 |
| `AWS_REGION` | `us-east-1` | 請求方付費的 openRxiv 儲存桶所在區域 |
| `PREPRINT_FULLTEXT_CACHE_DIR` | `~/.cache/preprint-fulltext` | 基於內容定址的快取 |
| `PREPRINT_FULLTEXT_CHUNK_TOKENS` | `512` | 每個區塊的最大 token 數 |
| `PREPRINT_FULLTEXT_CHUNK_OVERLAP` | `64` | 章節內區塊之間的 token 重疊 |

## 合規

語料僅供使用者自身在 openRxiv TDM 條款下進行文字與資料探勘。`preprint-fulltext` **不會**
重新代管或再散布預印本全文。每個 `FullText`/`Chunk` 都攜帶其授權；匯出關卡有兩種模式：

- **analysis**（預設）：直通，用於你自己的探勘。
- **redistribution**（`--redistribution`）：授權允許再散布的作品原樣通過；其餘一律降級為
  **回鏈存根**（中繼資料 + URL，無正文）。未知/含糊的授權一律按不可再散布處理。

## 開發

```bash
pip install -e ".[dev]"
pytest              # offline suite (HTTP mocked with respx, S3 with moto)
ruff check preprint_fulltext/
```

連網測試為可選（它們會存取真實的公開 API——Europe PMC、arXiv 以及 bioRxiv/medRxiv 的 JSON API）：

```bash
PREPRINT_FULLTEXT_LIVE=1 CONTACT_EMAIL=you@example.org pytest -m live   # EPMC / arXiv / medRxiv / versions
PREPRINT_FULLTEXT_LIVE_S3=1 pytest -m live_s3    # requester-pays S3 (small; needs AWS creds)
```

同樣的連網冒煙測試也會在 CI 中按需執行（Actions → **live-smoke**）並每週執行一次，以便及時
發現上游 API 的變動；預設的 `test` 工作流程則保持完全離線。

面向代理的文件（`AGENTS.md`、`llms.txt`、`.cursor/rules/…`、`.github/copilot-instructions.md`）
由 `skills/preprint-fulltext/SKILL.md` 產生：

```bash
python scripts/build_agent_docs.py
```

## 聯絡方式

**Min Dai** — <dai@broadinstitute.org>（[Gord Fishell Lab](https://fishelllab.hms.harvard.edu)，
哈佛醫學院 / 布洛德研究所）。歡迎在
<https://github.com/genecell/preprint-fulltext> 提交 issue 與 pull request。

## 授權

BSD-3-Clause（見 [`LICENSE`](LICENSE)）。該授權僅涵蓋**軟體本身**——所取得的預印本內容仍
受其作者所選擇的授權約束。
