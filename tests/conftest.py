"""Shared pytest fixtures and the offline/live gating.

The whole suite runs offline and free by default. Tests marked
``live`` need ``PREPRINT_FULLTEXT_LIVE=1``; ``live_s3`` additionally needs
``PREPRINT_FULLTEXT_LIVE_S3=1`` (requester-pays cost).
"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    live_on = os.environ.get("PREPRINT_FULLTEXT_LIVE") == "1"
    live_s3_on = os.environ.get("PREPRINT_FULLTEXT_LIVE_S3") == "1"
    skip_live = pytest.mark.skip(reason="set PREPRINT_FULLTEXT_LIVE=1 to run live tests")
    skip_live_s3 = pytest.mark.skip(reason="set PREPRINT_FULLTEXT_LIVE_S3=1 to run live S3 tests")
    for item in items:
        if "live_s3" in item.keywords and not live_s3_on:
            item.add_marker(skip_live_s3)
        elif "live" in item.keywords and not live_on:
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Keep unit tests hermetic: no ambient credentials/keys/TOML leak in, and the
    cache defaults under a tmp dir. Individual tests set what they need."""
    for var in (
        "CONTACT_EMAIL",
        "OPENALEX_API_KEY",
        "PREPRINT_FULLTEXT_CONTACT_EMAIL",
        "PREPRINT_FULLTEXT_OPENALEX_API_KEY",
        "PREPRINT_FULLTEXT_AWS_REGION",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PREPRINT_FULLTEXT_CACHE_DIR", str(tmp_path / "cache"))
    # Clear the settings cache so each test builds fresh from the patched env.
    from preprint_fulltext.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
