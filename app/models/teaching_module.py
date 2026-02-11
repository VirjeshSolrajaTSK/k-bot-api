"""TeachingModule model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


class TeachingModule(Base):
    """TeachingModule model matching DDL schema."""

    __tablename__ = "teaching_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kb_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_module_id = Column(UUID(as_uuid=True), ForeignKey("teaching_modules.id", ondelete="CASCADE"))
    title = Column(String(500), nullable=False)
    description = Column(Text)
    sequence_order = Column(Integer, nullable=False)
    estimated_minutes = Column(Integer)
    difficulty_level = Column(String(20))
    prerequisites = Column(ARRAY(UUID), default=list)
    learning_objectives = Column(ARRAY(Text), default=list)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    knowledge_base = relationship("KnowledgeBase")
    parent_module = relationship("TeachingModule", remote_side=[id])
    concepts = relationship("TeachingConcept", back_populates="module", cascade="all, delete-orphan")
