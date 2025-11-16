# Dutch Language Enforcement Strategy

Complete strategy for ensuring all AGORA interactions occur in Dutch for NVWA inspectors.

## Current State

**Partial Dutch Support:**
- ✅ Reporting agent has explicit Dutch instruction: "Use Dutch language for all inspector interactions"
- ✅ Reporting agent recognizes Dutch trigger phrases
- ❌ Regulation agent has no language specification
- ❌ Orchestrator/routing has no language enforcement
- ❌ MCP servers return English responses
- ❌ No system-wide language policy

## Multi-Layer Language Enforcement

### Layer 1: System-Wide Instructions (Orchestrator Level)

**Location:** `server-openai/src/agora_openai/pipelines/orchestrator.py`

Add a system message prefix to all agent interactions:

```python
SYSTEM_LANGUAGE_INSTRUCTION = """
CRITICAL: All responses to the inspector MUST be in Dutch (Nederlands).
The inspector is a Dutch-speaking NVWA employee.

LANGUAGE RULES:
- User messages may be in Dutch or English
- ALL assistant responses MUST be in Dutch
- Technical terms can remain in English if commonly used (e.g., "API", "JSON")
- Regulation citations should use original language + Dutch summary
- Error messages MUST be in Dutch

EXAMPLES:
❌ "Company information retrieved successfully"
✅ "Bedrijfsinformatie succesvol opgehaald"

❌ "This is a repeat violation"
✅ "Dit is een herhaalde overtreding"
"""
```

**Implementation:**
```python
# In orchestrator.py - modify send_message
await self.openai.send_message(
    thread_id, 
    f"{SYSTEM_LANGUAGE_INSTRUCTION}\n\nInspector: {message.content}"
)
```

### Layer 2: Agent Instructions

**Location:** `server-openai/src/agora_openai/core/agent_definitions.py`

Update each agent with explicit Dutch requirements:

```python
AGENT_CONFIGS: list[AgentConfig] = [
    {
        "id": "regulation-agent",
        "name": "Regulation Analysis Expert",
        "instructions": (
            "You are a regulatory compliance expert for NVWA inspectors.\n\n"
            "🇳🇱 LANGUAGE REQUIREMENT:\n"
            "- ALL responses MUST be in Dutch (Nederlands)\n"
            "- You are assisting Dutch-speaking NVWA inspectors\n"
            "- Technical regulation names can remain in original language with Dutch explanation\n"
            "- Example: 'EU Verordening 852/2004 (Levensmiddelenhygiëne)'\n\n"
            "YOUR CAPABILITIES:\n"
            "- Search and analyze regulatory documents\n"
            "- Execute compliance checks via MCP tools\n"
            "- Provide actionable guidance in clear Dutch\n\n"
            "ALWAYS:\n"
            "- Cite specific regulations with Dutch summaries\n"
            "- Provide actionable compliance guidance in Dutch\n"
            "- Flag high-risk areas clearly: 'WAARSCHUWING', 'HOOG RISICO'\n"
            "- Use tools to verify current regulations\n\n"
            "FORMAT:\n"
            "Structure responses with: Samenvatting, Details, Aanbevelingen, Bronnen"
        ),
        "model": "gpt-4o",
        "tools": ["file_search", "code_interpreter"],
        "temperature": 0.3,
    },
    {
        "id": "reporting-agent",
        "name": "HAP Inspection Report Specialist",
        "instructions": (
            "You are an NVWA inspection reporting expert specialized in HAP reports.\n\n"
            "🇳🇱 LANGUAGE REQUIREMENT:\n"
            "- ALL responses MUST be in Dutch (Nederlands)\n"
            "- You are assisting Dutch-speaking NVWA inspectors\n"
            "- Technical field names in reports can be in English (for system compatibility)\n"
            "- All explanations and questions MUST be in Dutch\n\n"
            "YOUR CAPABILITIES:\n"
            "- Analyze inspection conversations and extract structured data\n"
            "- Generate HAP reports in JSON and PDF formats\n"
            "- Verify missing information with inspectors IN DUTCH\n"
            "- Use MCP reporting tools for automated report generation\n\n"
            "WORKFLOW:\n"
            "1. When inspector says 'genereer rapport' or 'maak rapport':\n"
            "   - Call start_inspection_report with session details\n"
            "   - Call extract_inspection_data with full conversation history\n"
            "2. If data extraction shows low completion (<80%):\n"
            "   - Call verify_inspection_data to get verification questions\n"
            "   - Ask inspector IN DUTCH: 'Ik heb nog een paar vragen...'\n"
            "   - Call submit_verification_answers with responses\n"
            "3. Once data is complete:\n"
            "   - Call generate_final_report to create JSON and PDF\n"
            "   - Respond IN DUTCH: 'Het rapport is gegenereerd...'\n\n"
            "ALWAYS:\n"
            "- Extract company name, violations, severity levels\n"
            "- Verify critical fields before finalizing\n"
            "- Provide clear summaries in Dutch\n"
            "- Flag serious violations: 'ERNSTIGE OVERTREDING'\n\n"
            "DUTCH TRIGGER PHRASES:\n"
            "- 'Genereer rapport' / 'Maak rapport'\n"
            "- 'Maak inspectierapport'\n"
            "- 'Finaliseer documentatie'\n"
            "- 'Rond inspectie af'\n\n"
            "FORMAT:\n"
            "Samenvatting → Verificatie (indien nodig) → Rapport Generatie → Download Links"
        ),
        "model": "gpt-4o",
        "tools": ["file_search", "code_interpreter"],
        "temperature": 0.3,
    },
]
```

### Layer 3: Routing Prompt

**Location:** `server-openai/src/agora_openai/core/routing_logic.py`

Update routing prompt to emphasize Dutch:

```python
ROUTING_SYSTEM_PROMPT = """You are an intelligent routing system for AGORA compliance platform.

🇳🇱 CRITICAL: All agent responses will be in Dutch for NVWA inspectors.

Analyze the user's request and select the most appropriate specialized agent:

**regulation-agent**: 
- Regulatory compliance questions
- Legal requirements and regulations
- Standards and certifications
- Risk assessment and analysis
- Will respond in DUTCH about regulations

**reporting-agent**:
- Report generation (HAP inspection reports)
- Data extraction from conversations
- Report verification and validation
- Will respond in DUTCH with report status

Consider:
1. Primary topic and domain
2. Required expertise level
3. User's apparent intent

Return your selection with reasoning and confidence score."""
```

### Layer 4: MCP Server Response Templates

**Location:** Each MCP server's tool implementations

Add Dutch response templates to key MCP servers:

#### Inspection History Server

```python
# In mcp-servers/inspection-history/server.py

DUTCH_MESSAGES = {
    "not_found": "Geen inspectiegeschiedenis gevonden voor dit bedrijf. Dit kan een eerste inspectie zijn.",
    "no_violations": "Er zijn geen overtredingen gevonden voor dit bedrijf.",
    "repeat_warning": "⚠️ WAARSCHUWING: Dit is een herhaalde overtreding.",
    "escalation_required": "🚨 ESCALATIE VEREIST",
    "follow_up_overdue": "Follow-up actie is OVERDUE",
    "no_history": "Geen geschiedenis bekend. Dit lijkt een eerste inspectie te zijn.",
}

# Update get_inspection_history tool
@mcp.tool()
async def get_inspection_history(kvk_number: str, limit: int = 10) -> dict:
    """
    Haal inspectiegeschiedenis op voor een bedrijf op basis van KVK nummer.
    
    Geeft een lijst van eerdere inspecties inclusief data, inspecteurs, bevindingen en overtredingen.
    """
    logger.info(f"Getting inspection history for KVK: {kvk_number}")
    
    if not kvk_number or len(kvk_number) != 8:
        return {
            "status": "error",
            "error": "Ongeldig KVK nummer formaat. Moet 8 cijfers zijn.",
            "kvk_number": kvk_number
        }
    
    company_data = DEMO_INSPECTIONS.get(kvk_number)
    
    if not company_data:
        return {
            "status": "not_found",
            "kvk_number": kvk_number,
            "message": DUTCH_MESSAGES["not_found"],
            "inspections": []
        }
    
    # ... rest of implementation
```

#### KVK Lookup Server

```python
# In mcp-servers/kvk-lookup/server.py

@mcp.tool()
async def get_company_info(kvk_number: str) -> dict:
    """
    Haal uitgebreide bedrijfsinformatie op van de KVK.
    
    Geeft bedrijfsgegevens, rechtsvorm, activiteiten en registratiedetails.
    """
    # ... implementation
    
    if not found:
        return {
            "status": "not_found",
            "message": "Bedrijf niet gevonden in KVK register.",
            "kvk_number": kvk_number
        }
```

### Layer 5: Frontend Language Hints

**Location:** `HAI/src/components/chat/ChatInput.tsx`

Add language hints in the UI:

```typescript
<input
  placeholder="Stel een vraag in het Nederlands... (bijvoorbeeld: 'Start inspectie bij bedrijf X')"
  lang="nl"
  // ...
/>
```

### Layer 6: Voice Mode Language Settings

**Location:** `HAI/src/hooks/useVoiceMode.ts`

Ensure Realtime API is configured for Dutch:

```typescript
{
  model: "gpt-4o-realtime-preview",
  modalities: ["text", "audio"],
  voice: "alloy",
  instructions: "Je bent een Nederlandse NVWA inspectie-assistent. Alle antwoorden MOETEN in het Nederlands zijn.",
  input_audio_transcription: {
    model: "whisper-1",
    language: "nl"  // Force Dutch transcription
  }
}
```

## Implementation Priority

### Phase 1: Critical (Immediate)
1. ✅ Update agent instructions with Dutch language requirements
2. ✅ Add Dutch response templates to Inspection History server
3. ✅ Update routing prompt

### Phase 2: Important (This Week)
4. ⚠️ Add system-wide language instruction in orchestrator
5. ⚠️ Update KVK Lookup server with Dutch messages
6. ⚠️ Add frontend language hints

### Phase 3: Nice-to-have (Future)
7. 📋 Voice mode Dutch language configuration
8. 📋 Comprehensive Dutch error messages across all components

## Testing Dutch Language Enforcement

### Test Cases

```python
# Test 1: English input, Dutch output
Input: "What are the previous violations?"
Expected: "Er zijn de volgende overtredingen gevonden..."

# Test 2: Dutch input, Dutch output
Input: "Wat zijn de eerdere overtredingen?"
Expected: "Er zijn de volgende overtredingen gevonden..."

# Test 3: Regulation citations
Input: "Which regulation applies?"
Expected: "EU Verordening 852/2004 (Levensmiddelenhygiëne) is van toepassing..."

# Test 4: Error messages
Input: Invalid KVK number
Expected: "Ongeldig KVK nummer. Moet 8 cijfers bevatten."

# Test 5: Report generation
Input: "Generate report"
Expected: "Het rapport wordt gegenereerd. Even geduld..."
```

### Testing Script

```bash
# Test all three scenarios with Dutch validation
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_inspection_history",
    "arguments": {"kvk_number": "invalid"}
  }' | jq '.message'
# Should output: "Ongeldig KVK nummer formaat..."

curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "check_repeat_violation",
    "arguments": {
      "kvk_number": "59581883",
      "violation_category": "hygiene_measures"
    }
  }' | jq '.escalation_reason'
# Should include Dutch warnings
```

## Implementation Code Changes

### 1. Update Agent Definitions

```bash
# Update file: server-openai/src/agora_openai/core/agent_definitions.py
```

### 2. Update Inspection History Server

```bash
# Update file: mcp-servers/inspection-history/server.py
```

### 3. Add Orchestrator Language Prefix

```bash
# Update file: server-openai/src/agora_openai/pipelines/orchestrator.py
```

## Expected Outcomes

After implementing these changes:

✅ **Agents always respond in Dutch** regardless of input language
✅ **MCP tool descriptions are in Dutch** for better context
✅ **Error messages are in Dutch** for inspector clarity
✅ **Technical terms remain readable** (e.g., "JSON", "PDF", "CE-markering")
✅ **Regulation citations are bilingual** (original + Dutch)
✅ **Voice mode transcribes Dutch correctly**

## Fallback Strategy

If GPT-4 occasionally responds in English despite instructions:

**Option 1: Post-processing (not recommended)**
- Translate responses using GPT-4 before sending
- Adds latency and cost

**Option 2: Stronger system instructions (recommended)**
- Add to every message: "RESPOND IN DUTCH ONLY"
- Use explicit examples in system prompt

**Option 3: Model fine-tuning (future)**
- Fine-tune GPT-4 on Dutch inspection conversations
- Expensive but most reliable

## Monitoring Dutch Compliance

Add logging to track language compliance:

```python
# In orchestrator.py
async def _validate_dutch_response(self, response: str) -> bool:
    """Check if response is primarily in Dutch."""
    # Simple heuristic: check for common Dutch words
    dutch_indicators = ['de', 'het', 'een', 'van', 'is', 'zijn', 'voor', 'op']
    word_count = len(response.split())
    dutch_word_count = sum(1 for word in response.lower().split() if word in dutch_indicators)
    
    ratio = dutch_word_count / max(word_count, 1)
    is_dutch = ratio > 0.15  # At least 15% common Dutch words
    
    if not is_dutch:
        log.warning("Response may not be in Dutch. Ratio: %.2f", ratio)
    
    return is_dutch
```

## Quick Start Implementation

Run this to implement Phase 1:

```bash
# 1. Update agent definitions
code server-openai/src/agora_openai/core/agent_definitions.py

# 2. Update inspection history with Dutch messages
code mcp-servers/inspection-history/server.py

# 3. Test Dutch responses
docker-compose -f mcp-servers/docker-compose.yml restart inspection-history

# 4. Verify
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "get_inspection_history", "arguments": {"kvk_number": "99999999"}}' \
  | jq '.message'
```

## Conclusion

**Multi-layer enforcement ensures Dutch throughout the system:**
1. 🇳🇱 System instructions in orchestrator
2. 🇳🇱 Agent-level language requirements
3. 🇳🇱 MCP server response templates
4. 🇳🇱 Frontend language hints
5. 🇳🇱 Voice mode configuration

**Priority: Implement Phase 1 immediately** for demo readiness.

