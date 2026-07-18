"""Test helpers: fixture loading and a `.meca` builder (no committed binaries)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_path(name: str) -> Path:
    return FIXTURES / name


def read_fixture(name: str) -> bytes:
    return fixture_path(name).read_bytes()


# MECA manifest listing the article JATS inside content/. bioRxiv's real manifest
# is richer, but our parser only needs to resolve the article item's href (and
# falls back to the largest content/*.xml), so this minimal-but-valid form suffices.
_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest xmlns:xlink="http://www.w3.org/1999/xlink">
  <item id="art" item-type="article-metadata" item-version="0">
    <instance media-type="application/xml" xlink:href="{article}"/>
  </item>
  <item id="pdf" item-type="article" item-version="0">
    <instance media-type="application/pdf" xlink:href="content/{stem}.pdf"/>
  </item>
</manifest>
"""


def make_meca(
    xml_bytes: bytes,
    *,
    article_name: str = "content/article.xml",
    include_manifest: bool = True,
    extra_content: dict[str, bytes] | None = None,
) -> bytes:
    """Build a ``.meca`` (zip) around a JATS XML payload.

    Mirrors the real layout: ``manifest.xml`` at the root, the article JATS and a
    dummy PDF under ``content/``, plus the ``mimetype`` marker.
    """
    stem = Path(article_name).stem
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/zip")
        if include_manifest:
            zf.writestr("manifest.xml", _MANIFEST.format(article=article_name, stem=stem))
        zf.writestr(article_name, xml_bytes)
        zf.writestr(f"content/{stem}.pdf", b"%PDF-1.4 dummy")
        for path, data in (extra_content or {}).items():
            zf.writestr(path, data)
    return buf.getvalue()
