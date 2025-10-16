# Utilities MCP Server

Mock MCP server providing utility tools for NVWA inspectors, including text translation.

## Tools

### translate_text
Translate text between supported languages.

**Input:**
```json
{
  "text": "string",
  "target_language": "en | de | fr | es | nl"
}
```

**Output:**
```json
{
  "original_text": "string",
  "translated": "string",
  "target_language": "string",
  "source_language_detected": "string",
  "confidence": "number"
}
```

## Supported Languages

- **en**: English
- **de**: German (Deutsch)
- **fr**: French (Français)
- **es**: Spanish (Español)
- **nl**: Dutch (Nederlands)

## Running

### With Docker
```bash
docker build -t mcp-utilities .
docker run -i mcp-utilities
```

### Locally
```bash
pip install -r requirements.txt
python server.py
```

## Use Cases

- Translating foreign product documentation
- Understanding labels on imported goods
- Communicating with international stakeholders
- Translating inspection reports for international cooperation

## Notes

This is a mock implementation with basic keyword-based translation. In production, this would integrate with a proper translation service like Google Translate, DeepL, or similar.

