import logging
from typing import List, Dict, Any, Protocol

logger = logging.getLogger(__name__)


class EmbedderProtocol(Protocol):
    """Protocol for embedding providers."""

    dimension: int

    def embed_chunks(self, chunks: List[Dict[str, Any]], task: str = "search_document") -> List[Dict[str, Any]]:
        ...

    def embed_query(self, query: str) -> List[float]:
        ...


class OpenAIEmbedder:
    """OpenAI embeddings using text-embedding-3-small."""

    def __init__(self, api_key: str, dimension: int = 768):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = "text-embedding-3-small"
        self.dimension = dimension

        logger.info(f"Initialized OpenAI embedder with {self.model} (dimension: {self.dimension})")

    def embed_chunks(self, chunks: List[Dict[str, Any]], task: str = "search_document") -> List[Dict[str, Any]]:
        """Embed multiple chunks."""
        logger.info(f"Embedding {len(chunks)} chunks with OpenAI")

        texts = [chunk['content'] for chunk in chunks]
        embeddings = self._get_embeddings(texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk['embedding'] = embedding

        return chunks

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query."""
        logger.info(f"Embedding query: {query[:50]}...")
        return self._get_embeddings([query])[0]

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings from OpenAI API."""
        # Process in batches of 100 (OpenAI limit is 2048)
        batch_size = 100
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimension
            )

            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

        logger.info(f"Successfully embedded {len(all_embeddings)} texts with OpenAI")
        return all_embeddings


class LocalEmbedder:
    """Local embeddings using sentence-transformers."""

    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1.5", device: str = None):
        import torch
        from sentence_transformers import SentenceTransformer

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

        logger.info(f"Loading local embedding model: {self.model_name} on device: {self.device}")

        self.model = SentenceTransformer(
            self.model_name,
            device=self.device,
            trust_remote_code=True
        )
        logger.info(f"Model loaded successfully (dimension: {self.dimension})")

    def embed_chunks(self, chunks: List[Dict[str, Any]], task: str = "search_document") -> List[Dict[str, Any]]:
        """Embed multiple chunks."""
        logger.info(f"Embedding {len(chunks)} chunks locally")

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
        """Embed a single query."""
        logger.info(f"Embedding query: {query[:50]}...")
        return self._get_embeddings([query], task="search_query")[0]

    def _get_embeddings(self, texts: List[str], task: str) -> List[List[float]]:
        """Get embeddings from local model."""
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
        logger.info(f"Successfully embedded {len(embeddings_list)} texts locally")
        return embeddings_list


def create_embedder(
    provider: str = "openai",
    api_key: str = None,
    model_name: str = "nomic-ai/nomic-embed-text-v1.5",
    device: str = None,
) -> EmbedderProtocol:
    """Factory function to create the appropriate embedder.

    Args:
        provider: 'openai' or 'local'
        api_key: OpenAI API key (required for 'openai' provider)
        model_name: Model name for local embedder
        device: Device for local embedder (auto-detected if None)

    Returns:
        Embedder instance
    """
    if provider == "openai":
        if not api_key:
            raise ValueError("OpenAI API key required for openai embedding provider")
        return OpenAIEmbedder(api_key=api_key, dimension=768)
    elif provider == "local":
        return LocalEmbedder(model_name=model_name, device=device)
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


# Backwards compatibility alias
class Embedder(LocalEmbedder):
    """Backwards compatible alias for LocalEmbedder."""
    pass
