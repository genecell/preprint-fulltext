# preprint-fulltext

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh.md">简体中文</a> |
  <a href="README.zht.md">繁體中文</a> |
  <b>한국어</b> |
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

bioRxiv / medRxiv / **arXiv** 프리프린트의 **전문(full text)**을 깔끔하고 구조화된, 임베딩에
바로 쓸 수 있는 형태로 가져옵니다 — CLI, Python 라이브러리, MCP 서버 어느 쪽에서든.

`preprint-fulltext`는 DOI(또는 검색)를 구조화된 섹션(초록 / 서론 / 방법 / 결과 / 논의),
단일 JSON/Markdown 문서, 또는 임베딩과 RAG에 바로 쓸 수 있도록 청크로 나뉜 JSONL/Parquet
말뭉치로 변환합니다. openRxiv의 텍스트·데이터 마이닝(TDM) 준수는 사용자에게 맡기지 않고
구조적으로 강제됩니다.

> **“임베딩에 바로 쓸 수 있다”는 것은, 출력이 깔끔하고 섹션을 인지하며 토큰 상한을 지키는
> 청크라는 뜻입니다 — *당신의* 임베딩 모델에 바로 넣을 수 있습니다. 임베딩 계산은 당신이
> 관리하는 선택적 마지막 단계이며, 이 도구는 임베딩 모델을 포함하지 않습니다.**

---

## 왜 필요한가

프리프린트 전문은 서로 호환되지 않는 여러 경로에 흩어져 있습니다. Europe PMC는 오픈
액세스 부분집합에 JATS XML을 제공하고, openRxiv S3 버킷은 권위 있는 `.meca` 말뭉치를
(요청자 부담으로) 보관하며, OpenAlex는 n-gram 전문 검색만 지원하는 카탈로그이고,
bioRxiv/medRxiv 웹사이트는 HTML을 렌더링합니다. `preprint-fulltext`는 이들을 하나의
정규 데이터 모델과 **하나의 공유 JATS 파서** 뒤로 통합하므로, 문서가 어디에서 왔든 동일한
구조화 출력을 얻습니다.

## 누구를 위한 것인가

- **ML / NLP 연구자** — 프리프린트 문헌 위에 임베딩 말뭉치나 RAG 시스템을 구축하는 분.
- **생물정보학 연구자와 연구실** — 논문의 방법/결과를 분석·추출·LLM 파이프라인용 깔끔한
  텍스트로 필요로 하는 분.
- **코딩 에이전트** — MCP 서버 / `SKILL.md`를 통해 작업 중에 프리프린트 전문을 가져오거나
  문헌을 검색하는 분.
- JATS를 손으로 파싱하거나 HTML을 스크래핑하지 않고 **DOI로부터 프리프린트의 섹션을** 얻고
  싶은 모든 사람.

## AI 기반 과학을 위한 전문

언어 모델과 에이전트는 초록만 볼 때보다 논문의 **방법과 결과**에 대해 훨씬 더 신뢰성 있게
추론합니다 — 대부분의 과학적 주장, 프로토콜, 수치, 단서는 본문에 있습니다.
`preprint-fulltext`는 그 본문을 깔끔하고 섹션 라벨이 붙었으며 출처와 라이선스 태그가 달린
텍스트로 Claude, Codex 등 에이전트에 제공하며, 이는 **근거에 기반한 과학적 추론과 심층
연구**의 토대가 됩니다:

- **문헌 심층 연구** — 초록이 아니라 여러 논문의 전문을 가로질러 읽기.
- **방법 / 프로토콜 추출** — 정확한 절차, 매개변수, 데이터셋 가져오기.
- **주장 검증** — 서술된 결과를 실제 “결과” 섹션과 대조.
- **재현성과 메타분석** — 연구 간 방법과 수치 비교.
- **자체 말뭉치 위 RAG** — 섹션 인지, 토큰 상한, 인용이 있는 청크.

각 `Section`/`Chunk`가 자신의 `kind`(방법 / 결과 / …), `source`, `license`를 지니므로
에이전트는 **정확하게 인용**(어느 논문/버전의 어느 섹션인지)하고 추론하는 동안
**라이선스 범위 내**에 머물 수 있습니다. 전문은 기억이 아니라 검색입니다. 모델은 오래되었을
수도 있는 요약을 회상하는 대신 1차 자료에 근거해 추론합니다.

## 기능

- **`get <id>`** — 한 프리프린트의 전문을 구조화 JSON 또는 Markdown으로. bioRxiv/medRxiv는
  Europe PMC → S3(선택적 HTML 대체)로, **arXiv** id는 arXiv의 LaTeXML 전문(네이티브 HTML → ar5iv)으로
  라우팅. 기본은 최신 버전, `--version`으로 선택.
- **`search` / `discover`** — Europe PMC, OpenAlex, **arXiv** 전반에서 키워드·제목·초록·저자
  검색과 주제/분류/날짜 발견.
- **`ingest`** — openRxiv S3 버킷에서 재개 가능하고 증분적인 대량 수집으로, 청크 말뭉치
  (JSONL 또는 Parquet)와 사이드카 매니페스트를 생성.
- **MCP 서버** — 동일한 기능을 코딩 에이전트용 도구로 제공.
- **컴플라이언스 내장** — 내보내기 게이트가 재배포 불가 저작물을 링크백 스텁으로 강등하고,
  알 수 없는 라이선스는 재배포 불가로 처리(안전 우선).
- **하나의 JATS 파서** — Europe PMC와 S3 경로가 공유. 토큰과 섹션 경계를 인지하는 청킹,
  청크 id는 결정적이며 멱등적.

## 설치

```bash
pip install preprint-fulltext                       # CLI + Python library + MCP server
pip install "preprint-fulltext[parquet,openalex]"   # + Parquet output, pyalex
```

**MCP 서버는 내장**되어 있습니다 — 추가 설치도, 서드파티 MCP 프레임워크도 필요 없습니다.
작고 자기완결적인 JSON-RPC 2.0 stdio 서버이므로 `preprint-fulltext-mcp`는 핵심 의존성만으로
바로 동작합니다.

Europe PMC / OpenAlex의 polite pool을 위해 연락 이메일을 설정하고(권장), OpenAlex를 쓰면
그 API 키도 설정하세요(OpenAlex는 2026-02-13부터 필수):

```bash
export CONTACT_EMAIL="you@example.org"
export OPENALEX_API_KEY="..."            # only needed for OpenAlex discover/search
```

## 빠른 시작 (CLI)

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

`get`은 `FullText` 문서(JSON) 또는 Markdown(`--markdown`)을 출력합니다. `search` / `discover`는
한 줄에 하나씩 `SearchHit`(JSONL)를 스트리밍합니다. `ingest`는 한 줄에 하나씩 `Chunk`를
쓰고, 감사와 재개를 위한 `<out>_manifest.jsonl`을 함께 남깁니다.

## 대표적인 워크플로

**1. 논문의 방법/결과를 텍스트로 읽기.**

```bash
preprint-fulltext get 10.64898/2026.01.29.702557 --markdown > paper.md
# -> # Title / ## Abstract / ## Introduction / ## Methods / ## Results / ## Discussion
```

**2. 특정 주제에 대한 임베딩용 말뭉치 구축(무료, AWS 불필요).**

```bash
# CC/open-access subset via Europe PMC — one Chunk per JSONL line
preprint-fulltext ingest cortex.jsonl --source europepmc --query "cortical interneurons" -n 500
# cortex.jsonl          -> {doi, version, chunk_id, section_kind, text, token_count, license, ...}
# cortex_manifest.jsonl -> one row per preprint (doi, version, license, n_chunks, status)
```

**3. S3에서 한 달치 완전 말뭉치 구축(요청자 부담).**

```bash
export AWS_PROFILE=...           # needs AWS credentials; ~$0.09/GB
preprint-fulltext ingest 2025-06.jsonl --source s3 --server both --since 2025-06 --format parquet
# resumable: rerun after an interruption and it skips finished preprints (no duplicates)
```

**4. 저자나 제목으로 논문을 찾은 뒤 가져오기.**

```bash
preprint-fulltext search "Min Dai" --field author -n 20 > hits.jsonl
preprint-fulltext get "$(head -1 hits.jsonl | python -c 'import sys,json;print(json.load(sys.stdin)["doi"])')" --markdown
```

**5. 코딩 에이전트에 문헌 접근 권한 부여** — `preprint-fulltext-mcp`를 실행하고 에이전트를
연결하세요([`skills/preprint-fulltext/SKILL.md`](skills/preprint-fulltext/SKILL.md) 참고).

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

## MCP 서버

코딩 에이전트에 프리프린트 실시간 접근을 제공합니다. 서버는 stdio를 통해 네 개의 도구—
`search_preprints`, `get_fulltext`, `get_metadata`, `resolve`—를 노출합니다. (대량 `ingest`는
의도적으로 도구가 **아닙니다**: 오래 걸리고 요청자 부담 비용이 발생합니다.)

`mcp-name: io.github.genecell/preprint-fulltext`

**로컬 stdio** 서버이므로 Claude Code / Cursor / VS Code / Windsurf / Zed / Codex / Cline에서
동작합니다 — 다만 claude.ai 웹 앱에서는 동작하지 않습니다(그곳에서는
[Skill](skills/preprint-fulltext/SKILL.md)을 사용하세요).

### 권장: `uvx`로 실행(설치 불필요)

[uv](https://docs.astral.sh/uv/)는 게시된 패키지를 필요할 때 실행합니다 — `pip install`이나
PATH 등록이 필요 없습니다. uv는 한 번만 설치하세요:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# or:  pipx install uv  |  pip install --user uv  |  brew install uv  |  winget install astral-sh.uv
```

실행 명령은 `uvx --from preprint-fulltext preprint-fulltext-mcp`입니다(실행 명령이 패키지
이름과 달라 `--from`이 필요). 첫 실행은 패키지를 내려받고(약 30초), 이후에는 캐시됩니다.

<details>
<summary><b>Claude Code</b> — 키 <code>mcpServers</code></summary>

```bash
claude mcp add preprint-fulltext --scope user -- uvx --from preprint-fulltext preprint-fulltext-mcp
# uvx not on PATH? use its absolute path:
claude mcp add preprint-fulltext --scope user -- "$(which uvx)" --from preprint-fulltext preprint-fulltext-mcp
claude mcp get preprint-fulltext        # verify → Status: ✔ Connected
```

또는 `~/.claude.json`(사용자) / 프로젝트 `.mcp.json`을 편집:

```json
{ "mcpServers": { "preprint-fulltext": {
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"],
  "env": { "CONTACT_EMAIL": "you@example.org" }
} } }
```
</details>

<details>
<summary><b>Cursor / Windsurf / Cline / Continue</b> — 키 <code>mcpServers</code>(동일한 형태)</summary>

Cursor: `~/.cursor/mcp.json`(전역) 또는 `.cursor/mcp.json`(프로젝트). Windsurf:
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
<summary><b>VS Code</b>(GitHub Copilot, Agent 모드)— 키 <code>servers</code> + <code>type</code></summary>

`.vscode/mcp.json`(워크스페이스) 또는 사용자 `settings.json`의 `"mcp"` 아래:

```json
{ "servers": { "preprint-fulltext": {
  "type": "stdio",
  "command": "uvx",
  "args": ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
} } }
```

또는 한 번에: `code --add-mcp '{"name":"preprint-fulltext","command":"uvx","args":["--from","preprint-fulltext","preprint-fulltext-mcp"]}'`
</details>

<details>
<summary><b>Zed</b> — 키 <code>context_servers</code>(형태가 다름)</summary>

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
<summary><b>Codex</b>(OpenAI Codex CLI)— JSON이 아니라 TOML</summary>

`~/.codex/config.toml`:

```toml
[mcp_servers.preprint-fulltext]
command = "uvx"
args = ["--from", "preprint-fulltext", "preprint-fulltext-mcp"]
# env = { CONTACT_EMAIL = "you@example.org" }
```

또는: `codex mcp add preprint-fulltext -- uvx --from preprint-fulltext preprint-fulltext-mcp`
</details>

### 대안: pip로 설치

이미 `pip install preprint-fulltext`를 했다면 서버가 `preprint-fulltext-mcp`로 PATH에
있습니다 — 위 어느 설정에서든 `"command": "preprint-fulltext-mcp"`(그리고 `args` 없이)를
사용하세요.

> **환경 변수:** 설정의 `env` 블록으로(또는 클라이언트 실행 전 셸에서) `CONTACT_EMAIL`
> (Europe PMC / OpenAlex polite pool)과 `OPENALEX_API_KEY`(OpenAlex 검색/발견 시에만)를
> 설정하세요. 에이전트용 전체 도구 레퍼런스는
> [`SKILL.md`](skills/preprint-fulltext/SKILL.md)를 참고하세요.

## 데이터 소스와 라우팅

| 명령        | 기본 소스             | 비고                                             |
|-------------|-----------------------|---------------------------------------------------|
| `get`       | 자동 (Europe PMC → S3, 또는 arXiv) | bioRxiv/medRxiv: EPMC(CC/OA 부분집합) → S3(완전, AWS 자격증명 필요), `--html`은 선택적 대체. **arXiv id** → arXiv LaTeXML 전문(네이티브 HTML → ar5iv). |
| `search`    | Europe PMC            | 실제 관련도 랭킹; `--source openalex\|arxiv`. |
| `discover`  | OpenAlex              | 2.5억+ 저작물, OA 위치, 주제/날짜 필터; `--source arxiv`. |
| `ingest`    | S3 (또는 Europe PMC)  | S3 = 완전 말뭉치; Europe PMC = 무료 CC 부분집합. arXiv 대량은 범위 밖(arXiv 자체 S3 LaTeX 버킷 사용). |

## 설정

환경 변수(접두사 `PREPRINT_FULLTEXT_` 또는 아래의 단순 이름), `.env` 파일, 또는
`preprint-fulltext.toml`로 설정합니다:

| 설정 | 기본값 | 용도 |
|---|---|---|
| `CONTACT_EMAIL` | – | Europe PMC / OpenAlex polite pool 식별자 |
| `OPENALEX_API_KEY` | – | OpenAlex는 2026-02-13부터 필수 |
| `AWS_REGION` | `us-east-1` | 요청자 부담 openRxiv 버킷의 리전 |
| `PREPRINT_FULLTEXT_CACHE_DIR` | `~/.cache/preprint-fulltext` | 콘텐츠 주소 지정 캐시 |
| `PREPRINT_FULLTEXT_CHUNK_TOKENS` | `512` | 청크당 최대 토큰 수 |
| `PREPRINT_FULLTEXT_CHUNK_OVERLAP` | `64` | 섹션 내 청크 간 토큰 중첩 |

## 컴플라이언스

말뭉치는 openRxiv TDM 약관 하에서 운영자 자신의 텍스트·데이터 마이닝을 위한 것입니다.
`preprint-fulltext`는 프리프린트 전문을 재호스팅하거나 재배포하지 **않습니다**. 각
`FullText`/`Chunk`는 자신의 라이선스를 지닙니다. 내보내기 게이트에는 두 가지 모드가 있습니다:

- **analysis**(기본): 자신의 마이닝을 위한 그대로 통과.
- **redistribution**(`--redistribution`): 라이선스가 재배포를 허용하는 저작물은 그대로 통과하고,
  나머지는 모두 **링크백 스텁**(메타데이터 + URL, 본문 없음)으로 강등. 알 수 없거나 모호한
  라이선스는 재배포 불가로 처리.

## 개발

```bash
pip install -e ".[dev]"
pytest              # offline suite (HTTP mocked with respx, S3 with moto)
ruff check preprint_fulltext/
```

라이브 테스트는 선택 사항입니다(실제 공개 API — Europe PMC, arXiv, bioRxiv/medRxiv JSON API에 접속):

```bash
PREPRINT_FULLTEXT_LIVE=1 CONTACT_EMAIL=you@example.org pytest -m live   # EPMC / arXiv / medRxiv / versions
PREPRINT_FULLTEXT_LIVE_S3=1 pytest -m live_s3    # requester-pays S3 (small; needs AWS creds)
```

동일한 라이브 스모크가 CI에서 필요 시(Actions → **live-smoke**)와 매주 실행되어 상위 API의
변화를 잡아냅니다. 기본 `test` 워크플로는 완전히 오프라인으로 유지됩니다.

에이전트용 문서(`AGENTS.md`, `llms.txt`, `.cursor/rules/…`, `.github/copilot-instructions.md`)는
`skills/preprint-fulltext/SKILL.md`에서 생성됩니다:

```bash
python scripts/build_agent_docs.py
```

## 연락처

**Min Dai** — <dai@broadinstitute.org> ([Gord Fishell Lab](https://fishelllab.hms.harvard.edu),
하버드 의과대학 / 브로드 연구소). 이슈와 풀 리퀘스트는
<https://github.com/genecell/preprint-fulltext>에서 환영합니다.

## 라이선스

BSD-3-Clause([`LICENSE`](LICENSE) 참고). 이는 **소프트웨어**에만 적용됩니다 — 가져온
프리프린트 콘텐츠는 저자가 선택한 라이선스 하에 유지됩니다.
