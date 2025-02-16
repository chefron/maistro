from chromadb import PersistentClient
from typing import Dict, List, Optional
from uuid import uuid4
import logging
import math
import os
from pathlib import Path
from .types import Memory, SearchResult

os.environ["ANONYMIZED_TELEMETRY"] = "false"
logger = logging.getLogger('maistro.core.memory.store')

class VectorStore:
    """Vector database for storing and searching memories by category."""
    def __init__(self, artist_name: str):
        # Create path to artist's memory directory
        self.db_path = Path(__file__).parent.parent.parent / "artists" / artist_name.lower() / "memory" / "memory_db"
        # Create memory_db directory if it doesn't exist
        self.db_path.mkdir(exist_ok=True)

        # Create a persistent client with artist-specific path
        self.client = PersistentClient(path=str(self.db_path))
        self.collections = {}

        # Load existing collections
        try:
            collection_names = self.client.list_collections()
            for name in collection_names:
                try:
                    self.collections[name] = self.client.get_collection(name)
                except Exception as e:
                    logger.error(f"Error loading collection {name}: {e}")
        except Exception as e:
            logger.error(f"Error loading existing collections: {e}")

    def _clean_metadata(self, metadata: Dict) -> Dict:
        """Clean metadata to ensure all values are ChromaDB-compatible types"""
        cleaned = {}
        for key, value in metadata.items():
            # Convert none to empty string
            if value is None:
                cleaned[key] = ""
            # Convert any other values to strings if they're not primitive types
            elif not isinstance(value, (str, int, float, bool)):
                cleaned[key] = str(value)
            else:
                cleaned[key] = value
        return cleaned
    
    def add(self, category: str, content: str, metadata: Dict) -> Memory:
        """Add a new memory"""
        if category not in self.collections:
            self.collections[category] = self.client.create_collection(category)
        
        collection = self.collections[category]
        memory_id = str(uuid4())

        try:
            clean_metadata = self._clean_metadata(metadata)

            collection.add(
                documents=[content],
                metadatas=[clean_metadata],
                ids=[memory_id]
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
        return list(self.collections.keys())
    
    def get_memories(
        self,
        category: str,
        n_results: int = 10,
        filter_metadata: Optional[Dict] = None
    ) -> List[Memory]:
        """Get most recent memories from a category"""
        if category not in self.collections:
            return []
        
        collection = self.collections[category]
        results = collection.get(
            where=filter_metadata,
            limit=n_results,
        )

        memories = []
        for i in range(len(results['ids'])):
            memories.append(Memory(
                id=results['ids'][i],
                content=results['documents'][i],
                category=category,
                metadata=results['metadatas'][i],
            ))
        
        return memories[::-1] # Reverse to get the most recent first

    def search(
        self,
        category: str,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict] = None
    ) -> List[SearchResult]:
        """Search for similar memories in a category"""
        if category not in self.collections:
            print(f"Category {category} not found in collections: {list(self.collections.keys())}")
            return []

        collection = self.collections[category]

        try:
            total_docs = len(collection.get()['ids'])
            logger.info(f"Searching through {total_docs} documents in {category}")
            if total_docs == 0:
                logger.error("Collection is empty")
                return []
            
            n_results = min(n_results, total_docs)

            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filter_metadata,
                include=['distances', 'documents', 'metadatas']
            )

            search_results = []
            for i in range(len(results['ids'][0])):
                memory = Memory(
                    id=results['ids'][0][i],
                    content=results['documents'][0][i],
                    category=category,
                    metadata=results['metadatas'][0][i]
                )

                # Calculate similarity score
                distance = float(results['distances'][0][i])
                similarity_score = math.exp(-distance)
                if category == "streaming_stats":
                    similarity_score *= 1.5  # Boost streaming stats scores

                search_results.append(SearchResult(
                    memory=memory,
                    similarity_score=similarity_score
                ))

            return search_results

        except Exception as e:
            logger.error(f"Error searching collection {category}: {e}")
            return []
    
    def delete(self, category: str, memory_id: str) -> bool:
        """Delete a specific memory"""
        if category not in self.collections:
            return False
        
        collection = self.collections[category]

        try:
            collection.delete(ids=[memory_id])
            return True
        
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id} from {category}: {e}")
            return False