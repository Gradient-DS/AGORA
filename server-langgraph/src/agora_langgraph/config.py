"""Application configuration - matching server-openai settings for compatibility."""

import logging
import os
from functools import lru_cache

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

env_file = find_dotenv(usecwd=True)
if env_file:
    load_dotenv(env_file)
    logger.info(f"Loaded environment variables from {env_file}")


class ProviderConfig(BaseModel):
    """A single provider-model pair in a fallback chain."""

    base_url: str
    model: str
    api_key_env: str  # Name of env var holding the API key

    @property
    def is_vertex(self) -> bool:
        """Check if this provider uses Google Vertex AI (ADC auth, no API key)."""
        return "aiplatform.googleapis.com" in self.base_url

    @property
    def api_key(self) -> str:
        if self.is_vertex:
            return ""  # Vertex AI uses ADC, not API keys
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise ValueError(f"API key env var '{self.api_key_env}' is not set")
        return key


class Settings(BaseSettings):
    """Application settings for LangGraph orchestrator."""

    openai_api_key: SecretStr = Field(description="OpenAI-compatible API key")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL for OpenAI-compatible API",
    )
    openai_model: str = Field(default="gpt-4o", description="Default OpenAI model")

    # Spoken text generation (can use faster/different model)
    spoken_model: str | None = Field(
        default=None,
        description="Model for spoken text generation (defaults to openai_model if not set)",
    )
    spoken_base_url: str | None = Field(
        default=None,
        description="Base URL for spoken model API (defaults to openai_base_url if not set)",
    )
    spoken_api_key: SecretStr | None = Field(
        default=None,
        description="API key for spoken model (defaults to openai_api_key if not set)",
    )

    # Provider fallback chains
    llm_providers: str = Field(
        default="",
        description="Semicolon-separated fallback chain: base_url|model|api_key_env;...",
    )
    spoken_providers: str = Field(
        default="",
        description="Semicolon-separated spoken fallback chain: base_url|model|api_key_env;...",
    )

    # Google Vertex AI
    vertex_project: str | None = Field(
        default=None,
        description="GCP project ID for Vertex AI (e.g. agora-484112)",
    )
    vertex_location: str = Field(
        default="europe-west4",
        description="GCP region for Vertex AI",
    )

    mcp_servers: str = Field(
        default="",
        description=(
            "Comma-separated MCP servers (name=url,name2=url2). "
            "Optional - leave empty for testing without MCP tools."
        ),
    )

    guardrails_enabled: bool = Field(default=True, description="Enable moderation")

    otel_endpoint: str = Field(
        default="http://localhost:4317", description="OpenTelemetry endpoint"
    )

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    log_level: str = Field(default="INFO", description="Logging level")

    sessions_db_path: str = Field(
        default="sessions.db", description="SQLite database path for sessions"
    )

    reload: bool = Field(default=True, description="Enable uvicorn auto-reload")

    model_config = SettingsConfigDict(
        env_prefix="LANGGRAPH_",
        case_sensitive=False,
        extra="ignore",
    )

    def parse_provider_chain(self, providers_str: str) -> list[ProviderConfig]:
        """Parse semicolon-separated provider chain into ProviderConfig list."""
        if not providers_str or not providers_str.strip():
            return []
        providers = []
        for entry in providers_str.split(";"):
            parts = entry.strip().split("|")
            if len(parts) == 3:
                providers.append(
                    ProviderConfig(
                        base_url=parts[0].strip(),
                        model=parts[1].strip(),
                        api_key_env=parts[2].strip(),
                    )
                )
        return providers

    @property
    def agent_provider_chain(self) -> list[ProviderConfig]:
        """Get agent provider chain. Falls back to single-provider config if not set."""
        chain = self.parse_provider_chain(self.llm_providers)
        if chain:
            return chain
        return [
            ProviderConfig(
                base_url=self.openai_base_url,
                model=self.openai_model,
                api_key_env="LANGGRAPH_OPENAI_API_KEY",
            )
        ]

    @property
    def spoken_provider_chain(self) -> list[ProviderConfig]:
        """Get spoken provider chain. Falls back to spoken config, then agent chain."""
        chain = self.parse_provider_chain(self.spoken_providers)
        if chain:
            return chain
        # Fall back to existing single spoken config if set
        if self.spoken_model:
            api_key_env = (
                "LANGGRAPH_SPOKEN_API_KEY"
                if self.spoken_api_key
                else "LANGGRAPH_OPENAI_API_KEY"
            )
            return [
                ProviderConfig(
                    base_url=self.spoken_base_url or self.openai_base_url,
                    model=self.spoken_model,
                    api_key_env=api_key_env,
                )
            ]
        # Fall back to agent chain
        return self.agent_provider_chain


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]


def parse_mcp_servers(servers_str: str) -> dict[str, str]:
    """Parse MCP servers from comma-separated string.

    Args:
        servers_str: Format "name1=url1,name2=url2" or empty string for no servers

    Returns:
        Dictionary mapping server names to URLs
    """
    if not servers_str or not servers_str.strip():
        return {}

    result = {}
    for pair in servers_str.split(","):
        if "=" in pair:
            name, url = pair.split("=", 1)
            result[name.strip()] = url.strip()
    return result
