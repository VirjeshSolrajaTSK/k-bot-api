"""Knowledge base routes."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.db.sessions import get_db
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.core.security import get_current_user


router = APIRouter(prefix="/kb", tags=["Knowledge Base"])


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


@router.get("/{kb_id}", response_model=KBResponse)
def get_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific knowledge base by ID.
    
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
    
    return KBResponse(
        id=str(kb.id),
        user_id=str(kb.user_id),
        title=kb.title,
        description=kb.description,
        status=kb.status,
        created_at=kb.created_at.isoformat()
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
