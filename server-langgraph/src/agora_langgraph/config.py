"""Application configuration - matching server-openai settings for compatibility."""

import logging
from functools import lru_cache

from dotenv import find_dotenv, load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

env_file = find_dotenv(usecwd=True)
if env_file:
    load_dotenv(env_file)
    logger.info(f"Loaded environment variables from {env_file}")


class Settings(BaseSettings):
    """Application settings for LangGraph orchestrator."""

    openai_api_key: SecretStr = Field(description="OpenAI-compatible API key")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL for OpenAI-compatible API",
    )
    openai_model: str = Field(default="gpt-4o", description="Default OpenAI model")

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

    model_config = SettingsConfigDict(
        env_prefix="LANGGRAPH_",
        case_sensitive=False,
        extra="ignore",
    )


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
