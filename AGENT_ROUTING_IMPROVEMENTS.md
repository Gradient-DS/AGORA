# Agent Routing Improvements

## Overview
This document describes improvements made to the AGORA agent routing system to better utilize specialist agents and improve the user experience with active/inactive agent displays.

## Problem Statement
- **General agent was handling most requests**: The routing system was biased towards the general agent being the "DEFAULT", causing it to handle tasks that specialist agents should have picked up
- **Only reporting agent was being selected**: Other specialist agents (regulation, history) were rarely getting routed to
- **UI needed to show agent availability**: No way to display active vs inactive agents in the interface

## Solutions Implemented

### 1. Removed Tools from General Agent
**File**: `server-openai/src/agora_openai/core/agent_definitions.py`

The general agent now has:
- **No MCP tools** (`"tools": []` instead of `["file_search", "code_interpreter"]`)
- **Coordinator role** instead of executor
- **Increased temperature** (0.7 vs 0.5) for more conversational responses
- **Clear limitations** documented in instructions

#### New General Agent Purpose:
- Handle greetings and small talk
- Provide procedural guidance
- Explain what specialist agents can do
- Guide inspectors to specialist agents
- **NOT**: Execute tool calls, access databases, generate reports, etc.

### 2. Rebalanced Routing Logic
**File**: `server-openai/src/agora_openai/core/routing_logic.py`

#### Key Changes:
- **Removed "DEFAULT" bias**: General agent is now "ONLY as fallback"
- **Prioritized specialists**: Each specialist agent is marked with "PREFER"
- **Clear routing strategy**: Explicit rules for when to route to each agent
- **Keyword-based hints**: Maps common request patterns to agents

#### New Routing Priority:
1. **history-agent**: For any KVK, company, or inspection history queries
2. **regulation-agent**: For regulatory/compliance questions
3. **reporting-agent**: For report generation
4. **general-agent**: Only for greetings or truly ambiguous requests

### 3. Added Inactive Agents for UI
**File**: `server-openai/src/agora_openai/core/agent_definitions.py`

Added new data structure for inactive/placeholder agents:

```python
INACTIVE_AGENT_CONFIGS: list[InactiveAgentConfig] = [
    {
        "id": "ns-reisplanner-agent",
        "name": "NS Reisplanner",
        "description": "Plan inspectie routes en reistijden met openbaar vervoer",
        "coming_soon": True,
    },
    {
        "id": "process-verbaal-agent",
        "name": "Proces-Verbaal Generator",
        "description": "Genereer officiële processen-verbaal voor overtredingen",
        "coming_soon": True,
    },
    {
        "id": "planning-agent",
        "name": "Inspectie Planning",
        "description": "Plan en organiseer meerdere inspecties efficiënt",
        "coming_soon": True,
    },
    {
        "id": "risk-analysis-agent",
        "name": "Risico Analyse Expert",
        "description": "Uitgebreide risicoanalyse en prioritering van inspecties",
        "coming_soon": True,
    },
]
```

### 4. Added API Endpoint for Agent List
**File**: `server-openai/src/agora_openai/api/server.py`

New endpoint: `GET /agents`

Returns:
```json
{
  "active_agents": [
    {
      "id": "general-agent",
      "name": "NVWA General Assistant",
      "model": "gpt-4o",
      "description": "You are a general NVWA inspection assistant..."
    },
    // ... other active agents
  ],
  "inactive_agents": [
    {
      "id": "ns-reisplanner-agent",
      "name": "NS Reisplanner",
      "description": "Plan inspectie routes en reistijden met openbaar vervoer",
      "coming_soon": true
    },
    // ... other inactive agents
  ]
}
```

## Expected Behavior Changes

### Before:
- User: "Geef me het dossier van KVK 12345678"
- Routing: → **general-agent** (with all tools)
- Result: General agent executes all tools directly

### After:
- User: "Geef me het dossier van KVK 12345678"
- Routing: → **history-agent** (specialist with tools)
- Result: History agent provides expert analysis with company data

### Before:
- User: "Wat zijn de regels voor voedselveiligheid?"
- Routing: → **general-agent** (with all tools)
- Result: General agent searches regulations

### After:
- User: "Wat zijn de regels voor voedselveiligheid?"
- Routing: → **regulation-agent** (specialist)
- Result: Regulation agent provides expert regulatory guidance

### Before:
- User: "Hallo"
- Routing: → **general-agent** (with all tools)
- Result: Could potentially use tools unnecessarily

### After:
- User: "Hallo"
- Routing: → **general-agent** (no tools)
- Result: Simple greeting, guides user to ask specific questions

## Frontend Integration

The frontend can now:
1. Fetch `/agents` endpoint on load
2. Display **active_agents** as interactive/selectable
3. Display **inactive_agents** as greyed out with "Coming Soon" badges
4. Show which agent is currently responding to queries
5. Show agent metadata (name, description, model)

## Testing Recommendations

Test these scenarios to verify routing:

1. **Company queries** → should route to `history-agent`:
   - "Geef me het dossier van KVK 12345678"
   - "Start inspectie bij Bakkerij Jansen"
   - "Wat is de inspectiegeschiedenis van deze firma?"

2. **Regulation queries** → should route to `regulation-agent`:
   - "Wat zijn de regels voor voedselveiligheid?"
   - "Welke wetgeving geldt voor dit product?"
   - "Is dit conform EU verordening 852/2004?"

3. **Report queries** → should route to `reporting-agent`:
   - "Genereer rapport"
   - "Maak een HAP inspectie rapport"
   - "Rond de inspectie af"

4. **General queries** → should route to `general-agent`:
   - "Hallo"
   - "Hoe werkt dit systeem?"
   - "Wat kan je voor me doen?"

## Benefits

1. **Better specialist utilization**: Each agent handles what it's designed for
2. **Clearer separation of concerns**: General agent doesn't try to do everything
3. **Improved UI/UX**: Users can see available and upcoming agents
4. **Easier debugging**: Clear routing rules make it easier to understand agent selection
5. **Better error handling**: If general agent is selected, it guides users to rephrase for specialists
6. **Scalability**: Easy to add new specialist agents without affecting general routing

## Migration Notes

- No breaking changes to existing APIs
- Existing sessions will continue to work
- Routing will automatically improve with new logic
- Frontend changes are optional but recommended for best UX

