# Regulation & Analysis MCP Server

Mock MCP server providing regulation lookup and document analysis capabilities for NVWA inspectors.

## Tools

### lookup_regulation_articles
Search for relevant regulation articles by domain and keywords.

**Input:**
```json
{
  "domain": "food_safety | product_safety | animal_welfare",
  "keywords": ["string"]
}
```

**Output:**
```json
{
  "articles": [
    {
      "id": "string",
      "title": "string",
      "text": "string",
      "url": "string"
    }
  ],
  "domain": "string",
  "keywords_searched": ["string"]
}
```

### analyze_document
Analyze a document for summary, risks, or non-compliance issues.

**Input:**
```json
{
  "document_uri": "string",
  "analysis_type": "summary | risks | noncompliance"
}
```

**Output (varies by analysis_type):**

**Summary:**
```json
{
  "summary": "string",
  "key_points": ["string"],
  "page_count": "number",
  "confidence": "number"
}
```

**Risks:**
```json
{
  "identified_risks": [
    {
      "risk": "string",
      "severity": "string",
      "likelihood": "string",
      "mitigation": "string"
    }
  ],
  "overall_risk_level": "string",
  "confidence": "number"
}
```

**Non-compliance:**
```json
{
  "violations": [
    {
      "regulation_id": "string",
      "description": "string",
      "severity": "string",
      "page_reference": "string",
      "remediation_required": "string"
    }
  ],
  "compliance_score": "number",
  "confidence": "number"
}
```

## Resources

- `regulation_catalog://{domain}` - Complete regulation library for a domain

## Running

### With Docker
```bash
docker build -t mcp-regulation-analysis .
docker run -i mcp-regulation-analysis
```

### Locally
```bash
pip install -r requirements.txt
python server.py
```

## Mock Data

The server includes regulations for:
- food_safety (temperature control, HACCP, allergen labeling)
- product_safety (general safety, CE marking)
- animal_welfare (transport regulations)

