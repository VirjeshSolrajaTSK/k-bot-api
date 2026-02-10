"""Question bank model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


class QuestionBank(Base):
    """Question bank model for storing pre-generated questions per KB."""
    
    __tablename__ = "question_bank"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kb_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    options = Column(ARRAY(Text))  # For MCQ options [A, B, C, D]
    difficulty = Column(String(20), nullable=False)  # EASY / MEDIUM / HARD
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="question_bank")
