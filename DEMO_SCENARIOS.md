# AGORA v1.0 - Demo Scenarios Guide

Complete walkthrough of the three inspector scenarios using AGORA's MCP servers and agents.

---

## 📋 Quick Copy-Paste Inputs for Demo

### Scenario 1: Inspecteur Koen – Restaurant Bella Rosa

```
Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854
```

```
Welke europese wetgeving heeft betrekking op het niet ingevulde schoonmaakschema?
```

```
Ik zie een geopende ton met rauwe vis op kamertemperatuur naast een afvoerputje vol schoonmaakmiddelresten, welke regels worden hiermee overtreden?
```

```
Genereer rapport
```

---

### Scenario 2: Inspecteur Fatima – SpeelgoedPlaza

```
Start inspectie bij SpeelgoedPlaza
```

```
92262856
```

```
Zijn er eerder onveilige producten aangetroffen?
```

```
Geen CE-markering zichtbaar op product, geen conformiteitsverklaring aanwezig
```

```
Welke regelgeving is van toepassing voor CE-markering?
```

```
Genereer rapport
```

---

### Scenario 3: Inspecteur Jan – Slagerij de Boer

```
Start inspectie bij Slagerij de Boer
```

```
34084173
```

```
Wat is er eerder geconstateerd?
```

```
Ongeëtiketteerde producten in de koeling, herhaling van eerdere overtreding
```

```
Genereer rapport met escalatie
```

---

## Setup

Ensure all MCP servers are running:
```bash
cd mcp-servers
docker-compose up
```

Verify health:
```bash
curl http://localhost:5002/health  # Regulation Analysis
curl http://localhost:5003/health  # Reporting
curl http://localhost:5004/health  # KVK Lookup
curl http://localhost:5005/health  # Inspection History
```

---

## Scenario 1: Inspecteur Koen – Restaurant Bella Rosa

**Context:** Reguliere hygiënecontrole bij een restaurant in Den Haag

### Step 1: Start Inspection
**Inspector says:** "Start inspectie bij Restaurant Bella Rosa"

**System workflow:**
1. Agent recognizes inspection start trigger
2. May prompt for KVK number if not in system

### Step 2: Get Company Information
**Inspector says:** "Wat zijn de bedrijfsgegevens?" or provides KVK: "59581883"

**MCP Calls:**
```bash
# 1. KVK Lookup - Get company info
curl -X POST http://localhost:5004/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_company_info",
    "arguments": {"kvk_number": "59581883"}
  }'
```

**Response:**
- Company name, legal form, registration date
- SBI codes (e.g., 5610 - Restaurants)
- Active status
- Postal region

**Agent response:**
"Restaurant is geregistreerd als BV sinds 2019. Het bedrijf is actief en valt onder SBI code 5610 (Restaurants). De Hygiënecode voor de Horeca en Warenwetregeling zijn van toepassing."

### Step 3: Check Inspection History
**Inspector says:** "Zijn er eerdere overtredingen bekend?"

**MCP Calls:**
```bash
# 2. Inspection History - Get history
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_inspection_history",
    "arguments": {"kvk_number": "59581883"}
  }'

# 3. Get violations specifically
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_company_violations",
    "arguments": {"kvk_number": "59581883"}
  }'
```

**Agent response:**
"Ja, er is 1 eerdere overtreding bekend:
- **Datum:** 15 mei 2022
- **Overtreding:** Onvoldoende hygiënemaatregelen in de keuken
- **Ernst:** Waarschuwing
- **Status:** Nog niet opgelost
- **Regelgeving:** Hygiënecode Horeca artikel 4.2
- **Follow-up vereist:** Ja, gepland op 15 augustus 2022 maar nog niet uitgevoerd"

### Step 4: Document Findings
**Inspector says:** "Ik zie een geopende ton met rauwe vis op kamertemperatuur naast een afvoerputje vol schoonmaakmiddelresten"

**System captures:**
- Finding description
- Likely violation category (hygiene_measures, temperature_control)

### Step 5: Check for Repeat Violation
**System automatically calls:**
```bash
# 4. Check if this is a repeat
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "check_repeat_violation",
    "arguments": {
      "kvk_number": "59581883",
      "violation_category": "hygiene_measures"
    }
  }'
```

**Response:**
```json
{
  "is_repeat": true,
  "enforcement_recommendation": "IMMEDIATE_ACTION_REQUIRED",
  "escalation_reason": "This company has 1 previous violation(s) in category 'hygiene_measures'. 1 violation(s) remain unresolved.",
  "previous_occurrences": 1
}
```

**Agent response:**
"⚠️ **WAARSCHUWING:** Dit is een herhaalde overtreding. In mei 2022 was er een soortgelijk probleem met hygiënemaatregelen dat nog niet is opgelost. **Escalatie geadviseerd.**"

### Step 6: Get Applicable Regulations
**Inspector says:** "Welke regelgeving is van toepassing?"

**MCP Call:**
```bash
# 5. Regulation Analysis - Search regulations
curl -X POST http://localhost:5002/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "search_regulations",
    "arguments": {
      "query": "bewaren rauwe vis temperatuur hygiëne horeca",
      "filters": {"source_type": "Dutch"},
      "limit": 3
    }
  }'
```

**Agent response:**
"De volgende regelgeving is van toepassing:
- **Hygiënecode Horeca artikel 4.2** - Hygiënische werkwijze
- **Warenwetregeling Hygiëne van Levensmiddelen** - Bewaartemperaturen bederfelijke waar
- **EU Verordening 852/2004** - Levensmiddelenhygiëne

Bederfelijke levensmiddelen zoals rauwe vis moeten onder 7°C bewaard worden."

### Step 7: Decide on Enforcement
**Inspector says:** "Ik ga handhaven"

**Agent confirms:**
"Gezien de ernst (direct risico voedselvergiftiging), herhaalde overtreding, en onopgeloste eerdere waarschuwing is handhaving passend. Ik bereid het rapport voor."

### Step 8: Generate Report
**Inspector says:** "Genereer rapport"

**MCP Call:**
```bash
# 6. Reporting - Generate inspection report
curl -X POST http://localhost:5003/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "start_inspection_report",
    "arguments": {
      "session_id": "koen-20250116-001",
      "company_name": "Restaurant Bella Rosa",
      "company_address": "Haagweg 123, Den Haag",
      "inspector_name": "Koen van der Berg"
    }
  }'
```

**Report includes:**
- Company info (from KVK)
- Inspection history context (from Inspection History)
- Current findings
- Applicable regulations (from Regulation Analysis)
- Enforcement recommendation
- Repeat violation flag

---

## Scenario 2: Inspecteur Fatima – SpeelgoedPlaza

**Context:** Controle op CE-markeringen bij winkelketen

### Step 1: Start Inspection
**Inspector says:** "Start inspectie bij SpeelgoedPlaza"

### Step 2: Company Lookup
**Inspector provides:** KVK number "12345678"

**MCP Calls:**
```bash
# KVK Lookup
curl -X POST http://localhost:5004/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_company_info",
    "arguments": {"kvk_number": "12345678"}
  }'

# Get activities to determine product categories
curl -X POST http://localhost:5004/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_company_activities",
    "arguments": {"kvk_number": "12345678"}
  }'
```

### Step 3: Check History
**Inspector says:** "Zijn er eerder onveilige producten aangetroffen?"

**MCP Call:**
```bash
# Inspection History
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_inspection_history",
    "arguments": {"kvk_number": "12345678"}
  }'
```

**Agent response:**
"Ja, er is 1 eerdere inspectie:
- **Datum:** 22 augustus 2023
- **Type:** Productveiligheid
- **Bevinding:** 8 speelgoedartikelen zonder Nederlandstalige handleiding
- **Status:** Opgelost (15 september 2023)
- **Conclusie:** Bedrijf heeft direct actie ondernomen en is compliant"

### Step 4: Document Current Findings
**Inspector says:** "Geen CE-markering zichtbaar op product, geen conformiteitsverklaring aanwezig"

### Step 5: Check Regulations
**MCP Call:**
```bash
# Regulation Analysis - EU Toy Directive
curl -X POST http://localhost:5002/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "search_regulations",
    "arguments": {
      "query": "CE markering speelgoed conformiteitsverklaring",
      "filters": {"source_type": "EU"},
      "limit": 3
    }
  }'
```

**Agent response:**
"**Speelgoedrichtlijn 2009/48/EG artikel 11** - Waarschuwingen en veiligheidsinformatie
CE-markering is verplicht voor alle speelgoed dat in de EU wordt verkocht..."

### Step 6: Generate Report
Report includes product photos, CE marking status, and references to resolved previous violation showing company's willingness to comply.

---

## Scenario 3: Inspecteur Jan – Slagerij de Boer

**Context:** Inspectie op verzoek bij dorpsslager

### Step 1: Start Inspection
**Inspector says:** "Start inspectie bij Slagerij de Boer"
**System:** "Wat is het KVK nummer?"
**Inspector:** "87654321"

### Step 2: Company Info
**MCP Calls:**
```bash
# KVK Lookup
curl -X POST http://localhost:5004/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_company_info",
    "arguments": {"kvk_number": "87654321"}
  }'
```

**Agent response:**
"Slagerij de Boer is geregistreerd sinds 1995. Hoofdactiviteit: detailhandel vlees en vleeswaren. Het bedrijf staat onder toezicht vanwege eerdere signalen."

### Step 3: Check History
**Inspector says:** "Wat is er eerder geconstateerd?"

**MCP Calls:**
```bash
# Inspection History - Full history
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_inspection_history",
    "arguments": {"kvk_number": "87654321"}
  }'

# Check follow-ups
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_follow_up_status",
    "arguments": {"kvk_number": "87654321"}
  }'
```

**Agent response:**
"Er zijn 2 eerdere inspecties:

**Inspectie 1 - 10 november 2021:**
- **Overtreding:** Onvolledige ingrediëntenvermelding bij zelfgemaakte vleeswaren
- **Ernst:** Waarschuwing
- **Producten:** Rookworst, leverworst, gehaktballen
- **Regelgeving:** EU Verordening 1169/2011 artikel 9
- **Status:** ONOPGELOST
- **Follow-up:** Gepland 10 februari 2022, maar NIET uitgevoerd
- **Opmerking:** Eigenaar vond etikettering 'overdreven voor lokale klanten'

**Inspectie 2 - 15 juni 2019:**
- Geen bijzonderheden, hygiëne was op orde

⚠️ **WAARSCHUWING:** Er staat 1 follow-up actie open die OVERDUE is (meer dan 2 jaar)."

### Step 4: Current Finding
**Inspector says:** "Ongeëtiketteerde producten in de koeling, herhaling van eerdere overtreding"

### Step 5: Check Repeat
**MCP Call:**
```bash
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "check_repeat_violation",
    "arguments": {
      "kvk_number": "87654321",
      "violation_category": "food_labeling"
    }
  }'
```

**Agent response:**
"🚨 **ESCALATIE VEREIST**
- Dit is een HERHAALDE overtreding
- Vorige overtreding uit 2021 is ONOPGELOST
- Follow-up inspectie heeft NIET plaatsgevonden
- Bedrijf heeft geen corrigerende maatregelen genomen

**Aanbeveling:** Directe handhaving met hogere boete vanwege recidive en gebrek aan medewerking."

### Step 6: Generate Report with Escalation
Report automatically includes:
- Repeat violation marker
- Overdue follow-up status
- Historical context
- Escalation recommendation
- Applicable regulations

---

## Integration Flow: KVK + Inspection History

### Typical Workflow

```
1. Inspector starts inspection
   ↓
2. KVK Lookup provides:
   - Company legal info
   - SBI codes (→ applicable regulations)
   - Active status
   ↓
3. Inspection History provides:
   - Past inspection results
   - Violation patterns
   - Follow-up status
   ↓
4. Regulation Analysis provides:
   - Regulations based on SBI codes
   - Specific articles for violations
   ↓
5. Inspector documents findings
   ↓
6. System checks for repeat violations
   ↓
7. Reporting generates comprehensive report
```

### Example Combined Query

**Inspector says:** "Geef me het complete dossier van bedrijf 59581883"

**System executes in parallel:**
```javascript
await Promise.all([
  kvkLookup.get_company_info("59581883"),
  kvkLookup.get_company_activities("59581883"),
  inspectionHistory.get_inspection_history("59581883"),
  inspectionHistory.get_company_violations("59581883"),
  inspectionHistory.get_follow_up_status("59581883")
])
```

**Agent synthesizes response:**
"# Bedrijfsdossier Restaurant Bella Rosa (KVK: 59581883)

## Bedrijfsgegevens
- **Rechtsvorm:** BV
- **Registratie:** 2019
- **Status:** Actief
- **Sector:** Horeca (SBI 5610 - Restaurants)

## Inspectiehistorie
- **Totaal inspecties:** 2 (2020, 2022)
- **Laatste inspectie:** 15 mei 2022
- **Overtredingen:** 1 actieve waarschuwing

## Openstaande zaken
⚠️ 1 onopgeloste overtreding uit 2022:
- Onvoldoende hygiënemaatregelen
- Follow-up nog niet uitgevoerd

## Toepasselijke regelgeving
Op basis van SBI code 5610:
- Hygiënecode voor de Horeca
- Warenwetregeling Hygiëne van Levensmiddelen
- EU Verordening 852/2004

## Risicoprofiel
🟡 MEDIUM - Actieve onopgeloste overtreding vereist extra aandacht"

---

## Testing the Demo

### Test All Three Scenarios

```bash
# Test Scenario 1 - Koen
curl -X POST http://localhost:5004/mcp/tools/call -H "Content-Type: application/json" \
  -d '{"name": "get_company_info", "arguments": {"kvk_number": "59581883"}}'
curl -X POST http://localhost:5005/mcp/tools/call -H "Content-Type: application/json" \
  -d '{"name": "get_inspection_history", "arguments": {"kvk_number": "59581883"}}'

# Test Scenario 2 - Fatima
curl -X POST http://localhost:5004/mcp/tools/call -H "Content-Type: application/json" \
  -d '{"name": "get_company_info", "arguments": {"kvk_number": "12345678"}}'
curl -X POST http://localhost:5005/mcp/tools/call -H "Content-Type: application/json" \
  -d '{"name": "get_inspection_history", "arguments": {"kvk_number": "12345678"}}'

# Test Scenario 3 - Jan
curl -X POST http://localhost:5004/mcp/tools/call -H "Content-Type: application/json" \
  -d '{"name": "get_company_info", "arguments": {"kvk_number": "87654321"}}'
curl -X POST http://localhost:5005/mcp/tools/call -H "Content-Type: application/json" \
  -d '{"name": "check_repeat_violation", "arguments": {"kvk_number": "87654321", "violation_category": "food_labeling"}}'
```

### Verify Integration

All demo KVK numbers should work:
- `59581883` - Restaurant Bella Rosa (repeat offender)
- `12345678` - SpeelgoedPlaza (resolved violations)
- `87654321` - Slagerij de Boer (overdue follow-up)
- `11223344` - Café Het Bruine Paard (clean record)

---

## Key Takeaways

1. **KVK Lookup** provides the business context and determines applicable regulations via SBI codes
2. **Inspection History** provides the compliance track record and identifies repeat violations
3. **Together** they enable intelligent enforcement decisions based on complete company profiles
4. **Regulation Analysis** provides the legal framework for violations
5. **Reporting** synthesizes all information into comprehensive inspection reports

The integration ensures inspectors have complete context for every inspection, leading to:
- ✅ Faster inspections
- ✅ Better enforcement decisions
- ✅ Consistent documentation
- ✅ Clear escalation paths for repeat offenders

