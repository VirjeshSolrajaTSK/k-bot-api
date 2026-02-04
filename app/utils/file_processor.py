"""File processing utilities for extracting text from various file formats."""
import os
from typing import Tuple
from pathlib import Path
import pypdf
from docx import Document as DocxDocument


class FileProcessor:
    """Extract text content from various file formats."""
    
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md'}
    
    @staticmethod
    def extract_text(file_path: str) -> Tuple[str, str]:
        """
        Extract text from a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Tuple of (extracted_text, file_type)
            
        Raises:
            ValueError: If file format is not supported
        """
        path = Path(file_path)
        extension = path.suffix.lower()
        
        if extension not in FileProcessor.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file format: {extension}")
        
        if extension == '.pdf':
            return FileProcessor._extract_from_pdf(file_path), 'PDF'
        elif extension == '.docx':
            return FileProcessor._extract_from_docx(file_path), 'DOCX'
        elif extension in {'.txt', '.md'}:
            return FileProcessor._extract_from_text(file_path), 'TEXT'
        
        raise ValueError(f"Unsupported file format: {extension}")
    
    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """Extract text from PDF file."""
        text_parts = []
        
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = pypdf.PdfReader(file)
                
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    page_text = page.extract_text()
                    if page_text.strip():
                        text_parts.append(f"[Page {page_num}]\n{page_text}")
        except Exception as e:
            raise ValueError(f"Error extracting text from PDF: {str(e)}")
        
        return "\n\n".join(text_parts)
    
    @staticmethod
    def _extract_from_docx(file_path: str) -> str:
        """Extract text from DOCX file."""
        try:
            doc = DocxDocument(file_path)
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
            return "\n\n".join(paragraphs)
        except Exception as e:
            raise ValueError(f"Error extracting text from DOCX: {str(e)}")
    
    @staticmethod
    def _extract_from_text(file_path: str) -> str:
        """Extract text from plain text file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            # Try with different encoding
            with open(file_path, 'r', encoding='latin-1') as file:
                return file.read()
        except Exception as e:
            raise ValueError(f"Error reading text file: {str(e)}")
    
    @staticmethod
    def is_supported(filename: str) -> bool:
        """Check if a file format is supported."""
        extension = Path(filename).suffix.lower()
        return extension in FileProcessor.SUPPORTED_EXTENSIONS
