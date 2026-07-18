#!/usr/bin/env python3
"""Generate per-platform agent docs from the single source of truth.

Source:  skills/preprint-fulltext/SKILL.md  (Claude Code skill; canonical)
Outputs (all regenerated, do not edit by hand):
  - AGENTS.md                          cross-agent standard (Codex, etc.)
  - llms.txt                           the llms.txt convention
  - .cursor/rules/preprint-fulltext.mdc   Cursor project rule
  - .github/copilot-instructions.md    GitHub Copilot

Run:  python scripts/build_agent_docs.py   (also runnable in CI)
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "skills" / "preprint-fulltext" / "SKILL.md"
BANNER = "<!-- GENERATED from skills/preprint-fulltext/SKILL.md by scripts/build_agent_docs.py — do not edit. -->"


def parse_skill(text: str) -> tuple[dict[str, str], str]:
    """Split YAML-ish frontmatter (name/description) from the markdown body."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    front_raw, body = m.group(1), m.group(2).lstrip("\n")
    front: dict[str, str] = {}
    key = None
    for line in front_raw.splitlines():
        if re.match(r"^\w[\w-]*:", line):
            key, _, val = line.partition(":")
            key = key.strip()
            # Drop YAML block-scalar indicators (>, |, >-, |-) so they don't leak in.
            front[key] = "" if val.strip() in (">", ">-", "|", "|-") else val.strip()
        elif key and line.strip():  # folded continuation
            front[key] = (front[key] + " " + line.strip()).strip()
    return front, body


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


def main() -> None:
    front, body = parse_skill(SOURCE.read_text(encoding="utf-8"))
    desc = front.get("description", "").strip()

    # AGENTS.md — cross-agent standard (body already opens with an H1 title).
    write(ROOT / "AGENTS.md", f"{BANNER}\n\n{body}")

    # GitHub Copilot instructions.
    write(ROOT / ".github" / "copilot-instructions.md", f"{BANNER}\n\n{body}")

    # Cursor project rule (.mdc with its own frontmatter).
    mdc_front = (
        "---\n"
        f"description: {desc}\n"
        "globs:\n"
        "alwaysApply: false\n"
        "---\n"
    )
    write(ROOT / ".cursor" / "rules" / "preprint-fulltext.mdc", mdc_front + "\n" + body)

    # llms.txt — concise, link-first.
    llms = (
        f"# preprint-fulltext\n\n> {desc}\n\n"
        "## Docs\n"
        "- [SKILL.md](skills/preprint-fulltext/SKILL.md): full agent guide (CLI, MCP, data model)\n"
        "- [README.md](README.md): overview, install, configuration\n\n"
        + body
    )
    write(ROOT / "llms.txt", llms)


if __name__ == "__main__":
    main()
