from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Memory:
    """Represents a single memory item"""
    id: str
    content: str
    category: str
    metadata: Dict
    embedding: Optional[List[float]] = None
    created_at: datetime = datetime.now()

@dataclass
class SearchResult:
    """Represents a search result with its similarity score"""
    memory: Memory
    similiarty_score: float

@dataclass
class MemoryStats:
    """Statistics about a memory category"""
    document_count: int
    total_chunks: int
    documents: List[Dict]