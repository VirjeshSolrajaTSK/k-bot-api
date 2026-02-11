"""TeachingConcept model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base


class TeachingConcept(Base):
    """TeachingConcept model matching DDL schema."""

    __tablename__ = "teaching_concepts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id = Column(UUID(as_uuid=True), ForeignKey("teaching_modules.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_name = Column(String(300), nullable=False)
    explanation = Column(Text, nullable=False)
    chunk_ids = Column(ARRAY(UUID), default=list)
    keywords = Column(ARRAY(Text), default=list)
    related_concept_ids = Column(ARRAY(UUID), default=list)
    checkpoint_question = Column(Text)
    checkpoint_options = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    module = relationship("TeachingModule", back_populates="concepts")
