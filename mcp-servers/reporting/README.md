# HAP Inspection Report Automation Server

Automated HAP (Hygiëne en ARBO Protocol) inspection report generation for NVWA inspectors using conversation analysis and structured data extraction.

## Overview

This MCP server analyzes inspection conversations, extracts structured HAP form data, verifies missing information with inspectors, and generates comprehensive reports in both JSON and PDF formats.

## Features

- **Conversation Analysis**: Uses GPT-4 to extract inspection data from natural language conversations
- **Structured Data Extraction**: Maps conversational findings to official HAP form structure
- **Smart Verification**: Identifies missing/uncertain fields and generates clarifying questions
- **Dual-Format Reports**: Generates both JSON (for systems) and PDF (for humans)
- **File-Based Storage**: Temporary session management with organized file structure
- **Confidence Scoring**: Tracks confidence levels for all extracted fields

## MCP Tools

### 1. `start_inspection_report`
Initialize a new HAP inspection report session.

```json
{
  "session_id": "unique-session-id",
  "company_name": "Restaurant Bella Rosa",
  "company_address": "Haagweg 123, Den Haag",
  "inspector_name": "Koen van der Berg"
}
```

### 2. `extract_inspection_data`
Extract structured HAP data from conversation history.

```json
{
  "session_id": "unique-session-id",
  "conversation_history": [
    {"role": "user", "content": "Start inspectie bij Restaurant Bella Rosa"},
    {"role": "assistant", "content": "..."}
  ]
}
```

### 3. `verify_inspection_data`
Generate verification questions for missing fields.

```json
{
  "session_id": "unique-session-id",
  "max_questions": 5
}
```

### 4. `submit_verification_answers`
Process inspector's answers to verification questions.

```json
{
  "session_id": "unique-session-id",
  "answers": {
    "company_name": "Restaurant Bella Rosa",
    "hygiene_general.compliant": "Nee"
  }
}
```

### 5. `generate_final_report`
Create final JSON and PDF reports.

```json
{
  "session_id": "unique-session-id"
}
```

### 6. `get_report_status`
Check report completion and status.

```json
{
  "session_id": "unique-session-id"
}
```

## Workflow

### Phase 1: Data Extraction
1. Inspector completes inspection conversation
2. System calls `extract_inspection_data` with full conversation history
3. AI extracts all known HAP fields with confidence scores
4. Returns draft data + fields needing verification

### Phase 2: Verification
1. System calls `verify_inspection_data` with draft data
2. AI generates 3-5 targeted questions for missing critical fields
3. Inspector answers via chat interface
4. System calls `submit_verification_answers` to update draft

### Phase 3: Generation
1. System calls `generate_final_report`
2. Generator creates structured JSON matching HAP schema
3. Generator creates formatted PDF with all sections
4. Both files saved to `storage/{session_id}/`
5. Return download links and summary

## HAP Report Structure

### Categories Covered:
- **Hygiëne Algemeen**: Cleanliness, facilities, equipment
- **Ongediertebestrijding**: Pest control and prevention
- **Veilig Omgaan met Voedsel**: Food safety, storage, temperatures
- **Allergeneninformatie**: Allergen labeling and information
- **Aanvullende Informatie**: Inspector notes, hygiene codes, repeat violations

### Violation Severity:
- **Ernstige overtreding** (Serious): Direct food safety risk
- **Overtreding** (Moderate): Hygiene deficiencies
- **Geringe overtreding** (Minor): Minor issues

## NVWA Scenario Coverage

### Scenario 1: Koen (Horeca Inspection)
- Extracts: Restaurant details, hygiene violations, temperature issues
- Maps to: HAP hygiene categories, food safety fields
- Generates: Process-verbaal for serious violations

### Scenario 2: Fatima (Product Safety)
- Extracts: Product scans, CE markings, documentation
- Maps to: Product compliance fields
- Generates: Product safety report with items list

### Scenario 3: Jan (Butcher Shop)
- Extracts: Labeling violations, repeat offenses
- Maps to: HAP labeling fields, historical flags
- Generates: Follow-up enforcement report

## Storage Structure

```
storage/
├── reports/
│   └── {session_id}/
│       ├── draft_data.json
│       ├── final_report.json
│       └── final_report.pdf
└── conversation_history/
    └── {session_id}.json
```

## Dependencies

- **pydantic**: Data validation and schema enforcement
- **openai**: GPT-4 for conversation analysis
- **reportlab**: PDF generation
- **fastmcp**: MCP server framework

## Configuration

Set the following environment variable:

```bash
export OPENAI_API_KEY="your-openai-api-key"
```

## Running

### With Docker
```bash
docker build -t mcp-reporting .
docker run -p 8000:8000 -e OPENAI_API_KEY=$OPENAI_API_KEY mcp-reporting
```

### Locally
```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your-key"
python server.py
```

## Health Check

```bash
curl http://localhost:8000/health
```

## Example Usage

```python
# 1. Start report
result = await start_inspection_report(
    session_id="session-123",
    company_name="Restaurant Bella Rosa",
    inspector_name="Koen van der Berg"
)

# 2. Extract data
result = await extract_inspection_data(
    session_id="session-123",
    conversation_history=messages
)

# 3. Verify if needed
if result["completeness"]["needs_verification"]:
    questions = await verify_inspection_data(session_id="session-123")
    # Ask inspector questions...
    await submit_verification_answers(session_id="session-123", answers=answers)

# 4. Generate final report
report = await generate_final_report(session_id="session-123")
print(f"Report generated: {report['paths']}")
```

## Integration with AGORA

The reporting agent automatically uses these tools when inspectors request report generation:

**Trigger phrases:**
- "Genereer rapport"
- "Maak inspectierapport"
- "Finaliseer documentatie"
- "Rondt inspectie af"

## Future Enhancements

- Database storage (PostgreSQL/Supabase)
- Photo/evidence attachment handling
- Digital signature integration
- Multi-language support (Dutch/English)
- Offline mode support
- Real-time collaboration
- Template customization

## License

Internal NVWA/AGORA project
