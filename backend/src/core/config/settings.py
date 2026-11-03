"""Application settings: config.yaml for non-secret values, .env / env vars for secrets.

Priority (highest first): constructor kwargs > environment > .env file > config.yaml.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_FILE = BACKEND_ROOT / "config.yaml"
DEFAULT_ENV_FILE = BACKEND_ROOT / ".env"


class AppConfig(BaseModel):
    name: str = "Fathom · AI Finance Assistant"
    env: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    # Empty = derived from WEB_PORT for local dev. Set explicitly for a deployed domain.
    frontend_url: str = ""
    cors_origins: list[str] = Field(default_factory=list)


class StubUser(BaseModel):
    sub: str = "stub-user-0001"
    email: str = "dev.user@example.com"
    name: str = "Dev User"


class AuthConfig(BaseModel):
    # google: Google sign-in only.
    # guest:  Google sign-in disabled; each visitor gets their own guest account.
    # stub:   local dev/tests, everyone is one fixed user (refused in production).
    mode: Literal["google", "guest", "stub"] = "google"
    session_cookie_name: str = "fa_session"
    session_ttl_hours: int = Field(default=12, gt=0)
    cookie_secure: bool = False
    google_redirect_uri: str = ""  # empty = <frontend_url><api_prefix>/auth/google/callback
    google_metadata_url: str = "https://accounts.google.com/.well-known/openid-configuration"
    stub_user: StubUser = Field(default_factory=StubUser)


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./var/app.db"
    echo: bool = False


class LoggingConfig(BaseModel):
    level: str = "INFO"
    json_format: bool = Field(default=True, alias="json")


class AlpacaConfig(BaseModel):
    data_base_url: str = "https://data.alpaca.markets"
    feed: Literal["sip", "iex"] = "sip"
    requests_per_minute: int = Field(default=180, gt=0)
    # Read-only assets list for symbol search (MD-09), served from the Trading API host.
    # Empty = picked from the key: paper keys (PK...) use paper-api, live keys use api.
    assets_base_url: str = ""


class AlphaVantageConfig(BaseModel):
    base_url: str = "https://www.alphavantage.co/query"
    requests_per_minute: int = Field(default=5, gt=0)


class RetryConfig(BaseModel):
    attempts: int = Field(default=3, ge=1)
    base_delay_seconds: float = Field(default=0.5, ge=0)
    max_delay_seconds: float = Field(default=4.0, ge=0)


class CircuitBreakerConfig(BaseModel):
    failure_threshold: int = Field(default=5, ge=1)
    reset_seconds: float = Field(default=60, gt=0)


class CacheTtlConfig(BaseModel):
    quote: int = 60
    bars_intraday: int = 3600
    bars_daily: int = 86400
    news: int = 900
    index: int = 900
    reference: int = 86400
    symbols: int = 86400


class IndexConfig(BaseModel):
    id: str
    name: str
    av_symbol: str
    proxy_symbol: str


class SectorEtfConfig(BaseModel):
    sector: str
    symbol: str


class WarmCacheConfig(BaseModel):
    # Off by default: warming calls Alpha Vantage once or twice per sample ticker, which
    # queues behind its rate limit and can use up a small daily quota on every restart.
    on_startup: bool = False


class MarketConfig(BaseModel):
    http_timeout_seconds: float = 10
    alpaca: AlpacaConfig = Field(default_factory=AlpacaConfig)
    alpha_vantage: AlphaVantageConfig = Field(default_factory=AlphaVantageConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    cache_ttl_seconds: CacheTtlConfig = Field(default_factory=CacheTtlConfig)
    indices: list[IndexConfig] = Field(default_factory=list)
    benchmark_symbol: str = "SPY"
    sector_etfs: list[SectorEtfConfig] = Field(default_factory=list)
    movers_universe: list[str] = Field(default_factory=list)
    warm_cache: WarmCacheConfig = Field(default_factory=WarmCacheConfig)


class EmbeddingModelConfig(BaseModel):
    """One embedding model and the Chroma collection that holds its vectors (KB-04).

    Vectors from different models are not comparable, so each model gets its own collection.
    """

    provider: Literal["gemini", "openai"]
    model: str
    collection: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,510}[a-zA-Z0-9]$")
    # Texts embedded per minute during ingestion (each text counts as one request on the
    # Gemini free tier). None = no pacing.
    requests_per_minute: int | None = Field(default=None, gt=0)


class RetrievalConfig(BaseModel):
    """Hybrid retrieval knobs (KB-05, KB-06)."""

    vector_k: int = Field(default=20, ge=1)
    keyword_k: int = Field(default=20, ge=1)
    rrf_k: int = Field(default=60, ge=1)
    rerank_candidates: int = Field(default=20, ge=1)
    top_n: int = Field(default=5, ge=1)
    level_boost: float = Field(default=0.05, ge=0, le=1)


class RerankerConfig(BaseModel):
    # cross_encoder: local sentence-transformers model, loaded once (falls back to lexical
    # if the package or weights are missing). lexical: query-term overlap, no model.
    kind: Literal["cross_encoder", "lexical"] = "cross_encoder"
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # Relevance threshold per reranker; scores are 0..1. Below it a chunk is dropped.
    cross_encoder_min_score: float = Field(default=0.02, ge=0, le=1)
    lexical_min_score: float = Field(default=0.5, ge=0, le=1)


class KnowledgeBaseConfig(BaseModel):
    source_dir: str = "data/kb"
    index_dir: str = "var/index"
    vector_dir: str = "var/chroma"
    chunk_tokens: int = Field(default=500, gt=50)
    chunk_overlap: float = Field(default=0.15, ge=0, lt=0.5)
    categories: list[str] = Field(default_factory=list)
    levels: list[str] = Field(default_factory=lambda: ["beginner", "intermediate", "advanced"])
    # First entry is the primary; the rest are query-time fallbacks, in order.
    embeddings: list[EmbeddingModelConfig] = Field(default_factory=list)
    embed_batch_size: int = Field(default=64, ge=1)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)


class LlmModelConfig(BaseModel):
    provider: Literal["gemini", "anthropic", "openai"]
    model: str
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_output_tokens: int = Field(default=1200, gt=0)
    timeout_seconds: float = Field(default=30, gt=0)


class LlmConfig(BaseModel):
    """Chat models in fallback order (D1, NF-R02). Models without an API key are skipped."""

    models: list[LlmModelConfig] = Field(default_factory=list)


class WorkflowConfig(BaseModel):
    """LangGraph workflow knobs (OR-01 to OR-07)."""

    clarify_below_confidence: float = Field(default=0.6, ge=0, le=1)
    agent_timeout_seconds: float = Field(default=20, gt=0)
    agent_retries: int = Field(default=1, ge=0)
    max_tool_rounds: int = Field(default=3, ge=0)
    max_agents_per_turn: int = Field(default=3, ge=1)
    history_messages: int = Field(default=8, ge=0)
    max_focus_tickers: int = Field(default=3, ge=1)
    max_message_chars: int = Field(default=4000, ge=100)
    # A portfolio screenshot attached to a chat message (CH-09).
    max_image_bytes: int = Field(default=5_000_000, ge=100_000)
    max_screenshot_holdings: int = Field(default=25, ge=1)
    # Conversation memory (OR-05): a SQLite file for LangGraph checkpoints, kept apart from
    # the app DB so the async checkpointer and the sync ORM never contend for one write
    # lock. Empty = in memory (lost on restart).
    checkpoint_path: str = ""


class SeedConfig(BaseModel):
    dir: str = "data/seed"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(DEFAULT_ENV_FILE),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )

    app: AppConfig = Field(default_factory=AppConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    market: MarketConfig = Field(default_factory=MarketConfig)
    kb: KnowledgeBaseConfig = Field(default_factory=KnowledgeBaseConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    seed: SeedConfig = Field(default_factory=SeedConfig)

    # Secrets: environment / .env only, never in config.yaml, never sent to the browser.
    session_secret: SecretStr = SecretStr("change-me")
    google_client_id: SecretStr = SecretStr("")
    google_client_secret: SecretStr = SecretStr("")
    alpaca_api_key_id: SecretStr = SecretStr("")
    alpaca_api_secret_key: SecretStr = SecretStr("")
    alpha_vantage_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    langsmith_api_key: SecretStr = SecretStr("")
    # LangSmith tracing (optional): LANGSMITH_TRACING=true plus the key above. EU accounts
    # also set LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com.
    langsmith_tracing: bool = False
    langsmith_project: str = "fathom"
    langsmith_endpoint: str = ""

    # Local ports (WEB_PORT / API_PORT in .env). The web app's URL, CORS origin and Google
    # redirect URI are derived from WEB_PORT unless set explicitly.
    web_port: int = Field(default=5173, ge=1, le=65535)
    api_port: int = Field(default=8000, ge=1, le=65535)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        config_file = Path(os.environ.get("APP_CONFIG_FILE", str(DEFAULT_CONFIG_FILE)))
        yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=config_file)
        return init_settings, env_settings, dotenv_settings, yaml_source

    @model_validator(mode="after")
    def _derive_local_urls(self) -> Settings:
        if not self.app.frontend_url:
            self.app.frontend_url = f"http://localhost:{self.web_port}"
        if not self.app.cors_origins:
            self.app.cors_origins = [self.app.frontend_url]
        if not self.auth.google_redirect_uri:
            self.auth.google_redirect_uri = (
                f"{self.app.frontend_url}{self.app.api_prefix}/auth/google/callback"
            )
        return self

    @model_validator(mode="after")
    def _guard_production(self) -> Settings:
        if self.app.env == "production":
            if self.auth.mode == "stub":
                raise ValueError("AUTH mode 'stub' is not allowed when app.env=production")
            if self.session_secret.get_secret_value() in ("", "change-me"):
                raise ValueError("SESSION_SECRET must be set in production")
        return self

    # --- Convenience -------------------------------------------------------

    @property
    def google_configured(self) -> bool:
        return bool(
            self.google_client_id.get_secret_value()
            and self.google_client_secret.get_secret_value()
        )

    @property
    def alpaca_configured(self) -> bool:
        return bool(
            self.alpaca_api_key_id.get_secret_value()
            and self.alpaca_api_secret_key.get_secret_value()
        )

    @property
    def alpha_vantage_configured(self) -> bool:
        return bool(self.alpha_vantage_api_key.get_secret_value())

    def provider_api_key(self, provider: str) -> str:
        """API key for an LLM or embedding provider ("" when not configured)."""
        keys = {
            "gemini": self.gemini_api_key,
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
        }
        secret = keys.get(provider)
        return secret.get_secret_value() if secret else ""


def resolve_path(path: str | Path) -> Path:
    """Resolve a config path relative to the backend root."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else BACKEND_ROOT / candidate


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
