import logging
import os
from typing import List, Dict, Any
import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class JinaEmbedder:
    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1.5", device: str = None):
        self.model_name = model_name
        
        # Dimension varies by model
        if "nomic" in model_name:
            self.dimension = 768
        elif "jina" in model_name:
            self.dimension = 1024
        else:
            self.dimension = 768  # default
        
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        else:
            self.device = device
        
        logger.info(f"Loading embedding model: {self.model_name} on device: {self.device}")
        
        try:
            self.model = SentenceTransformer(
                self.model_name,
                device=self.device,
                trust_remote_code=True
            )
            logger.info(f"Model loaded successfully (dimension: {self.dimension})")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise
    
    def embed_chunks(self, chunks: List[Dict[str, Any]], task: str = "search_document") -> List[Dict[str, Any]]:
        logger.info(f"Embedding {len(chunks)} chunks")
        
        texts = [chunk['content'] for chunk in chunks]
        
        max_length = 8192 if "nomic" in self.model_name else 8192
        truncated_count = 0
        for i, text in enumerate(texts):
            if len(text) > max_length:
                texts[i] = text[:max_length]
                truncated_count += 1
        
        if truncated_count > 0:
            logger.warning(f"Truncated {truncated_count} chunks that exceeded {max_length} characters")
        
        embeddings = self._get_embeddings(texts, task)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk['embedding'] = embedding
        
        return chunks
    
    def embed_query(self, query: str) -> List[float]:
        logger.info(f"Embedding query: {query[:50]}...")
        
        embeddings = self._get_embeddings([query], task="search_query")
        
        return embeddings[0]
    
    def _get_embeddings(self, texts: List[str], task: str) -> List[List[float]]:
        try:
            if "nomic" in self.model_name:
                if task == "search_query":
                    texts = [f"search_query: {text}" for text in texts]
                else:
                    texts = [f"search_document: {text}" for text in texts]
            
            embeddings = self.model.encode(
                texts,
                batch_size=32,
                show_progress_bar=len(texts) > 100,
                convert_to_numpy=True,
                normalize_embeddings=True,
                truncate_dim=2048
            )
            
            embeddings_list = embeddings.tolist()
            logger.info(f"Successfully embedded {len(embeddings_list)} texts")
            
            return embeddings_list
        
        except Exception as e:
            logger.error(f"Error getting embeddings: {e}")
            raise
    
    def batch_embed(self, texts: List[str], task: str, batch_size: int = 32) -> List[List[float]]:
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}/{(len(texts) + batch_size - 1) // batch_size}")
            
            embeddings = self._get_embeddings(batch, task)
            all_embeddings.extend(embeddings)
        
        return all_embeddings

