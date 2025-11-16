import logging
import os
from typing import Dict, Any
from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAISummarizer:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.error("No OpenAI API key provided")
            raise ValueError("OpenAI API key is required")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o-mini"
        self.max_tokens = 200
    
    def summarize_document(self, document_data: Dict[str, Any]) -> str:
        logger.info(f"Summarizing document: {document_data['document_name']}")
        
        markdown_content = document_data['markdown_content']
        
        truncated_content = markdown_content[:8000]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a legal expert specializing in food safety and regulatory compliance. Summarize regulatory documents concisely."
                    },
                    {
                        "role": "user",
                        "content": f"""Summarize this regulatory document in exactly 200 tokens or less. Focus on:
1. The scope and purpose of the regulation
2. Key requirements and obligations
3. Who must comply
4. Main compliance areas

Document:
{truncated_content}

Summary:"""
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=0.3
            )
            
            summary = response.choices[0].message.content.strip()
            logger.info(f"Successfully generated summary ({len(summary)} chars)")
            
            return summary
        
        except Exception as e:
            logger.error(f"Error generating summary with OpenAI: {e}")
            logger.warning("Using fallback summary")
            return self._fallback_summary(markdown_content)
    
    def _fallback_summary(self, content: str) -> str:
        words = content.split()[:200]
        summary = ' '.join(words)
        
        if len(words) == 200:
            summary += "..."
        
        return summary

