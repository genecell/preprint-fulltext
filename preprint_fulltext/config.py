"""Runtime configuration.

Backed by ``pydantic-settings``: values come from (highest precedence first)
constructor args, environment variables, a ``.env`` file, then an optional
``preprint-fulltext.toml``. AWS credentials themselves are left to the standard
boto3 chain; only the region and bucket names live here.

Externally-standard names (``CONTACT_EMAIL``, ``OPENALEX_API_KEY``,
``AWS_REGION``) are accepted both bare and with the ``PREPRINT_FULLTEXT_`` prefix.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from . import __version__

# Both buckets confirmed against the openRxiv TDM pages (biorxiv.org/tdm,
# medrxiv.org/tdm, 2026-07-17): requester-pays, us-east-1, $0.09/GB (~6 TB total).
DEFAULT_BIORXIV_BUCKET = "biorxiv-src-monthly"
DEFAULT_MEDRXIV_BUCKET = "medrxiv-src-monthly"


class Settings(BaseSettings):
    """Process-wide settings. Instantiate via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_prefix="PREPRINT_FULLTEXT_",
        env_file=".env",
        env_file_encoding="utf-8",
        toml_file="preprint-fulltext.toml",
        extra="ignore",
        populate_by_name=True,  # accept the field name too, not only validation_alias
    )

    # --- polite-pool identity -------------------------------------------------
    contact_email: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PREPRINT_FULLTEXT_CONTACT_EMAIL", "CONTACT_EMAIL"),
        description="Email for OpenAlex/EPMC polite pools; sent in User-Agent and mailto.",
    )
    openalex_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PREPRINT_FULLTEXT_OPENALEX_API_KEY", "OPENALEX_API_KEY"),
        description="OpenAlex API key (required since 2026-02-13, still free).",
    )

    # --- AWS / S3 -------------------------------------------------------------
    aws_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("PREPRINT_FULLTEXT_AWS_REGION", "AWS_REGION"),
        description="Region for the requester-pays openRxiv buckets (us-east-1).",
    )
    biorxiv_bucket: str = DEFAULT_BIORXIV_BUCKET
    medrxiv_bucket: str = DEFAULT_MEDRXIV_BUCKET

    # --- arXiv ----------------------------------------------------------------
    arxiv_api_base: str = "https://export.arxiv.org/api/query"
    arxiv_html_base: str = "https://arxiv.org/html"
    ar5iv_base: str = "https://ar5iv.labs.arxiv.org/html"

    # --- cache ----------------------------------------------------------------
    cache_dir: Path = Field(
        default=Path.home() / ".cache" / "preprint-fulltext",
        description="Content-addressed cache of fetched .meca/XML.",
    )

    # --- chunking -------------------------------------------------------------
    chunk_tokens: int = Field(default=512, ge=1, description="Max tokens per chunk.")
    chunk_overlap: int = Field(default=64, ge=0, description="Token overlap within a section.")
    tokenizer: str = Field(
        default="tiktoken:cl100k_base",
        description="Tokenizer spec, 'tiktoken:<encoding>'.",
    )
    cross_section: bool = Field(
        default=False, description="Allow a chunk to span section boundaries."
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # env/.env win over the TOML file; TOML wins over hard-coded defaults.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    @property
    def user_agent(self) -> str:
        """User-Agent for polite-pool HTTP requests."""
        base = f"preprint-fulltext/{__version__}"
        return f"{base} (mailto:{self.contact_email})" if self.contact_email else base

    def bucket_for(self, server: str) -> str:
        """Return the S3 bucket name for a server ('biorxiv' | 'medrxiv')."""
        if server == "biorxiv":
            return self.biorxiv_bucket
        if server == "medrxiv":
            return self.medrxiv_bucket
        raise ValueError(f"unknown server: {server!r}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


__all__ = ["Settings", "get_settings", "DEFAULT_BIORXIV_BUCKET", "DEFAULT_MEDRXIV_BUCKET"]
