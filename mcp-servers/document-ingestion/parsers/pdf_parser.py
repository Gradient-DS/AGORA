import logging
import re
import base64
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, Optional
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from pdf2image import convert_from_path
from openai import OpenAI

logger = logging.getLogger(__name__)


class PDFParser:
    def __init__(self, output_dir: Path, openai_api_key: Optional[str] = None):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.openai_api_key = openai_api_key
        
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True
        pipeline_options.images_scale = 2.0
        pipeline_options.generate_page_images = True
        
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        )
    
    def parse_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        logger.info(f"Parsing PDF: {pdf_path.name}")
        
        try:
            result = self.converter.convert(str(pdf_path))
            markdown_content = result.document.export_to_markdown()
            
            text_content = markdown_content.replace("<!-- image -->", "").strip()
            if len(text_content) < 100 and self.openai_api_key:
                logger.warning(f"Standard OCR produced minimal text ({len(text_content)} chars), trying OpenAI Vision fallback")
                markdown_content = self._ocr_with_openai_vision(pdf_path)
            
            metadata = self._extract_metadata(pdf_path, markdown_content)
            
            output_path = self.output_dir / f"{pdf_path.stem}.md"
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            logger.info(f"Saved markdown to: {output_path}")
            
            return {
                "document_name": pdf_path.name,
                "markdown_path": str(output_path),
                "markdown_content": markdown_content,
                "metadata": metadata
            }
        
        except Exception as e:
            logger.error(f"Error parsing {pdf_path.name}: {e}")
            raise
    
    def _ocr_with_openai_vision(self, pdf_path: Path) -> str:
        logger.info(f"Using OpenAI Vision OCR for {pdf_path.name}")
        
        try:
            client = OpenAI(api_key=self.openai_api_key)
            
            logger.info("Converting PDF to images...")
            images = convert_from_path(str(pdf_path), dpi=300)
            logger.info(f"Converted {len(images)} pages to images")
            
            all_text = []
            
            for i, image in enumerate(images):
                logger.info(f"Processing page {i+1}/{len(images)} with OpenAI Vision")
                
                buffered = BytesIO()
                image.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Extract all text from this image. If it contains a table, format it as a markdown table. Preserve the structure and layout as much as possible. Return only the extracted text without any additional commentary."
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{img_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=4096
                )
                
                page_text = response.choices[0].message.content
                all_text.append(f"# Page {i+1}\n\n{page_text}")
                logger.info(f"Extracted {len(page_text)} characters from page {i+1}")
            
            markdown_content = "\n\n".join(all_text)
            logger.info(f"OpenAI Vision OCR complete: {len(markdown_content)} total characters")
            
            return markdown_content
        
        except Exception as e:
            logger.error(f"Error during OpenAI Vision OCR: {e}")
            raise
    
    def _extract_metadata(self, pdf_path: Path, markdown_content: str) -> Dict[str, Any]:
        filename = pdf_path.name
        
        if filename.startswith("Nederlandse wetgeving"):
            source_type = "Dutch"
        elif filename.startswith("Europese wetgeving"):
            source_type = "EU"
        elif filename.startswith("Algemeen"):
            source_type = "SPEC"
        else:
            source_type = "Unknown"
        
        regulation_type = self._infer_regulation_type(filename, markdown_content)
        
        regulation_number = self._extract_regulation_number(markdown_content)
        
        effective_date = self._extract_date(markdown_content)
        
        nvwa_category = self._infer_nvwa_category(regulation_type)
        
        return {
            "source_type": source_type,
            "regulation_type": regulation_type,
            "regulation_number": regulation_number,
            "effective_date": effective_date,
            "nvwa_category": nvwa_category
        }
    
    def _infer_regulation_type(self, filename: str, content: str) -> str:
        filename_lower = filename.lower()
        content_lower = content.lower()
        
        if "allergen" in filename_lower or "allergen" in content_lower:
            return "allergens"
        elif "hygiëne" in filename_lower or "hygiene" in content_lower:
            return "hygiene"
        elif "microbiolog" in filename_lower or "microbiolog" in content_lower:
            return "microbiological_criteria"
        elif "voedselinformatie" in filename_lower or "informatie" in filename_lower:
            return "food_information"
        elif "voedselveiligheid" in filename_lower or "food safety" in content_lower:
            return "food_safety"
        elif "controle" in filename_lower or "control" in content_lower:
            return "control"
        elif "dierlijke" in filename_lower or "animal" in content_lower:
            return "animal_products"
        elif "bereiding" in filename_lower or "behandeling" in filename_lower:
            return "food_preparation"
        else:
            return "general"
    
    def _extract_regulation_number(self, content: str) -> Optional[str]:
        bwbr_match = re.search(r'BWBR\d+', content)
        if bwbr_match:
            return bwbr_match.group(0)
        
        eu_reg_match = re.search(r'Verordening\s*\(E[GU]\)\s*[Nn]r\.?\s*(\d+/\d+)', content)
        if eu_reg_match:
            return f"EU {eu_reg_match.group(1)}"
        
        eu_short_match = re.search(r'(\d+/\d+/E[GU])', content)
        if eu_short_match:
            return f"EU {eu_short_match.group(1)}"
        
        return None
    
    def _extract_date(self, content: str) -> Optional[str]:
        date_patterns = [
            r'\d{1,2}\s+(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)\s+\d{4}',
            r'\d{4}-\d{2}-\d{2}',
            r'\d{1,2}/\d{1,2}/\d{4}'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(0)
        
        return None
    
    def _infer_nvwa_category(self, regulation_type: str) -> str:
        category_mapping = {
            "allergens": "Food Safety - Allergens",
            "hygiene": "Food Safety - Hygiene",
            "microbiological_criteria": "Food Safety - Microbiological",
            "food_information": "Food Safety - Labeling",
            "food_safety": "Food Safety - General",
            "control": "Enforcement - Control",
            "animal_products": "Food Safety - Animal Products",
            "food_preparation": "Food Safety - Preparation",
            "general": "General Compliance"
        }
        
        return category_mapping.get(regulation_type, "General Compliance")

