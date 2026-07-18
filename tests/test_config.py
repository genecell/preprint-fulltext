"""Tests for preprint_fulltext.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from preprint_fulltext.config import (
    DEFAULT_BIORXIV_BUCKET,
    Settings,
    get_settings,
)


def test_defaults():
    s = Settings()
    assert s.aws_region == "us-east-1"
    assert s.chunk_tokens == 512
    assert s.chunk_overlap == 64
    assert s.tokenizer == "tiktoken:cl100k_base"
    assert s.cross_section is False
    assert s.biorxiv_bucket == DEFAULT_BIORXIV_BUCKET
    assert s.contact_email is None
    assert s.openalex_api_key is None


def test_bare_env_names_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONTACT_EMAIL", "me@example.org")
    monkeypatch.setenv("OPENALEX_API_KEY", "k-123")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    s = Settings()
    assert s.contact_email == "me@example.org"
    assert s.openalex_api_key == "k-123"
    assert s.aws_region == "us-west-2"


def test_prefixed_env_names_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PREPRINT_FULLTEXT_CONTACT_EMAIL", "you@example.org")
    monkeypatch.setenv("PREPRINT_FULLTEXT_CHUNK_TOKENS", "256")
    s = Settings()
    assert s.contact_email == "you@example.org"
    assert s.chunk_tokens == 256


def test_user_agent_includes_email_when_set():
    assert "mailto:" not in Settings(contact_email=None).user_agent
    ua = Settings(contact_email="a@b.org").user_agent
    assert ua.startswith("preprint-fulltext/")
    assert "mailto:a@b.org" in ua


def test_bucket_for():
    s = Settings(biorxiv_bucket="bio-bkt", medrxiv_bucket="med-bkt")
    assert s.bucket_for("biorxiv") == "bio-bkt"
    assert s.bucket_for("medrxiv") == "med-bkt"
    with pytest.raises(ValueError):
        s.bucket_for("arxiv")


def test_toml_file_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "preprint-fulltext.toml").write_text(
        'contact_email = "toml@example.org"\nchunk_tokens = 128\n'
    )
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.contact_email == "toml@example.org"
    assert s.chunk_tokens == 128


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "preprint-fulltext.toml").write_text('chunk_tokens = 128\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PREPRINT_FULLTEXT_CHUNK_TOKENS", "999")
    assert Settings().chunk_tokens == 999


def test_get_settings_is_cached():
    a = get_settings()
    b = get_settings()
    assert a is b
