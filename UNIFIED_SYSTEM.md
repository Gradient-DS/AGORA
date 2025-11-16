# Unified Voice & Chat System

The AGORA system now provides a **unified backend** that can be accessed through both voice and text interfaces, with full tool access in both modes.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Frontend                          │
│  ┌─────────────┐              ┌─────────────┐      │
│  │    Voice    │              │    Chat     │      │
│  │  Interface  │              │  Interface  │      │
│  │             │              │             │      │
│  │  - Audio    │              │  - Text     │      │
│  │  - Speech   │              │  - Typing   │      │
│  └──────┬──────┘              └──────┬──────┘      │
│         │                             │              │
│         │ Audio/PCM16                 │ Text/JSON    │
└─────────┼─────────────────────────────┼─────────────┘
          │                             │
          │ ws://backend/ws/voice       │ ws://backend/ws
          ▼                             ▼
┌─────────────────────────────────────────────────────┐
│              Unified Backend System                  │
│                                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │         Voice Handler                          │ │
│  │  ┌──────────────────────────────────────────┐ │ │
│  │  │  OpenAI Realtime API                     │ │ │
│  │  │  - Audio I/O                             │ │ │
│  │  │  - Function Calling Enabled              │ │ │
│  │  │  - Tool Definitions Registered           │ │ │
│  │  └──────────────┬───────────────────────────┘ │ │
│  │                 │ Tool Call Requests          │ │
│  │                 ▼                             │ │
│  └────────────────────────────────────────────────┘ │
│                    │                                 │
│  ┌────────────────┼────────────────────────────────┐│
│  │                ▼                                 ││
│  │         ┌──────────────┐                        ││
│  │         │ ORCHESTRATOR │◄──────────────┐        ││
│  │         └──────┬───────┘               │        ││
│  │                │                        │        ││
│  │                │                        │        ││
│  │         ┌──────▼───────┐               │        ││
│  │         │  MCP Client  │               │        ││
│  │         │              │               │        ││
│  │         │ - Tool Exec  │               │        ││
│  │         │ - Discovery  │               │        ││
│  │         └──────┬───────┘               │        ││
│  │                │                        │        ││
│  │                ▼                        │        ││
│  │    ┌───────────────────────┐           │        ││
│  │    │   MCP Tools/Servers   │           │        ││
│  │    │                       │           │        ││
│  │    │ • Reporting           │           │        ││
│  │    │ • Regulation Analysis │           │        ││
│  │    └───────────────────────┘           │        ││
│  │                                         │        ││
│  │  ┌──────────────────────────────────┐  │        ││
│  │  │         Chat Handler             │  │        ││
│  │  │  - HAI Protocol                  │  │        ││
│  │  │  - Text Messages                 │──┘        ││
│  │  │  - Agent Routing                 │           ││
│  │  └──────────────────────────────────┘           ││
│  └──────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

## Key Features

### 1. **Unified Tool Access** 
Both voice and chat can access the same MCP tools:
- Regulatory information and analysis
- HAP inspection reporting capabilities
- Any custom MCP tools you add

### 2. **Shared Conversation Context**
- When you switch from chat to voice, the AI remembers your chat history
- Seamless transitions between modalities
- Persistent session state

### 3. **Same Capabilities, Different Interfaces**
| Feature | Voice Mode | Chat Mode |
|---------|------------|-----------|
| Tool Execution | ✅ Yes | ✅ Yes |
| MCP Tools | ✅ Yes | ✅ Yes |
| Conversation History | ✅ Yes | ✅ Yes |
| Real-time | ✅ Audio | ✅ Text |
| Approval Workflow | ⚠️ Auto* | ✅ Yes |
| Agent Routing | ⚠️ Realtime AI | ✅ Orchestrator |

*Note: Voice mode currently executes tools automatically. Approval workflow integration is planned.

## How It Works

### Voice Mode with Tools

1. **User speaks**: "Check if XYZ Corp is compliant with SOX regulations"

2. **OpenAI Realtime API**:
   - Transcribes speech
   - Understands intent
   - Determines it needs the `check_compliance` tool
   - Makes a function call request

3. **Voice Handler**:
   - Receives function call request
   - Forwards to MCP Client
   - Executes tool via MCP server
   - Returns result to Realtime API

4. **OpenAI Realtime API**:
   - Receives tool result
   - Generates natural language response
   - Synthesizes to audio

5. **User hears**: "I've checked XYZ Corp's compliance status. They are currently compliant with SOX regulations, with the last audit completed on..."

### Chat Mode with Tools

1. User types the same question
2. Orchestrator routes to appropriate agent
3. Agent uses tools via MCP Client
4. Results processed and formatted
5. Text response returned to user

## Usage Examples

### Example 1: Voice Tool Use

```
User (voice): "What are the HACCP regulations for temperature control?"

Assistant (voice): "Let me search the regulations for you..."
[Tool executing: semantic_search_regulations]
[Tool completed: semantic_search_regulations]

Assistant (voice): "According to HACCP regulations, temperature control requirements state:
- Cold foods must be kept at 4°C or below
- Hot foods must be maintained at 60°C or above
- Food in the danger zone (4-60°C) should not exceed 2 hours
- Temperature logs must be maintained daily

Would you like more details on any specific aspect?"
```

### Example 2: Mixed Voice and Chat

```
[User starts in chat]
User (typed): "Show me the inspection report for session ABC123"
Assistant: [Generates report using reporting tool]

[User switches to voice]
User (voice): "What were the main findings in that report?"
Assistant (voice): [Remembers context, discusses inspection findings]

[User switches back to chat to see details]
User (typed): "Can you generate the PDF version?"
Assistant: [Uses generate_final_report tool, provides download link]
```

## Implementation Details

### Backend Components

#### 1. Voice Handler (`voice_handler.py`)
```python
class VoiceSessionHandler:
    def __init__(self, client_ws, realtime_client, mcp_client):
        # Connects voice to tools
        self.mcp_client = mcp_client  # Access to all tools
        
    async def start(self, session_id, conversation_history):
        # Register all MCP tools with Realtime API
        tools = self.mcp_client.tool_definitions
        session_config = {
            "tools": tools,  # All MCP tools available
            "tool_choice": "auto",  # AI decides when to use
        }
```

#### 2. OpenAI Realtime Client (`realtime_client.py`)
```python
class OpenAIRealtimeClient:
    async def send_function_result(self, call_id, result):
        # Return tool results to OpenAI
        await self._send_event("conversation.item.create", {
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result),
            }
        })
```

#### 3. Function Call Handling
```python
# In voice_handler.py
async def _handle_openai_message(self, event):
    if event_type == "response.function_call_arguments.done":
        name = event.get("name")
        arguments = event.get("arguments")
        
        # Execute via MCP
        result = await self.mcp_client.execute_tool(name, arguments)
        
        # Send result back
        await self.realtime_client.send_function_result(call_id, result)
```

### Frontend Components

#### Voice Mode Tool Feedback
The UI shows when tools are being executed:
- 🔧 "Executing check_compliance..."
- ✅ "check_compliance completed"
- ❌ "Tool failed: [error]"

## Configuration

### Enable Tools in Voice Mode (Automatic)
Tools are automatically registered from your MCP servers:

```bash
# .env
APP_MCP_SERVERS=regulation-analysis=http://localhost:5002,reporting=http://localhost:5003
```

All discovered tools are automatically available in both voice and chat modes.

### Custom Instructions for Voice
You can customize how the AI behaves in voice mode:

```python
# When starting voice session from frontend
voiceClient.startSession(
    "You are an NVWA inspection assistant. Always follow Dutch inspection protocols."
)
```

## Limitations & Roadmap

### Current Limitations

1. **No Approval Workflow in Voice (Yet)**
   - Voice tools execute automatically
   - Chat mode has full approval workflow
   - **Planned**: Voice approval via speech confirmation

2. **No Agent Routing in Voice**
   - Voice uses OpenAI's Realtime API directly
   - Chat mode routes to specialized agents
   - **Consideration**: May not be needed as Realtime API is highly capable

3. **Tool Results Not Read Aloud**
   - Tool execution status shown in UI
   - Results used by AI but not explicitly announced
   - **Planned**: Configurable verbosity

### Roadmap

#### Phase 1 (Completed) ✅
- [x] Voice mode with OpenAI Realtime API
- [x] Tool registration in voice sessions
- [x] Function call handling
- [x] Tool execution via MCP client
- [x] Shared conversation context
- [x] UI feedback for tool execution

#### Phase 2 (In Progress)
- [ ] Voice approval workflow
- [ ] Rich tool result display in UI
- [ ] Tool call confirmation before execution
- [ ] Rate limiting for expensive tools

#### Phase 3 (Planned)
- [ ] Multi-agent coordination in voice
- [ ] Voice-triggered complex workflows
- [ ] Custom voice personas per agent
- [ ] Advanced conversation analytics

## Testing

### Test Voice Tool Access

1. Start backend with MCP servers:
```bash
cd server-openai
APP_MCP_SERVERS=regulation-analysis=http://localhost:5002,reporting=http://localhost:5003 python -m agora_openai.api.server
```

2. Start frontend:
```bash
cd HAI
pnpm run dev
```

3. Activate voice mode and say:
```
"What are the HACCP requirements for temperature control?"
```

4. Watch for:
- Console log: "Function call requested: semantic_search_regulations"
- UI: "🔧 Executing semantic_search_regulations..."
- Voice response with regulation information

### Test Context Sharing

1. Start in chat mode
2. Type: "What regulations apply to food safety in restaurants?"
3. Switch to voice mode
4. Say: "Tell me more about the second one"
5. AI should remember the previous context

## Best Practices

### For Voice Interactions

1. **Be Specific**: "Search for HACCP temperature requirements" vs "Search regulations"
2. **Use Natural Language**: The AI understands context and nuance
3. **Wait for Confirmation**: Let tool execution complete before next request
4. **Review Results**: Check the chat interface for detailed tool outputs

### For Tool Design

1. **Fast Tools for Voice**: Voice tools should complete quickly (<3s ideal)
2. **Clear Tool Names**: Use descriptive function names
3. **Concise Results**: Return summaries, not full reports
4. **Error Messages**: Provide helpful error messages for voice users

## Security Considerations

### Voice Mode Security

- Tools execute without explicit approval (currently)
- Consider restricting high-risk tools in voice mode
- Audit logs capture all tool executions
- Rate limiting recommended for production

### Recommended Settings

```python
# For high-risk tools
HIGH_RISK_TOOLS = [
    "generate_final_report",
    "delete_session_data"
]

# Disable in voice mode or require approval
session_config = {
    "tools": [t for t in tools if t["function"]["name"] not in HIGH_RISK_TOOLS]
}
```

## Summary

You now have a **truly unified system** where:

✅ **Voice users** can access all tools through natural conversation  
✅ **Chat users** get structured interactions with full approval workflow  
✅ **Both modes** share conversation history and context  
✅ **Same backend** handles both interfaces  
✅ **All MCP tools** available in both modalities  

This architecture provides the flexibility of voice with the power of your specialized tools and agents!

