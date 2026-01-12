"""Configuration management for MCP document ingestion."""
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field
from functools import lru_cache
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Calculate .env path: config.py -> document-ingestion -> mcp-servers -> AGORA
_config_file = Path(__file__)
_env_path = _config_file.parent.parent.parent / ".env"

logger.info(f"Looking for .env at: {_env_path}")
logger.info(f".env exists: {_env_path.exists()}")


class MCPSettings(BaseSettings):
    """MCP Server settings with MCP_ prefix."""

    openai_api_key: SecretStr = Field(description="OpenAI API key for document summarization and embeddings")

    embedding_provider: Literal["openai", "local"] = Field(
        default="openai",
        description="Embedding provider: 'openai' (text-embedding-3-small) or 'local' (sentence-transformers)"
    )

    embedding_model: str = Field(
        default="nomic-ai/nomic-embed-text-v1.5",
        description="Local embedding model from Hugging Face (only used when embedding_provider=local)"
    )

    embedding_device: str | None = Field(
        default=None,
        description="Device for local embedding model (cuda/mps/cpu). Auto-detected if not set."
    )
    
    weaviate_url: str = Field(
        default="http://localhost:8080",
        description="Weaviate database URL"
    )
    
    batch_size: int = Field(
        default=32,
        description="Batch size for embedding"
    )
    
    max_chunk_size: int = Field(
        default=2000,
        description="Maximum chunk size for semantic splitting (in characters)"
    )
    
    chunk_overlap: int = Field(
        default=200,
        description="Overlap between chunks (in characters)"
    )

    input_dir: str = Field(
        default="",
        description="Input directory for PDFs. If empty, uses ../input/SPEC Agent relative to script."
    )

    model_config = SettingsConfigDict(
        env_file=str(_env_path),
        env_prefix="MCP_",
        case_sensitive=False,
        extra="ignore"
    )


@lru_cache
def get_settings() -> MCPSettings:
    """Get cached settings instance."""
    return MCPSettings()

