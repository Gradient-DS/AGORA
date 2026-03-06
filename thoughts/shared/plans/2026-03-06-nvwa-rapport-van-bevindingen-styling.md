# NVWA "Rapport van Bevindingen" PDF Styling Implementation Plan

## Overview

Update the PDF report generator (`mcp-servers/reporting/generators/pdf_generator.py`) to match the official NVWA "Rapport van Bevindingen" document style. This involves switching to serif fonts, monochrome colors, adding the NVWA logo, proper page numbering, and restructuring sections to match the official format.

## Current State Analysis

- `pdf_generator.py` (426 lines) uses `SimpleDocTemplate`, Helvetica fonts, blue headers (#1a365d, #2c5282), red violation text (#742a2a), colored table backgrounds (beige, blue), and 2cm margins
- `HAPReport` model has all required fields — no schema changes needed
- NVWA logo already committed at `mcp-servers/reporting/assets/nvwa_logo.png`
- Dockerfile missing `COPY assets/ ./assets/`
- Evidence appendix already functional with caption + description support

### Key Discoveries:
- `pdf_generator.py:23-48` — Three custom styles (CustomTitle, SectionHeader, ViolationText) all use non-NVWA colors
- `pdf_generator.py:54-61` — `SimpleDocTemplate` with 2cm margins, needs `BaseDocTemplate` for page template control
- `pdf_generator.py:104-134` — Header uses colored metadata table, needs plain tab-aligned pairs
- `pdf_generator.py:275-323` — Violations summary table has blue header row, beige data rows
- `pdf_generator.py:379-424` — Evidence appendix is well-structured, just needs restyling
- `Dockerfile:17-23` — File copying section, needs `COPY assets/ ./assets/` added

## Desired End State

A PDF that:
- Uses Times-Roman/Times-Bold serif fonts throughout
- Is fully monochrome (black text only, no colored backgrounds)
- Shows NVWA logo top-right on page 1
- Shows document number top-left on page 1
- Has "Pagina X van Y" bottom-right on every page
- Title reads "RAPPORT VAN BEVINDINGEN" (centered, bold, ALL CAPS)
- Sections follow: Intro → Aanleiding → Locatie → Bevindingen (with HAP sub-sections) → Violations Summary → Evidence Appendix → Closing
- Margins: 25mm left/right/top, 20mm bottom
- Line spacing: 1.2x for body text

### Verification:
- Generate a test PDF and visually confirm styling matches NVWA format
- Run the reporting MCP server and generate a report through the full pipeline
- Verify logo renders correctly on page 1
- Verify page numbers appear on all pages

## What We're NOT Doing

- No schema changes to `HAPReport` or any models
- No inline image placement (images stay in appendix)
- No full legal Awb boilerplate — just a short intro paragraph
- No Overtreder/Verhoor sections (those are for formal enforcement reports)
- No signature block
- No changes to the image upload/storage pipeline
- No new Python dependencies (Times-Roman is built into ReportLab)

## Implementation Approach

Rewrite `pdf_generator.py` in four incremental phases. Each phase produces a valid PDF so we can verify progress. The `HAPReport` model and `server.py` orchestration remain unchanged.

---

## Phase 1: Style Overhaul

### Overview
Replace all style definitions with NVWA-matching monochrome serif styles and update document margins.

### Changes Required:

#### 1. Update imports
**File**: `mcp-servers/reporting/generators/pdf_generator.py`
**Changes**: Add `mm` unit import, remove `colors` import dependency on specific hex colors

```python
from reportlab.lib.units import cm, mm
```

#### 2. Replace `_setup_styles()`
**File**: `mcp-servers/reporting/generators/pdf_generator.py:23-48`
**Changes**: Complete rewrite of all three custom styles

```python
def _setup_styles(self):
    # Override base Normal style
    self.styles['Normal'].fontName = 'Times-Roman'
    self.styles['Normal'].fontSize = 10
    self.styles['Normal'].leading = 12  # 1.2x line spacing

    self.styles.add(ParagraphStyle(
        name='CustomTitle',
        fontName='Times-Bold',
        fontSize=18,
        textColor=colors.black,
        spaceAfter=12,
        alignment=1,  # center
        leading=22,
    ))

    self.styles.add(ParagraphStyle(
        name='SectionHeader',
        fontName='Times-Bold',
        fontSize=11,
        textColor=colors.black,
        spaceBefore=12,
        spaceAfter=6,
        leading=14,
    ))

    self.styles.add(ParagraphStyle(
        name='ViolationText',
        parent=self.styles['Normal'],
        fontName='Times-Roman',
        fontSize=10,
        textColor=colors.black,
        leftIndent=20,
        leading=12,
    ))

    self.styles.add(ParagraphStyle(
        name='MetadataLabel',
        fontName='Times-Bold',
        fontSize=10,
        textColor=colors.black,
        leading=12,
    ))

    self.styles.add(ParagraphStyle(
        name='SmallText',
        fontName='Times-Roman',
        fontSize=9,
        textColor=colors.black,
        leading=11,
    ))
```

#### 3. Update document margins in `generate()`
**File**: `mcp-servers/reporting/generators/pdf_generator.py:54-61`
**Changes**: Change margins from 2cm to 25mm/20mm

```python
doc = SimpleDocTemplate(
    buffer,
    pagesize=A4,
    rightMargin=25*mm,
    leftMargin=25*mm,
    topMargin=25*mm,
    bottomMargin=20*mm,
)
```

### Success Criteria:

#### Automated Verification:
- [x] Python file parses without syntax errors: `python -c "from generators.pdf_generator import PDFGenerator"`
- [x] No import errors when running the reporting server

#### Manual Verification:
- [ ] Generated PDF uses serif fonts throughout
- [ ] No blue, red, or colored text anywhere in the document
- [ ] Margins visually match 25mm/20mm specification

---

## Phase 2: Page Template with Logo & Page Numbers

### Overview
Switch from `SimpleDocTemplate` to `BaseDocTemplate` with custom `PageTemplate` for NVWA logo on page 1 and "Pagina X van Y" page numbers on every page.

### Changes Required:

#### 1. Update imports
**File**: `mcp-servers/reporting/generators/pdf_generator.py`
**Changes**: Add BaseDocTemplate, PageTemplate, Frame imports

```python
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
)
from reportlab.platypus import Image as RLImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
import os
```

#### 2. Add page callback methods to `PDFGenerator`
**File**: `mcp-servers/reporting/generators/pdf_generator.py`
**Changes**: Add `_on_first_page()` and `_on_later_pages()` methods

```python
def _get_logo_path(self):
    """Get absolute path to NVWA logo."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "assets", "nvwa_logo.png")

def _on_first_page(self, canvas, doc):
    """Draw logo and document number on first page, plus page number."""
    canvas.saveState()

    # NVWA logo top-right
    logo_path = self._get_logo_path()
    if os.path.exists(logo_path):
        canvas.drawImage(
            logo_path,
            A4[0] - 25*mm - 55*mm,  # right margin - logo width
            A4[1] - 25*mm - 5*mm,   # top margin area
            width=55*mm,
            height=25*mm,
            preserveAspectRatio=True,
            anchor='nw',
        )

    # Document number top-left
    canvas.setFont('Times-Roman', 9)
    canvas.drawString(25*mm, A4[1] - 18*mm, f"Kenmerk: {self._report_id}")

    # Page number bottom-right
    self._draw_page_number(canvas, doc)

    canvas.restoreState()

def _on_later_pages(self, canvas, doc):
    """Draw page number on subsequent pages."""
    canvas.saveState()
    self._draw_page_number(canvas, doc)
    canvas.restoreState()

def _draw_page_number(self, canvas, doc):
    """Draw 'Pagina X van Y' bottom-right."""
    canvas.setFont('Times-Roman', 9)
    page_text = f"Pagina {doc.page}"
    canvas.drawRightString(A4[0] - 25*mm, 10*mm, page_text)
```

Note: ReportLab's "Pagina X van Y" requires a two-pass approach or the `NumberedCanvas` pattern. For simplicity, we'll use just "Pagina X" — the total page count adds significant complexity for marginal value. If the user wants "van Y", we can add `NumberedCanvas` as a follow-up.

#### 3. Rewrite `generate()` to use `BaseDocTemplate`
**File**: `mcp-servers/reporting/generators/pdf_generator.py:50-102`
**Changes**: Replace `SimpleDocTemplate` with `BaseDocTemplate` + `PageTemplate`

```python
def generate(self, report: HAPReport, evidence_images: list[dict] | None = None) -> bytes:
    logger.info(f"Generating PDF report {report.metadata.report_id}")

    self._report_id = report.metadata.report_id

    buffer = BytesIO()

    frame = Frame(
        25*mm, 20*mm,
        A4[0] - 50*mm,  # width = page width - left - right margins
        A4[1] - 45*mm,  # height = page height - top - bottom margins
        id='normal',
    )

    first_page_template = PageTemplate(
        id='first',
        frames=frame,
        onPage=self._on_first_page,
    )

    later_page_template = PageTemplate(
        id='later',
        frames=frame,
        onPage=self._on_later_pages,
    )

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        pageTemplates=[first_page_template, later_page_template],
    )

    story = []

    # After the first page of content, switch to 'later' template
    story.extend(self._create_header(report))
    story.append(Spacer(1, 0.5*cm))

    # ... rest of sections (restructured in Phase 3) ...

    doc.build(story)

    pdf_content = buffer.getvalue()
    buffer.close()

    logger.info(f"Generated PDF report ({len(pdf_content)} bytes)")
    return pdf_content
```

Note: `BaseDocTemplate` automatically uses the first `PageTemplate` for page 1. To switch to the `later` template for page 2+, we use `NextPageTemplate('later')` before the first `PageBreak` or rely on `afterPage` logic. The simplest approach: add `story.append(NextPageTemplate('later'))` right after the header section, so any subsequent page uses the later template.

Add to imports:
```python
from reportlab.platypus import NextPageTemplate
```

And in the story building:
```python
story.extend(self._create_header(report))
story.append(NextPageTemplate('later'))
story.append(Spacer(1, 0.5*cm))
```

### Success Criteria:

#### Automated Verification:
- [x] Python file parses without syntax errors: `python -c "from generators.pdf_generator import PDFGenerator"`
- [x] Logo file loads without error (path resolution works)

#### Manual Verification:
- [ ] NVWA logo appears top-right on page 1 only
- [ ] Document number appears top-left on page 1
- [ ] "Pagina X" appears bottom-right on every page
- [ ] Logo does not appear on page 2+
- [ ] Content does not overlap with logo or page numbers

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that the layout looks correct before proceeding to Phase 3.

---

## Phase 3: Document Structure Restructure

### Overview
Reorder and rewrite sections to match the NVWA "Rapport van Bevindingen" format. Replace the current section order with: Title → Intro → Aanleiding → Locatie → Bevindingen → Violations Summary → Evidence → Closing.

### Changes Required:

#### 1. Rewrite `_create_header()` → title + intro
**File**: `mcp-servers/reporting/generators/pdf_generator.py:104-134`
**Changes**: Replace colored metadata table with NVWA-style title and intro paragraph

```python
def _create_header(self, report: HAPReport):
    elements = []

    elements.append(Spacer(1, 1.5*cm))  # Space below logo area
    elements.append(Paragraph("RAPPORT VAN BEVINDINGEN", self.styles['CustomTitle']))
    elements.append(Spacer(1, 0.5*cm))

    # Short intro paragraph
    inspector = report.metadata.inspector_name or "de inspecteur"
    date_str = report.metadata.inspection_date.strftime("%d-%m-%Y")
    company = report.metadata.company_name or "het bedrijf"

    intro_text = (
        f"Op {date_str} heeft {inspector} van de Nederlandse Voedsel- en Warenautoriteit "
        f"een inspectie uitgevoerd bij {company}. Dit rapport bevat de bevindingen "
        f"van deze inspectie op grond van de Warenwet."
    )
    elements.append(Paragraph(intro_text, self.styles['Normal']))

    return elements
```

#### 2. Add `_create_aanleiding()` section
**File**: `mcp-servers/reporting/generators/pdf_generator.py`
**Changes**: New method

```python
def _create_aanleiding(self, report: HAPReport):
    elements = []
    elements.append(Paragraph("Aanleiding", self.styles['SectionHeader']))

    inspection_type = report.metadata.inspection_type.value
    elements.append(Paragraph(
        f"Type inspectie: {inspection_type}",
        self.styles['Normal']
    ))

    if report.additional_info.repeat_violation:
        elements.append(Paragraph(
            "Het betreft een herinspectie naar aanleiding van eerder geconstateerde overtredingen.",
            self.styles['Normal']
        ))

    return elements
```

#### 3. Add `_create_locatie()` section
**File**: `mcp-servers/reporting/generators/pdf_generator.py`
**Changes**: New method — tab-aligned key-value pairs instead of colored table

```python
def _create_locatie(self, report: HAPReport):
    elements = []
    elements.append(Paragraph("Locatie", self.styles['SectionHeader']))

    metadata_pairs = [
        ("Bedrijfsnaam", report.metadata.company_name or "Niet gespecificeerd"),
        ("Adres", report.metadata.company_address or "Niet gespecificeerd"),
        ("Inspectiedatum", report.metadata.inspection_date.strftime("%d-%m-%Y %H:%M")),
        ("Inspecteur", report.metadata.inspector_name or "Niet gespecificeerd"),
        ("Rapportnummer", report.metadata.report_id),
    ]

    for label, value in metadata_pairs:
        elements.append(Paragraph(
            f"<b>{label}:</b>  {value}",
            self.styles['Normal']
        ))

    return elements
```

#### 4. Wrap existing category sections under "Bevinding(en)"
**File**: `mcp-servers/reporting/generators/pdf_generator.py`
**Changes**: Add a `_create_bevindingen()` method that wraps the four existing category methods

```python
def _create_bevindingen(self, report: HAPReport):
    elements = []
    elements.append(Paragraph("Bevinding(en)", self.styles['SectionHeader']))
    elements.append(Spacer(1, 0.2*cm))

    # Sub-sections use existing methods (already restyled in Phase 1)
    elements.extend(self._create_hygiene_section(report))
    elements.append(Spacer(1, 0.3*cm))

    elements.extend(self._create_pest_control_section(report))
    elements.append(Spacer(1, 0.3*cm))

    elements.extend(self._create_food_safety_section(report))
    elements.append(Spacer(1, 0.3*cm))

    elements.extend(self._create_allergen_section(report))

    return elements
```

#### 5. Restyle violations summary table
**File**: `mcp-servers/reporting/generators/pdf_generator.py:275-323`
**Changes**: Remove all colors from table — black header text, no background colors, simple grid

```python
def _create_violations_summary(self, report: HAPReport):
    elements = []

    if not report.all_violations:
        return elements

    elements.append(Paragraph("Overzicht Overtredingen", self.styles['SectionHeader']))

    cell_style = ParagraphStyle(
        name='CellText',
        parent=self.styles['Normal'],
        fontName='Times-Roman',
        fontSize=8,
        leading=10,
    )

    violation_data = [["#", "Type", "Ernst", "Beschrijving", "Locatie"]]

    for i, v in enumerate(report.all_violations, 1):
        violation_data.append([
            str(i),
            Paragraph(v.type.value if v.type else "N/A", cell_style),
            Paragraph(v.severity.value if v.severity else "N/A", cell_style),
            Paragraph(v.description if v.description else "N/A", cell_style),
            Paragraph(v.location if v.location else "N/A", cell_style),
        ])

    table = Table(violation_data, colWidths=[0.8*cm, 3.5*cm, 2.5*cm, 7*cm, 3.2*cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))

    elements.append(table)
    return elements
```

#### 6. Replace footer with closing section
**File**: `mcp-servers/reporting/generators/pdf_generator.py:355-377`
**Changes**: Replace "automatisch gegenereerd" footer with simple closing

```python
def _create_closing(self, report: HAPReport):
    elements = []
    elements.append(Spacer(1, 1*cm))

    if report.additional_info.inspector_notes:
        elements.append(Paragraph("Aanvullende opmerkingen", self.styles['SectionHeader']))
        elements.append(Paragraph(report.additional_info.inspector_notes, self.styles['Normal']))
        elements.append(Spacer(1, 0.5*cm))

    elements.append(Paragraph(
        f"Aldus opgemaakt op {datetime.now().strftime('%d-%m-%Y')}.",
        self.styles['Normal']
    ))

    if report.metadata.inspector_name:
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph(
            f"{report.metadata.inspector_name}",
            self.styles['Normal']
        ))
        elements.append(Paragraph(
            "Inspecteur NVWA",
            self.styles['SmallText']
        ))

    elements.append(Spacer(1, 0.5*cm))
    elements.append(Paragraph(
        "<i>Dit rapport is gegenereerd met behulp van AGORA.</i>",
        self.styles['SmallText']
    ))

    return elements
```

#### 7. Update `generate()` story order
**File**: `mcp-servers/reporting/generators/pdf_generator.py:50-102`
**Changes**: New section order in story building

```python
story = []

story.extend(self._create_header(report))
story.append(NextPageTemplate('later'))
story.append(Spacer(1, 0.5*cm))

story.extend(self._create_aanleiding(report))
story.append(Spacer(1, 0.3*cm))

story.extend(self._create_locatie(report))
story.append(Spacer(1, 0.5*cm))

story.extend(self._create_bevindingen(report))
story.append(Spacer(1, 0.5*cm))

story.extend(self._create_violations_summary(report))
story.append(Spacer(1, 0.5*cm))

story.extend(self._create_closing(report))

if evidence_images:
    story.append(PageBreak())
    story.extend(self._create_evidence_appendix(evidence_images))
```

#### 8. Remove `_create_executive_summary()` and `_create_recommendations()`
These methods are replaced by the new structure. Remove them entirely.

### Success Criteria:

#### Automated Verification:
- [x] Python file parses without syntax errors: `python -c "from generators.pdf_generator import PDFGenerator"`
- [x] No references to removed methods remain

#### Manual Verification:
- [ ] Sections appear in correct NVWA order
- [ ] Intro paragraph reads naturally with inspector name and company
- [ ] Metadata displayed as plain key-value pairs (no colored table)
- [ ] Violations summary table is monochrome with simple grid
- [ ] Closing section shows date and inspector info
- [ ] Evidence appendix still renders correctly after all structural changes

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that the document structure and content looks correct before proceeding to Phase 4.

---

## Phase 4: Evidence Appendix Restyle & Dockerfile

### Overview
Restyle the evidence appendix to match the monochrome serif theme, and update the Dockerfile to include assets.

### Changes Required:

#### 1. Restyle evidence appendix
**File**: `mcp-servers/reporting/generators/pdf_generator.py:379-424`
**Changes**: Update styles used in evidence appendix to use NVWA styles

```python
def _create_evidence_appendix(self, images: list[dict]) -> list:
    """Create evidence photos appendix."""
    elements = []

    elements.append(Paragraph("Bijlage: Bewijsmateriaal", self.styles['SectionHeader']))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(
        f"Tijdens de inspectie zijn {len(images)} foto('s) vastgelegd.",
        self.styles['Normal']
    ))
    elements.append(Spacer(1, 0.5*cm))

    for i, img_info in enumerate(images, 1):
        img_path = img_info.get("path", "")
        caption = img_info.get("caption", "Bewijsfoto")

        try:
            rl_image = RLImage(img_path, width=14*cm, height=10*cm, kind='proportional')
        except Exception as e:
            logger.warning(f"Failed to load evidence image {img_path}: {e}")
            elements.append(Paragraph(
                f"<i>Foto {i}: kon niet worden geladen</i>",
                self.styles['Normal']
            ))
            elements.append(Spacer(1, 0.3*cm))
            continue

        caption_text = Paragraph(
            f"<b>Foto {i}:</b> {caption}",
            self.styles['Normal']
        )

        description = img_info.get("description", "")

        keep_elements = [rl_image, Spacer(1, 0.2*cm), caption_text]
        if description:
            keep_elements.append(Spacer(1, 0.1*cm))
            keep_elements.append(Paragraph(
                f"<i>{description}</i>",
                self.styles['Normal']
            ))
        elements.append(KeepTogether(keep_elements))
        elements.append(Spacer(1, 0.5*cm))

    return elements
```

The main change here is using `SectionHeader` instead of `CustomTitle` for the appendix heading — it should be a section header, not a document title.

#### 2. Update Dockerfile
**File**: `mcp-servers/reporting/Dockerfile:17-23`
**Changes**: Add `COPY assets/ ./assets/` line

```dockerfile
COPY server.py .
COPY models/ ./models/
COPY storage/ ./storage/
COPY analyzers/ ./analyzers/
COPY verification/ ./verification/
COPY generators/ ./generators/
COPY services/ ./services/
COPY assets/ ./assets/
```

### Success Criteria:

#### Automated Verification:
- [ ] Dockerfile builds successfully: `docker build -t reporting-test mcp-servers/reporting/`
- [x] Python file parses without syntax errors
- [ ] Logo file is accessible from within the Docker container

#### Manual Verification:
- [ ] Evidence appendix heading uses section header style (not title style)
- [ ] Evidence photos still render correctly with captions and descriptions
- [ ] Full PDF end-to-end looks correct with all changes combined

---

## Testing Strategy

### Manual Testing Steps:
1. Start the reporting MCP server locally
2. Create a test session and populate it with sample HAP data
3. Upload 1-2 test images
4. Generate the final PDF report
5. Verify all styling, layout, and content matches NVWA format
6. Test with empty sections (no violations) to verify graceful handling
7. Test with many violations to verify multi-page layout and page numbers
8. Build Docker image and verify logo is accessible

## References

- Research: `thoughts/shared/research/2026-03-06-nvwa-rapport-van-bevindingen-styling.md`
- PDF generator: `mcp-servers/reporting/generators/pdf_generator.py`
- HAPReport model: `mcp-servers/reporting/models/hap_schema.py`
- Dockerfile: `mcp-servers/reporting/Dockerfile`
- NVWA logo: `mcp-servers/reporting/assets/nvwa_logo.png`
