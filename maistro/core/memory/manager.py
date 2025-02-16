from typing import Dict, List, Optional, Union
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import logging
import re
from pypdf import PdfReader
from .store import VectorStore
from .types import Memory, SearchResult, MemoryStats

logger = logging.getLogger('maistro.core.memory.manager')

class MemoryManager:
    def __init__(self, artist_name: str):
        self.store = VectorStore(artist_name)
        self.artist_name = artist_name

    def create(self,
               category: str,
               content: str,
               metadata: Optional[Dict] = None
    ) -> Memory:
        """Create a new memory"""
        metadata = metadata or {}
        metadata.update({
            "timestamp": datetime.now().isoformat(),
            "artist": self.artist_name
        })

        return self.store.add(category, content, metadata)

    def search(
        self,
        query: str,
        category: Optional[Union[str, List[str]]] = None,
        n_results: int = 5,
        min_similarity: float = 0.25,
        filter_metadata: Optional[Dict] = None,
    ) -> List[SearchResult]:
        """Search for similar memories across one or multiple categories"""
        available_categories = self.list_categories()
        if not available_categories:
            print("No categories available")
            return []
        
        # Determine categories to search
        if category is None:
            categories = available_categories
        elif isinstance(category, str):
            categories = [category] if category in available_categories else []
        else: # List of categories
            categories = [cat for cat in category if cat in available_categories]

        # Search each category
        results = []
        for cat in categories:
            cat_results = self.store.search(
                cat,
                query,
                n_results=n_results,
                filter_metadata=filter_metadata
            )
            results.extend(cat_results)

        # Sort and filter results
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        filtered_results = [
            result for result in results
            if result.similarity_score > min_similarity
        ]

        return filtered_results[:n_results]

    def get_relevant_context(
        self,
        query: str,
        categories: Optional[List[str]] = None,
        n_results: int = 5,
    ) -> tuple[str, List[SearchResult]]:
        """Get relevant memory context for a query"""
        results = self.search(
            query=query,
            category=categories,
            n_results=n_results
        )

        if not results:
            return "", []
        
        context = "\n\n".join(
            f"From {result.memory.category}/{result.memory.metadata.get('source', 'reference')}:\n"
            f"{result.memory.content}"
            for result in results
        )

        return context, results

    def _is_header(
        self, 
        line: str,
        prev_line: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """Detect if a line is a header and return the header text if it is
        
        Args:
            line: Current line to check
            prev_line: Previous line (needed for Setext headers)

        Returns:
            Tuple of (is_header, header_text)
        """

        stripped = line.strip()

        # ATX-style headers (# Header)
        if stripped.startswith('#'):
            # Count the number of #s at start
            level = 0
            for char in stripped:
                if char == '#':
                    level += 1
                else:
                    break

            # Verify it's a proper header with space after #s
            if level > 0 and level <= 6 and (len(stripped) == level or stripped[level] == ' '):
                return True, stripped.lstrip('#').strip()
            
        # Setext-style headers (underlines)
        if prev_line and stripped and all(c == '=' or c == '-' for c in stripped):
            if '=' in stripped: # h1
                return True, prev_line.strip()
            elif '-' in stripped: # h2
                return True, prev_line.strip()
            
        # HTML-style headers
        if stripped.lower().startswith(('<h1>', '<h2>', '<h3>', '<h4>', '<h5>', '<h6>')):
            # Extract text between tags
            match = re.match(r'<h[1-6]>(.*?)</h[1-6]>', stripped, re.IGNORECASE)
            if match:
                return True, match.group(1).strip()
            
        # All caps text (with minimum length and allowing some special characters)
        if len(stripped) > 4 and stripped.upper() == stripped:
            # Allow common characters like : - _ .
            allowed_special = set(':-_.?!')
            if all(c.isupper() or c in allowed_special or c.isspace() for c in stripped):
                return True, stripped
        
        return False, None

    def split_document(
        self,
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        respect_boundaries: bool = True,
        content_type: Optional[str] = None,
    ) -> List[Dict[str, Optional[str]]]:
        """Split a document into overlapping chunks while respecting content boundaries
        
        Args:
            text: Source text to split
            chunk_size: Target size for each chunk
            chunk_overlap: Number of characters to overlap between chunks
            respect_boundaries: Try to break at sentence/paragraph boundaries
            content_type: Type of content e.g., 'lyrics', 'analysis', 'feedback') is used to adjust chunking behavior
        """

        # Adjust chunk parameters based on content type
        if content_type:
            if content_type == 'lyrics':
                chunk_size = min(chunk_size, 300) # Smaller chunks for lyrics to preserve line breaks and stanzas
                respect_boundaries = True
            elif content_type == 'feedback':
                if len(text) < chunk_size:
                    return [{'header': None, 'content': text.strip()}]
            elif content_type == 'analysis':
                chunk_size = max(chunk_size, 800) # Larger chunks for analysis

        sections = []

        # First, split into coarse sections based on headers
        coarse_sections = []
        current_section = []
        current_header = None
        prev_line = None

        for line in text.splitlines():
            is_header, header_text = self._is_header(line, prev_line)

            if is_header:
                # Save previous section if it exists
                if current_section:
                    coarse_sections.append({
                        'header': current_header,
                        'content': '\n'.join(current_section)
                    })
                current_header = header_text
                current_section = []

                # For setext headers, include the previous line
                if prev_line and all(c == '=' or c == '-' for c in line.strip()):
                    current_section.append(prev_line)
            
            current_section.append(line)
            prev_line = line
 
        # Add final section
        if current_section:
            coarse_sections.append({
                'header': current_header,
                'content': '\n'.join(current_section)
            })

        # Now split each coarse section into smaller chunks
        for section in coarse_sections:
            content = section['content']
            header = section['header']

            # If content is short enough, keep it as one chunk
            if len(content) <= chunk_size:
                sections.append({
                    'header': header,
                    'content': content.strip()
                })
                continue

            # Split into overlapping chunks
            start = 0
            while start < len(content):
                # First end of chunk
                end = start + chunk_size

                if respect_boundaries and end < len(content):
                    # Define a window to look for boundaries
                    window_start = max(0, end - 50)
                    window_end = min(len(content), end + 50)
                    window = content[window_start:window_end]

                    # Look for sentence endings in the window
                    endings = [
                        '. ', '! ', '? ',     # Basic sentence endings
                        '."', '!"', '?"',      # Quote endings
                        ".'", "!'", "?'",      # Single quote endings
                    ]
                    best_end = -1

                    for ending in endings:
                        # Find all occurrences of this ending in the window
                        pos = window.find(ending)
                        while pos != -1:
                            absolute_pos = window_start + pos
                            if absolute_pos >= end - 50 and absolute_pos <= end + 50:
                                # Found a valid ending
                                if best_end == -1 or abs(end - absolute_pos) < abs(end - best_end):
                                    best_end = absolute_pos
                            pos = window.find(ending, pos + 1)

                    if best_end != -1:
                        end = best_end + 1
                    else:
                        # Try paragraph boundary
                        para_end = content.find('\n\n', end - 50, end + 50)
                        if para_end != -1:
                            end = para_end

                chunk_content = content[start:end].strip()
                if chunk_content: # Only add non-empty chunks
                    sections.append({
                        'header': header,
                        'content': chunk_content
                    })

                # Move start for next chunk, considering overlap
                start = end - chunk_overlap
                if start < 0:
                    start = 0

        return sections

    def create_chunks(
        self,
        file_path: Optional[str] = None,
        category: str = None,
        content_type: Optional[str] = None,
        metadata: Optional[Dict] = None,
        should_chunk: Optional[bool] = None,
        direct_content: Optional[str] = None # Programmatically generated content, e.g. streaming stats  
    ) -> List[str]:
        """
        Process and store content, either from a file or direct text input

        Args:
            file_path: Path to the document (optional if direct_context provided)
            category: Memory category to store in
            content_type: Type of content (e.g., 'lyrics', 'analysis', 'feedback')
            metadata: Additional metadata
            should_chunk: Override automatic chunking decision
            direct_content: Direct text input (optional if file_path provided)
        """
        if not (file_path or direct_content):
            raise ValueError("Either file_path or direct_content must be provided")

        memory_ids = []
        base_metadata = {
            **({"source": file_path, "document_type": Path(file_path).suffix[1:].lower()} if file_path 
            else {"source": "direct_input"}),  # Set a default source for text content
            "content_type": content_type,
            **(metadata or {})
        }
        
        try:
            # Get content from different file types or direct input (text)
            if direct_content:
                text = direct_content
            else:
                if file_path.endswith('.pdf'):
                    reader = PdfReader(file_path)
                    text = ""
                    for i, page in enumerate(reader.pages):
                        page_text = page.extract_text()
                        if page_text.strip():
                            text += f"Page {i+1} of {len(reader.pages)}:\n{page_text}\n\n"
                    base_metadata.update({
                        "total_pages": len(reader.pages),
                        "has_text": bool(text.strip())
                    })
                else:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        text = file.read()

            # Determine if we should chunk this document
            if should_chunk is None:
                should_chunk = len(text) > 1000 # Default threshold

                # Adjust based on content type
                if content_type == 'feedback' and len(text) < 500:
                    should_chunk = False
                elif content_type == 'analysis':
                    should_chunk = True
            
            # Process content
            if should_chunk:
                sections = self.split_document(
                    text,
                    content_type = content_type
                )
            else:
                sections = [{'header': None, 'content': text.strip()}]

            # Create memories for each section
            for i, section in enumerate(sections):
                section_metadata = {
                    **base_metadata,
                    "chunk_index": i,
                    "chunks_total": len(sections),
                    "section_header": section['header'],
                    "chunk_size": len(section['content'])
                }

                memory = self.create(
                    category=category,
                    content=section['content'],
                    metadata=section_metadata
                )
                memory_ids.append(memory.id)

            return memory_ids
        
        except Exception as e:
            logger.error(f"Failed to process document {file_path}: {str(e)}")
            raise

    def upload_documents(
        self,
        filepaths: List[str],
        category: str,
        content_type: Optional[str] = None,
        metadata: Optional[Dict] = None,
        should_chunk: Optional[bool] = None
    ) -> Dict[str, int]:
        """Upload one or more documents to memory"""
        successful = 0
        failed = 0
        total_chunks = 0

        for filepath in filepaths:
            try:
                memory_ids = self.create_chunks(
                    filepath,
                    category=category,
                    content_type=content_type,
                    metadata={
                        "type": "document",
                        "original_filename": filepath,
                        "upload_timestamp": datetime.now().isoformat(),
                        **(metadata or {})
                    },
                    should_chunk=should_chunk
                )
                successful += 1
                total_chunks += len(memory_ids)

            except FileNotFoundError:
                failed += 1
            except Exception as e:
                logger.error(f"Error processing {filepath}: {e}")
                failed += 1
            
        # Return upload statistics
        return {
            "total_attempted": len(filepaths),
            "successful": successful,
            "failed": failed,
            "total_chunks": total_chunks
        }

    def get_category_stats(self, category: str) -> MemoryStats:
        """Get statistics about a category's contents"""
        if category not in self.store.collections:
            return MemoryStats(
                document_count=0,
                total_chunks=0,
                documents=[]
            )
        
        memories = self.store.get_memories(category, n_results=1000)
        
        # Handle empty category
        if not memories:
            return MemoryStats(
                document_count=0,
                total_chunks=0,
                documents=[]
            )
        
        # Group memories by original source
        docs = defaultdict(list)
        for memory in memories:
            source = memory.metadata.get('source', 'Unknown source')
            docs[source].append(memory)
        
        documents = [
            {
                "source": source,
                "chunk_count": len(chunks),
                "total_size": sum(len(chunk.content) for chunk in chunks),
                "created_at": min(chunk.created_at for chunk in chunks)
            }
            for source, chunks in docs.items()
        ]
        
        return MemoryStats(
            document_count=len(docs),
            total_chunks=len(memories),
            documents=documents
        )

    def list_categories(self) -> List[str]:
        """List all memory categories"""
        return self.store.list_categories()

    def delete_memory(self, category: str, memory_id: str) -> bool:
        """Delete a specific memory"""
        return self.store.delete(category, memory_id)
        
    def remove_category(self, category: str) -> bool:
        """Delete an entire category of memories"""
        try:
            if category in self.store.collections:
                # Delete the collection from ChromaDB
                self.store.client.delete_collection(category)
                # Remove from our collections dict
                del self.store.collections[category]
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting category {category}: {e}")
            return False
        
    def wipe_document(self, category: str, filename: str) -> int:
        """Delete all chunks belonging to a specific document
        Returns number of chunks deleted"""
        memories = self.store.get_memories(category, n_results=1000)
        chunks_deleted = 0
        
        for memory in memories:
            if memory.metadata.get('original_filename') == filename:
                if self.delete_memory(category, memory.id):
                    chunks_deleted += 1
        
        return chunks_deleted

    def wipe_category(self, category: str) -> Dict[str, int]:
        """Delete all memories in a category
        Returns statistics about what was deleted"""
        stats = self.get_category_stats(category)
        success = self.remove_category(category)
        return {
            "success": success,
            "documents_deleted": stats.document_count,
            "chunks_deleted": stats.total_chunks
        }
    
    def wipe_all_memories(self) -> bool:
        """Delete all memories and collections"""
        try:
            for category in self.list_categories():
                self.remove_category(category)
            return True
        except Exception as e:
            logger.error(f"Error wiping all memories: {e}")
            return False