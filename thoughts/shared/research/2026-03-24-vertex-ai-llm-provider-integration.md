---
date: 2026-03-24T12:00:00+01:00
researcher: Claude Code
git_commit: f1d0dff7fb4887135195c9949d32868537eb867d
branch: main
repository: AGORA
topic: "Google Vertex AI integration as LLM provider in server-langgraph"
tags: [research, codebase, vertex-ai, llm-providers, server-langgraph, google-cloud]
status: complete
last_updated: 2026-03-24
last_updated_by: Claude Code
---

# Research: Google Vertex AI Models in LANGGRAPH_LLM_PROVIDERS

**Date**: 2026-03-24
**Researcher**: Claude Code
**Git Commit**: f1d0dff
**Branch**: main
**Repository**: AGORA

## Research Question

Can we include Google Vertex AI models (via the OpenAI-compatible endpoint) in `LANGGRAPH_LLM_PROVIDERS` alongside existing API models?

## Summary

**Yes, Vertex AI models can be integrated.** There are two viable approaches, each with trade-offs:

| Approach | Auth Handling | Code Changes | Provider Chain Format |
|----------|--------------|--------------|----------------------|
| **A: `ChatGoogleGenerativeAI` with `vertexai=True`** | Automatic (ADC) | Modify `_make_llm()` to detect Vertex URLs and pass `vertexai=True` | New URL pattern + project config |
| **B: OpenAI-compatible endpoint via `ChatOpenAI`** | Manual token refresh (~1h expiry) | Token refresh wrapper needed | Standard `base_url\|model\|api_key_env` but api_key must be a token |

**Recommended: Approach A** — uses existing `ChatGoogleGenerativeAI` with a `vertexai=True` flag, letting the SDK handle auth/token refresh automatically via Application Default Credentials (ADC).

## Detailed Findings

### Current Architecture

The provider chain is configured via `LANGGRAPH_LLM_PROVIDERS` env var in pipe-separated format:

```
base_url|model|api_key_env;base_url|model|api_key_env
```

The `_make_llm()` function in `agents.py:168` auto-detects Google providers by checking if `"googleapis.com"` appears in the `base_url`, then creates either `ChatGoogleGenerativeAI` or `ChatOpenAI`.

Currently, the Google path uses a **static API key** (`google_api_key=provider.api_key`), which works for Google AI Studio but **not** for Vertex AI (which requires OAuth2 tokens or ADC).

### Approach A: ChatGoogleGenerativeAI with vertexai=True (Recommended)

`langchain-google-genai>=4.0.0` (already a dependency in `pyproject.toml`) supports Vertex AI natively:

```python
ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    vertexai=True,
    project="agora-484112",
    location="europe-west4",  # optional, defaults to us-central1
    temperature=0.7,
    streaming=True,
    max_retries=0,
)
```

When `vertexai=True`, the SDK uses ADC for authentication and handles token refresh internally. No API key is needed.

**Implementation changes needed:**

1. **Add Vertex detection** in `_is_google_provider()` or `_make_llm()` — differentiate between Google AI Studio URLs (`generativelanguage.googleapis.com`) and Vertex AI URLs (`aiplatform.googleapis.com`).

2. **Add settings fields** for Vertex project/location (or parse from URL):
   - `LANGGRAPH_VERTEX_PROJECT` (or extract from base_url)
   - `LANGGRAPH_VERTEX_LOCATION` (default: `europe-west4`)

3. **Modify `_make_llm()`** to pass `vertexai=True` and `project`/`location` when a Vertex URL is detected.

4. **Provider chain entry** could look like:
   ```
   vertex://europe-west4|gemini-2.5-flash|_UNUSED_
   ```
   Or use a sentinel value for `api_key_env` since ADC handles auth.

**Pros:**
- Token refresh is automatic (no expiry issues)
- Already have `langchain-google-genai>=4.0.0` as dependency
- All existing Gemini workarounds (`_filter_extra_tool_args`, `extract_text`) apply
- No new dependencies needed

**Cons:**
- Requires additional config fields (project, location)
- Provider chain format needs slight extension for Vertex-specific params

### Approach B: OpenAI-Compatible Endpoint via ChatOpenAI

Use Google's OpenAI-compatible endpoint as shown in the user's code snippet:

```python
client = OpenAI(
    base_url="https://europe-west4-aiplatform.googleapis.com/v1beta1/projects/agora-484112/locations/europe-west4/endpoints/openai/",
    api_key=credentials.token,  # Expires in ~1 hour
)
```

This would use `ChatOpenAI` (not `ChatGoogleGenerativeAI`), meaning the Vertex URL must NOT match `_is_google_provider()`, or a new detection path is needed.

**Critical problem: Token expiry.** Google OAuth2 tokens expire after ~1 hour. Since `_make_llm()` results are cached in `_agent_llms_cache`, the token would go stale. Solutions:
- Invalidate cache periodically
- Create a custom `ChatOpenAI` subclass that refreshes tokens
- Use a `httpx` auth handler for automatic token injection

**Provider chain entry:**
```
https://europe-west4-aiplatform.googleapis.com/v1beta1/projects/agora-484112/locations/europe-west4/endpoints/openai/|google/gemini-2.5-flash|VERTEX_TOKEN
```

But `VERTEX_TOKEN` can't be a static env var — it needs dynamic refresh.

**Pros:**
- Uses standard `ChatOpenAI` class
- Model naming follows OpenAI convention (`google/gemini-2.5-flash`)
- Fewer Gemini-specific workarounds needed (standard OpenAI schema handling)

**Cons:**
- Token expires every hour — requires refresh mechanism
- Breaks the current `api_key_env` pattern (static env var → dynamic token)
- Requires `google-auth` dependency for token generation
- Model must be prefixed with `google/`

### Authentication for Vertex AI

Vertex AI requires GCP authentication, not API keys. Options:

| Method | Setup | Best For |
|--------|-------|----------|
| `gcloud auth application-default login` | One-time CLI login | Local development |
| Service Account JSON | `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json` | CI/CD, servers |
| Workload Identity | Automatic on GKE/Cloud Run | Production GCP |

The service account needs the **Vertex AI User** role (`roles/aiplatform.user`).

### Available Vertex AI Gemini Models

| Model | ID | Context | Notes |
|-------|----|---------|-------|
| Gemini 2.5 Pro | `gemini-2.5-pro` | 1M | Complex reasoning |
| Gemini 2.5 Flash | `gemini-2.5-flash` | 1M | Balanced speed/quality |
| Gemini 2.5 Flash-Lite | `gemini-2.5-flash-lite` | 1M | Cost-optimized |
| Gemini 3 Flash | `gemini-3-flash` | 1M | Latest multimodal |
| Gemini 3.1 Pro | `gemini-3.1-pro-preview` | 1M | Preview, reasoning-first |

## Code References

- `server-langgraph/src/agora_langgraph/config.py:19-31` — `ProviderConfig` class with `api_key_env` pattern
- `server-langgraph/src/agora_langgraph/config.py:99-114` — `parse_provider_chain()` semicolon/pipe format
- `server-langgraph/src/agora_langgraph/core/agents.py:163-165` — `_is_google_provider()` detection
- `server-langgraph/src/agora_langgraph/core/agents.py:168-194` — `_make_llm()` factory with Google/OpenAI branching
- `server-langgraph/src/agora_langgraph/core/agents.py:197-217` — `get_llms_for_agent()` with caching
- `server-langgraph/src/agora_langgraph/core/agents.py:265-287` — `_filter_extra_tool_args()` Gemini workaround

## Proposed Implementation (Approach A)

### 1. Extend `config.py`

Add Vertex-specific settings:

```python
class Settings(BaseSettings):
    # ... existing fields ...
    vertex_project: str | None = Field(default=None, description="GCP project for Vertex AI")
    vertex_location: str = Field(default="europe-west4", description="Vertex AI region")
```

### 2. Extend `_make_llm()` in `agents.py`

```python
def _is_vertex_provider(base_url: str) -> bool:
    return "aiplatform.googleapis.com" in base_url

def _make_llm(provider: ProviderConfig, temperature: float) -> BaseChatModel:
    if _is_vertex_provider(provider.base_url):
        settings = get_settings()
        return ChatGoogleGenerativeAI(
            model=provider.model,
            temperature=temperature,
            streaming=True,
            vertexai=True,
            project=settings.vertex_project,
            location=settings.vertex_location,
            max_retries=0,
        )
    if _is_google_provider(provider.base_url):
        # existing Google AI Studio path
        ...
```

### 3. Provider chain entry

```bash
LANGGRAPH_LLM_PROVIDERS="https://api.openai.com/v1|gpt-4.1|OPENAI_TOKEN;https://europe-west4-aiplatform.googleapis.com|gemini-2.5-flash|_VERTEX_ADC_;https://generativelanguage.googleapis.com/v1beta/openai/|gemini-3-flash-preview|GOOGLE_TOKEN"
```

Use a sentinel like `_VERTEX_ADC_` for `api_key_env` since Vertex uses ADC, and make `ProviderConfig.api_key` tolerate this sentinel.

## Open Questions

1. **Should Vertex and Google AI Studio coexist?** The current `_is_google_provider` detects both. Need separate detection for Vertex (`aiplatform.googleapis.com`) vs Google AI Studio (`generativelanguage.googleapis.com`).
2. **Provider chain format extension** — should we add a 4th pipe field for provider type (e.g., `vertex`, `openai`, `google`) instead of URL-based detection?
3. **Multiple Vertex projects/regions** — if different models need different projects, should this be per-provider or global?
4. **Existing places that bypass the provider chain** — `parallel_streaming.py` and `session_metadata.py` create standalone `ChatOpenAI` instances. These won't benefit from Vertex integration without additional changes.

## Related Research

- `thoughts/shared/research/2026-03-01-llm-provider-fallback-strategy.md` — Provider fallback chain design
