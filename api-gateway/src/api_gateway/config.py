"""API Gateway configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """API Gateway configuration."""

    # Backend URLs
    openai_backend_url: str = Field(
        default="http://server-openai:8000",
        description="URL for server-openai backend",
    )
    langgraph_backend_url: str = Field(
        default="http://server-langgraph:8000",
        description="URL for server-langgraph backend",
    )
    mock_backend_url: str = Field(
        default="http://mock-server:8000",
        description="URL for mock server backend",
    )
    default_backend: str = Field(
        default="langgraph",
        description="Default backend when no path prefix specified",
    )

    # Authentication
    api_keys: str = Field(
        default="",
        description="Comma-separated API keys (empty = no auth required)",
    )
    require_auth: bool = Field(
        default=False,
        description="Whether to require API key authentication",
    )

    # ElevenLabs
    elevenlabs_api_key: str = Field(
        default="",
        description="ElevenLabs API key for voice features (kept server-side)",
    )
    elevenlabs_voice_id: str = Field(
        default="pNInz6obpgDQGcFmaJgB",
        description="Default ElevenLabs voice ID",
    )

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    model_config = {"env_prefix": "GATEWAY_"}


def get_settings() -> Settings:
    """Get gateway settings singleton."""
    return Settings()
