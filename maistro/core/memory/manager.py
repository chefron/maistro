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
        n_results: int = 10,
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

        print(f"\nSearch Results for query: \"{query}\"")
        if results:
            print("\nRetrieved Chunks (in order of relevance):")
            for i, result in enumerate(results, 1):
                print(f"\n{i}. Score: {result.similarity_score:.3f}")
                print(f"Category: {result.memory.category}")
                print(f"Source: {result.memory.metadata.get('source', 'Unknown')}")
                print(f"Content Preview: {result.memory.content[:200]}...")
        else:
            print("No relevant memories found.")

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
        prev_line: Optional[str] = None,
        min_header_length: int = 3  # Minimum meaningful header length
    ) -> tuple[bool, Optional[str]]:
        """Detect if a line is a header and return the header text if it is
        
        Args:
            line: Current line to check
            prev_line: Previous line (needed for Setext headers)
            min_header_length: Minimum length for a meaningful header

        Returns:
            Tuple of (is_header, header_text)
        """
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            return False, None
            
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
                header_text = stripped.lstrip('#').strip()
                # Only consider it a header if it has meaningful content
                if len(header_text) >= min_header_length:
                    return True, header_text
                
        # Setext-style headers (underlines)
        if prev_line and stripped and all(c == '=' or c == '-' for c in stripped):
            prev_stripped = prev_line.strip()
            # Only consider it a header if the previous line has meaningful content
            if len(prev_stripped) >= min_header_length:
                return True, prev_stripped
                
        # HTML-style headers
        if stripped.lower().startswith(('<h1>', '<h2>', '<h3>', '<h4>', '<h5>', '<h6>')):
            # Extract text between tags
            match = re.match(r'<h[1-6]>(.*?)</h[1-6]>', stripped, re.IGNORECASE)
            if match:
                header_text = match.group(1).strip()
                if len(header_text) >= min_header_length:
                    return True, header_text
                
        # All caps text (with minimum length and allowing some special characters)
        if len(stripped) > 6 and stripped.upper() == stripped:
            # Allow common characters like : - _ .
            allowed_special = set(':-_.?!')
            if all(c.isupper() or c in allowed_special or c.isspace() or c.isdigit() for c in stripped):
                # Skip if it's too short or likely not a header
                if len(stripped) >= min_header_length and ' ' in stripped:
                    return True, stripped
        
        return False, None

    def split_document(
        self,
        text: str,
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
        respect_boundaries: bool = True,
        content_type: Optional[str] = None,  # Keep parameter for backward compatibility
        min_chunk_size: int = 500,  # Added minimum chunk size parameter
        preserve_header_context: bool = True  # New parameter to preserve header context
    ) -> List[Dict[str, Optional[str]]]:
        """Split a document into overlapping chunks while respecting content boundaries
        
        Args:
            text: Source text to split
            chunk_size: Target size for each chunk
            chunk_overlap: Number of characters to overlap between chunks
            respect_boundaries: Try to break at sentence/paragraph boundaries
            content_type: Type of content (kept for backward compatibility)
            min_chunk_size: Minimum size for any chunk (except the last one if needed)
            preserve_header_context: Whether to preserve header context in chunks
        """
        # For very small texts, don't chunk at all
        if len(text) < min_chunk_size:
            return [{'header': None, 'content': text.strip()}]

        sections = []

        # First, split into coarse sections based on headers
        coarse_sections = []
        current_section = []
        current_header = None
        header_hierarchy = []  # Track hierarchical header structure
        prev_line = None

        for line in text.splitlines():
            is_header, header_text = self._is_header(line, prev_line)

            if is_header:
                # Save previous section if it exists
                if current_section:
                    coarse_sections.append({
                        'header': current_header,
                        'hierarchy': header_hierarchy.copy(),  # Store hierarchy
                        'content': '\n'.join(current_section)
                    })
                
                # Update header hierarchy (simplified version)
                current_header = header_text
                header_hierarchy.append(current_header)
                if len(header_hierarchy) > 3:  # Keep only most recent 3 levels
                    header_hierarchy = header_hierarchy[-3:]
                    
                current_section = []

                # For setext headers, include the previous line
                if prev_line and all(c == '=' or c == '-' for c in line.strip()):
                    current_section.append(prev_line)
                
                # Include the header line in the section content
                current_section.append(line)
            else:
                current_section.append(line)
                
            prev_line = line

        # Add final section
        if current_section:
            coarse_sections.append({
                'header': current_header,
                'hierarchy': header_hierarchy.copy(),
                'content': '\n'.join(current_section)
            })

        # Merge very small coarse sections with the next section
        merged_sections = []
        buffer = None
        
        for section in coarse_sections:
            if buffer is None:
                buffer = section
            else:
                # If current buffer is too small, merge with the next section
                if len(buffer['content']) < min_chunk_size:
                    buffer = {
                        'header': buffer['header'],
                        'hierarchy': buffer['hierarchy'],
                        'content': buffer['content'] + '\n\n' + section['content']
                    }
                else:
                    merged_sections.append(buffer)
                    buffer = section
        
        # Add the last buffer if it exists
        if buffer is not None:
            merged_sections.append(buffer)
        
        # If no sections after merging, return the original text
        if not merged_sections:
            return [{'header': None, 'content': text.strip()}]
        
        # Now process the merged sections into chunks
        for section in merged_sections:
            content = section['content']
            header = section['header']
            hierarchy = section.get('hierarchy', [])
            
            # Create header context prefix if enabled
            header_context = ""
            if preserve_header_context and hierarchy:
                # Add hierarchical headers as context
                header_context = " > ".join(hierarchy) + ":\n"
            
            # If content is short enough, keep it as one chunk
            if len(content) <= chunk_size:
                sections.append({
                    'header': header,
                    'content': (header_context + content).strip()
                })
                continue

            # Split into overlapping chunks
            start = 0
            
            while start < len(content):
                # First end of chunk
                end = start + chunk_size - len(header_context)  # Account for header context length

                if respect_boundaries and end < len(content):
                    # Find sentence/paragraph boundaries (same logic as before)
                    window_start = max(0, end - 100)
                    window_end = min(len(content), end + 100)
                    window = content[window_start:window_end]

                    # Look for sentence endings in the window
                    endings = [
                        '. ', '! ', '? ',     # Basic sentence endings
                        '."', '!"', '?"',     # Quote endings
                        ".'", "!'", "?'",     # Single quote endings
                        '.\n', '!\n', '?\n',  # Line endings
                        '.\r\n', '!\r\n', '?\r\n',  # Windows line endings
                    ]
                    best_end = -1

                    for ending in endings:
                        # Find all occurrences of this ending in the window
                        pos = window.find(ending)
                        while pos != -1:
                            absolute_pos = window_start + pos + len(ending)
                            if absolute_pos >= end - 100 and absolute_pos <= end + 100:
                                # Found a valid ending
                                if best_end == -1 or abs(end - absolute_pos) < abs(end - best_end):
                                    best_end = absolute_pos
                            pos = window.find(ending, pos + 1)

                    if best_end != -1:
                        end = best_end
                    else:
                        # Try paragraph boundary
                        para_end = content.find('\n\n', end - 100, end + 100)
                        if para_end != -1:
                            end = para_end + 2  # Include the newlines

                chunk_content = content[start:end].strip()
                
                # Only add chunks that meet the minimum size requirement
                # (unless it's the last chunk of the document)
                if len(chunk_content) >= min_chunk_size or end >= len(content):
                    # Add header context to the chunk
                    contextualized_content = header_context + chunk_content
                    
                    sections.append({
                        'header': header,
                        'content': contextualized_content
                    })

                # Move start for next chunk, considering overlap
                start = end - chunk_overlap
                if start < 0:
                    start = 0
                # Ensure we make progress
                if start >= end:
                    start = end

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
                should_chunk = len(text) > 1024 # Default threshold

            """COMMENTED OUT FOR TESTING
                # Adjust based on content type
                if content_type == 'feedback' and len(text) < 500:
                    should_chunk = False
                elif content_type == 'analysis':
                    should_chunk = True
            """
                    
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
                # Delete the collection from Qdrant
                self.store.client.delete_collection(collection_name=category)
                
                # Remove from our collections set
                self.store.collections.remove(category)
                
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
        
        # For debugging
        logger.info(f"Searching for document with filename: '{filename}'")
        
        for memory in memories:
            # Log what we're checking to see the actual stored values
            source = memory.metadata.get('source', '')
            logger.info(f"Checking memory with source: '{source}'")
            
            # Try multiple matching strategies
            is_match = False
            
            # Check if source ends with the filename (path/to/filename.md)
            if source.endswith(f"/{filename}") or source == filename:
                is_match = True
            
            # Check if just the basename matches
            source_basename = Path(source).name
            if source_basename == filename:
                is_match = True
                
            # If a match was found, delete the memory
            if is_match:
                logger.info(f"Found match - deleting memory {memory.id}")
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
            # Get all categories first
            categories = self.list_categories()
            if not categories:
                logger.info("No categories to wipe")
                return True
                
            logger.info(f"Wiping {len(categories)} categories: {categories}")
            
            # Remove each category properly, one by one
            for category in categories:
                logger.info(f"Wiping category: {category}")
                self.remove_category(category)
            
            # Close the current client to release file locks
            if hasattr(self.store, 'client') and self.store.client:
                logger.info("Closing Qdrant client to release file locks")
                try:
                    self.store.client.close()
                except Exception as e:
                    logger.warning(f"Error closing client: {e}")
            
            # Wait a moment to ensure locks are released
            import time
            time.sleep(1)
            
            # Recreate the store with a fresh client
            logger.info("Reinitializing vector store")
            self.store = VectorStore(self.artist_name)
            
            return True
                
        except Exception as e:
            logger.error(f"Error wiping all memories: {e}")
            return False