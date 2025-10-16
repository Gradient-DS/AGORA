# Company & Compliance MCP Server

Mock MCP server providing company profiles and inspection history data for NVWA inspectors.

## Tools

### get_company_profile
Fetch core business, permit, and registration info for a company.

**Input:**
```json
{
  "company_id": "string"
}
```

**Output:**
```json
{
  "name": "string",
  "address": "string",
  "permit_status": "string",
  "business_activities": ["string"],
  "registration_date": "string"
}
```

### fetch_inspection_history
Retrieve past inspection records for a company.

**Input:**
```json
{
  "company_id": "string",
  "limit": "number (optional, default: 10)"
}
```

**Output:**
```json
{
  "records": [
    {
      "date": "string",
      "type": "string",
      "findings": "string",
      "sanctions": "string | null"
    }
  ]
}
```

## Resources

- `company_profile://{company_id}` - Company profile data
- `inspection_record://{company_id}/{record_id}` - Individual inspection records

## Running

### With Docker
```bash
docker build -t mcp-company-compliance .
docker run -i mcp-company-compliance
```

### Locally
```bash
pip install -r requirements.txt
python server.py
```

## Mock Data

The server includes mock data for three companies:
- C001: De Verse Bakker BV (active bakery)
- C002: FreshMart Supermarkt (active retail)
- C003: Import Foods International (suspended import/wholesale)

