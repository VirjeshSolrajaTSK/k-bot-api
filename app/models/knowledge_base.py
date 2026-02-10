"""Knowledge base model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


class KnowledgeBase(Base):
    """Knowledge base model matching DDL schema."""
    
    __tablename__ = "knowledge_bases"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    status = Column(String(30), default="UPLOADED")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="knowledge_bases")
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="knowledge_base", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", back_populates="knowledge_base", cascade="all, delete-orphan")
    question_bank = relationship("QuestionBank", back_populates="knowledge_base", cascade="all, delete-orphan")
