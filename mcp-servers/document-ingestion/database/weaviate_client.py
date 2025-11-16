import logging
import os
from typing import List, Dict, Any, Optional
import weaviate
from weaviate.classes.config import Property, DataType, Configure
from weaviate.classes.query import Filter, MetadataQuery

logger = logging.getLogger(__name__)


class WeaviateClient:
    def __init__(self, url: str = None):
        self.url = url or os.getenv("WEAVIATE_URL", "http://localhost:8080")
        self.client = None
        self.collection_name = "RegulationChunk"
    
    def connect(self):
        logger.info(f"Connecting to Weaviate at {self.url}")
        try:
            self.client = weaviate.connect_to_local(host=self.url.replace("http://", "").replace(":8080", ""))
            logger.info("Successfully connected to Weaviate")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            return False
    
    def disconnect(self):
        if self.client:
            self.client.close()
            logger.info("Disconnected from Weaviate")
    
    def create_schema(self):
        logger.info("Creating Weaviate schema")
        
        try:
            if self.client.collections.exists(self.collection_name):
                logger.info(f"Collection {self.collection_name} already exists, deleting...")
                self.client.collections.delete(self.collection_name)
            
            self.client.collections.create(
                name=self.collection_name,
                vectorizer_config=Configure.Vectorizer.none(),
                properties=[
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="chunk_id", data_type=DataType.TEXT),
                    Property(name="document_name", data_type=DataType.TEXT),
                    Property(name="document_summary", data_type=DataType.TEXT),
                    Property(name="source_type", data_type=DataType.TEXT),
                    Property(name="regulation_type", data_type=DataType.TEXT),
                    Property(name="regulation_number", data_type=DataType.TEXT),
                    Property(name="article_number", data_type=DataType.TEXT),
                    Property(name="section_title", data_type=DataType.TEXT),
                    Property(name="page_number", data_type=DataType.INT),
                    Property(name="page_range", data_type=DataType.TEXT),
                    Property(name="effective_date", data_type=DataType.TEXT),
                    Property(name="nvwa_category", data_type=DataType.TEXT),
                    Property(name="keywords", data_type=DataType.TEXT_ARRAY),
                    Property(name="previous_chunk_id", data_type=DataType.TEXT),
                    Property(name="next_chunk_id", data_type=DataType.TEXT),
                ]
            )
            
            logger.info(f"Schema created successfully for {self.collection_name}")
            return True
        
        except Exception as e:
            logger.error(f"Error creating schema: {e}")
            return False
    
    def ingest_chunks(self, chunks: List[Dict[str, Any]], document_summary: str):
        logger.info(f"Ingesting {len(chunks)} chunks into Weaviate")
        
        try:
            collection = self.client.collections.get(self.collection_name)
            
            with collection.batch.dynamic() as batch:
                for chunk in chunks:
                    vector = chunk.pop('embedding', None)
                    
                    if vector is None:
                        logger.warning(f"Chunk {chunk.get('chunk_id')} has no embedding, skipping")
                        continue
                    
                    properties = {
                        "content": chunk.get("content", ""),
                        "chunk_id": chunk.get("chunk_id", ""),
                        "document_name": chunk.get("document_name", ""),
                        "document_summary": document_summary,
                        "source_type": chunk.get("source_type", "Unknown"),
                        "regulation_type": chunk.get("regulation_type", "general"),
                        "regulation_number": chunk.get("regulation_number") or "",
                        "article_number": chunk.get("article_number") or "",
                        "section_title": chunk.get("section_title") or "",
                        "page_number": chunk.get("page_number", 0),
                        "page_range": chunk.get("page_range", ""),
                        "effective_date": chunk.get("effective_date") or "",
                        "nvwa_category": chunk.get("nvwa_category", "General Compliance"),
                        "keywords": chunk.get("keywords", []),
                        "previous_chunk_id": chunk.get("previous_chunk_id") or "",
                        "next_chunk_id": chunk.get("next_chunk_id") or "",
                    }
                    
                    batch.add_object(
                        properties=properties,
                        vector=vector
                    )
            
            logger.info(f"Successfully ingested {len(chunks)} chunks")
            return True
        
        except Exception as e:
            logger.error(f"Error ingesting chunks: {e}")
            return False
    
    def search(self, query_vector: List[float], filters: Optional[Dict[str, Any]] = None, 
               limit: int = 10, alpha: float = 0.7) -> List[Dict[str, Any]]:
        logger.info(f"Searching with filters: {filters}, limit: {limit}")
        
        try:
            collection = self.client.collections.get(self.collection_name)
            
            where_filter = None
            if filters:
                filter_conditions = []
                
                if "source_type" in filters:
                    filter_conditions.append(
                        Filter.by_property("source_type").equal(filters["source_type"])
                    )
                
                if "regulation_type" in filters:
                    filter_conditions.append(
                        Filter.by_property("regulation_type").equal(filters["regulation_type"])
                    )
                
                if filter_conditions:
                    where_filter = filter_conditions[0]
                    for condition in filter_conditions[1:]:
                        where_filter = where_filter & condition
            
            response = collection.query.hybrid(
                query=None,
                vector=query_vector,
                alpha=alpha,
                limit=limit,
                filters=where_filter,
                return_metadata=MetadataQuery(score=True, distance=True)
            )
            
            results = []
            for obj in response.objects:
                result = {
                    "content": obj.properties.get("content", ""),
                    "chunk_id": obj.properties.get("chunk_id", ""),
                    "document_name": obj.properties.get("document_name", ""),
                    "document_summary": obj.properties.get("document_summary", ""),
                    "source_type": obj.properties.get("source_type", ""),
                    "regulation_type": obj.properties.get("regulation_type", ""),
                    "regulation_number": obj.properties.get("regulation_number", ""),
                    "article_number": obj.properties.get("article_number", ""),
                    "section_title": obj.properties.get("section_title", ""),
                    "page_number": obj.properties.get("page_number", 0),
                    "page_range": obj.properties.get("page_range", ""),
                    "nvwa_category": obj.properties.get("nvwa_category", ""),
                    "score": obj.metadata.score if obj.metadata else None,
                }
                results.append(result)
            
            logger.info(f"Found {len(results)} results")
            return results
        
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        logger.info(f"Getting chunk by ID: {chunk_id}")
        
        try:
            collection = self.client.collections.get(self.collection_name)
            
            response = collection.query.fetch_objects(
                filters=Filter.by_property("chunk_id").equal(chunk_id),
                limit=1
            )
            
            if response.objects:
                obj = response.objects[0]
                return {
                    "content": obj.properties.get("content", ""),
                    "chunk_id": obj.properties.get("chunk_id", ""),
                    "previous_chunk_id": obj.properties.get("previous_chunk_id", ""),
                    "next_chunk_id": obj.properties.get("next_chunk_id", ""),
                    "document_name": obj.properties.get("document_name", ""),
                    "article_number": obj.properties.get("article_number", ""),
                    "section_title": obj.properties.get("section_title", ""),
                }
            
            return None
        
        except Exception as e:
            logger.error(f"Error getting chunk by ID: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        logger.info("Getting collection statistics")
        
        try:
            collection = self.client.collections.get(self.collection_name)
            
            response = collection.aggregate.over_all(total_count=True)
            
            return {
                "total_chunks": response.total_count,
                "collection_name": self.collection_name
            }
        
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}

