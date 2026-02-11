"""TeachingInteraction model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, String, Text, Boolean, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


class TeachingInteraction(Base):
    """TeachingInteraction model matching DDL schema."""

    __tablename__ = "teaching_interactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("teaching_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("teaching_modules.id"))
    concept_id = Column(UUID(as_uuid=True), ForeignKey("teaching_concepts.id"))
    interaction_type = Column(String(50), nullable=False)
    user_input = Column(Text)
    system_response = Column(Text)
    checkpoint_correct = Column(Boolean)
    time_spent_seconds = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("TeachingSession", back_populates="interactions")
