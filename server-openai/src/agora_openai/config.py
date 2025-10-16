from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings."""
    
    openai_api_key: SecretStr = Field(description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="Default OpenAI model")
    
    mcp_servers: str = Field(
        default="",
        description="Comma-separated MCP servers (name=url,name2=url2). Optional - leave empty for testing without MCP tools."
    )
    
    guardrails_enabled: bool = Field(default=True, description="Enable moderation")
    
    otel_endpoint: str = Field(
        default="http://localhost:4317",
        description="OpenTelemetry endpoint"
    )
    
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    
    log_level: str = Field(default="INFO", description="Logging level")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        case_sensitive=False,
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

