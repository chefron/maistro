from qdrant_client import QdrantClient
from qdrant_client.http import models
from typing import Dict, List, Optional
from uuid import uuid4
import logging
import math
import os
import inspect
from pathlib import Path
from sentence_transformers import SentenceTransformer
from .types import Memory, SearchResult

logger = logging.getLogger('maistro.core.memory.store')

class VectorStore:
    """Vector database for storing and searching memories by category using Qdrant."""
    def __init__(self, artist_name: str):
        # Create path to artist's memory directory
        self.db_path = Path(__file__).parent.parent.parent / "artists" / artist_name.lower() / "memory" / "qdrant_db"
        logger.info(f"Initializing VectorStore with path: {self.db_path}")
        
        # Create memory_db directory if it doesn't exist
        self.db_path.mkdir(exist_ok=True)

        # Create a persistent client with artist-specific path
        self.client = QdrantClient(path=str(self.db_path))
        self.collections = set()
        
        # Initialize embedding model
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.vector_size = self.embedding_model.get_sentence_embedding_dimension()
        logger.info(f"Initialized SentenceTransformer model with dimension: {self.vector_size}")

        # Load existing collections
        try:
            collection_list = self.client.get_collections().collections
            for collection in collection_list:
                self.collections.add(collection.name)
            logger.info(f"Found existing collections: {self.collections}")
        except Exception as e:
            logger.error(f"Error loading existing collections: {e}")

    def _create_collection_if_not_exists(self, category: str) -> None:
        """Create a new collection if it doesn't already exist"""
        if category in self.collections:
            return
            
        try:
            # Create the collection
            self.client.create_collection(
                collection_name=category,
                vectors_config=models.VectorParams(
                    size=self.vector_size, 
                    distance=models.Distance.COSINE
                )
            )
            self.collections.add(category)
            logger.info(f"Created new collection: {category}")
        except Exception as e:
            logger.error(f"Error creating collection {category}: {e}")
            raise
    
    def _get_embeddings(self, text: str) -> List[float]:
        """Generate embeddings for text content using SentenceTransformers"""
        try:
            # Generate embeddings
            embedding = self.embedding_model.encode(text, normalize_embeddings=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            # Return a zero vector as fallback (not ideal but prevents crashes)
            return [0.0] * self.vector_size
    
    def add(self, category: str, content: str, metadata: Dict) -> Memory:
        """Add a new memory"""
        self._create_collection_if_not_exists(category)
        
        memory_id = str(uuid4())
        logger.info(f"Adding memory {memory_id} to collection {category}")

        try:
            # Get embeddings for the content
            embedding = self._get_embeddings(content)
            
            # Store content in the payload
            payload = {**metadata, "content": content}
            
            # Store in Qdrant
            self.client.upsert(
                collection_name=category,
                points=[
                    models.PointStruct(
                        id=memory_id,
                        vector=embedding,
                        payload=payload
                    )
                ]
            )

            return Memory(
                id=memory_id,
                content=content,
                category=category,
                metadata=metadata
            )
        
        except Exception as e:
            logger.error(f"Error adding document to collection: {e}")
            raise e
        
    def list_categories(self) -> List[str]:
        """List all categories"""
        return list(self.collections)
    
    def get_memories(
        self,
        category: str,
        n_results: int = 10,
        filter_metadata: Optional[Dict] = None
    ) -> List[Memory]:
        """Get memories from a category with optional filtering"""
        if category not in self.collections:
            return []
        
        try:
            # Convert filter_metadata to Qdrant filter format
            qdrant_filter = None
            if filter_metadata:
                qdrant_filter = self._metadata_to_filter(filter_metadata)
            
            # Scroll through points without vector search (retrieves in insertion order)
            points = self.client.scroll(
                collection_name=category,
                limit=n_results,
                scroll_filter=qdrant_filter
            )[0]  # The scroll method returns a tuple (points, next_page_offset)
            
            memories = []
            for point in points:
                payload = point.payload
                content = payload.pop("content")  # Extract content from payload
                
                memories.append(Memory(
                    id=str(point.id),
                    content=content,
                    category=category,
                    metadata=payload
                ))
            
            return memories
            
        except Exception as e:
            logger.error(f"Error retrieving memories from {category}: {e}")
            return []

    def search(
        self,
        category: str,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict] = None
    ) -> List[SearchResult]:
        """Search for similar memories in a category"""
        if category not in self.collections:
            logger.info(f"Category {category} not found in collections: {list(self.collections)}")
            return []

        try:
            # Get embeddings for the query
            query_vector = self._get_embeddings(query)
            
            # Convert filter_metadata to Qdrant filter format
            qdrant_filter = None
            if filter_metadata:
                qdrant_filter = self._metadata_to_filter(filter_metadata)
            
            search_results = self.client.search(
                collection_name=category,
                query_vector=query_vector,
                limit=n_results,
                query_filter=qdrant_filter
            )
            
            results = []
            for point in search_results:
                payload = point.payload
                content = payload.pop("content")  # Extract content from payload
                
                memory = Memory(
                    id=str(point.id),
                    content=content,
                    category=category,
                    metadata=payload
                )
                
                # Similarity score is provided by Qdrant
                similarity_score = point.score
                
                # Apply category boost if needed
                if category == "metrics":
                    similarity_score *= 1.1  # Boost scores for metrics to keep at top of mind
                
                results.append(SearchResult(
                    memory=memory,
                    similarity_score=similarity_score
                ))
            
            return results

        except Exception as e:
            logger.error(f"Error searching collection {category}: {e}")
            return []
    
    def _metadata_to_filter(self, metadata: Dict) -> models.Filter:
        """Convert metadata dictionary to Qdrant filter format"""
        conditions = []
        
        for key, value in metadata.items():
            if isinstance(value, (list, tuple)):
                # Handle lists (any value in the list matches)
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchAny(any=value)
                    )
                )
            else:
                # Handle single values
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value)
                    )
                )
        
        # Combine all conditions with AND logic
        if len(conditions) == 1:
            return conditions[0]
        elif len(conditions) > 1:
            return models.Filter(
                must=conditions
            )
        else:
            return None
    
    def delete(self, category: str, memory_id: str) -> bool:
        """Delete a specific memory"""
        if category not in self.collections:
            return False
        
        logger.info(f"Deleting memory {memory_id} from collection {category}")

        try:
            self.client.delete(
                collection_name=category,
                points_selector=models.PointIdsList(
                    points=[memory_id]
                )
            )
            return True
        
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id} from {category}: {e}")
            return False