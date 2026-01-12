#!/usr/bin/env python3
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import get_settings
from parsers.pdf_parser import PDFParser
from chunkers.semantic_chunker import SemanticChunker
from embeddings.embedder import create_embedder
from summarizers.openai_summarizer import OpenAISummarizer
from database.weaviate_client import WeaviateClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting document ingestion pipeline")
    
    try:
        settings = get_settings()
        logger.info(f"Loaded configuration with MCP_ prefix from .env")
        logger.info(f"  Embedding Model: {settings.embedding_model}")
        logger.info(f"  Weaviate URL: {settings.weaviate_url}")
        logger.info(f"  Batch Size: {settings.batch_size}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        logger.error("Make sure MCP_OPENAI_API_KEY is set in your .env file")
        return
    
    base_dir = Path(__file__).parent
    input_dir = base_dir.parent / "input" / "SPEC Agent"
    output_markdown_dir = base_dir / "output" / "markdown"
    output_chunks_dir = base_dir / "output" / "chunks"
    
    output_markdown_dir.mkdir(parents=True, exist_ok=True)
    output_chunks_dir.mkdir(parents=True, exist_ok=True)
    
    if not input_dir.exists():
        logger.error(f"Input directory not found: {input_dir}")
        return
    
    pdf_files = list(input_dir.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files to process")
    
    if not pdf_files:
        logger.error("No PDF files found in input directory")
        return
    
    parser = PDFParser(
        output_markdown_dir,
        openai_api_key=settings.openai_api_key.get_secret_value()
    )
    chunker = SemanticChunker(
        output_chunks_dir,
        max_chunk_size=settings.max_chunk_size,
        overlap=settings.chunk_overlap
    )
    embedder = create_embedder(
        provider=settings.embedding_provider,
        api_key=settings.openai_api_key.get_secret_value() if settings.embedding_provider == "openai" else None,
        model_name=settings.embedding_model,
        device=settings.embedding_device,
    )
    summarizer = OpenAISummarizer(api_key=settings.openai_api_key.get_secret_value())
    weaviate = WeaviateClient(settings.weaviate_url)
    
    if not weaviate.connect():
        logger.error("Failed to connect to Weaviate")
        return
    
    logger.info("Creating Weaviate schema")
    if not weaviate.create_schema():
        logger.error("Failed to create schema")
        weaviate.disconnect()
        return
    
    for i, pdf_file in enumerate(pdf_files):
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing file {i+1}/{len(pdf_files)}: {pdf_file.name}")
        logger.info(f"{'='*80}")
        
        try:
            logger.info("Step 1: Parsing PDF to markdown")
            document_data = parser.parse_pdf(pdf_file)
            
            logger.info("Step 2: Generating document summary")
            document_summary = summarizer.summarize_document(document_data)
            logger.info(f"Summary: {document_summary[:200]}...")
            
            logger.info("Step 3: Chunking document semantically")
            chunks = chunker.chunk_document(document_data)
            
            logger.info("Step 4: Embedding chunks")
            chunks_with_embeddings = embedder.embed_chunks(
                chunks,
                task="search_document"
            )
            
            logger.info("Step 5: Ingesting chunks into Weaviate")
            success = weaviate.ingest_chunks(chunks_with_embeddings, document_summary)
            
            if success:
                logger.info(f"✓ Successfully processed {pdf_file.name}")
            else:
                logger.error(f"✗ Failed to ingest {pdf_file.name}")
        
        except Exception as e:
            logger.error(f"✗ Error processing {pdf_file.name}: {e}", exc_info=True)
            continue
    
    logger.info("\n" + "="*80)
    logger.info("Ingestion complete!")
    logger.info("="*80)
    
    stats = weaviate.get_stats()
    logger.info(f"Total chunks in database: {stats.get('total_chunks', 'unknown')}")
    
    weaviate.disconnect()
    
    logger.info(f"\nIntermediate files saved to:")
    logger.info(f"  Markdown: {output_markdown_dir}")
    logger.info(f"  Chunks: {output_chunks_dir}")


if __name__ == "__main__":
    main()

