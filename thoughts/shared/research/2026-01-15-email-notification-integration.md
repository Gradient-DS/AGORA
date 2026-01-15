---
date: 2026-01-15T14:30:00+01:00
researcher: Claude
git_commit: 3a26a07069b256101c1f2f9cd715b33c499e9a43
branch: fix/parallel-stream-context
repository: Gradient-DS/AGORA
topic: "Email Notification Integration for Report Generation"
tags: [research, codebase, reporting, mcp-server, microsoft-graph, email]
status: complete
last_updated: 2026-01-15
last_updated_by: Claude
---

# Research: Email Notification Integration for Report Generation

**Date**: 2026-01-15T14:30:00+01:00
**Researcher**: Claude
**Git Commit**: 3a26a07069b256101c1f2f9cd715b33c499e9a43
**Branch**: fix/parallel-stream-context
**Repository**: Gradient-DS/AGORA

## Research Question
Where and how should email functionality be implemented in AGORA to send notifications when reports are generated? The goal is to use Microsoft Graph API for email delivery.

## Summary

The ideal integration point is the **reporting MCP server** at `mcp-servers/reporting/server.py`, specifically within the `generate_final_report` tool. After PDF generation succeeds, email sending can be triggered as an additional side effect. This follows the existing pattern of MCP tools having file-system side effects and keeps the email logic co-located with report generation.

**Required Environment Variables:**
- `MCP_GRAPH_TENANT_ID` - Azure AD tenant ID
- `MCP_GRAPH_CLIENT_ID` - Azure AD app client ID
- `MCP_GRAPH_CLIENT_SECRET` - Azure AD app client secret
- `MCP_GRAPH_MAIL_SENDER_ADDRESS` - Email address to send from
- `MCP_GRAPH_MAIL_SENDER_DISPLAY` - Display name for sender (optional, default "AGORA")

## Detailed Findings

### Integration Point: `generate_final_report` Tool

**File**: `mcp-servers/reporting/server.py:292-361`

The `generate_final_report` tool is the natural integration point for email notifications:

```python
@mcp.tool
async def generate_final_report(session_id: str) -> dict:
    # ... existing code ...

    # Line 332-333: PDF and JSON generation
    json_data = json_generator.generate(hap_report)
    pdf_content = pdf_generator.generate(hap_report)

    # Line 335: File storage
    paths = session_manager.finalize_report(session_id, json_data, pdf_content)

    # << EMAIL INTEGRATION POINT >>
    # Add email sending here, after successful report generation

    # Line 339-343: Return download URLs
    return { ... }
```

**Why this location?**
1. Report has been successfully generated and saved
2. We have the PDF content in memory for attachment
3. We have session metadata for recipient email
4. Follows existing pattern of tools having side effects

### Existing Patterns for Side Effects

MCP tools already perform side effects in the reporting server:

| Tool | Side Effects |
|------|--------------|
| `start_inspection_report` | Creates session in memory + saves draft to disk |
| `extract_inspection_data` | Updates draft JSON on disk |
| `generate_final_report` | Saves JSON + PDF to `./storage/reports/{session_id}/` |

Adding email sending is consistent with this pattern.

### Environment Variable Pattern

The reporting server uses direct `os.getenv()` rather than Pydantic Settings:

**Current pattern** (`server.py:20`):
```python
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("MCP_OPENAI_API_KEY", "")
```

**Recommended email configuration** (same pattern):
```python
GRAPH_TENANT_ID = os.getenv("MCP_GRAPH_TENANT_ID") or os.getenv("GRAPH_TENANT_ID")
GRAPH_CLIENT_ID = os.getenv("MCP_GRAPH_CLIENT_ID") or os.getenv("GRAPH_CLIENT_ID")
GRAPH_CLIENT_SECRET = os.getenv("MCP_GRAPH_CLIENT_SECRET") or os.getenv("GRAPH_CLIENT_SECRET")
GRAPH_MAIL_SENDER = os.getenv("MCP_GRAPH_MAIL_SENDER_ADDRESS") or os.getenv("GRAPH_MAIL_SENDER_ADDRESS")
GRAPH_MAIL_DISPLAY = os.getenv("MCP_GRAPH_MAIL_SENDER_DISPLAY", "AGORA")
```

### Session Data for Recipient Email

Currently, session data does not store recipient email. We need to:

1. **Option A**: Add `inspector_email` parameter to `start_inspection_report`
2. **Option B**: Store email in session metadata via a new parameter
3. **Option C**: Create a new tool `send_report_email` that takes email as parameter

**Recommended: Option A** - Extend `start_inspection_report`:

```python
async def start_inspection_report(
    session_id: str,
    company_id: str = None,
    company_name: str = None,
    company_address: str = None,
    inspector_name: str = None,
    inspector_email: str = None,  # NEW
) -> dict:
```

### Implementation Approach

#### Step 1: Add Email Service Module

Create `mcp-servers/reporting/services/email_service.py`:

```python
"""Microsoft Graph API mailer service for AGORA reports."""

import logging
import os
from typing import Optional
import requests

logger = logging.getLogger(__name__)

# Configuration
TENANT_ID = os.getenv("MCP_GRAPH_TENANT_ID") or os.getenv("GRAPH_TENANT_ID")
CLIENT_ID = os.getenv("MCP_GRAPH_CLIENT_ID") or os.getenv("GRAPH_CLIENT_ID")
CLIENT_SECRET = os.getenv("MCP_GRAPH_CLIENT_SECRET") or os.getenv("GRAPH_CLIENT_SECRET")
SENDER_ADDRESS = os.getenv("MCP_GRAPH_MAIL_SENDER_ADDRESS") or os.getenv("GRAPH_MAIL_SENDER_ADDRESS")
SENDER_DISPLAY = os.getenv("MCP_GRAPH_MAIL_SENDER_DISPLAY", "AGORA")

def is_email_configured() -> bool:
    """Check if email is configured."""
    return all([TENANT_ID, CLIENT_ID, CLIENT_SECRET, SENDER_ADDRESS])

def get_graph_token() -> str:
    """Get bearer token for Microsoft Graph."""
    # ... implementation from reference code ...

def send_report_email(
    to_email: str,
    report_id: str,
    company_name: str,
    download_url: str,
    pdf_attachment: Optional[bytes] = None,
) -> bool:
    """Send report notification email."""
    # ... implementation ...
```

#### Step 2: Update generate_final_report

```python
# At top of server.py
from services.email_service import is_email_configured, send_report_email

# In generate_final_report, after line 335:
# Send email notification if configured
if is_email_configured():
    session = session_manager.get_session(session_id)
    inspector_email = session.get("inspector_email")
    if inspector_email:
        try:
            send_report_email(
                to_email=inspector_email,
                report_id=report_id,
                company_name=session.get("company_name", "Onbekend bedrijf"),
                download_url=download_urls["pdf"],
                pdf_attachment=pdf_content,
            )
            logger.info(f"Report email sent to {inspector_email}")
        except Exception as e:
            logger.error(f"Failed to send report email: {e}")
            # Don't fail the tool call - email is non-critical
```

#### Step 3: Update SessionManager

In `mcp-servers/reporting/storage/session_manager.py`, store inspector_email:

```python
def create_session(
    self,
    session_id: str,
    company_id: Optional[str] = None,
    company_name: Optional[str] = None,
    inspector_name: Optional[str] = None,
    inspector_email: Optional[str] = None,  # NEW
) -> dict:
    # ... existing code ...
    session_data = {
        "session_id": session_id,
        "report_id": report_id,
        "company_id": company_id,
        "company_name": company_name,
        "inspector_name": inspector_name,
        "inspector_email": inspector_email,  # NEW
        # ...
    }
```

#### Step 4: Add Dependencies

Add to `mcp-servers/reporting/requirements.txt`:
```
requests>=2.31.0
```

### Docker Configuration

Update `mcp-servers/docker-compose.yml` for the reporting service:

```yaml
reporting:
  env_file:
    - ../.env
  environment:
    MCP_GRAPH_TENANT_ID: ${MCP_GRAPH_TENANT_ID}
    MCP_GRAPH_CLIENT_ID: ${MCP_GRAPH_CLIENT_ID}
    MCP_GRAPH_CLIENT_SECRET: ${MCP_GRAPH_CLIENT_SECRET}
    MCP_GRAPH_MAIL_SENDER_ADDRESS: ${MCP_GRAPH_MAIL_SENDER_ADDRESS}
    MCP_GRAPH_MAIL_SENDER_DISPLAY: ${MCP_GRAPH_MAIL_SENDER_DISPLAY:-AGORA}
```

## Code References

- `mcp-servers/reporting/server.py:292-361` - `generate_final_report` tool (integration point)
- `mcp-servers/reporting/server.py:32-86` - `start_inspection_report` tool (add email param)
- `mcp-servers/reporting/server.py:20` - Environment variable pattern
- `mcp-servers/reporting/storage/session_manager.py:15-48` - Session creation
- `mcp-servers/reporting/generators/pdf_generator.py:49-96` - PDF generation
- `mcp-servers/docker-compose.yml:31-56` - Docker config for reporting

## Architecture Insights

### MCP Tool Side Effects Pattern
AGORA's MCP tools are designed to have side effects. The reporting server already:
- Writes files to disk
- Maintains session state
- Makes external API calls (OpenAI)

Adding email sending is consistent with this architecture.

### Error Handling Philosophy
Email sending should be **non-critical** - if it fails, the tool should still return success with the generated report. The email failure should be logged but not block the workflow.

### Alternative: Separate Email Tool
An alternative architecture would be a separate `send_report_email` tool that the agent calls explicitly after report generation. This gives the agent more control but requires updating agent instructions.

## Environment Variables Summary

| Variable | Required | Description |
|----------|----------|-------------|
| `MCP_GRAPH_TENANT_ID` | Yes | Azure AD tenant ID |
| `MCP_GRAPH_CLIENT_ID` | Yes | Azure AD application client ID |
| `MCP_GRAPH_CLIENT_SECRET` | Yes | Azure AD application client secret |
| `MCP_GRAPH_MAIL_SENDER_ADDRESS` | Yes | Email address to send from |
| `MCP_GRAPH_MAIL_SENDER_DISPLAY` | No | Display name (default: "AGORA") |

## Implementation Summary (2026-01-15)

The following changes have been implemented:

### Files Created
- `mcp-servers/reporting/services/__init__.py` - Service module exports
- `mcp-servers/reporting/services/email_service.py` - Microsoft Graph API email service

### Files Modified

**Frontend (HAI/):**
- `src/types/user.ts` - Added `email_reports?: boolean` to UserPreferences
- `src/components/admin/UserForm.tsx` - Added email reports toggle UI
- `src/components/layout/Header.tsx` - Added email reports badge display

**Backend (server-langgraph/):**
- `src/agora_langgraph/api/server.py` - Added email_reports to preferences validation
- `src/agora_langgraph/pipelines/orchestrator.py` - Fetch and pass user email/preferences to metadata
- `src/agora_langgraph/core/agents.py` - Inject user context for reporting-agent

**Backend (server-openai/):**
- `src/agora_openai/api/server.py` - Added email_reports to preferences validation

**MCP Servers:**
- `mcp-servers/reporting/server.py` - Added inspector_email and send_email parameters
- `mcp-servers/reporting/storage/session_manager.py` - Store inspector_email in session
- `mcp-servers/reporting/requirements.txt` - Added requests>=2.31.0

**Configuration:**
- `.env.example` - Added Microsoft Graph API environment variables
- `mcp-servers/docker-compose.yml` - Added Graph API env vars for reporting service

### Follow-up Work
- **server-openai context injection**: The OpenAI Agents SDK uses static agent instructions. Full context injection for server-openai would require either creating dynamic agents per request or passing context via the conversation. This can be addressed in a follow-up PR.

## Open Questions (Resolved)

1. **PDF Attachment**: Implemented - PDF is attached to the email.

2. **Email Template**: Implemented - Dutch template with NVWA branding.

3. **Recipient Email Source**: Implemented - Uses the user's email from the user management system. The orchestrator fetches user info and passes it to the reporting agent via metadata.

4. **Email Opt-out**: Implemented - `email_reports` user preference controls whether emails are sent.

5. **Multiple Recipients**: Not implemented - currently single recipient only.
