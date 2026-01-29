"""Quiz models."""
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, Numeric, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


class Quiz(Base):
    """Quiz model matching DDL schema."""
    
    __tablename__ = "quizzes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kb_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    difficulty = Column(String(20), nullable=False)  # EASY / MEDIUM / HARD / MIXED
    num_questions = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="quizzes")
    user = relationship("User", back_populates="quizzes")
    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")
    summaries = relationship("QuizSummary", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base):
    """Quiz question model matching DDL schema."""
    
    __tablename__ = "quiz_questions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL"))
    question_text = Column(Text, nullable=False)
    difficulty = Column(String(20), nullable=False)
    question_order = Column(Integer, nullable=False)
    
    # Relationships
    quiz = relationship("Quiz", back_populates="questions")
    chunk = relationship("Chunk", back_populates="quiz_questions")
    answers = relationship("QuizAnswer", back_populates="question", cascade="all, delete-orphan")


class QuizAnswer(Base):
    """Quiz answer model matching DDL schema."""
    
    __tablename__ = "quiz_answers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(UUID(as_uuid=True), ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False)
    user_answer = Column(Text, nullable=False)
    score = Column(Numeric(4, 2))  # 0.00 → 1.00
    result = Column(String(20))  # CORRECT / PARTIAL / WRONG
    feedback = Column(Text)
    answered_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    question = relationship("QuizQuestion", back_populates="answers")


class QuizSummary(Base):
    """Quiz summary model matching DDL schema."""
    
    __tablename__ = "quiz_summaries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False)
    total_questions = Column(Integer)
    correct_answers = Column(Integer)
    accuracy = Column(Numeric(5, 2))
    strength_topics = Column(ARRAY(Text))
    weak_topics = Column(ARRAY(Text))
    system_verdict = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    quiz = relationship("Quiz", back_populates="summaries")
