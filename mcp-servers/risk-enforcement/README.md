# Risk & Enforcement MCP Server

Mock MCP server for calculating risk scores and flagging companies for enforcement actions.

## Tools

### calculate_risk_score
Calculate risk score based on inspection history, business activities, and geographic region.

**Input:**
```json
{
  "history": [
    {
      "date": "string",
      "type": "string",
      "findings": "string",
      "sanctions": "string | null"
    }
  ],
  "business_activities": ["string"],
  "region": "string"
}
```

**Output:**
```json
{
  "risk_score": "number (0-1)",
  "risk_category": "low | medium | high",
  "contributing_factors": [
    {
      "factor": "string",
      "weight": "number",
      "score": "number",
      "contribution": "number"
    }
  ],
  "recommendation": "string",
  "calculated_at": "string (ISO timestamp)"
}
```

### flag_for_enforcement
Flag a company for enforcement action based on violations.

**Input:**
```json
{
  "company_id": "string",
  "violation_id": "string",
  "severity": "low | medium | high",
  "justification": "string"
}
```

**Output:**
```json
{
  "enforcement_id": "string",
  "company_id": "string",
  "violation_id": "string",
  "severity": "string",
  "status": "flagged",
  "justification": "string",
  "recommended_actions": ["string"],
  "timeline": "string",
  "flagged_at": "string (ISO timestamp)",
  "assigned_to": "string",
  "escalation_required": "boolean"
}
```

## Running

### With Docker
```bash
docker build -t mcp-risk-enforcement .
docker run -i mcp-risk-enforcement
```

### Locally
```bash
pip install -r requirements.txt
python server.py
```

## Risk Calculation

The risk score (0-1) is calculated using weighted factors:
- **Inspection History (35%)**: Based on violation rate in past inspections
- **Business Activities (25%)**: Higher risk for import, production, catering
- **Region (15%)**: Port areas and border regions have higher risk
- **Compliance Record (25%)**: Based on recent compliance performance

### Risk Categories
- **Low (< 0.3)**: Standard inspection frequency
- **Medium (0.3-0.6)**: Increased monitoring recommended
- **High (> 0.6)**: Priority for targeted inspection

