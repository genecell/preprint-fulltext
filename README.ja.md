# preprint-fulltext

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh.md">简体中文</a> |
  <a href="README.zht.md">繁體中文</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.es.md">Español</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.it.md">Italiano</a> |
  <b>日本語</b>
</p>

[![PyPI](https://img.shields.io/pypi/v/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![Python](https://img.shields.io/pypi/pyversions/preprint-fulltext.svg)](https://pypi.org/project/preprint-fulltext/)
[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](LICENSE)
[![CI](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml/badge.svg)](https://github.com/genecell/preprint-fulltext/actions/workflows/test.yml)

bioRxiv / medRxiv / **arXiv** プレプリントの**全文**を、クリーンで構造化された、埋め込み
（embedding）にすぐ使える形で取得します——CLI、Python ライブラリ、MCP サーバーのいずれからでも。

`preprint-fulltext` は、DOI（または検索）を、構造化されたセクション（要旨 / 序論 / 方法 /
結果 / 考察）、単一の JSON/Markdown ドキュメント、あるいは埋め込みや RAG にそのまま使える
チャンク化済みの JSONL/Parquet コーパスへと変換します。openRxiv のテキスト・データマイニング
（TDM）コンプライアンスは、利用者任せではなく構造として強制されます。

> **「埋め込みにすぐ使える」とは、出力がクリーンでセクション単位、トークン数の上限を守った
> チャンクであることを意味します——*あなた自身の*埋め込みモデルにそのまま投入できます。
> 埋め込みの計算はあなたが管理する任意の最終ステップであり、本ツールは埋め込みモデルを同梱しません。**

---

## なぜ必要か

プレプリントの全文は、互いに非互換なチャネルに散らばっています。Europe PMC はオープン
アクセス部分集合に JATS XML を提供し、openRxiv の S3 バケットは権威ある `.meca` コーパスを
（リクエスター負担で）保持し、OpenAlex は n-gram 全文検索のみのカタログで、bioRxiv/medRxiv の
ウェブサイトは HTML を返します。`preprint-fulltext` は、これらを 1 つの正規化データモデルと
**1 つの共有 JATS パーサー**の背後に統合します——文書がどこ由来でも、同じ構造化出力が得られます。

## 対象ユーザー

- **ML / NLP 研究者**——プレプリント文献上に埋め込みコーパスや RAG システムを構築する方。
- **バイオインフォマティクス研究者・研究室**——論文の方法/結果を、解析・抽出・LLM パイプライン
  向けのクリーンなテキストとして必要とする方。
- **コーディングエージェント**——MCP サーバー / `SKILL.md` を通じて、作業中にプレプリント全文を
  取得したり文献を検索したりする方。
- **DOI から 1 本のプレプリントのセクションを得たい**が、JATS を手作業でパースしたり HTML を
  スクレイピングしたりはしたくない、すべての方。

## AI 駆動科学のための全文

言語モデルやエージェントは、要旨だけよりも論文の**方法と結果**に対してはるかに信頼性の高い
推論を行えます——ほとんどの科学的主張・プロトコル・数値・注意点は本文にあります。
`preprint-fulltext` は、その本文を、クリーンでセクションラベル付き、出所とライセンスの
タグ付きテキストとして Claude や Codex などのエージェントに提供します。これは
**根拠に基づく科学的推論とディープリサーチ**の土台です。

- **文献のディープリサーチ**——要旨だけでなく、多数の論文の全文を横断的に読む。
- **方法 / プロトコルの抽出**——正確な手順・パラメータ・データセットを取り出す。
- **主張の検証**——ある記述を実際の「結果」セクションと突き合わせる。
- **再現性とメタアナリシス**——研究間で方法や数値を比較する。
- **自前コーパス上の RAG**——セクション単位・トークン制限付き・引用付きのチャンク。

各 `Section`/`Chunk` はその `kind`（方法 / 結果 / …）、`source`、`license` を保持するため、
エージェントは**正確に引用**（どの論文/バージョンのどのセクションか）でき、推論中も
**ライセンス範囲内に留まれます**。全文は記憶ではなく検索です。モデルは、古くなっている
かもしれない要約の記憶ではなく、一次資料に基づいて推論します。

## 機能

- **`get <id>`**——1 本のプレプリントの全文を構造化 JSON または Markdown として取得。
  bioRxiv/medRxiv は Europe PMC → S3（任意の HTML フォールバック）、**arXiv** id は arXiv の
  LaTeXML 全文（ネイティブ HTML → ar5iv）へルーティング。既定は最新バージョン、`--version` で指定可。
- **`search` / `discover`**——Europe PMC、OpenAlex、**arXiv** 全体でキーワード・タイトル・
  要旨・著者による検索、およびトピック/カテゴリ/日付による発見。
- **`ingest`**——openRxiv S3 バケットからの再開可能・増分的な一括取り込みで、チャンク化
  コーパス（JSONL または Parquet）とサイドカーのマニフェストを生成。
- **MCP サーバー**——同じ機能をコーディングエージェント向けのツールとして提供。
- **コンプライアンス内蔵**——エクスポートゲートは再配布不可の著作物をリンクバック用スタブへ
  格下げ。未知のライセンスは再配布不可として扱う（フェイルセーフ）。
- **1 つの JATS パーサー**——Europe PMC と S3 の経路で共有。トークンとセクション境界を意識した
  チャンク化で、chunk id は決定的かつ冪等。

## インストール

```bash
pip install preprint-fulltext                       # CLI + Python library + MCP server
pip install "preprint-fulltext[parquet,openalex]"   # + Parquet output, pyalex
```

**MCP サーバーは内蔵**です——追加インストールも、サードパーティ製 MCP フレームワークも不要。
小さく自己完結した JSON-RPC 2.0 stdio サーバーなので、`preprint-fulltext-mcp` はコア依存だけで
そのまま動作します。

Europe PMC / OpenAlex の polite pool 用に連絡先メールを設定してください（推奨）。OpenAlex を
使う場合はその API キーも必要です（OpenAlex は 2026-02-13 以降に必須化）：

```bash
export CONTACT_EMAIL="you@example.org"
export OPENALEX_API_KEY="..."            # only needed for OpenAlex discover/search
```

## クイックスタート（CLI）

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

`get` は `FullText` ドキュメント（JSON）または Markdown（`--markdown`）を出力します。
`search` / `discover` は 1 行 1 件の `SearchHit`（JSONL）をストリーム出力します。`ingest` は
1 行 1 件の `Chunk` を書き出し、監査・再開用に `<out>_manifest.jsonl` を併せて出力します。

## 代表的なワークフロー

**1. 1 本の論文の方法/結果をテキストとして読む。**

```bash
preprint-fulltext get 10.64898/2026.01.29.702557 --markdown > paper.md
# -> # Title / ## Abstract / ## Introduction / ## Methods / ## Results / ## Discussion
```

**2. あるトピックについて埋め込み用コーパスを構築（無料・AWS 不要）。**

```bash
# CC/open-access subset via Europe PMC — one Chunk per JSONL line
preprint-fulltext ingest cortex.jsonl --source europepmc --query "cortical interneurons" -n 500
# cortex.jsonl          -> {doi, version, chunk_id, section_kind, text, token_count, license, ...}
# cortex_manifest.jsonl -> one row per preprint (doi, version, license, n_chunks, status)
```

**3. S3 からある 1 か月分の完全なコーパスを構築（リクエスター負担）。**

```bash
export AWS_PROFILE=...           # needs AWS credentials; ~$0.09/GB
preprint-fulltext ingest 2025-06.jsonl --source s3 --server both --since 2025-06 --format parquet
# resumable: rerun after an interruption and it skips finished preprints (no duplicates)
```

**4. 著者名やタイトルで論文を探し、全文を取得する。**

```bash
preprint-fulltext search "Min Dai" --field author -n 20 > hits.jsonl
preprint-fulltext get "$(head -1 hits.jsonl | python -c 'import sys,json;print(json.load(sys.stdin)["doi"])')" --markdown
```

**5. コーディングエージェントに文献アクセスを与える**——`preprint-fulltext-mcp` を起動し、
エージェントを接続します（[`skills/preprint-fulltext/SKILL.md`](skills/preprint-fulltext/SKILL.md) を参照）。

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

## MCP サーバー

コーディングエージェントにプレプリントへのライブアクセスを与えます。サーバーは stdio 経由で
4 つのツール——`search_preprints`、`get_fulltext`、`get_metadata`、`resolve`——を公開します。
（一括 `ingest` は意図的に**ツールとして提供しません**：長時間実行かつリクエスター負担の
コストが発生するためです。）

`mcp-name: io.github.genecell/preprint-fulltext`

これは**ローカル stdio** サーバーなので、Claude Code / Cursor / VS Code / Windsurf / Zed /
Codex / Cline で動作します——ただし claude.ai のウェブアプリでは動作しません（そこでは
[Skill](skills/preprint-fulltext/SKILL.md) を使ってください）。

### 推奨：`uvx` で実行（インストール不要）

[uv](https://docs.astral.sh/uv/) は公開済みパッケージをオンデマンドで実行します——`pip install`
も PATH への登録も不要です。uv は一度だけインストールしてください：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# or:  pipx install uv  |  pip install --user uv  |  brew install uv  |  winget install astral-sh.uv
```

起動コマンドは `uvx --from preprint-fulltext preprint-fulltext-mcp` です（実行コマンドが
パッケージ名と異なるため `--from` が必要）。初回起動でパッケージをダウンロードし（約 30 秒）、
以降はキャッシュされます。

<details>
<summary><b>Claude Code</b> — キー <code>mcpServers</code></summary>

```bash
claude mcp add preprint-fulltext --scope user -- uvx --from preprint-fulltext preprint-fulltext-mcp
# uvx not on PATH? use its absolute path:
claude mcp add preprint-fulltext --scope user -- "$(which uvx)" --from preprint-fulltext preprint-fulltext-mcp
claude mcp get preprint-fulltext        # verify → Status: ✔ Connected
```

または `~/.claude.json`（ユーザー）/ プロジェクトの `.mcp.json` を編集：

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>Cursor / Windsurf / Cline / Continue</b> — キー <code>mcpServers</code>（同じ形式）</summary>

Cursor：`~/.cursor/mcp.json`（グローバル）または `.cursor/mcp.json`（プロジェクト）。Windsurf：
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
<summary><b>VS Code</b>（GitHub Copilot、Agent モード）— キー <code>servers</code> + <code>type</code></summary>

`.vscode/mcp.json`（ワークスペース）またはユーザー `settings.json` の `"mcp"` 配下：

```json
{ "servers": { "preprint-fulltext": {
  "type": "stdio",
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
} } }
```

または一発で：`code --add-mcp '{"name":"preprint-fulltext","command":"uvx","args":["--from","preprint-fulltext","preprint-fulltext-mcp"]}'`
</details>

<details>
<summary><b>Zed</b> — キー <code>context_servers</code>（形式が異なる）</summary>

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
<summary><b>Codex</b>（OpenAI Codex CLI）— JSON ではなく TOML</summary>

`~/.codex/config.toml`：

```toml
[mcp_servers.preprint-fulltext]
command = "uvx"
args = ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
# env = { CONTACT_EMAIL = "you@example.org" }
```

または：`codex mcp add preprint-fulltext -- uvx --from preprint-fulltext preprint-fulltext-mcp`
</details>

### 代替：pip でインストール

すでに `pip install preprint-fulltext` 済みなら、サーバーは `preprint-fulltext-mcp` として
PATH 上にあります——上記いずれの設定でも `"command": "preprint-fulltext-mcp"`（`args` 不要）を
使ってください。

> **環境変数：** `CONTACT_EMAIL`（Europe PMC / OpenAlex polite pool）と `OPENALEX_API_KEY`
> （OpenAlex の検索/発見時のみ）を、設定の `env` ブロックで、あるいはクライアント起動前に
> シェルで設定してください。エージェント向けの完全なツールリファレンスは
> [`SKILL.md`](skills/preprint-fulltext/SKILL.md) を参照。

## データソースとルーティング

| コマンド    | 既定のソース          | 備考                                             |
|-------------|-----------------------|---------------------------------------------------|
| `get`       | 自動（Europe PMC → S3、または arXiv） | bioRxiv/medRxiv：EPMC（CC/OA 部分集合）→ S3（完全、AWS 認証情報が必要）、`--html` は任意のフォールバック。**arXiv id** → arXiv LaTeXML 全文（ネイティブ HTML → ar5iv）。 |
| `search`    | Europe PMC            | 実際の関連度ランキング；`--source openalex\|arxiv`。 |
| `discover`  | OpenAlex              | 2.5 億件以上の著作物、OA 位置、トピック/日付フィルタ；`--source arxiv`。 |
| `ingest`    | S3（または Europe PMC） | S3 = 完全コーパス；Europe PMC = 無料の CC 部分集合。arXiv の一括は対象外（arXiv 独自の S3 LaTeX バケットを使用）。 |

## 設定

環境変数（接頭辞 `PREPRINT_FULLTEXT_`、または下記の裸の名前）、`.env` ファイル、あるいは
`preprint-fulltext.toml` で設定できます：

| 設定 | 既定値 | 用途 |
|---|---|---|
| `CONTACT_EMAIL` | – | Europe PMC / OpenAlex polite pool の識別子 |
| `OPENALEX_API_KEY` | – | OpenAlex は 2026-02-13 以降に必須 |
| `AWS_REGION` | `us-east-1` | リクエスター負担の openRxiv バケットのリージョン |
| `PREPRINT_FULLTEXT_CACHE_DIR` | `~/.cache/preprint-fulltext` | コンテンツアドレス指定のキャッシュ |
| `PREPRINT_FULLTEXT_CHUNK_TOKENS` | `512` | チャンクあたりの最大トークン数 |
| `PREPRINT_FULLTEXT_CHUNK_OVERLAP` | `64` | セクション内チャンク間のトークン重複 |

## コンプライアンス

コーパスは、openRxiv TDM 条項の下での利用者自身のテキスト・データマイニング用です。
`preprint-fulltext` はプレプリント全文を再ホストしたり再配布したりは**しません**。各
`FullText`/`Chunk` はそのライセンスを保持します。エクスポートゲートには 2 つのモードがあります：

- **analysis**（既定）：自分自身のマイニング用にそのまま通過。
- **redistribution**（`--redistribution`）：ライセンスが再配布を許可する著作物はそのまま通過し、
  それ以外はすべて**リンクバック用スタブ**（メタデータ + URL、本文なし）へ格下げ。未知/
  曖昧なライセンスは再配布不可として扱う。

## 開発

```bash
pip install -e ".[dev]"
pytest              # offline suite (HTTP mocked with respx, S3 with moto)
ruff check preprint_fulltext/
```

ライブテストはオプトインです（実際の公開 API——Europe PMC、arXiv、bioRxiv/medRxiv の
JSON API——にアクセスします）：

```bash
PREPRINT_FULLTEXT_LIVE=1 CONTACT_EMAIL=you@example.org pytest -m live   # EPMC / arXiv / medRxiv / versions
PREPRINT_FULLTEXT_LIVE_S3=1 pytest -m live_s3    # requester-pays S3 (small; needs AWS creds)
```

同じライブスモークは CI でもオンデマンド（Actions → **live-smoke**）および毎週実行され、上流
API の変化を捉えます。既定の `test` ワークフローは完全にオフラインを維持します。

エージェント向けドキュメント（`AGENTS.md`、`llms.txt`、`.cursor/rules/…`、
`.github/copilot-instructions.md`）は `skills/preprint-fulltext/SKILL.md` から生成されます：

```bash
python scripts/build_agent_docs.py
```

## 連絡先

**Min Dai** — <dai@broadinstitute.org>（[Gord Fishell Lab](https://fishelllab.hms.harvard.edu)、
ハーバード医学大学院 / ブロード研究所）。issue と pull request は
<https://github.com/genecell/preprint-fulltext> へどうぞ。

## ライセンス

BSD-3-Clause（[`LICENSE`](LICENSE) を参照）。これは**ソフトウェア**のみを対象とします——
取得したプレプリントの内容は、その著者が選択したライセンスの下に留まります。
