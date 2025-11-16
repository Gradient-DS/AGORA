# AGORA v1.0 - Gap Analysis & Recommendations

## Executive Summary

AGORA currently has **2 agents** and **3 MCP servers** operational. Analysis of the three persona scenarios reveals **1 critical gap** that must be addressed for demo readiness: **Inspection History data access**.

---

## Current Capabilities ✅

### MCP Servers (3)
| Server | Port | Function | Status |
|--------|------|----------|--------|
| KVK Lookup | 5004 | Company information, SBI codes, insolvency | ✅ Operational |
| Regulation Analysis | 5002 | Semantic search Dutch/EU regulations | ✅ Operational |
| Reporting | 5003 | HAP report generation (JSON + PDF) | ✅ Operational |

### Agents (2)
| Agent | Function | Status |
|-------|----------|--------|
| Regulation Agent | Compliance checks, regulation lookup | ✅ Operational |
| Reporting Agent | HAP report generation, data extraction | ✅ Operational |

---

## Scenario Analysis

### Scenario 1: Koen (Horeca Inspection)
**Coverage:** 85%
- ✅ Company lookup (KVK)
- ✅ Regulation lookup
- ✅ Report generation
- ❌ **Inspection history** (Can't answer: "Zijn er eerdere overtredingen bekend?")
- ⚠️ Proces-verbaal (Explicitly excluded from scope)

### Scenario 2: Fatima (Product Safety)
**Coverage:** 70%
- ✅ Company lookup
- ✅ Regulation lookup (EU directives)
- ✅ Report generation
- ❌ **Inspection history**
- ❌ Product scanning/barcode lookup
- ⚠️ Photo integration

### Scenario 3: Jan (Butcher Shop)
**Coverage:** 85%
- ✅ Company lookup
- ✅ Regulation lookup
- ✅ Report generation
- ❌ **Inspection history** (Can't answer: "Wat is er eerder geconstateerd?")
- ⚠️ Client communication templates

---

## Critical Gap: Inspection History 🚨

**Impact:** All 3 scenarios are blocked

**Example queries that currently fail:**
- "Zijn er eerdere overtredingen bekend?" (Koen)
- "Zijn er eerder onveilige producten aangetroffen?" (Fatima)  
- "Wat is er eerder geconstateerd?" (Jan)

**Solution: Fake Inspection History MCP Server**

Since no real data source exists yet, build a mock MCP server with hardcoded data for demo purposes.

### Proposed Implementation

**Server Name:** `inspection-history`  
**Port:** 5005  
**Storage:** In-memory (Python dict) with demo data

**Required Tools:**

1. `get_inspection_history(kvk_number: str) -> dict`
   - Returns list of past inspections for a company
   - Includes date, inspector, type, findings

2. `get_company_violations(kvk_number: str, limit: int = 10) -> dict`
   - Returns past violations for a company
   - Includes severity, category, date, resolution status

3. `check_repeat_violation(kvk_number: str, violation_category: str) -> dict`
   - Checks if current violation is a repeat
   - Returns boolean + details of previous occurrence

4. `get_follow_up_status(kvk_number: str, inspection_id: str) -> dict`
   - Returns follow-up actions and compliance status
   - Useful for determining enforcement escalation

**Demo Data Structure:**

```python
DEMO_DATA = {
    "59581883": {  # Restaurant Bella Rosa (Koen scenario)
        "company_name": "Restaurant Bella Rosa",
        "inspections": [
            {
                "inspection_id": "INS-2022-001234",
                "date": "2022-05-15",
                "inspector": "Jan Pietersen",
                "type": "hygiene_routine",
                "violations": [
                    {
                        "category": "hygiene_measures",
                        "severity": "warning",
                        "description": "Onvoldoende hygiënemaatregelen in de keuken",
                        "regulation": "Hygiënecode Horeca artikel 4.2",
                        "resolved": False,
                        "follow_up_required": True
                    }
                ]
            }
        ]
    },
    "12345678": {  # SpeelgoedPlaza (Fatima scenario)
        "company_name": "SpeelgoedPlaza",
        "inspections": [
            {
                "inspection_id": "INS-2023-005678",
                "date": "2023-08-22",
                "inspector": "Maria de Vries",
                "type": "product_safety",
                "violations": [
                    {
                        "category": "product_labeling",
                        "severity": "warning",
                        "description": "Producten zonder Nederlandstalige gebruiksaanwijzing",
                        "regulation": "Speelgoedrichtlijn 2009/48/EG",
                        "products": ["Product A", "Product B"],
                        "resolved": True
                    }
                ]
            }
        ]
    },
    "87654321": {  # Slagerij de Boer (Jan scenario)
        "company_name": "Slagerij de Boer",
        "inspections": [
            {
                "inspection_id": "INS-2021-009876",
                "date": "2021-11-10",
                "inspector": "Kees Bakker",
                "type": "food_safety_labeling",
                "violations": [
                    {
                        "category": "food_labeling",
                        "severity": "warning",
                        "description": "Onvolledige ingrediëntenvermelding bij zelfgemaakte vleeswaren",
                        "regulation": "EU Verordening 1169/2011",
                        "resolved": False,
                        "follow_up_date": "2022-02-10"
                    }
                ]
            }
        ]
    }
}
```

**Implementation Timeline:** 
- **Effort:** 4-6 hours
- **Complexity:** Low (FastMCP + in-memory dict)
- **Dependencies:** None
- **Priority:** 🔥 Critical for demo

---

## Secondary Gaps (Not Demo-Blocking)

### 1. Product Scanning (Fatima scenario)
**Impact:** Medium  
**Workaround:** Manual product entry via voice/text

**If needed later:**
- Build `product-compliance` MCP server
- Tools: `lookup_product(barcode)`, `check_ce_marking(product_id)`
- Data source: External product safety database or fake data

### 2. Foto/Evidence Management
**Impact:** Low  
**Workaround:** Photos can be handled separately

**If needed later:**
- Extend reporting MCP server
- Add tools: `upload_photo(session_id, photo)`, `annotate_photo()`
- Storage: Local filesystem or S3

### 3. Client Communication Templates
**Impact:** Low  
**Workaround:** Reporting agent can generate basic text

**If needed later:**
- Add templates to reporting agent instructions
- Tools: `generate_warning_letter()`, `generate_follow_up_email()`

### 4. Dossier Agent
**Impact:** Medium-Low  
**Workaround:** Users can call KVK + Inspection History separately

**If wanted:**
- New agent that orchestrates:
  - KVK Lookup
  - Inspection History
  - Regulation Analysis (based on SBI codes)
- Provides unified "company dossier" view

---

## Recommendations

### Phase 1: Demo Readiness (This Week)

**DO:**
1. ✅ Build fake Inspection History MCP server
2. ✅ Add 3-5 demo companies with realistic data
3. ✅ Test all three scenarios end-to-end

**DON'T:**
- ❌ Build process-verbaal agent (explicitly excluded)
- ❌ Integrate real NVWA databases (no access yet)
- ❌ Build product scanning (nice-to-have)

### Phase 2: Production Readiness (Future)

1. **Data Integration:**
   - Connect real NVWA inspection database
   - Replace fake server with real data adapter

2. **Additional Agents:**
   - Dossier Agent (orchestration)
   - Process-verbaal Agent (if approved)

3. **Enhanced Capabilities:**
   - Product compliance database
   - Photo/evidence management
   - Digital signatures

---

## Technical Integration

### Update Agent Routing (Optional)

If we add Dossier Agent:

```python
# server-openai/src/agora_openai/core/routing_logic.py
class AgentSelection(BaseModel):
    selected_agent: Literal[
        "regulation-agent",
        "reporting-agent",
        "dossier-agent",  # NEW: For company history queries
    ]
```

### Update MCP Configuration

```bash
# server-openai/.env
APP_MCP_SERVERS=regulation-analysis=http://localhost:5002,reporting=http://localhost:5003,kvk-lookup=http://localhost:5004,inspection-history=http://localhost:5005
```

### Update Docker Compose

```yaml
# mcp-servers/docker-compose.yml
inspection-history:
  build: ./inspection-history
  ports:
    - "5005:8000"
  environment:
    - LOG_LEVEL=INFO
  networks:
    - agora-network
```

---

## Testing Checklist

### Scenario 1: Koen (Restaurant Bella Rosa)
- [ ] Start inspectie bij Restaurant Bella Rosa
- [ ] Vraag: "Zijn er eerdere overtredingen bekend?"
- [ ] AGORA antwoordt met mei 2022 waarschuwing
- [ ] Dicteer bevindingen over rauwe vis
- [ ] Genereer rapport met herhalingsindicatie

### Scenario 2: Fatima (SpeelgoedPlaza)
- [ ] Start inspectie bij SpeelgoedPlaza  
- [ ] Vraag: "Zijn er eerder onveilige producten aangetroffen?"
- [ ] AGORA antwoordt met 2023 waarschuwing labeling
- [ ] Registreer CE-markering issues
- [ ] Genereer rapport met productlijst

### Scenario 3: Jan (Slagerij de Boer)
- [ ] Start inspectie bij Slagerij de Boer
- [ ] Vraag: "Wat is er eerder geconstateerd?"
- [ ] AGORA antwoordt met 2021 waarschuwing ingrediënten
- [ ] Constateer herhaalde etikettering issues
- [ ] Genereer rapport met escalatie-suggestie

---

## Conclusion

**You need to build 1 thing: Fake Inspection History MCP Server**

Once that's in place, all three scenarios will be fully demonstrable with the existing agents and MCP servers.

**Timeline:**
- ⏰ Inspection History server: 4-6 hours
- ✅ Integration testing: 2-3 hours
- 🎯 **Total: 1 day to demo-ready**

Everything else can wait for future iterations.

