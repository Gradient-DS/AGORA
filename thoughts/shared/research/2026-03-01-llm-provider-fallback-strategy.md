---
date: "2026-03-01T10:53:53Z"
researcher: Claude
git_commit: e263eb30d3b6267eb8af00bf84ffcc706113dd60
branch: feat/comments-youri
repository: AGORA
topic: "LLM Provider Fallback Strategy: N Provider-Model Pair Chains"
tags: [research, codebase, llm, fallback, provider, resilience, langchain, openai-agents]
status: complete
last_updated: "2026-03-01"
last_updated_by: Claude
---

# Research: LLM Provider Fallback Strategy

**Date**: 2026-03-01T10:53:53Z
**Researcher**: Claude
**Git Commit**: e263eb30d3b6267eb8af00bf84ffcc706113dd60
**Branch**: feat/comments-youri
**Repository**: AGORA

## Research Question

How to implement a fallback mechanism so that if an LLM request fails, the system automatically tries the next provider-model pair from a configurable list of N pairs.

## Summary

The codebase currently has **zero retry or fallback logic** for LLM calls across all components. Both orchestrators use a single provider-model pair globally. The **server-langgraph** orchestrator is the natural place to implement this, as it already supports configurable `base_url` (enabling any OpenAI-compatible provider) and LangChain provides a built-in `with_fallbacks()` API. The **server-openai** orchestrator is locked to OpenAI and lacks native fallback support.

The recommended approach is a **configuration-driven fallback chain** using LangChain's `RunnableWithFallbacks`, configured via a single environment variable listing N provider-model pairs.

---

## Current State

### LLM Call Sites (All Components)

| Component | File | LLM Client | Model | Fallback? |
|-----------|------|------------|-------|-----------|
| server-langgraph agents | `core/agents.py:53` | `ChatOpenAI` | `settings.openai_model` | No |
| server-langgraph spoken | `core/agents.py:86` | `ChatOpenAI` | `settings.spoken_model` | No |
| server-langgraph title | `adapters/session_metadata.py:387` | `ChatOpenAI` | `gpt-4o-mini` (hardcoded) | No |
| server-openai agents | `core/agent_runner.py:85` | `Agent` (SDK) | `settings.openai_model` | No |
| server-openai spoken | `pipelines/orchestrator.py:295` | `AsyncOpenAI` | `settings.openai_model` | No |
| server-openai title | `adapters/session_metadata.py:395` | `AsyncOpenAI` | `gpt-4o-mini` (hardcoded) | No |
| MCP reporting | `analyzers/conversation_extractor.py:35` | `AsyncOpenAI` | `gpt-4o` (constructor default) | No |
| MCP reporting | `verification/verifier.py:58` | `AsyncOpenAI` | `gpt-4o` (constructor default) | No |
| MCP document-ingestion | `summarizers/openai_summarizer.py:28` | `OpenAI` | `gpt-4o-mini` (hardcoded) | No |

### Current Configuration (server-langgraph)

```python
# config.py - Settings class
openai_api_key: SecretStr        # LANGGRAPH_OPENAI_API_KEY
openai_base_url: str             # LANGGRAPH_OPENAI_BASE_URL (default: https://api.openai.com/v1)
openai_model: str                # LANGGRAPH_OPENAI_MODEL (default: gpt-4o)
spoken_model: str | None         # LANGGRAPH_SPOKEN_MODEL (falls back to openai_model)
spoken_base_url: str | None      # LANGGRAPH_SPOKEN_BASE_URL (falls back to openai_base_url)
spoken_api_key: SecretStr | None # LANGGRAPH_SPOKEN_API_KEY (falls back to openai_api_key)
```

### Current LLM Factory (server-langgraph)

```python
# agents.py - get_llm_for_agent()
_llm_cache: dict[str, ChatOpenAI] = {}

def get_llm_for_agent(agent_id: str) -> ChatOpenAI:
    if agent_id not in _llm_cache:
        settings = get_settings()
        config = get_agent_by_id(agent_id)
        model = config.get("model") or settings.openai_model
        temperature = config.get("temperature", 0.7)
        _llm_cache[agent_id] = ChatOpenAI(
            model=model, temperature=temperature, streaming=True,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
        )
    return _llm_cache[agent_id]
```

---

## Recommended Approach

### 1. Configuration Format

Define provider-model pairs as a semicolon-separated list in a single environment variable. Each entry contains `base_url|model|api_key_env_var`:

```bash
# .env
LANGGRAPH_LLM_PROVIDERS="https://api.openai.com/v1|gpt-4o|OPENAI_API_KEY;https://router.huggingface.co/v1|openai/gpt-oss-120b|HF_TOKEN;https://api.mistral.ai/v1|mistral-large-latest|MISTRAL_API_KEY"

# For spoken channel (separate fallback chain)
LANGGRAPH_SPOKEN_PROVIDERS="https://router.huggingface.co/v1|openai/gpt-oss-120b|HF_TOKEN;https://api.openai.com/v1|gpt-4o-mini|OPENAI_API_KEY"
```

### 2. Settings Model Extension

```python
# config.py additions
from pydantic import Field, model_validator

class ProviderConfig(BaseModel):
    """A single provider-model pair."""
    base_url: str
    model: str
    api_key_env: str  # Name of env var holding the API key

    @property
    def api_key(self) -> str:
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise ValueError(f"API key env var {self.api_key_env} not set")
        return key

class Settings(BaseSettings):
    # ... existing fields ...

    # New: provider fallback chains
    llm_providers: str = Field(
        default="",
        description="Semicolon-separated provider-model pairs: base_url|model|api_key_env;..."
    )
    spoken_providers: str = Field(
        default="",
        description="Semicolon-separated spoken provider-model pairs"
    )

    def get_provider_chain(self, providers_str: str) -> list[ProviderConfig]:
        """Parse provider chain string into list of ProviderConfig."""
        if not providers_str:
            return []
        providers = []
        for entry in providers_str.split(";"):
            parts = entry.strip().split("|")
            if len(parts) == 3:
                providers.append(ProviderConfig(
                    base_url=parts[0], model=parts[1], api_key_env=parts[2]
                ))
        return providers

    @property
    def agent_providers(self) -> list[ProviderConfig]:
        chain = self.get_provider_chain(self.llm_providers)
        if chain:
            return chain
        # Backward compatible: fall back to single-provider config
        return [ProviderConfig(
            base_url=self.openai_base_url,
            model=self.openai_model,
            api_key_env="LANGGRAPH_OPENAI_API_KEY",
        )]
```

### 3. LLM Factory with Fallbacks

The key change is in `agents.py`, modifying `get_llm_for_agent()` to return a `RunnableWithFallbacks` instead of a bare `ChatOpenAI`:

```python
# agents.py
from langchain_core.language_models import BaseChatModel
from openai import RateLimitError, APIConnectionError, APITimeoutError, InternalServerError

TRANSIENT_EXCEPTIONS = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    ConnectionError,
    TimeoutError,
)

_llm_cache: dict[str, BaseChatModel] = {}

def get_llm_for_agent(agent_id: str) -> BaseChatModel:
    """Create an LLM with fallback chain for the given agent."""
    if agent_id not in _llm_cache:
        settings = get_settings()
        config = get_agent_by_id(agent_id)
        temperature = config.get("temperature", 0.7) if config else 0.7
        providers = settings.agent_providers

        def make_llm(provider: ProviderConfig) -> ChatOpenAI:
            return ChatOpenAI(
                model=provider.model,
                temperature=temperature,
                streaming=True,
                api_key=provider.api_key,
                base_url=provider.base_url,
                max_retries=0,  # Disable built-in retries; let fallback handle it
            )

        primary = make_llm(providers[0])

        if len(providers) > 1:
            fallbacks = [make_llm(p) for p in providers[1:]]
            _llm_cache[agent_id] = primary.with_fallbacks(
                fallbacks,
                exceptions_to_handle=TRANSIENT_EXCEPTIONS,
            )
        else:
            _llm_cache[agent_id] = primary

    return _llm_cache[agent_id]
```

### 4. Same Pattern for Spoken Channel

```python
_spoken_llm: BaseChatModel | None = None

def get_llm_for_spoken() -> BaseChatModel:
    global _spoken_llm
    if _spoken_llm is None:
        settings = get_settings()
        providers = settings.get_provider_chain(settings.spoken_providers)
        if not providers:
            providers = settings.agent_providers  # Fall back to agent providers

        temperature = 0.7

        def make_llm(provider: ProviderConfig) -> ChatOpenAI:
            return ChatOpenAI(
                model=provider.model, temperature=temperature,
                streaming=True, api_key=provider.api_key,
                base_url=provider.base_url, max_retries=0,
            )

        primary = make_llm(providers[0])
        if len(providers) > 1:
            fallbacks = [make_llm(p) for p in providers[1:]]
            _spoken_llm = primary.with_fallbacks(
                fallbacks, exceptions_to_handle=TRANSIENT_EXCEPTIONS,
            )
        else:
            _spoken_llm = primary

    return _spoken_llm
```

### 5. Backward Compatibility

The design is fully backward compatible:

- If `LANGGRAPH_LLM_PROVIDERS` is **empty** (default), the system uses the existing `LANGGRAPH_OPENAI_BASE_URL` + `LANGGRAPH_OPENAI_MODEL` + `LANGGRAPH_OPENAI_API_KEY` as a single-provider chain (no fallback, same as current behavior).
- If `LANGGRAPH_LLM_PROVIDERS` is **set**, it takes precedence and enables the fallback chain.
- The existing `LANGGRAPH_OPENAI_*` variables continue to work for the single-provider case.

---

## Architecture Decision: Why LangChain `with_fallbacks()`

### Pros
- **Built-in**: No additional dependencies needed; LangChain is already a core dependency
- **Streaming support**: `RunnableWithFallbacks` supports `astream()`, which the graph already uses
- **Configurable exception handling**: Can scope fallback to transient errors only
- **Composable**: Works with `with_retry()` for per-provider retries before falling through
- **Type-compatible**: Returns `BaseChatModel`, same interface as `ChatOpenAI`

### Alternatives Considered

| Approach | Pros | Cons |
|----------|------|------|
| **LangChain `with_fallbacks()`** | Native, streaming, no deps | LangGraph-only |
| **LiteLLM Router** | Provider-agnostic, load balancing | Extra dependency, separate config system |
| **Custom retry wrapper** | Full control | Reinventing the wheel, error-prone |
| **OpenAI Agents SDK workaround** | Works for server-openai | No native support, complex |

### Recommendation

Use LangChain `with_fallbacks()` for **server-langgraph** (the primary/recommended backend). For **server-openai**, document that it is single-provider only, or defer to a future migration.

---

## Impact on server-openai

The OpenAI Agents SDK has **no built-in fallback mechanism**. Options:

1. **Do nothing**: Document that server-openai is single-provider. Since the project already recommends server-langgraph for production (vendor flexibility), this is acceptable.
2. **LiteLLM integration**: Use the Agents SDK's `LitellmModel` with `fallbacks` in `extra_args`. This adds a dependency on `litellm`.
3. **Custom `ModelProvider`**: Implement a wrapper that catches exceptions and retries with different clients. Complex and fragile.

**Recommendation**: Option 1. Focus fallback implementation on server-langgraph.

---

## Impact on MCP Servers

MCP servers use the `openai` Python SDK directly (not LangChain). Fallback options:

1. **Wrap calls with tenacity**: Add retry logic around individual `client.chat.completions.create()` calls.
2. **Abstract behind a provider factory**: Create a shared utility that accepts N providers and tries them in order.
3. **Defer to orchestrator**: Keep MCP servers simple; let the orchestrator handle resilience.

**Recommendation**: Option 3 for now. MCP server LLM calls are secondary (title generation, report extraction) and can tolerate occasional failures with graceful degradation (which already exists).

---

## Files That Need Changes

### server-langgraph (primary)
- `src/agora_langgraph/config.py` — Add `ProviderConfig` model, `llm_providers` and `spoken_providers` fields
- `src/agora_langgraph/core/agents.py` — Modify `get_llm_for_agent()` and `get_llm_for_spoken()` to build fallback chains
- `.env.example` — Document new `LANGGRAPH_LLM_PROVIDERS` and `LANGGRAPH_SPOKEN_PROVIDERS` variables

### Root config
- `.env.example` — Add documentation for the new provider chain variables
- `docker-compose.yml` — Pass through `LANGGRAPH_LLM_PROVIDERS` to the service

### Optional / Future
- `server-openai/` — No changes (single-provider only)
- `mcp-servers/` — No changes (graceful degradation already exists)

---

## Code References

- `server-langgraph/src/agora_langgraph/config.py:18-71` — Current Settings class
- `server-langgraph/src/agora_langgraph/core/agents.py:39-96` — Current LLM factory functions
- `server-langgraph/src/agora_langgraph/core/graph.py:458-512` — Where LLMs are used for streaming
- `server-langgraph/src/agora_langgraph/core/agents.py:194-195` — Where agent LLM is invoked
- `server-openai/src/agora_openai/config.py:19-45` — server-openai Settings (no base_url)
- `server-openai/src/agora_openai/core/agent_runner.py:79-89` — server-openai agent creation
- `mcp-servers/reporting/server.py:21-28` — MCP reporting LLM setup

## Open Questions

1. **Per-agent fallback chains?** Should different agents be able to have different fallback chains (e.g., regulation-agent uses a stronger model chain than general-agent)?
2. **Monitoring/observability**: Should fallback events be logged/traced to know when fallbacks are being triggered frequently?
3. **Timeout configuration**: Should timeouts be configurable per provider (e.g., 30s for OpenAI, 60s for HuggingFace)?
4. **Cache invalidation**: The current `_llm_cache` is process-lifetime. If env vars change (e.g., key rotation), the cache won't pick up changes until restart. Is this acceptable?
5. **Streaming mid-failure**: LangChain's `with_fallbacks` handles errors at invocation time. If a stream starts successfully but fails mid-stream, the fallback won't retry with a different provider. Is this acceptable?
