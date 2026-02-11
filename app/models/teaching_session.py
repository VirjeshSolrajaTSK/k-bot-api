"""TeachingSession model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Numeric, JSON, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base


class TeachingSession(Base):
    """TeachingSession model matching DDL schema."""

    __tablename__ = "teaching_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kb_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    current_module_id = Column(UUID(as_uuid=True), ForeignKey("teaching_modules.id"))
    current_concept_id = Column(UUID(as_uuid=True), ForeignKey("teaching_concepts.id"))
    progress_percentage = Column(Numeric(5,2), default=0.00)
    completed_modules = Column(ARRAY(UUID), default=list)
    weak_concepts = Column(ARRAY(UUID), default=list)
    session_state = Column(JSONB, default={})
    started_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    # Relationships
    user = relationship("User")
    knowledge_base = relationship("KnowledgeBase")
    interactions = relationship("TeachingInteraction", back_populates="session", cascade="all, delete-orphan")
