"""Text chunking utilities for splitting documents into manageable pieces."""
import re
from typing import List, Dict, Optional


class TextChunker:
    """Split text into chunks with metadata."""
    
    DEFAULT_CHUNK_SIZE = 1000  # characters
    DEFAULT_OVERLAP = 200  # characters
    
    @staticmethod
    def chunk_text(
        text: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
        source_filename: Optional[str] = None
    ) -> List[Dict[str, any]]:
        """
        Split text into overlapping chunks with metadata.
        
        Args:
            text: Text to chunk
            chunk_size: Maximum size of each chunk in characters
            overlap: Number of overlapping characters between chunks
            source_filename: Original filename for metadata
            
        Returns:
            List of chunk dictionaries with text and metadata
        """
        if not text or not text.strip():
            return []
        
        # Split by paragraphs first to maintain context
        paragraphs = TextChunker._split_into_paragraphs(text)
        
        chunks = []
        current_chunk = ""
        chunk_number = 1
        
        for para in paragraphs:
            # If paragraph alone is larger than chunk_size, split it
            if len(para) > chunk_size:
                # Save current chunk if it has content
                if current_chunk.strip():
                    chunks.append(TextChunker._create_chunk_dict(
                        current_chunk.strip(),
                        chunk_number,
                        source_filename
                    ))
                    chunk_number += 1
                    current_chunk = ""
                
                # Split large paragraph into sentences
                sentences = TextChunker._split_into_sentences(para)
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) <= chunk_size:
                        current_chunk += sentence + " "
                    else:
                        if current_chunk.strip():
                            chunks.append(TextChunker._create_chunk_dict(
                                current_chunk.strip(),
                                chunk_number,
                                source_filename
                            ))
                            chunk_number += 1
                        
                        # Start new chunk with overlap
                        if overlap > 0 and len(current_chunk) > overlap:
                            current_chunk = current_chunk[-overlap:] + sentence + " "
                        else:
                            current_chunk = sentence + " "
            else:
                # Try to add paragraph to current chunk
                if len(current_chunk) + len(para) <= chunk_size:
                    current_chunk += para + "\n\n"
                else:
                    # Save current chunk and start new one
                    if current_chunk.strip():
                        chunks.append(TextChunker._create_chunk_dict(
                            current_chunk.strip(),
                            chunk_number,
                            source_filename
                        ))
                        chunk_number += 1
                    
                    # Start new chunk with overlap
                    if overlap > 0 and len(current_chunk) > overlap:
                        current_chunk = current_chunk[-overlap:] + para + "\n\n"
                    else:
                        current_chunk = para + "\n\n"
        
        # Add final chunk
        if current_chunk.strip():
            chunks.append(TextChunker._create_chunk_dict(
                current_chunk.strip(),
                chunk_number,
                source_filename
            ))
        
        return chunks
    
    @staticmethod
    def _split_into_paragraphs(text: str) -> List[str]:
        """Split text into paragraphs."""
        # Split by double newlines or multiple spaces
        paragraphs = re.split(r'\n\s*\n+', text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    @staticmethod
    def _split_into_sentences(text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitter (can be improved with NLP)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    @staticmethod
    def _create_chunk_dict(
        text: str,
        chunk_number: int,
        source_filename: Optional[str]
    ) -> Dict[str, any]:
        """Create a chunk dictionary with metadata."""
        # Extract potential topic from first line or sentence
        first_line = text.split('\n')[0][:200] if '\n' in text else text[:200]
        
        # Extract page number if present in text
        page_match = re.search(r'\[Page (\d+)\]', text)
        page_number = int(page_match.group(1)) if page_match else None
        
        # Remove page markers from text
        clean_text = re.sub(r'\[Page \d+\]\n?', '', text)
        
        # Extract keywords (simple approach: get capitalized words)
        keywords = list(set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', clean_text)))
        keywords = keywords[:10]  # Limit to 10 keywords
        
        return {
            'text': clean_text.strip(),
            'topic': first_line.strip(),
            'section': f"Chunk {chunk_number}",
            'page_number': page_number,
            'keywords': keywords if keywords else None,
            'source_file': source_filename
        }
    
    @staticmethod
    def extract_metadata(text: str) -> Dict[str, any]:
        """Extract metadata from text."""
        return {
            'character_count': len(text),
            'word_count': len(text.split()),
            'line_count': text.count('\n') + 1,
        }
