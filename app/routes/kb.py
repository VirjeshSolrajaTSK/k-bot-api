"""Knowledge base routes."""
import os
import uuid
from typing import List, Optional
from pathlib import Path
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.db.sessions import get_db
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.question_bank import QuestionBank
from app.core.security import get_current_user
from app.utils.file_processor import FileProcessor
from app.utils.text_chunker import TextChunker
from app.services.openai_service import OpenAIService


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
    documents: Optional[List["DocumentResponse"]] = None
    
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


class DocumentResponse(BaseModel):
    id: str
    filename: str
    filesize: int
    download_url: str

    class Config:
        from_attributes = True


def _generate_and_save_question_bank(kb_id: str, db: Session) -> bool:
    """
    Generate and save question bank for a knowledge base.
    
    Args:
        kb_id: Knowledge base ID
        db: Database session
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get all chunks for this KB
        chunks = db.query(Chunk).filter(Chunk.kb_id == kb_id).all()
        
        if not chunks:
            print(f"No chunks found for KB {kb_id}, skipping question bank generation")
            return False
        
        # Prepare chunk data for OpenAI
        chunks_content = [
            {
                "text": chunk.text,
                "topic": chunk.topic or "General",
                "source_file": chunk.source_file or "Unknown"
            }
            for chunk in chunks[:100]  # Limit to 100 chunks to stay within context window
        ]
        
        # Generate question bank using OpenAI
        openai_service = OpenAIService()
        question_bank_data = openai_service.generate_question_bank(chunks_content)
        
        # Save questions to database
        for difficulty_level, questions in question_bank_data.items():
            difficulty = difficulty_level.upper()  # EASY, MEDIUM, HARD
            
            for q_data in questions:
                question = QuestionBank(
                    kb_id=kb_id,
                    question_text=q_data['question_text'],
                    correct_answer=q_data['correct_answer'],
                    options=q_data.get('options'),
                    difficulty=difficulty
                )
                db.add(question)
        
        db.commit()
        print(f"Successfully generated question bank for KB {kb_id}")
        return True
        
    except Exception as e:
        print(f"Error generating question bank for KB {kb_id}: {str(e)}")
        db.rollback()
        return False


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
        
        # Generate question bank if KB was successfully created
        if kb.status == "COMPLETED":
            _generate_and_save_question_bank(str(kb.id), db)
        
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


@router.post("/{kb_id}/upload", response_model=KBResponse, status_code=status.HTTP_201_CREATED)
async def upload_to_existing_kb(
    kb_id: str,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload files and attach them to an existing knowledge base.

    Protected endpoint - requires JWT authentication.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )

    # Find KB and check ownership
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.user_id == current_user.id
    ).first()

    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found"
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

    # Mark KB processing
    kb.status = "PROCESSING"
    db.commit()

    try:
        user_upload_dir = UPLOAD_DIR / str(current_user.id) / str(kb.id)
        user_upload_dir.mkdir(parents=True, exist_ok=True)

        total_chunks = 0

        for upload_file in files:
            file_path = user_upload_dir / upload_file.filename

            async with aiofiles.open(file_path, "wb") as buffer:
                content = await upload_file.read()
                await buffer.write(content)

            document = Document(
                kb_id=kb.id,
                filename=upload_file.filename,
                s3_path=str(file_path)
            )
            db.add(document)
            db.commit()
            db.refresh(document)

            try:
                text, _ = FileProcessor.extract_text(str(file_path))

                if not text.strip():
                    continue

                chunks = TextChunker.chunk_text(
                    text=text,
                    chunk_size=1000,
                    overlap=200,
                    source_filename=upload_file.filename
                )

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
                print(f"Error processing {upload_file.filename}: {str(e)}")
                continue

        kb.status = "COMPLETED" if total_chunks > 0 else "FAILED"
        db.commit()
        db.refresh(kb)
        
        # Regenerate question bank since new content was added
        if kb.status == "COMPLETED":
            # First, delete existing question bank for this KB
            db.query(QuestionBank).filter(QuestionBank.kb_id == kb.id).delete()
            db.commit()
            # Generate new question bank
            _generate_and_save_question_bank(str(kb.id), db)

        return KBResponse(
            id=str(kb.id),
            user_id=str(kb.user_id),
            title=kb.title,
            description=kb.description,
            status=kb.status,
            created_at=kb.created_at.isoformat()
        )

    except Exception as e:
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
    
    kb_responses = []
    for kb in kbs:
        # fetch documents for this KB
        docs = db.query(Document).filter(Document.kb_id == kb.id).all()
        doc_list = []
        for doc in docs:
            try:
                p = Path(doc.s3_path)
                filesize = p.stat().st_size if p.exists() else 0
            except Exception:
                filesize = 0

            download_url = f"/kb/{kb.id}/documents/{doc.id}/download"
            doc_list.append({
                "id": str(doc.id),
                "filename": doc.filename,
                "filesize": filesize,
                "download_url": download_url
            })

        kb_responses.append(
            KBResponse(
                id=str(kb.id),
                user_id=str(kb.user_id),
                title=kb.title,
                description=kb.description,
                status=kb.status,
                created_at=kb.created_at.isoformat(),
                documents=doc_list
            )
        )
    
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


@router.get("/{kb_id}/documents/{doc_id}/download")
def download_document(
    kb_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Download a document belonging to a knowledge base (owner-only).
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

    document = db.query(Document).filter(
        Document.id == doc_id,
        Document.kb_id == kb.id
    ).first()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    file_path = Path(document.s3_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on server"
        )

    return FileResponse(path=str(file_path), media_type='application/octet-stream', filename=document.filename)


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
