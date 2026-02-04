"""Knowledge base routes."""
import os
import uuid
from typing import List, Optional
from pathlib import Path
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.db.sessions import get_db
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.chunk import Chunk
from app.core.security import get_current_user
from app.utils.file_processor import FileProcessor
from app.utils.text_chunker import TextChunker


router = APIRouter(prefix="/kb", tags=["Knowledge Base"])


# Configuration
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


# Request/Response schemas
class CreateKBRequest(BaseModel):
    title: str
    description: Optional[str] = None


class KBResponse(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str]
    status: str
    created_at: str
    
    class Config:
        from_attributes = True


class KBDetailResponse(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str]
    status: str
    created_at: str
    document_count: int
    chunk_count: int
    
    class Config:
        from_attributes = True


class KBListResponse(BaseModel):
    knowledge_bases: List[KBResponse]
    total: int


@router.post("/create", response_model=KBResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    request: CreateKBRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new knowledge base.
    
    Protected endpoint - requires JWT authentication.
    """
    kb = KnowledgeBase(
        user_id=current_user.id,
        title=request.title,
        description=request.description,
        status="CREATED"
    )
    
    db.add(kb)
    db.commit()
    db.refresh(kb)
    
    return KBResponse(
        id=str(kb.id),
        user_id=str(kb.user_id),
        title=kb.title,
        description=kb.description,
        status=kb.status,
        created_at=kb.created_at.isoformat()
    )


@router.post("/upload", response_model=KBResponse, status_code=status.HTTP_201_CREATED)
async def upload_knowledge_base(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a knowledge base by uploading files.
    
    Accepts multiple files (PDF, DOCX, TXT, MD) and processes them into chunks.
    
    Protected endpoint - requires JWT authentication.
    
    Args:
        title: Title of the knowledge base
        description: Optional description
        files: List of files to upload (PDF, DOCX, TXT, MD)
        current_user: Authenticated user
        db: Database session
        
    Returns:
        KBResponse with created knowledge base details
        
    Raises:
        HTTPException 400: If no files provided or unsupported file format
        HTTPException 500: If processing fails
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )
    
    # Validate file formats
    unsupported_files = []
    for file in files:
        if not FileProcessor.is_supported(file.filename):
            unsupported_files.append(file.filename)
    
    if unsupported_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file formats: {', '.join(unsupported_files)}. "
                   f"Supported: PDF, DOCX, TXT, MD"
        )
    
    # Create knowledge base
    kb = KnowledgeBase(
        user_id=current_user.id,
        title=title,
        description=description,
        status="PROCESSING"
    )
    
    db.add(kb)
    db.commit()
    db.refresh(kb)
    
    try:
        # Create user-specific upload directory
        user_upload_dir = UPLOAD_DIR / str(current_user.id) / str(kb.id)
        user_upload_dir.mkdir(parents=True, exist_ok=True)
        
        total_chunks = 0
        
        # Process each file
        for upload_file in files:
            # Save file to disk
            file_path = user_upload_dir / upload_file.filename
            
            async with aiofiles.open(file_path, "wb") as buffer:
                content = await upload_file.read()
                await buffer.write(content)
            
            # Create document record
            document = Document(
                kb_id=kb.id,
                filename=upload_file.filename,
                s3_path=str(file_path)  # Using local path for now, can be S3 URL later
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            
            try:
                # Extract text from file
                text, _ = FileProcessor.extract_text(str(file_path))
                
                if not text.strip():
                    continue  # Skip empty files
                
                # Chunk the text
                chunks = TextChunker.chunk_text(
                    text=text,
                    chunk_size=1000,
                    overlap=200,
                    source_filename=upload_file.filename
                )
                
                # Save chunks to database
                for chunk_data in chunks:
                    chunk = Chunk(
                        kb_id=kb.id,
                        document_id=document.id,
                        text=chunk_data['text'],
                        topic=chunk_data.get('topic'),
                        section=chunk_data.get('section'),
                        page_number=chunk_data.get('page_number'),
                        keywords=chunk_data.get('keywords'),
                        source_file=chunk_data.get('source_file')
                    )
                    db.add(chunk)
                    total_chunks += 1
                
                db.commit()
                
            except ValueError as e:
                # File processing error - log and continue with other files
                print(f"Error processing {upload_file.filename}: {str(e)}")
                continue
        
        # Update KB status
        kb.status = "COMPLETED" if total_chunks > 0 else "FAILED"
        db.commit()
        db.refresh(kb)
        
        return KBResponse(
            id=str(kb.id),
            user_id=str(kb.user_id),
            title=kb.title,
            description=kb.description,
            status=kb.status,
            created_at=kb.created_at.isoformat()
        )
        
    except Exception as e:
        # Update status to failed
        kb.status = "FAILED"
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing files: {str(e)}"
        )


@router.get("/list", response_model=KBListResponse)
def list_knowledge_bases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all knowledge bases for the current user.
    
    Protected endpoint - requires JWT authentication.
    """
    kbs = db.query(KnowledgeBase).filter(
        KnowledgeBase.user_id == current_user.id
    ).order_by(KnowledgeBase.created_at.desc()).all()
    
    kb_responses = [
        KBResponse(
            id=str(kb.id),
            user_id=str(kb.user_id),
            title=kb.title,
            description=kb.description,
            status=kb.status,
            created_at=kb.created_at.isoformat()
        )
        for kb in kbs
    ]
    
    return KBListResponse(
        knowledge_bases=kb_responses,
        total=len(kb_responses)
    )


@router.get("/{kb_id}", response_model=KBDetailResponse)
def get_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific knowledge base by ID with detailed statistics.
    
    Protected endpoint - requires JWT authentication.
    Only returns knowledge bases owned by the current user.
    """
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.user_id == current_user.id
    ).first()
    
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found"
        )
    
    # Count documents and chunks
    document_count = db.query(Document).filter(Document.kb_id == kb.id).count()
    chunk_count = db.query(Chunk).filter(Chunk.kb_id == kb.id).count()
    
    return KBDetailResponse(
        id=str(kb.id),
        user_id=str(kb.user_id),
        title=kb.title,
        description=kb.description,
        status=kb.status,
        created_at=kb.created_at.isoformat(),
        document_count=document_count,
        chunk_count=chunk_count
    )


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a knowledge base.
    
    Protected endpoint - requires JWT authentication.
    Only allows deletion of knowledge bases owned by the current user.
    Cascades to all related documents, chunks, and quizzes.
    """
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.user_id == current_user.id
    ).first()
    
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found"
        )
    
    db.delete(kb)
    db.commit()
    
    return None
