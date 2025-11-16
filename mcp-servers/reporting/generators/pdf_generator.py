import logging
from datetime import datetime
from typing import Optional
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from models.hap_schema import HAPReport

logger = logging.getLogger(__name__)


class PDFGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_styles()
    
    def _setup_styles(self):
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a365d'),
            spaceAfter=12,
            alignment=1,
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2c5282'),
            spaceAfter=10,
            spaceBefore=10,
        ))
        
        self.styles.add(ParagraphStyle(
            name='ViolationText',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#742a2a'),
            leftIndent=20,
        ))
    
    def generate(self, report: HAPReport) -> bytes:
        logger.info(f"Generating PDF report {report.metadata.report_id}")
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
        )
        
        story = []
        
        story.extend(self._create_header(report))
        story.append(Spacer(1, 0.5*cm))
        
        story.extend(self._create_executive_summary(report))
        story.append(Spacer(1, 0.5*cm))
        
        story.extend(self._create_hygiene_section(report))
        story.append(Spacer(1, 0.5*cm))
        
        story.extend(self._create_pest_control_section(report))
        story.append(Spacer(1, 0.5*cm))
        
        story.extend(self._create_food_safety_section(report))
        story.append(Spacer(1, 0.5*cm))
        
        story.extend(self._create_allergen_section(report))
        story.append(Spacer(1, 0.5*cm))
        
        story.extend(self._create_violations_summary(report))
        story.append(Spacer(1, 0.5*cm))
        
        story.extend(self._create_recommendations(report))
        story.append(Spacer(1, 0.5*cm))
        
        story.extend(self._create_footer(report))
        
        doc.build(story)
        
        pdf_content = buffer.getvalue()
        buffer.close()
        
        logger.info(f"Generated PDF report ({len(pdf_content)} bytes)")
        return pdf_content
    
    def _create_header(self, report: HAPReport):
        elements = []
        
        elements.append(Paragraph("NVWA INSPECTIE RAPPORT", self.styles['CustomTitle']))
        elements.append(Paragraph(f"HAP Lijst - {report.metadata.product_version}", self.styles['Normal']))
        elements.append(Spacer(1, 0.3*cm))
        
        metadata_data = [
            ["Rapportnummer:", report.metadata.report_id],
            ["Bedrijfsnaam:", report.metadata.company_name or "Niet gespecificeerd"],
            ["Adres:", report.metadata.company_address or "Niet gespecificeerd"],
            ["Inspectiedatum:", report.metadata.inspection_date.strftime("%d-%m-%Y %H:%M")],
            ["Inspectietype:", report.metadata.inspection_type.value],
            ["Inspecteur:", report.metadata.inspector_name or "Niet gespecificeerd"],
        ]
        
        table = Table(metadata_data, colWidths=[5*cm, 12*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        
        elements.append(table)
        
        return elements
    
    def _create_executive_summary(self, report: HAPReport):
        elements = []
        
        elements.append(Paragraph("Samenvatting", self.styles['SectionHeader']))
        
        total_violations = len(report.all_violations)
        serious = len([v for v in report.all_violations if v.severity and "Ernstige" in v.severity.value])
        
        summary_text = f"""
        Dit rapport bevat de bevindingen van de inspectie uitgevoerd op {report.metadata.inspection_date.strftime("%d-%m-%Y")}.<br/>
        <br/>
        <b>Totaal aantal overtredingen:</b> {total_violations}<br/>
        <b>Waarvan ernstig:</b> {serious}<br/>
        <b>Vervolgactie vereist:</b> {"Ja" if report.requires_follow_up else "Nee"}<br/>
        <b>Handhavingsactie vereist:</b> {"Ja" if report.enforcement_action_required else "Nee"}<br/>
        <b>Rapportage compleetheid:</b> {report.metadata.completion_percentage:.1f}%<br/>
        """
        
        elements.append(Paragraph(summary_text, self.styles['Normal']))
        
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
        
        elements.append(Paragraph("Overzicht Alle Overtredingen", self.styles['SectionHeader']))
        
        # Create a style for table cells
        cell_style = ParagraphStyle(
            name='CellText',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10,
        )
        
        # Header row with plain text
        violation_data = [["#", "Type", "Ernst", "Beschrijving", "Locatie"]]
        
        # Data rows with Paragraph objects for text wrapping
        for i, v in enumerate(report.all_violations, 1):
            violation_data.append([
                str(i),
                Paragraph(v.type.value if v.type else "N/A", cell_style),
                Paragraph(v.severity.value if v.severity else "N/A", cell_style),
                Paragraph(v.description if v.description else "N/A", cell_style),
                Paragraph(v.location if v.location else "N/A", cell_style)
            ])
        
        # Adjusted column widths to fit within margins (total 17cm)
        table = Table(violation_data, colWidths=[0.8*cm, 3.5*cm, 2.5*cm, 7*cm, 3.2*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        elements.append(table)
        
        return elements
    
    def _create_recommendations(self, report: HAPReport):
        elements = []
        
        elements.append(Paragraph("Aanbevelingen en Vervolgacties", self.styles['SectionHeader']))
        
        if report.enforcement_action_required:
            elements.append(Paragraph(
                "<b>WAARSCHUWING:</b> Er zijn ernstige overtredingen geconstateerd die directe handhavingsacties vereisen.",
                self.styles['ViolationText']
            ))
            elements.append(Spacer(1, 0.2*cm))
        
        if report.requires_follow_up:
            elements.append(Paragraph("• Herinspectie is vereist om naleving te verifiëren", self.styles['Normal']))
        
        if report.additional_info.repeat_violation:
            elements.append(Paragraph(
                "• Dit betreft een herhaalde overtreding. Strengere maatregelen kunnen worden overwogen.",
                self.styles['Normal']
            ))
        
        if report.additional_info.action_required:
            elements.append(Paragraph(f"• {report.additional_info.action_required}", self.styles['Normal']))
        
        if not report.all_violations:
            elements.append(Paragraph("• Geen overtredingen geconstateerd. Bedrijf voldoet aan de eisen.", self.styles['Normal']))
            elements.append(Paragraph("• Blijf huidige voedselveiligheidspraktijken handhaven.", self.styles['Normal']))
        
        return elements
    
    def _create_footer(self, report: HAPReport):
        elements = []
        
        elements.append(Spacer(1, 1*cm))
        
        if report.additional_info.inspector_notes:
            elements.append(Paragraph("Aanvullende Opmerkingen Inspecteur", self.styles['SectionHeader']))
            elements.append(Paragraph(report.additional_info.inspector_notes, self.styles['Normal']))
            elements.append(Spacer(1, 0.5*cm))
        
        footer_text = f"""
        <br/>
        <br/>
        _________________________________________________<br/>
        Dit rapport is automatisch gegenereerd door AGORA v1.0<br/>
        Gegenereerd op: {datetime.now().strftime("%d-%m-%Y om %H:%M")}<br/>
        Rapportage compleetheid: {report.metadata.completion_percentage:.1f}%<br/>
        Betrouwbaarheid: {report.metadata.overall_confidence*100:.1f}%<br/>
        """
        
        elements.append(Paragraph(footer_text, self.styles['Normal']))
        
        return elements

