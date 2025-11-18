#!/usr/bin/env python3
"""
Convert a single PDF to markdown using the docling parser.
Falls back to OpenAI Vision OCR for image-based PDFs.

Usage:
    python pdf_to_markdown.py <pdf_file_path> [output_dir]

Example:
    python pdf_to_markdown.py ../input/SPEC\ Agent/Nederlandse\ wetgeving\ -\ Warenwetregeling\ allergeneninformatie\ niet-voorverpakte\ levensmiddelen.pdf
    python pdf_to_markdown.py my_document.pdf ./custom_output/
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parsers.pdf_parser import PDFParser
from config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def convert_pdf_to_markdown(pdf_path: str, output_dir: str = None):
    pdf_file = Path(pdf_path)
    
    if not pdf_file.exists():
        logger.error(f"PDF file not found: {pdf_path}")
        return False
    
    if not pdf_file.suffix.lower() == '.pdf':
        logger.error(f"File is not a PDF: {pdf_path}")
        return False
    
    if output_dir is None:
        output_dir = Path(__file__).parent / "output" / "markdown"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        settings = get_settings()
        openai_api_key = settings.openai_api_key.get_secret_value()
    except Exception as e:
        logger.warning(f"Could not load OpenAI API key from config: {e}")
        logger.warning("OpenAI Vision fallback will not be available")
        openai_api_key = None
    
    logger.info(f"Converting PDF to markdown: {pdf_file.name}")
    logger.info(f"Output directory: {output_dir}")
    
    parser = PDFParser(output_dir, openai_api_key=openai_api_key)
    
    try:
        result = parser.parse_pdf(pdf_file)
        
        logger.info("=" * 80)
        logger.info("✓ Conversion successful!")
        logger.info("=" * 80)
        logger.info(f"Markdown file: {result['markdown_path']}")
        logger.info("")
        logger.info("Extracted metadata:")
        for key, value in result['metadata'].items():
            logger.info(f"  {key}: {value}")
        logger.info("=" * 80)
        
        return True
    
    except Exception as e:
        logger.error(f"✗ Conversion failed: {e}", exc_info=True)
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    success = convert_pdf_to_markdown(pdf_path, output_dir)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

