---
date: 2025-01-15T12:00:00+01:00
researcher: Claude
git_commit: caf9d75b63c0e1f9de7ae56054b0fa84538d24cd
branch: main
repository: AGORA
topic: "Server-LangGraph Agent Flow and Dual Generation Pattern"
tags: [research, codebase, server-langgraph, agents, llm, dual-generation, tts, spoken-text]
status: complete
last_updated: 2025-01-15
last_updated_by: Claude
---

# Research: Server-LangGraph Agent Flow and Dual Generation Pattern

**Date**: 2025-01-15T12:00:00+01:00
**Researcher**: Claude
**Git Commit**: caf9d75b63c0e1f9de7ae56054b0fa84538d24cd
**Branch**: main
**Repository**: AGORA

## Research Question

How does the server-langgraph agent flow work, what exactly is sent to the LLM, and how does the dual generation pattern work for written vs spoken text for the frontend?

## Summary

The server-langgraph orchestrator implements a **multi-agent handoff pattern** using LangGraph's `StateGraph`. Four agents (`general-agent`, `regulation-agent`, `history-agent`, `reporting-agent`) are connected via transfer tools that route conversations to specialist agents. Each agent receives a **system message** (agent instructions) prepended to the conversation history when invoking the LLM.

The system implements a **dual-channel streaming pattern** that generates two separate text outputs simultaneously:
1. **Written text**: Full detailed response displayed in the UI
2. **Spoken text**: TTS-optimized 2-3 sentence summary for audio playback

Two modes control generation: "summarize" (two parallel LLM calls) and "dictate" (single LLM call duplicated to both channels).

## Detailed Findings

### 1. Agent Definitions and State

**Location**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`

Four agents are defined in `AGENT_CONFIGS`:

| Agent ID | Purpose | Temperature | MCP Server | Handoffs |
|----------|---------|-------------|------------|----------|
| `general-agent` | Triage & coordination | 0.7 | None | history, regulation, reporting |
| `regulation-agent` | Regulatory compliance | 0.3 | `regulation` | reporting, general |
| `history-agent` | Company/inspection history | 0.2 | `history` | regulation, reporting, general |
| `reporting-agent` | HAP report generation | 0.3 | `reporting` | general |

**State Schema** (`state.py:11-21`):
```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # Conversation history
    session_id: str                                        # Thread identifier
    current_agent: str                                     # Active agent
    pending_approval: dict[str, Any] | None               # HITL approval data
    metadata: dict[str, Any]                              # Client context
```

### 2. Graph Structure and Handoff Flow

**Location**: `server-langgraph/src/agora_langgraph/core/graph.py`

```
                    START
                      │
                      ▼
              ┌───────────────┐
              │ general-agent │◄─────────────────┐
              └───────┬───────┘                  │
                      │                          │
         ┌────────────┼────────────┐             │
         ▼            ▼            ▼             │
      [tools]      [tools]      [tools]          │
         │            │            │             │
         ▼            ▼            ▼             │
┌──────────────┐ ┌────────────┐ ┌──────────────┐ │
│history-agent │ │reg-agent   │ │report-agent  │ │
└──────┬───────┘ └─────┬──────┘ └──────┬───────┘ │
       │               │               │         │
       └───────────────┴───────────────┴─────────┘
                       │
                       ▼
                      END
```

**Handoff Mechanism**:
1. Agent calls a transfer tool (e.g., `transfer_to_regulation`)
2. `route_from_agent()` routes to `ToolNode` for execution
3. `route_after_tools()` detects handoff via `detect_handoff_target()`
4. Graph transitions to target agent with full conversation context

**Transfer Tools** (`tools.py:13-68`):
- `transfer_to_history()` - Routes to history-agent
- `transfer_to_regulation()` - Routes to regulation-agent
- `transfer_to_reporting()` - Routes to reporting-agent
- `transfer_to_general()` - Returns to general-agent

### 3. What is Sent to the LLM

**Location**: `server-langgraph/src/agora_langgraph/core/agents.py:56-104`

Each agent node executes `_run_agent_node()` which constructs the LLM input:

```python
# Line 85-86: Message construction
system_message = {"role": "system", "content": config["instructions"]}
messages_with_system = [system_message] + list(state["messages"])

# Line 89: LLM invocation
response = await llm_with_tools.ainvoke(messages_with_system)
```

**Final Message Structure Sent to LLM**:
```json
[
    {"role": "system", "content": "<agent instructions>"},
    {"role": "user", "content": "user message 1"},
    {"role": "assistant", "content": "response 1", "tool_calls": [...]},
    {"role": "tool", "content": "tool result", "tool_call_id": "..."},
    {"role": "user", "content": "user message 2"},
    ...
]
```

**Tool Binding**:
- Tools are bound via `llm.bind_tools(tools)` (line 81)
- LangChain converts tools to OpenAI function calling format
- General-agent gets transfer tools; specialists get MCP tools + `transfer_to_general`

### 4. Dual Generation Pattern (Written vs Spoken)

**Location**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:309-564`

The system generates **two parallel text streams** for every assistant response:

#### 4.1 Two Generation Modes

**User Preference** (`orchestrator.py:336-346`):
```python
spoken_mode = "summarize"  # default
if self.user_manager:
    user = await self.user_manager.get_user(user_id)
    prefs = user.get("preferences", {})
    spoken_mode = prefs.get("spoken_text_type", "summarize")
```

| Mode | Behavior | LLM Calls | Use Case |
|------|----------|-----------|----------|
| `summarize` | Two parallel LLM calls with different prompts | 2 | Concise TTS output |
| `dictate` | Single LLM call, content duplicated to both channels | 1 | Full text read aloud |

#### 4.2 Channel Initialization

**On First Content Chunk** (`orchestrator.py:415-431`):
```python
if not message_started:
    # Start BOTH channels simultaneously
    await protocol_handler.send_text_message_start(message_id, "assistant")
    await protocol_handler.send_spoken_text_start(message_id, "assistant")
    message_started = True
    spoken_message_started = True

    # In 'summarize' mode: start parallel LLM call
    if spoken_mode == "summarize":
        spoken_task = asyncio.create_task(generate_spoken_parallel(current_agent_id))
        asyncio.create_task(stream_spoken_to_frontend())
```

#### 4.3 Parallel Spoken Generation

**Function** (`orchestrator.py:352-388`):
```python
async def generate_spoken_parallel(agent_id: str) -> None:
    spoken_prompt = get_spoken_prompt(agent_id)  # TTS-optimized prompt
    llm = get_llm_for_agent(agent_id)

    # Same conversation context, different system prompt
    messages = list(input_state.get("messages", []))
    spoken_messages = [SystemMessage(content=spoken_prompt)] + messages

    async for chunk in llm.astream(spoken_messages):
        if hasattr(chunk, "content") and chunk.content:
            await spoken_queue.put(str(chunk.content))
```

#### 4.4 Spoken Prompts

**Location**: `agent_definitions.py:248-320`

Each agent has a dedicated TTS-optimized prompt in `SPOKEN_AGENT_PROMPTS`:

```python
"general-agent": (
    "Je bent een NVWA inspectie-assistent die KORTE gesproken antwoorden geeft.\n\n"
    "BELANGRIJK - Dit is voor tekst-naar-spraak (TTS):\n"
    "- Geef een SAMENVATTING van je antwoord in maximaal 2-3 zinnen\n"
    "- Focus op de kernboodschap, laat details weg\n"
    "- Gebruik GEEN opsommingstekens of nummering\n"
    "- Schrijf afkortingen UIT (bijv. 'KVK' → 'Kamer van Koophandel')\n"
    "- Schrijf getallen uit (bijv. '22°C' → 'tweeëntwintig graden Celsius')\n"
    ...
)
```

**Differences Between Written and Spoken Prompts**:

| Aspect | Written Prompt | Spoken Prompt |
|--------|---------------|---------------|
| Length | Full detailed response | 2-3 sentences max |
| Format | Markdown, bullet points, headers | Plain text, no formatting |
| Abbreviations | Allowed | Must be spelled out |
| Numbers | Numeric | Written out (for TTS) |
| Citations | Full references | Omitted or summarized |

#### 4.5 Dictate Mode

**Content Duplication** (`orchestrator.py:439-443`):
```python
# Send written content
await protocol_handler.send_text_message_content(message_id, content)

# In 'dictate' mode: send same content to spoken channel
if spoken_mode == "dictate":
    await protocol_handler.send_spoken_text_content(message_id, content)
```

#### 4.6 AG-UI Protocol Events for Spoken Text

**Custom Events** (`ag_ui_handler.py:224-281`):

| Event Name | Purpose |
|------------|---------|
| `agora:spoken_text_start` | Begin spoken stream |
| `agora:spoken_text_content` | Stream spoken chunk |
| `agora:spoken_text_end` | End spoken stream |
| `agora:spoken_text_error` | Report generation failure |

### 5. Complete Request Flow

```
1. WebSocket Message → server.py:487
   └─► handler.receive_message()

2. Message Parsing → ag_ui_handler.py:77-94
   └─► JSON → RunAgentInput

3. Orchestrator Processing → orchestrator.py:122
   ├─► Validate input (moderator)
   ├─► Emit RUN_STARTED
   └─► Call _stream_response()

4. LangGraph Streaming → orchestrator.py:404
   └─► graph.astream_events()
       └─► START → "general-agent"

5. Agent Node Execution → agents.py:89
   └─► llm_with_tools.ainvoke([system_msg, ...history])

6. Dual Channel Streaming → orchestrator.py:415-443
   ├─► TEXT_MESSAGE_* events (written)
   └─► agora:spoken_text_* events (spoken)

7. Frontend Handling
   ├─► Written → Chat UI display
   └─► Spoken → TTS buffer → ElevenLabs playback
```

## Code References

- `server-langgraph/src/agora_langgraph/core/state.py:11-21` - AgentState definition
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:19-245` - Agent configs with prompts
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:248-320` - Spoken prompts
- `server-langgraph/src/agora_langgraph/core/agents.py:56-104` - LLM message construction
- `server-langgraph/src/agora_langgraph/core/graph.py:123-202` - Graph building
- `server-langgraph/src/agora_langgraph/core/tools.py:13-68` - Transfer tools
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:352-388` - Parallel spoken generation
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:404-564` - Streaming response
- `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py:224-281` - Spoken text events

## Architecture Insights

1. **Dual-LLM Strategy**: The summarize mode uses two separate LLM calls - one for detailed written content, one for TTS-optimized spoken content. This allows each output to be optimized for its medium without compromise.

2. **Shared Context, Different Prompts**: Both LLM calls receive the same conversation history but different system prompts. The spoken prompt instructs the LLM to produce a 2-3 sentence summary.

3. **Async Queue Pattern**: Spoken chunks flow through an `asyncio.Queue` to the frontend, allowing interleaved streaming without blocking the written stream.

4. **Graceful Degradation**: Spoken stream errors (missing prompt, LLM failure) don't affect the written stream - errors are reported via `agora:spoken_text_error` event.

5. **User Preference Control**: The `spoken_text_type` preference gives users control over whether they want summarized audio or full dictation.

## Visual Diagram: Dual Generation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Message Arrives                          │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              graph.astream_events() starts                       │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              First content chunk arrives                         │
│                                                                  │
│   ┌────────────────────┐        ┌────────────────────┐          │
│   │ TEXT_MESSAGE_START │        │ spoken_text_start  │          │
│   └─────────┬──────────┘        └─────────┬──────────┘          │
│             │                             │                      │
│             │                             │ (if summarize mode)  │
│             │                             │                      │
│             ▼                             ▼                      │
│   ┌──────────────────┐          ┌──────────────────────┐        │
│   │   WRITTEN LLM    │          │   SPOKEN LLM (async) │        │
│   │  (main stream)   │          │  (parallel task)     │        │
│   │                  │          │                      │        │
│   │  System: Full    │          │  System: "2-3 zinnen │        │
│   │  agent prompt    │          │  samenvatting..."    │        │
│   │                  │          │                      │        │
│   │  Context: Full   │          │  Context: Full       │        │
│   │  conversation    │          │  conversation        │        │
│   └────────┬─────────┘          └──────────┬───────────┘        │
│            │                               │                     │
│            ▼                               ▼                     │
│   ┌────────────────────┐        ┌────────────────────┐          │
│   │TEXT_MESSAGE_CONTENT│        │spoken_text_content │          │
│   │ (streaming chunks) │        │ (streaming chunks) │          │
│   └────────┬───────────┘        └────────┬───────────┘          │
│            │                             │                       │
│            ▼                             ▼                       │
│   ┌────────────────────┐        ┌────────────────────┐          │
│   │ TEXT_MESSAGE_END   │        │ spoken_text_end    │          │
│   └────────────────────┘        └────────────────────┘          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │         Frontend              │
              │                               │
              │  ┌─────────┐    ┌─────────┐  │
              │  │ Chat UI │    │   TTS   │  │
              │  │(written)│    │(spoken) │  │
              │  └─────────┘    └─────────┘  │
              └───────────────────────────────┘
```

## Open Questions

1. **Token Cost**: The summarize mode doubles LLM calls. Is there monitoring for cost impact?
2. **Latency**: How much additional latency does the parallel spoken generation add?
3. **Fallback**: If spoken generation fails mid-stream, is there recovery or does TTS just skip that message?
