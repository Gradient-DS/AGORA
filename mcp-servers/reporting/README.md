# Reporting MCP Server

Mock MCP server for generating inspection reports for NVWA inspectors.

## Tools

### generate_inspection_report
Generate a draft inspection report based on inspection data, history, and notes.

**Input:**
```json
{
  "company_id": "string",
  "inspection_data": {
    "date": "string (optional)",
    "type": "string (optional)",
    "findings": ["string"] or "string"
  },
  "history": [
    {
      "date": "string",
      "type": "string",
      "findings": "string",
      "sanctions": "string | null"
    }
  ],
  "notes": "string (optional)"
}
```

**Output:**
```json
{
  "report_text": "string (full report text)",
  "sections": [
    {
      "title": "string",
      "content": "string"
    }
  ],
  "confidence": "number (0-1)",
  "resource_uri": "string (e.g., report_file://REP-0001)"
}
```

## Resources

- `report_file://{report_id}` - Generated report file (stored in memory during server runtime)

## Running

### With Docker
```bash
docker build -t mcp-reporting .
docker run -i mcp-reporting
```

### Locally
```bash
pip install -r requirements.txt
python server.py
```

## Features

- Generates structured inspection reports with multiple sections
- Analyzes findings to identify compliance issues
- Provides recommendations based on findings
- Includes historical context from previous inspections
- Returns confidence score based on data completeness
- Stores generated reports as resources for later retrieval

