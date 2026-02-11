"""Database models."""
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.quiz import Quiz, QuizQuestion, QuizAnswer, QuizSummary
from app.models.question_bank import QuestionBank
from app.models.teaching_module import TeachingModule
from app.models.teaching_concept import TeachingConcept
from app.models.teaching_session import TeachingSession
from app.models.teaching_interaction import TeachingInteraction

__all__ = [
    "User",
    "KnowledgeBase",
    "Document",
    "Chunk",
    "Quiz",
    "QuizQuestion",
    "QuizAnswer",
    "QuizSummary",
    "QuestionBank",
    "TeachingModule",
    "TeachingConcept",
    "TeachingSession",
    "TeachingInteraction",
]
