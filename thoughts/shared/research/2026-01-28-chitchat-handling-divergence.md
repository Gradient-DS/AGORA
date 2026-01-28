---
date: 2026-01-28T10:00:00+01:00
researcher: Claude
git_commit: 6b4f45b2a118fec177d27faec21f19f4d20bfebf
branch: feat/buffer
repository: AGORA
topic: "Chitchat handling causes unexpected transfers and written/spoken divergence"
tags: [research, codebase, general-agent, routing, parallel-generation, chitchat]
status: complete
last_updated: 2026-01-28
last_updated_by: Claude
---

# Research: Chitchat Handling Causes Unexpected Transfers and Written/Spoken Divergence

**Date**: 2026-01-28T10:00:00+01:00
**Researcher**: Claude
**Git Commit**: 6b4f45b2a118fec177d27faec21f19f4d20bfebf
**Branch**: feat/buffer
**Repository**: AGORA

## Research Question

When users send chitchat (e.g., "hoe gaat het?" / "how are you?"), the system exhibits:
1. Unexpected transfers from general-agent to history-agent
2. Significant divergence between written and spoken outputs
3. Confusing responses like "Ik kan je daar niet mee helpen" (written) vs "Hoi! Met mij gaat alles goed" (spoken)

The user wants to understand why this happens and what changes would be needed to have general-agent handle chitchat with an explanation of how AGORA works.

## Summary

The root cause is **intentional design**: the general-agent is explicitly configured as a **pure router** that must ALWAYS transfer to specialists. For ambiguous/greeting messages, it defaults to `transfer_to_history`. Once at history-agent, that specialist is instructed to stay in its domain and redirect off-topic queries.

The written/spoken divergence occurs because:
1. They use **completely different system prompts** (full vs TTS-optimized)
2. They run in **parallel with no coordination**
3. There is **no consistency validation** at merge

## Detailed Findings

### 1. General-Agent: The Pure Router Design

**Location**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py:23-61`

The general-agent's system prompt explicitly forbids answering questions:

```python
"⚠️ CRITICAL RULE - ALWAYS HAND OFF:\n"
"You MUST ALWAYS use a transfer tool. You are NOT allowed to answer "
"questions yourself. Your only job is to route to specialists.\n\n"
```

The decision logic for routing (lines 44-49):
```python
"DECISION LOGIC:\n"
"- Company/KVK mentioned? → transfer_to_history\n"
"- Rules/regulations question? → transfer_to_regulation\n"
"- Report generation request? → transfer_to_reporting\n"
"- Greeting or unclear? → transfer_to_history (default for starting inspections)\n"
"- Settings change request? → use update_user_settings tool\n\n"
```

**Key constraint** (line 57):
```
"You MUST call a tool on every turn"
```

The general-agent has only 4 tools (`tools.py:225-235`):
- `transfer_to_history`
- `transfer_to_regulation`
- `transfer_to_reporting`
- `update_user_settings`

There is **no tool for answering chitchat** and **no path to respond directly**.

### 2. History-Agent: Stuck with Off-Topic Queries

**Location**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py:174-226`

When general-agent transfers a greeting to history-agent, the history-agent is instructed:

```python
"⚠️ CRITICAL WORKFLOW - YOU MUST FOLLOW THESE STEPS:\n"
"1. FIRST: Call check_company_exists or get_inspection_history\n"
...
"NEVER skip step 1. ALWAYS call a tool before responding.\n"
```

For off-topic queries (lines 205-209):
```python
"- If the user asks about something outside your expertise, explain that "
"they should ask about company history\n\n"
```

This is why the written output says "Ik kan je daar niet mee helpen" - the agent is following its instruction to redirect off-topic queries.

### 3. Why Written and Spoken Diverge

**Parallel Generation** (`graph.py:317-387`): Both streams receive identical message history but use:

| Aspect | Written | Spoken |
|--------|---------|--------|
| **System Prompt** | Full agent instructions (detailed, tool-focused) | TTS-optimized (1-3 sentences max) |
| **LLM** | `settings.openai_model` | `settings.spoken_model` (optional override) |
| **Temperature** | Agent-specific (e.g., 0.2 for history) | Hardcoded 0.7 |
| **Coordination** | None | None |

**Spoken prompt for history-agent** (`agent_definitions.py:275-301`):
```python
"Je bent een bedrijfsinformatie-specialist die KORTE gesproken antwoorden geeft.\n\n"
"BELANGRIJK - Dit is voor tekst-naar-spraak (TTS):\n"
"- Geef een beknopte samenvatting in maximaal 2-3 zinnen\n"
```

The spoken prompt focuses on being friendly and brief, without the strict "redirect off-topic" instruction. This allows it to respond conversationally ("Hoi! Met mij gaat alles goed") while written follows the full instructions ("Ik kan je daar niet mee helpen").

**No Consistency Validation** (`graph.py:465-504`): The `merge_parallel_outputs()` function simply concatenates outputs without checking for semantic consistency.

### 4. The Routing Flow for Chitchat

```
User: "Hoe gaat het?"
    ↓
route_from_start() → "general-agent"
    ↓
general-agent: LLM sees greeting, follows "Greeting or unclear? → transfer_to_history"
    ↓
Calls transfer_to_history tool
    ↓
route_after_tools() detects handoff → "history-agent"
    ↓
history-agent: LLM sees greeting (off-topic for company history)
    ↓
Written follows: "redirect off-topic queries" → "Ik kan je daar niet mee helpen"
Spoken follows: TTS-friendly prompt → "Hallo! Hoe kan ik je helpen?"
    ↓
merge_parallel_outputs() combines divergent responses
```

## What Would Need to Change

### Option A: Minimal Change - Allow Chitchat in General-Agent

**Modify** `agent_definitions.py` general-agent instructions:

1. Remove "Greeting or unclear? → transfer_to_history"
2. Add exception for chitchat:
   ```
   "EXCEPTION - GREETINGS AND CHITCHAT:\n"
   "For simple greetings, introductions, or casual chitchat, respond directly "
   "in a friendly manner. Explain what AGORA is and what you can help with:\n"
   "- Company history and KVK verification\n"
   "- Regulation analysis and compliance questions\n"
   "- Inspection report generation\n"
   "Then ask how you can assist the inspector today.\n\n"
   ```

3. Change "You MUST call a tool on every turn" to:
   ```
   "You MUST call a tool for domain questions. For chitchat, respond directly."
   ```

**Issue**: The routing in `graph.py:269-285` expects either tool calls or parallel generation. If general-agent responds without tools, `route_from_agent()` would fork to parallel generation, which would regenerate the response using the parallel prompts.

### Option B: Add Chitchat Detection Before Routing

**Add a preprocessing step** in `route_from_start()` to detect chitchat:

1. Add a `detect_chitchat()` function that checks for greetings/small talk
2. Route chitchat directly to a new `chitchat_handler` node
3. Have that node respond with AGORA introduction + offer to help

**Example location**: `graph.py:171-214`

```python
def route_from_start(state: AgentState) -> str:
    messages = state.get("messages", [])
    if messages and is_chitchat(messages[-1].content):
        return "chitchat_handler"
    # ... existing logic
```

### Option C: Add an "answer_greeting" Tool to General-Agent

**Add a tool** that general-agent can call for greetings:

```python
@tool
async def answer_greeting(greeting_response: str) -> str:
    """Respond to a greeting or casual chitchat.

    Use this when the user sends a greeting, asks how you are,
    or engages in small talk that doesn't require specialist knowledge.

    Args:
        greeting_response: Your friendly response explaining what AGORA can do
    """
    return greeting_response
```

**Modify routing** to not treat this as a handoff in `route_after_tools()`.

### Recommended Approach

**Option A with routing modification** is the cleanest:

1. Update general-agent prompt to allow direct responses for chitchat
2. Modify `route_from_agent()` to check if general-agent produced a direct response (no tool calls) and handle it as final (skip parallel regeneration)
3. Update spoken prompt for general-agent to align with chitchat response style

This keeps the existing architecture while adding a specific carve-out for chitchat.

## Code References

- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:23-61` - general-agent system prompt
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:174-226` - history-agent definition
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:231-301` - SPOKEN_AGENT_PROMPTS
- `server-langgraph/src/agora_langgraph/core/graph.py:171-214` - route_from_start()
- `server-langgraph/src/agora_langgraph/core/graph.py:245-286` - route_from_agent()
- `server-langgraph/src/agora_langgraph/core/graph.py:288-314` - route_after_tools()
- `server-langgraph/src/agora_langgraph/core/graph.py:317-387` - _create_parallel_sends()
- `server-langgraph/src/agora_langgraph/core/graph.py:465-504` - merge_parallel_outputs()
- `server-langgraph/src/agora_langgraph/core/tools.py:225-235` - general-agent tools

## Architecture Insights

1. **Intentional pure-router pattern**: general-agent was designed to never answer questions - this is a deliberate architectural choice, not a bug
2. **Specialists don't hand back**: The design assumes one-way handoffs; specialists provide final answers
3. **Parallel generation assumes domain expertise**: The system assumes responses will come from specialists with domain knowledge, not from general-agent
4. **No consistency enforcement**: The parallel written/spoken architecture trades consistency for speed

## Open Questions

1. Should the AGORA introduction include specific examples of inspection scenarios?
2. Should chitchat reset the conversation or maintain context for follow-up domain questions?
3. Should the spoken prompt for general-agent be updated to match the new chitchat behavior?
4. Is there value in adding a `transfer_back_to_general` tool for specialists to use when they detect off-topic queries?
