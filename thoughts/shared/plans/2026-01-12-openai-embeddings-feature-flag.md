# OpenAI Embeddings Feature Flag Implementation Plan

## Overview

Add feature flag support to switch between local (sentence-transformers) and OpenAI embeddings in the MCP servers. This enables smaller Docker images (~800MB savings) and reduces VM memory requirements for GCP deployment while maintaining backwards compatibility with local embeddings.

## Current State Analysis

**Embeddings Implementation:**
- `mcp-servers/document-ingestion/embeddings/embedder.py` uses `sentence-transformers` with `nomic-ai/nomic-embed-text-v1.5`
- 768-dimensional vectors stored in Weaviate
- Used by both `regulation-analysis` server (query-time) and `document-ingestion` pipeline (ingestion-time)

**Configuration:**
- `mcp-servers/document-ingestion/config.py` uses `MCP_` prefix
- `MCP_OPENAI_API_KEY` already required for document summarization
- Embedding model/device configurable but provider not switchable

**Dependencies (regulation-analysis):**
- `torch>=2.0.0` - ~500MB
- `transformers>=4.40.0` - ~200MB
- `sentence-transformers>=2.2.0` - ~50MB
- `einops` - ~5MB

**Key Files:**
- `mcp-servers/document-ingestion/embeddings/embedder.py:10-106` - Current Embedder class
- `mcp-servers/document-ingestion/config.py:18-58` - MCPSettings class
- `mcp-servers/regulation-analysis/server.py:29-47` - Server initialization
- `mcp-servers/regulation-analysis/Dockerfile:1-32` - Docker build
- `mcp-servers/regulation-analysis/requirements.txt:1-13` - Dependencies

## Desired End State

1. **Feature Flag**: `MCP_EMBEDDING_PROVIDER` environment variable controls embedding backend
   - `openai` (default): Uses OpenAI `text-embedding-3-small` with 768 dimensions
   - `local`: Uses sentence-transformers with nomic-embed (current behavior)

2. **Unified API Key**: `MCP_OPENAI_API_KEY` used for all OpenAI operations (summarization + embeddings)

3. **Docker Optimization**: Build arg `EMBEDDING_PROVIDER` conditionally installs PyTorch dependencies
   - `--build-arg EMBEDDING_PROVIDER=openai` - Slim image (~300MB)
   - `--build-arg EMBEDDING_PROVIDER=local` - Full image (~1.1GB)

4. **Verification**:
   - Both providers produce 768-dimensional vectors
   - Existing Weaviate data remains compatible
   - Search quality comparable between providers

## What We're NOT Doing

- Re-ingesting existing documents (768 dimensions maintained)
- Changing Weaviate schema
- Adding support for other embedding providers (only local and openai)
- Modifying the inspection-history or reporting MCP servers

## Implementation Approach

Use the factory pattern to abstract embedding providers behind a common interface. The config determines which provider is instantiated at startup. Docker build args control dependency installation.

---

## Phase 1: Config and Embedder Interface

### Overview
Add embedding provider configuration and create a provider-agnostic interface.

### Changes Required:

#### 1. Update Configuration
**File**: `mcp-servers/document-ingestion/config.py`
**Changes**: Add embedding provider setting

```python
from typing import Literal

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

    # ... rest unchanged
```

#### 2. Create Embedder Factory
**File**: `mcp-servers/document-ingestion/embeddings/embedder.py`
**Changes**: Refactor to support multiple providers

```python
import logging
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Protocol

logger = logging.getLogger(__name__)


class EmbedderProtocol(Protocol):
    """Protocol for embedding providers."""

    dimension: int

    def embed_chunks(self, chunks: List[Dict[str, Any]], task: str = "search_document") -> List[Dict[str, Any]]:
        ...

    def embed_query(self, query: str) -> List[float]:
        ...


class OpenAIEmbedder:
    """OpenAI embeddings using text-embedding-3-small."""

    def __init__(self, api_key: str, dimension: int = 768):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = "text-embedding-3-small"
        self.dimension = dimension

        logger.info(f"Initialized OpenAI embedder with {self.model} (dimension: {self.dimension})")

    def embed_chunks(self, chunks: List[Dict[str, Any]], task: str = "search_document") -> List[Dict[str, Any]]:
        """Embed multiple chunks."""
        logger.info(f"Embedding {len(chunks)} chunks with OpenAI")

        texts = [chunk['content'] for chunk in chunks]
        embeddings = self._get_embeddings(texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk['embedding'] = embedding

        return chunks

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query."""
        logger.info(f"Embedding query: {query[:50]}...")
        return self._get_embeddings([query])[0]

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings from OpenAI API."""
        # Process in batches of 100 (OpenAI limit is 2048)
        batch_size = 100
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimension
            )

            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

        logger.info(f"Successfully embedded {len(all_embeddings)} texts with OpenAI")
        return all_embeddings


class LocalEmbedder:
    """Local embeddings using sentence-transformers."""

    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1.5", device: str = None):
        import torch
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name

        # Dimension varies by model
        if "nomic" in model_name:
            self.dimension = 768
        elif "jina" in model_name:
            self.dimension = 1024
        else:
            self.dimension = 768  # default

        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        else:
            self.device = device

        logger.info(f"Loading local embedding model: {self.model_name} on device: {self.device}")

        self.model = SentenceTransformer(
            self.model_name,
            device=self.device,
            trust_remote_code=True
        )
        logger.info(f"Model loaded successfully (dimension: {self.dimension})")

    def embed_chunks(self, chunks: List[Dict[str, Any]], task: str = "search_document") -> List[Dict[str, Any]]:
        """Embed multiple chunks."""
        logger.info(f"Embedding {len(chunks)} chunks locally")

        texts = [chunk['content'] for chunk in chunks]

        max_length = 8192 if "nomic" in self.model_name else 8192
        truncated_count = 0
        for i, text in enumerate(texts):
            if len(text) > max_length:
                texts[i] = text[:max_length]
                truncated_count += 1

        if truncated_count > 0:
            logger.warning(f"Truncated {truncated_count} chunks that exceeded {max_length} characters")

        embeddings = self._get_embeddings(texts, task)

        for chunk, embedding in zip(chunks, embeddings):
            chunk['embedding'] = embedding

        return chunks

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query."""
        logger.info(f"Embedding query: {query[:50]}...")
        return self._get_embeddings([query], task="search_query")[0]

    def _get_embeddings(self, texts: List[str], task: str) -> List[List[float]]:
        """Get embeddings from local model."""
        if "nomic" in self.model_name:
            if task == "search_query":
                texts = [f"search_query: {text}" for text in texts]
            else:
                texts = [f"search_document: {text}" for text in texts]

        embeddings = self.model.encode(
            texts,
            batch_size=32,
            show_progress_bar=len(texts) > 100,
            convert_to_numpy=True,
            normalize_embeddings=True,
            truncate_dim=2048
        )

        embeddings_list = embeddings.tolist()
        logger.info(f"Successfully embedded {len(embeddings_list)} texts locally")
        return embeddings_list


def create_embedder(
    provider: str = "openai",
    api_key: str = None,
    model_name: str = "nomic-ai/nomic-embed-text-v1.5",
    device: str = None,
) -> EmbedderProtocol:
    """Factory function to create the appropriate embedder.

    Args:
        provider: 'openai' or 'local'
        api_key: OpenAI API key (required for 'openai' provider)
        model_name: Model name for local embedder
        device: Device for local embedder (auto-detected if None)

    Returns:
        Embedder instance
    """
    if provider == "openai":
        if not api_key:
            raise ValueError("OpenAI API key required for openai embedding provider")
        return OpenAIEmbedder(api_key=api_key, dimension=768)
    elif provider == "local":
        return LocalEmbedder(model_name=model_name, device=device)
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


# Backwards compatibility alias
class Embedder(LocalEmbedder):
    """Backwards compatible alias for LocalEmbedder."""
    pass
```

### Success Criteria:

#### Automated Verification:
- [x] Python syntax valid: `python -m py_compile mcp-servers/document-ingestion/config.py`
- [x] Python syntax valid: `python -m py_compile mcp-servers/document-ingestion/embeddings/embedder.py`
- [ ] Config loads correctly: `cd mcp-servers/document-ingestion && python -c "from config import get_settings; print(get_settings().embedding_provider)"` (requires dependencies)

#### Manual Verification:
- [ ] Verify OpenAI embedder returns 768-dim vectors
- [ ] Verify local embedder still works with existing model

**Implementation Note**: After completing this phase and all automated verification passes, pause here for confirmation before proceeding.

---

## Phase 2: Update Server Initialization

### Overview
Update regulation-analysis server to use the embedder factory.

### Changes Required:

#### 1. Update Server Initialization
**File**: `mcp-servers/regulation-analysis/server.py`
**Changes**: Use factory function with config

Replace lines 29-47 with:

```python
weaviate_client = None
embedder = None

if WEAVIATE_AVAILABLE:
    try:
        settings = get_settings()
        logger.info(f"Loaded configuration with MCP_ prefix (embedding_provider={settings.embedding_provider})")

        weaviate_client = WeaviateClient(settings.weaviate_url)

        # Use factory function to create appropriate embedder
        from embeddings.embedder import create_embedder

        embedder = create_embedder(
            provider=settings.embedding_provider,
            api_key=settings.openai_api_key.get_secret_value() if settings.embedding_provider == "openai" else None,
            model_name=settings.embedding_model,
            device=settings.embedding_device,
        )

        if weaviate_client.connect():
            logger.info("Successfully connected to Weaviate")
        else:
            logger.warning("Failed to connect to Weaviate - will use fallback mode")
            weaviate_client = None
    except Exception as e:
        logger.error(f"Error loading configuration or connecting to Weaviate: {e}")
        weaviate_client = None
```

#### 2. Update Ingestion Pipeline
**File**: `mcp-servers/document-ingestion/ingest.py`
**Changes**: Use factory function

Replace lines 64-67 with:

```python
    from embeddings.embedder import create_embedder

    embedder = create_embedder(
        provider=settings.embedding_provider,
        api_key=settings.openai_api_key.get_secret_value() if settings.embedding_provider == "openai" else None,
        model_name=settings.embedding_model,
        device=settings.embedding_device,
    )
```

### Success Criteria:

#### Automated Verification:
- [x] Python syntax valid: `python -m py_compile mcp-servers/regulation-analysis/server.py`
- [x] Python syntax valid: `python -m py_compile mcp-servers/document-ingestion/ingest.py`

#### Manual Verification:
- [ ] Server starts with `MCP_EMBEDDING_PROVIDER=openai`
- [ ] Server starts with `MCP_EMBEDDING_PROVIDER=local`
- [ ] Search works with OpenAI embeddings against existing Weaviate data

**Implementation Note**: After completing this phase and all automated verification passes, pause here for confirmation before proceeding.

---

## Phase 3: Docker Build Optimization

### Overview
Add build args to conditionally install PyTorch dependencies.

### Changes Required:

#### 1. Split Requirements File
**File**: `mcp-servers/regulation-analysis/requirements.txt`
**Changes**: Keep only common dependencies

```
fastapi
fastmcp
starlette
uvicorn
httpx
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv
weaviate-client>=4.0.0
openai>=1.0.0
```

#### 2. Create Local Embeddings Requirements
**File**: `mcp-servers/regulation-analysis/requirements-local.txt` (new)
**Contents**:

```
torch>=2.0.0
transformers>=4.40.0
sentence-transformers>=2.2.0
einops
```

#### 3. Update Dockerfile with Build Arg
**File**: `mcp-servers/regulation-analysis/Dockerfile`
**Changes**: Conditional PyTorch installation

```dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Build argument for embedding provider
ARG EMBEDDING_PROVIDER=openai
ENV MCP_EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER}

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install base requirements
COPY regulation-analysis/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Conditionally install local embedding dependencies
COPY regulation-analysis/requirements-local.txt .
RUN if [ "$EMBEDDING_PROVIDER" = "local" ]; then \
        pip install --no-cache-dir -r requirements-local.txt; \
    fi

COPY regulation-analysis/server.py .
COPY document-ingestion/config.py ./config.py
COPY document-ingestion/database ./database
COPY document-ingestion/embeddings ./embeddings

RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

CMD ["python", "server.py"]
```

#### 4. Update Document Ingestion Requirements
**File**: `mcp-servers/document-ingestion/requirements.txt`
**Changes**: Add openai, make torch optional

```
docling>=2.0.0
weaviate-client>=4.0.0
openai>=1.0.0
python-dotenv>=1.0.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
pdf2image>=1.16.0
pillow>=10.0.0

# Local embeddings (optional, install with: pip install -r requirements-local.txt)
# torch>=2.0.0
# transformers>=4.40.0
# einops>=0.7.0
# sentence-transformers>=2.2.0
```

#### 5. Create Document Ingestion Local Requirements
**File**: `mcp-servers/document-ingestion/requirements-local.txt` (new)
**Contents**:

```
torch>=2.0.0
transformers>=4.40.0
einops>=0.7.0
sentence-transformers>=2.2.0
```

### Success Criteria:

#### Automated Verification:
- [ ] OpenAI build works: `docker build --build-arg EMBEDDING_PROVIDER=openai -t regulation-analysis:openai -f mcp-servers/regulation-analysis/Dockerfile mcp-servers/`
- [ ] Local build works: `docker build --build-arg EMBEDDING_PROVIDER=local -t regulation-analysis:local -f mcp-servers/regulation-analysis/Dockerfile mcp-servers/`
- [ ] OpenAI image is smaller: `docker images | grep regulation-analysis`

#### Manual Verification:
- [ ] OpenAI container starts and responds to `/health`
- [ ] Local container starts and responds to `/health`
- [ ] Search works in OpenAI container

**Implementation Note**: After completing this phase and all automated verification passes, pause here for confirmation before proceeding.

---

## Phase 4: Documentation and Testing

### Overview
Update documentation and add basic tests.

### Changes Required:

#### 1. Update MCP Servers README
**File**: `mcp-servers/README.md`
**Changes**: Document embedding provider configuration

Add section:

```markdown
## Embedding Configuration

The regulation-analysis server supports two embedding providers:

### OpenAI Embeddings (Default)

Uses `text-embedding-3-small` with 768 dimensions. Requires `MCP_OPENAI_API_KEY`.

```bash
MCP_EMBEDDING_PROVIDER=openai
MCP_OPENAI_API_KEY=sk-...
```

### Local Embeddings

Uses `nomic-ai/nomic-embed-text-v1.5` via sentence-transformers. Requires additional dependencies (~800MB).

```bash
MCP_EMBEDDING_PROVIDER=local
MCP_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5  # optional, this is default
MCP_EMBEDDING_DEVICE=cpu  # optional, auto-detected
```

### Docker Builds

For smaller images when using OpenAI embeddings:

```bash
# OpenAI embeddings (~300MB image)
docker build --build-arg EMBEDDING_PROVIDER=openai -t regulation-analysis .

# Local embeddings (~1.1GB image)
docker build --build-arg EMBEDDING_PROVIDER=local -t regulation-analysis .
```

### Re-ingesting Documents

When switching providers, documents should be re-ingested to ensure query/document embedding consistency:

```bash
cd mcp-servers/document-ingestion
MCP_EMBEDDING_PROVIDER=openai MCP_OPENAI_API_KEY=sk-... python ingest.py
```
```

#### 2. Update Root .env.example
**File**: `.env.example`
**Changes**: Add embedding provider documentation

```bash
# MCP Servers - Shared OpenAI API Key
MCP_OPENAI_API_KEY=sk-...

# Embedding Provider: 'openai' (default) or 'local'
MCP_EMBEDDING_PROVIDER=openai

# Local embedding config (only used when MCP_EMBEDDING_PROVIDER=local)
# MCP_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
# MCP_EMBEDDING_DEVICE=cpu
```

### Success Criteria:

#### Automated Verification:
- [x] README exists and is valid markdown

#### Manual Verification:
- [ ] Documentation is clear and complete
- [ ] Example commands work as documented

---

## Testing Strategy

### Unit Tests:
- Test `create_embedder()` factory returns correct type for each provider
- Test `OpenAIEmbedder` produces 768-dim vectors
- Test `LocalEmbedder` produces 768-dim vectors
- Test error handling when API key missing

### Integration Tests:
- Test full search flow with OpenAI embeddings
- Test ingestion pipeline with OpenAI embeddings
- Test Docker container health checks

### Manual Testing Steps:
1. Set `MCP_EMBEDDING_PROVIDER=openai` and start regulation-analysis server
2. Query Weaviate with existing data to verify search works
3. Run ingestion with a test document
4. Verify embedded document is searchable
5. Switch to `MCP_EMBEDDING_PROVIDER=local` and repeat

## Performance Considerations

- **OpenAI API latency**: ~100-200ms per embedding call vs ~50ms local
- **Batching**: OpenAI supports up to 2048 texts per call, we batch at 100 for safety
- **Cost**: ~$0.02/1M tokens for text-embedding-3-small (negligible for typical usage)
- **Memory**: OpenAI mode uses ~50MB vs ~800MB for local mode

## Migration Notes

**Switching from Local to OpenAI:**
1. No data migration needed if using 768 dimensions
2. For best results, re-ingest documents with OpenAI embeddings
3. Update `MCP_EMBEDDING_PROVIDER=openai` in environment

**Switching from OpenAI to Local:**
1. Install local dependencies: `pip install -r requirements-local.txt`
2. Re-ingest documents with local embeddings for consistency
3. Update `MCP_EMBEDDING_PROVIDER=local` in environment

## References

- Research document: `thoughts/shared/research/2026-01-12-gcp-backend-deployment-architecture.md`
- OpenAI Embeddings API: https://platform.openai.com/docs/guides/embeddings
- Sentence Transformers: https://www.sbert.net/
