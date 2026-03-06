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
| Font | Helvetica (sans-serif) | Times-Roman (built-in ReportLab serif) |
| Title | "NVWA INSPECTIE RAPPORT", blue | "RAPPORT VAN BEVINDINGEN", black, ALL CAPS |
| Colors | Blue headers, red violations, beige tables | Monochrome (black only) |
| Logo | None | NVWA logo PNG top-right on page 1 (committed to repo) |
| Page numbers | None | "Pagina X van Y" bottom-right |
| Doc number | In metadata table | Top-left, above title |
| Intro paragraph | None | Short intro identifying inspector + legal basis (concise, no full legal boilerplate) |
| Section order | Summary → Categories → Violations → Recommendations | Aanleiding → Locatie → Bevinding(en) (with per-category findings from HAPReport) → Evidence Appendix → Closing |
| Metadata display | Colored table with background | Tab-aligned label:value pairs, plain |
| Margins | 2cm all sides | 25mm left/right/top, 20mm bottom |
| Line spacing | Default | 1.15-1.2x |
| Section spacing | 0.5cm gaps | 12pt before headers, 6pt after paragraphs |
| Evidence images | Appendix at end | Keep in appendix (inline placement too unreliable) |
| Footer | "Automatisch gegenereerd door AGORA" | Simple closing with date + inspector info |

### Design Decisions

1. **No heavy legal jargon**: Skip the full Awb art. 5:11 boilerplate. Keep the intro short — just identify the inspector, the company, and the legal basis (e.g. Warenwet). The report should read as a clear summary of the actual inspection findings.
2. **Section structure stays inspection-focused**: Keep the existing HAP categories (Hygiene, Pest Control, Food Safety, Allergens) as sub-sections under "Bevinding(en)" — these map directly to what was inspected and discussed in the conversation. Don't introduce Overtreder/Verhoor sections (these are for formal enforcement reports, not our generated summary).
3. **Images stay in appendix**: Inline placement would require reliably matching image descriptions to specific findings — too fragile. Appendix with captions + AI descriptions works well.
4. **Font**: Use `Times-Roman` / `Times-Bold` / `Times-Italic` — built into ReportLab, no Docker font installation needed.
5. **Logo**: Commit a PNG to `mcp-servers/reporting/assets/nvwa-logo.png` — simplest for ReportLab, no `svglib` dependency.

### Implementation Approach

#### 1. Assets Setup
- Create `mcp-servers/reporting/assets/` directory
- Download NVWA logo as PNG and commit to repo
- Update Dockerfile: add `COPY assets/ ./assets/`

#### 2. Style Overhaul in `pdf_generator.py`
- Replace all `ParagraphStyle` definitions with NVWA-matching styles
- Use `Times-Roman` / `Times-Bold` / `Times-Italic` (built into ReportLab)
- Remove all color references — black text only
- Update margins: 25mm L/R/T, 20mm bottom

#### 3. Page Template with Logo + Page Numbers
- Switch from `SimpleDocTemplate` to `BaseDocTemplate` with custom `PageTemplate`
- Add `onPage` / `onFirstPage` callbacks:
  - First page: NVWA logo top-right, document number top-left
  - Every page: "Pagina X van Y" bottom-right, 9pt Times-Roman

#### 4. Restructure Document Sections
- **Title**: "RAPPORT VAN BEVINDINGEN" — centered, bold, 18pt, ALL CAPS
- **Intro**: Short paragraph identifying inspector + company + legal basis (1-2 sentences, no heavy Awb boilerplate)
- **Aanleiding**: One line — inspection reason / legal basis reference
- **Locatie**: Company name + address as tab-aligned key-value pairs
- **Bevinding(en)**:
  - Metadata (date/time, contact person, role) as tab-aligned pairs
  - Then existing HAP sections as sub-findings:
    1. Hygiëne Algemeen (from `hygiene_general`)
    2. Ongediertebestrijding (from `pest_control`)
    3. Veilig Omgaan met Voedsel (from `food_safety`)
    4. Allergeneninformatie (from `allergen_info`)
  - Each sub-finding: compliance status + violations + observations (same data, restyled)
- **Violations summary table**: Keep but restyle (no colors, simple grid, serif font)
- **Evidence appendix**: Keep current `_create_evidence_appendix()` — images with captions + descriptions
- **Closing**: Simple closing with date, inspector name, "gegenereerd door AGORA" note

#### 5. Evidence Images
- Keep in appendix — no inline placement (too unreliable to match to findings)
- Existing `_create_evidence_appendix()` already handles caption + description well
- Restyle to match monochrome serif theme

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
1. **Signature block**: Should we render a placeholder signature area or omit entirely? (The report is digitally generated, not physically signed.)
2. **Violations summary table**: Keep the full table, or simplify to just a count per category?
