import logging
import re
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class SemanticChunker:
    def __init__(self, output_dir: Path, max_chunk_size: int = 2000, overlap: int = 200):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
    
    def chunk_document(self, document_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        logger.info(f"Chunking document: {document_data['document_name']}")
        
        markdown_content = document_data['markdown_content']
        metadata = document_data['metadata']
        
        chunks = self._semantic_split(markdown_content, metadata)
        
        chunks = self._add_navigation_links(chunks)
        
        output_path = self.output_dir / f"{Path(document_data['document_name']).stem}_chunks.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Created {len(chunks)} chunks, saved to: {output_path}")
        
        return chunks
    
    def _semantic_split(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        chunks = []
        
        article_pattern = r'^#+\s*(Artikel\s+\d+[a-z]?\.?)(.*)$'
        section_pattern = r'^#+\s+(.+)$'
        
        lines = content.split('\n')
        current_chunk = []
        current_article = None
        current_section = None
        page_number = 1
        
        for i, line in enumerate(lines):
            article_match = re.match(article_pattern, line, re.IGNORECASE)
            if article_match:
                if current_chunk:
                    chunks.append(self._create_chunk(
                        current_chunk, metadata, current_article, current_section, page_number
                    ))
                
                current_article = article_match.group(1).strip()
                current_section = article_match.group(2).strip() if article_match.group(2) else None
                current_chunk = [line]
                continue
            
            section_match = re.match(section_pattern, line)
            if section_match and not article_match:
                if len(current_chunk) > 50:
                    chunks.append(self._create_chunk(
                        current_chunk, metadata, current_article, current_section, page_number
                    ))
                    current_chunk = []
                
                current_section = section_match.group(1).strip()
                current_chunk.append(line)
                continue
            
            current_chunk.append(line)
            
            chunk_text = '\n'.join(current_chunk)
            if len(chunk_text) > self.max_chunk_size:
                chunks.append(self._create_chunk(
                    current_chunk, metadata, current_article, current_section, page_number
                ))
                
                overlap_text = chunk_text[-self.overlap:]
                current_chunk = [overlap_text]
                page_number += 1
        
        if current_chunk:
            chunks.append(self._create_chunk(
                current_chunk, metadata, current_article, current_section, page_number
            ))
        
        if not chunks:
            chunks = self._fallback_chunking(content, metadata)
        
        return chunks
    
    def _create_chunk(self, lines: List[str], metadata: Dict[str, Any], 
                     article: str, section: str, page: int) -> Dict[str, Any]:
        content = '\n'.join(lines).strip()
        
        keywords = self._extract_keywords(content)
        
        return {
            "chunk_id": str(uuid.uuid4()),
            "content": content,
            "document_name": metadata.get("source_type", "Unknown"),
            "source_type": metadata.get("source_type", "Unknown"),
            "regulation_type": metadata.get("regulation_type", "general"),
            "regulation_number": metadata.get("regulation_number"),
            "article_number": article,
            "section_title": section,
            "page_number": page,
            "page_range": f"{page}",
            "effective_date": metadata.get("effective_date"),
            "nvwa_category": metadata.get("nvwa_category", "General Compliance"),
            "keywords": keywords,
            "previous_chunk_id": None,
            "next_chunk_id": None
        }
    
    def _extract_keywords(self, content: str) -> List[str]:
        keywords = set()
        
        content_lower = content.lower()
        
        keyword_patterns = [
            r'\b(haccp|allergen\w*|temperatuur|hygiëne|microbiolog\w*|etiket\w*|controle|inspectie)\b',
            r'\b(voedselveiligheid|levensmiddelen|horeca|retail|productie)\b',
            r'\b(verordening|artikel|voorschrift\w*|verplichting\w*)\b'
        ]
        
        for pattern in keyword_patterns:
            matches = re.findall(pattern, content_lower)
            keywords.update(matches)
        
        return list(keywords)[:10]
    
    def _add_navigation_links(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for i, chunk in enumerate(chunks):
            if i > 0:
                chunk['previous_chunk_id'] = chunks[i-1]['chunk_id']
            if i < len(chunks) - 1:
                chunk['next_chunk_id'] = chunks[i+1]['chunk_id']
        
        return chunks
    
    def _fallback_chunking(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        logger.warning("Using fallback chunking strategy")
        
        chunks = []
        words = content.split()
        
        for i in range(0, len(words), self.max_chunk_size - self.overlap):
            chunk_words = words[i:i + self.max_chunk_size]
            chunk_content = ' '.join(chunk_words)
            
            chunks.append(self._create_chunk(
                [chunk_content], metadata, None, None, i // self.max_chunk_size + 1
            ))
        
        return chunks

