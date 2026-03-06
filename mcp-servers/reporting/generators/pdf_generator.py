import logging
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, NextPageTemplate,
)
from reportlab.platypus import Image as RLImage
import os
from models.hap_schema import HAPReport

logger = logging.getLogger(__name__)


class PDFGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_styles()
    
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
        """Draw 'Pagina X' bottom-right."""
        canvas.setFont('Times-Roman', 9)
        page_text = f"Pagina {doc.page}"
        canvas.drawRightString(A4[0] - 25*mm, 10*mm, page_text)

    def generate(self, report: HAPReport, evidence_images: list[dict] | None = None) -> bytes:
        logger.info(f"Generating PDF report {report.metadata.report_id}")

        self._report_id = report.metadata.report_id

        buffer = BytesIO()

        frame = Frame(
            25*mm, 20*mm,
            A4[0] - 50*mm,   # width = page width - left - right margins
            A4[1] - 45*mm,   # height = page height - top - bottom margins
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

        doc.build(story)

        pdf_content = buffer.getvalue()
        buffer.close()

        logger.info(f"Generated PDF report ({len(pdf_content)} bytes)")
        return pdf_content
    
    def _create_header(self, report: HAPReport):
        elements = []

        elements.append(Spacer(1, 1.5*cm))  # Space below logo area
        elements.append(Paragraph("RAPPORT VAN BEVINDINGEN", self.styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*cm))

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

    def _create_bevindingen(self, report: HAPReport):
        elements = []
        elements.append(Paragraph("Bevinding(en)", self.styles['SectionHeader']))
        elements.append(Spacer(1, 0.2*cm))

        elements.extend(self._create_hygiene_section(report))
        elements.append(Spacer(1, 0.3*cm))

        elements.extend(self._create_pest_control_section(report))
        elements.append(Spacer(1, 0.3*cm))

        elements.extend(self._create_food_safety_section(report))
        elements.append(Spacer(1, 0.3*cm))

        elements.extend(self._create_allergen_section(report))

        return elements

    def _create_hygiene_section(self, report: HAPReport):
        elements = []
        
        elements.append(Paragraph("1. Hygiëne Algemeen", self.styles['SectionHeader']))
        
        compliance = report.hygiene_general.compliant
        if compliance:
            elements.append(Paragraph(f"<b>Status:</b> {compliance.value}", self.styles['Normal']))
        
        if report.hygiene_general.violations:
            elements.append(Paragraph("<b>Geconstateerde overtredingen:</b>", self.styles['Normal']))
            for v in report.hygiene_general.violations:
                severity_text = f" [{v.severity.value}]" if v.severity else ""
                violation_text = f"• {v.description}{severity_text}"
                if v.location:
                    violation_text += f" (Locatie: {v.location})"
                elements.append(Paragraph(violation_text, self.styles['ViolationText']))
        
        if report.hygiene_general.observations:
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph(f"<b>Opmerkingen:</b> {report.hygiene_general.observations}", self.styles['Normal']))
        
        return elements
    
    def _create_pest_control_section(self, report: HAPReport):
        elements = []
        
        elements.append(Paragraph("2. Ongediertebestrijding", self.styles['SectionHeader']))
        
        compliance = report.pest_control.pest_prevention_compliant
        if compliance:
            elements.append(Paragraph(f"<b>Ongediertewering voldoet:</b> {compliance.value}", self.styles['Normal']))
        
        if report.pest_control.pest_present:
            elements.append(Paragraph(f"<b>Ongedierte aanwezig:</b> Ja", self.styles['Normal']))
            if report.pest_control.pest_types:
                types = ", ".join([pt.value for pt in report.pest_control.pest_types])
                elements.append(Paragraph(f"<b>Type(s):</b> {types}", self.styles['Normal']))
            if report.pest_control.pest_severity:
                elements.append(Paragraph(f"<b>Ernst:</b> {report.pest_control.pest_severity.value}", self.styles['Normal']))
        else:
            elements.append(Paragraph(f"<b>Ongedierte aanwezig:</b> Nee", self.styles['Normal']))
        
        if report.pest_control.violations:
            elements.append(Paragraph("<b>Geconstateerde overtredingen:</b>", self.styles['Normal']))
            for v in report.pest_control.violations:
                severity_text = f" [{v.severity.value}]" if v.severity else ""
                elements.append(Paragraph(f"• {v.description}{severity_text}", self.styles['ViolationText']))
        
        if report.pest_control.observations:
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph(f"<b>Opmerkingen:</b> {report.pest_control.observations}", self.styles['Normal']))
        
        return elements
    
    def _create_food_safety_section(self, report: HAPReport):
        elements = []
        
        elements.append(Paragraph("3. Veilig Omgaan met Voedsel", self.styles['SectionHeader']))
        
        if report.food_safety.storage_compliant:
            elements.append(Paragraph(f"<b>Bewaren/opslag:</b> {report.food_safety.storage_compliant.value}", self.styles['Normal']))
        
        if report.food_safety.preparation_cooling_compliant:
            elements.append(Paragraph(f"<b>Bereiden/terugkoelen:</b> {report.food_safety.preparation_cooling_compliant.value}", self.styles['Normal']))
        
        if report.food_safety.presentation_compliant:
            elements.append(Paragraph(f"<b>Presenteren:</b> {report.food_safety.presentation_compliant.value}", self.styles['Normal']))
        
        if report.food_safety.temperature_violations:
            elements.append(Paragraph("<b>Temperatuuroverschrijdingen:</b>", self.styles['Normal']))
            for temp_v in report.food_safety.temperature_violations:
                elements.append(Paragraph(
                    f"• {temp_v.get('product', 'Onbekend product')}: {temp_v.get('temp', 'N/A')}°C",
                    self.styles['ViolationText']
                ))
        
        if report.food_safety.unsafe_products:
            elements.append(Paragraph("<b>Onveilige producten:</b>", self.styles['Normal']))
            for product in report.food_safety.unsafe_products:
                elements.append(Paragraph(f"• {product}", self.styles['ViolationText']))
        
        if report.food_safety.violations:
            elements.append(Paragraph("<b>Overige overtredingen:</b>", self.styles['Normal']))
            for v in report.food_safety.violations:
                severity_text = f" [{v.severity.value}]" if v.severity else ""
                elements.append(Paragraph(f"• {v.description}{severity_text}", self.styles['ViolationText']))
        
        if report.food_safety.observations:
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph(f"<b>Opmerkingen:</b> {report.food_safety.observations}", self.styles['Normal']))
        
        return elements
    
    def _create_allergen_section(self, report: HAPReport):
        elements = []
        
        elements.append(Paragraph("4. Allergeneninformatie", self.styles['SectionHeader']))
        
        if report.allergen_info.compliant:
            elements.append(Paragraph(f"<b>Status:</b> {report.allergen_info.compliant.value}", self.styles['Normal']))
        
        if report.allergen_info.information_method:
            elements.append(Paragraph(f"<b>Methode:</b> {report.allergen_info.information_method}", self.styles['Normal']))
        
        if report.allergen_info.violations:
            elements.append(Paragraph("<b>Geconstateerde overtredingen:</b>", self.styles['Normal']))
            for v in report.allergen_info.violations:
                severity_text = f" [{v.severity.value}]" if v.severity else ""
                elements.append(Paragraph(f"• {v.description}{severity_text}", self.styles['ViolationText']))
        
        if report.allergen_info.observations:
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph(f"<b>Opmerkingen:</b> {report.allergen_info.observations}", self.styles['Normal']))
        
        return elements
    
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

            # Keep image + caption + description together across page breaks
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

