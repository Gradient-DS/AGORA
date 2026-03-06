---
date: 2026-03-06T12:00:00+01:00
researcher: Claude
git_commit: ae92e0e4ea49a2de3196674b6ac60bf107d5cdbc
branch: feat/tool-description
repository: AGORA
topic: "NVWA Rapport van Bevindingen PDF Styling Update"
tags: [research, codebase, reporting, pdf-generation, nvwa-styling, evidence-images]
status: complete
last_updated: 2026-03-06
last_updated_by: Claude
---

# Research: NVWA "Rapport van Bevindingen" PDF Styling Update

**Date**: 2026-03-06T12:00:00+01:00
**Researcher**: Claude
**Git Commit**: ae92e0e4ea49a2de3196674b6ac60bf107d5cdbc
**Branch**: feat/tool-description
**Repository**: AGORA

## Research Question
How should we update the PDF report generator in the reporting MCP server to match the official NVWA "Rapport van Bevindingen" document style, and how do we properly integrate evidence images (with descriptions) into the report?

## Summary

The current PDF generator (`mcp-servers/reporting/generators/pdf_generator.py`) uses a custom style with colored headers (blue), Helvetica fonts, and a structured-but-non-standard layout. To match the NVWA style, we need significant changes to:

1. **Typography**: Switch from Helvetica to Georgia/Times New Roman serif fonts
2. **Color scheme**: Remove all colors — go monochrome (black text only)
3. **Layout**: Update margins, add NVWA logo, proper page numbering ("Pagina X van Y")
4. **Document structure**: Reorder sections to match official NVWA format (Aanleiding → Locatie → Bevinding(en) → Overtreder → Verhoor → Closing)
5. **Images**: Already partially implemented — images appear in an appendix; should also be embeddable inline with findings
6. **Logo**: Download NVWA logo SVG/PNG once and add to repo as an asset

## Detailed Findings

### Current PDF Generator State
- **File**: `mcp-servers/reporting/generators/pdf_generator.py` (425 lines)
- **Library**: ReportLab (SimpleDocTemplate, Platypus flowables)
- **Current styles**:
  - Title: 18pt, blue (#1a365d), centered — needs to become black serif, ALL CAPS, letter-spaced
  - Section headers: 14pt, blue (#2c5282) — needs to become 11pt, bold, black, serif
  - Body: 10pt Normal (Helvetica) — needs to become 10pt Georgia/Times New Roman
  - Violation text: 10pt, red (#742a2a) — needs to become black
- **Current margins**: 2cm all sides — should become 25mm left/right/top, 20mm bottom
- **Current sections**: Header → Summary → Hygiene → Pest Control → Food Safety → Allergens → Violations Summary → Recommendations → Footer → Evidence Appendix
- **Evidence images**: Already implemented in `_create_evidence_appendix()` (lines 379-424) with caption and description support

### Data Model (HAPReport)
- **File**: `mcp-servers/reporting/models/hap_schema.py` (148 lines)
- `InspectionMetadata`: report_id, company_name, company_address, inspection_date, inspection_type, inspector_name, inspector_id
- `HygieneGeneral`, `PestControl`, `FoodSafetyInspection`, `AllergenInformation`: each with compliance fields, violations list, observations
- `AdditionalInformation`: hygiene code, repeat violation, action required, inspector notes
- `Violation`: type, severity, description, location, evidence

### Image Pipeline
- **Upload**: `POST /reports/{session_id}/images` — base64 image stored to disk
- **Storage**: `FileStorage.save_image()` / `load_images()` — manifest.json + image files in `storage/reports/{session_id}/images/`
- **Description update**: `PATCH /reports/{session_id}/images/{index}/description` — for AI-generated descriptions
- **PDF integration**: `generate_final_report()` loads images via `storage.load_images()` and passes to `pdf_generator.generate()`

### Logo Requirements
- No `assets/` directory exists yet in `mcp-servers/reporting/`
- Need to create `mcp-servers/reporting/assets/` and download the NVWA logo
- SVG from Wikimedia Commons (CC-BY-3.0-NL) — need PNG for ReportLab compatibility
- Logo placement: top-right of page 1, ~55mm × 25mm
- Dockerfile needs updating to `COPY assets/ ./assets/`

### Key Gaps Between Current and NVWA Style

| Aspect | Current | NVWA Target |
|--------|---------|-------------|
| Font | Helvetica (sans-serif) | Georgia/Times New Roman (serif) |
| Title | "NVWA INSPECTIE RAPPORT", blue | "RAPPORT VAN BEVINDINGEN", black, ALL CAPS |
| Colors | Blue headers, red violations, beige tables | Monochrome (black only) |
| Logo | None | NVWA logo top-right on page 1 |
| Page numbers | None | "Pagina X van Y" bottom-right |
| Doc number | In metadata table | Top-left, above title |
| Intro paragraph | None | Legal boilerplate (inspector authority under Awb) |
| Section order | Summary → Categories → Violations → Recommendations | Aanleiding → Locatie → Bevinding(en) → Overtreder → Verhoor → Closing |
| Metadata display | Colored table with background | Tab-aligned label:value pairs, plain |
| Margins | 2cm all sides | 25mm left/right/top, 20mm bottom |
| Line spacing | Default | 1.15-1.2x |
| Section spacing | 0.5cm gaps | 12pt before headers, 6pt after paragraphs |
| Evidence images | Appendix at end | Could be inline with findings AND/OR appendix |
| Footer | "Automatisch gegenereerd door AGORA" | Formal closing declaration + signature block |

### Implementation Approach

#### 1. Assets Setup
- Create `mcp-servers/reporting/assets/` directory
- Download NVWA logo as PNG (ReportLab can't natively render SVG; need PNG or use `svglib`)
- Update Dockerfile to copy assets

#### 2. Style Overhaul in `pdf_generator.py`
- Replace all `ParagraphStyle` definitions with NVWA-matching styles
- Use `'Times-Roman'` (built-in ReportLab font) or register Georgia
- Remove all color references except black
- Update margins to match spec

#### 3. Page Template with Logo + Page Numbers
- Switch from `SimpleDocTemplate` to `BaseDocTemplate` with custom `PageTemplate`
- Add `onPage` callback for:
  - Logo on page 1 (top-right)
  - Document number on page 1 (top-left)
  - "Pagina X van Y" on every page (bottom-right)

#### 4. Restructure Document Sections
- Add legal intro boilerplate paragraph
- Reorder to: Aanleiding → Locatie → Bevinding(en) (with CCP sub-findings) → Overtreder → Verhoor → Closing
- Map existing HAP data to new section structure
- Evidence images inline near relevant findings (if image descriptions mention specific findings) and/or as appendix

#### 5. Evidence Images Integration
- Current appendix approach works well — keep it
- Additionally, if an image's description/caption references a specific section (e.g., "hygiëne", "temperatuur"), consider placing it inline
- Images already have `caption` and `description` fields — use these for contextual placement

## Code References
- `mcp-servers/reporting/generators/pdf_generator.py:18-425` - Current PDF generator class
- `mcp-servers/reporting/generators/pdf_generator.py:23-48` - Current style setup (needs complete rewrite)
- `mcp-servers/reporting/generators/pdf_generator.py:50-102` - Main generate() method (needs restructuring)
- `mcp-servers/reporting/generators/pdf_generator.py:379-424` - Evidence appendix (keep, enhance)
- `mcp-servers/reporting/models/hap_schema.py:94-108` - InspectionMetadata (has all needed fields)
- `mcp-servers/reporting/models/hap_schema.py:110-148` - HAPReport model
- `mcp-servers/reporting/storage/file_storage.py:68-111` - Image save with manifest
- `mcp-servers/reporting/storage/file_storage.py:133-149` - Image loading
- `mcp-servers/reporting/server.py:246-361` - generate_final_report tool (orchestrates image + PDF)
- `mcp-servers/reporting/Dockerfile:17-24` - File copying (needs assets/ line)

## Architecture Insights
- ReportLab is already the PDF library — no need to change it
- `SimpleDocTemplate` should become `BaseDocTemplate` for proper page template control (logo, page numbers)
- The `HAPReport` data model has all fields needed for the NVWA format — no schema changes required
- Images are already flowing through the pipeline correctly; only placement in the PDF needs updating
- The Dockerfile needs a `COPY assets/ ./assets/` line added

## Historical Context
- `thoughts/shared/plans/2026-03-01-images-in-pdf-report.md` - Previous plan for images in PDF
- `thoughts/shared/research/2026-03-01-images-in-pdf-report.md` - Research on image integration
- `thoughts/shared/plans/2026-03-06-image-decoupling-from-llm-messages.md` - Today's image decoupling plan
- `thoughts/shared/research/2026-03-06-image-decoupling-from-llm-messages.md` - Today's image decoupling research

## Open Questions
1. **Legal boilerplate text**: The exact introductory paragraph wording under Awb art. 5:11 needs to be sourced — should it be hardcoded or configurable?
2. **Signature block**: Should we render a placeholder signature block or leave it for physical signing?
3. **Image placement strategy**: Keep as appendix only, or also attempt inline placement based on description content?
4. **Font licensing**: Georgia is a Microsoft font — is it available in the Docker container? `Times-Roman` is built into ReportLab and is a safe fallback.
5. **Logo format**: ReportLab works best with PNG/JPG. Should we convert SVG to PNG before committing, or use `svglib` at runtime?
