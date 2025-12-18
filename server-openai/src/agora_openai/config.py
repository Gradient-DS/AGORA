from functools import lru_cache
import logging

from dotenv import load_dotenv, find_dotenv
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Configure logging for config loading
logger = logging.getLogger(__name__)

# Load environment variables from .env file if present
# find_dotenv searches for .env file starting from current directory and going up
env_file = find_dotenv(usecwd=True)
if env_file:
    load_dotenv(env_file)
    logger.info(f"Loaded environment variables from {env_file}")


class Settings(BaseSettings):
    """Application settings for OpenAI Agents SDK orchestrator."""

    openai_api_key: SecretStr = Field(description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="Default OpenAI model")

    mcp_servers: str = Field(
        default="",
        description="Comma-separated MCP servers (name=url,name2=url2). Optional - leave empty for testing without MCP tools.",
    )

    guardrails_enabled: bool = Field(default=True, description="Enable moderation")

    otel_endpoint: str = Field(
        default="http://localhost:4317", description="OpenTelemetry endpoint"
    )

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    log_level: str = Field(default="INFO", description="Logging level")

    model_config = SettingsConfigDict(
        env_prefix="OPENAI_AGENTS_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


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
