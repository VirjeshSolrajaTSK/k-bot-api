"""Quiz routes."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.sessions import get_db
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.chunk import Chunk
from app.models.quiz import Quiz, QuizQuestion
from app.models.quiz import QuizAnswer, QuizSummary
from app.core.security import get_current_user
from app.services.openai_service import OpenAIService


router = APIRouter(prefix="/quiz", tags=["Quiz"])


# Request/Response schemas
class GenerateQuizRequest(BaseModel):
    kb_id: str
    num_questions: int = Field(default=5, ge=1, le=20)
    difficulty: str = Field(default="MEDIUM", pattern="^(EASY|MEDIUM|HARD|MIXED)$")
    topic_filter: Optional[str] = None
    custom_prompt: Optional[str] = None


class QuestionResponse(BaseModel):
    id: str
    question_text: str
    options: Optional[List[str]]
    difficulty: str
    question_order: int
    
    class Config:
        from_attributes = True


class QuizResponse(BaseModel):
    id: str
    kb_id: str
    user_id: str
    difficulty: str
    num_questions: int
    created_at: str
    questions: List[QuestionResponse]
    
    class Config:
        from_attributes = True


class AnswerKeyResponse(BaseModel):
    question_id: str
    question_text: str
    correct_answer: str
    options: Optional[List[str]]


class QuizWithAnswersResponse(BaseModel):
    quiz: QuizResponse
    answer_key: List[AnswerKeyResponse]


class AnswerSubmission(BaseModel):
    question_id: str
    user_answer: str


class SubmitQuizRequest(BaseModel):
    answers: List[AnswerSubmission]


class QuestionResult(BaseModel):
    question_id: str
    correct_answer: Optional[str]
    user_answer: str
    is_correct: bool
    score: float


class SubmitQuizResponse(BaseModel):
    quiz_id: str
    total_questions: int
    correct_answers: int
    accuracy: float
    results: List[QuestionResult]


@router.post("/generate", response_model=QuizWithAnswersResponse, status_code=status.HTTP_201_CREATED)
def generate_quiz(
    request: GenerateQuizRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a quiz from knowledge base content using OpenAI.
    
    This endpoint:
    1. Retrieves chunks from the specified knowledge base
    2. Calls OpenAI to generate quiz questions
    3. Saves the quiz and questions to the database
    4. Returns the quiz with an answer key
    
    Protected endpoint - requires JWT authentication.
    
    Args:
        request: Quiz generation parameters
        current_user: Authenticated user
        db: Database session
        
    Returns:
        QuizWithAnswersResponse containing the quiz and answer key
        
    Raises:
        HTTPException 404: KB not found or not owned by user
        HTTPException 400: No chunks available for quiz generation
        HTTPException 500: Error generating quiz
    """
    # Verify KB exists and belongs to user
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == request.kb_id,
        KnowledgeBase.user_id == current_user.id
    ).first()
    
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found"
        )
    
    # Retrieve chunks for quiz generation
    query = db.query(Chunk).filter(Chunk.kb_id == request.kb_id)
    
    # Apply topic filter if provided
    if request.topic_filter:
        query = query.filter(Chunk.topic.ilike(f"%{request.topic_filter}%"))
    
    chunks = query.limit(100).all()  # Limit to 100 chunks for context window
    
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No chunks available for quiz generation. Upload documents first."
        )
    
    # Prepare chunk data for OpenAI
    chunks_content = [
        {
            "text": chunk.text,
            "topic": chunk.topic or "General",
            "source_file": chunk.source_file or "Unknown",
            "chunk_id": str(chunk.id)
        }
        for chunk in chunks
    ]
    
    try:
        # Generate questions using OpenAI
        openai_service = OpenAIService()
        generated_questions = openai_service.generate_quiz_questions(
            chunks_content=chunks_content,
            num_questions=request.num_questions,
            difficulty=request.difficulty,
            custom_prompt=request.custom_prompt
        )
        
        if not generated_questions:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate questions from OpenAI"
            )
        
        # Create quiz record
        quiz = Quiz(
            kb_id=kb.id,
            user_id=current_user.id,
            difficulty=request.difficulty,
            num_questions=len(generated_questions)
        )
        
        db.add(quiz)
        db.commit()
        db.refresh(quiz)
        
        # Create question records
        answer_key = []
        question_responses = []
        
        for order, q_data in enumerate(generated_questions, 1):
            # Get chunk reference if provided
            chunk_index = q_data.get('chunk_index', 0)
            chunk_id = None
            if 0 <= chunk_index < len(chunks):
                chunk_id = chunks[chunk_index].id
            
            question = QuizQuestion(
                quiz_id=quiz.id,
                chunk_id=chunk_id,
                question_text=q_data['question_text'],
                correct_answer=q_data['correct_answer'],
                options=q_data.get('options'),
                difficulty=q_data.get('difficulty', request.difficulty),
                question_order=order
            )
            
            db.add(question)
            db.commit()
            db.refresh(question)
            
            # Build response objects
            question_responses.append(QuestionResponse(
                id=str(question.id),
                question_text=question.question_text,
                options=question.options,
                difficulty=question.difficulty,
                question_order=question.question_order
            ))
            
            answer_key.append(AnswerKeyResponse(
                question_id=str(question.id),
                question_text=question.question_text,
                correct_answer=question.correct_answer,
                options=question.options
            ))
        
        # Build final response
        quiz_response = QuizResponse(
            id=str(quiz.id),
            kb_id=str(quiz.kb_id),
            user_id=str(quiz.user_id),
            difficulty=quiz.difficulty,
            num_questions=quiz.num_questions,
            created_at=quiz.created_at.isoformat(),
            questions=question_responses
        )
        
        return QuizWithAnswersResponse(
            quiz=quiz_response,
            answer_key=answer_key
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating quiz: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_quiz(
    quiz_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a quiz by ID (without answer key).
    
    Protected endpoint - requires JWT authentication.
    Only returns quizzes owned by the current user.
    """
    quiz = db.query(Quiz).filter(
        Quiz.id == quiz_id,
        Quiz.user_id == current_user.id
    ).first()
    
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found"
        )
    
    questions = db.query(QuizQuestion).filter(
        QuizQuestion.quiz_id == quiz.id
    ).order_by(QuizQuestion.question_order).all()
    
    question_responses = [
        QuestionResponse(
            id=str(q.id),
            question_text=q.question_text,
            options=q.options,
            difficulty=q.difficulty,
            question_order=q.question_order
        )
        for q in questions
    ]
    
    return QuizResponse(
        id=str(quiz.id),
        kb_id=str(quiz.kb_id),
        user_id=str(quiz.user_id),
        difficulty=quiz.difficulty,
        num_questions=quiz.num_questions,
        created_at=quiz.created_at.isoformat(),
        questions=question_responses
    )


@router.get("/{quiz_id}/answers", response_model=List[AnswerKeyResponse])
def get_quiz_answers(
    quiz_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the answer key for a quiz.
    
    Protected endpoint - requires JWT authentication.
    Only returns answer keys for quizzes owned by the current user.
    """
    quiz = db.query(Quiz).filter(
        Quiz.id == quiz_id,
        Quiz.user_id == current_user.id
    ).first()
    
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found"
        )
    
    questions = db.query(QuizQuestion).filter(
        QuizQuestion.quiz_id == quiz.id
    ).order_by(QuizQuestion.question_order).all()
    
    return [
        AnswerKeyResponse(
            question_id=str(q.id),
            question_text=q.question_text,
            correct_answer=q.correct_answer,
            options=q.options
        )
        for q in questions
    ]

@router.post("/{quiz_id}/submit", response_model=SubmitQuizResponse)
def submit_quiz_answers(
        quiz_id: str,
        request: SubmitQuizRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Submit answers for a quiz (MCQ only for POC), grade them (correct/wrong),
        persist `QuizAnswer` rows, create a `QuizSummary`, and return results.
        """
        # Verify quiz exists
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

        # Load questions for the quiz
        questions = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).all()
        question_map = {str(q.id): q for q in questions}

        if not questions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quiz has no questions")

        results = []
        correct_count = 0

        # Persist answers
        for ans in request.answers:
            q = question_map.get(ans.question_id)
            if not q:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid question id: {ans.question_id}")

            # MCQ grading - handle stored answer as letter (A/B/C/...) or full text.
            correct = False
            if q.correct_answer is not None:
                stored = q.correct_answer.strip()

                # If question has options and stored answer is a single letter (A/B/C...)
                if q.options and len(stored) == 1 and stored.isalpha():
                    # Try to map user's submitted value to a letter.
                    ua = ans.user_answer.strip()
                    user_letter = None

                    # If user submitted a single letter, use it directly
                    if len(ua) == 1 and ua.isalpha():
                        user_letter = ua.upper()
                    else:
                        # Otherwise try to find which option text matches the submitted answer
                        for idx, opt in enumerate(q.options):
                            if opt and opt.strip().lower() == ua.lower():
                                user_letter = chr(65 + idx)
                                break

                    if user_letter:
                        correct = user_letter.upper() == stored.upper()
                    else:
                        # Fallback to text comparison
                        correct = ua.lower() == stored.lower()
                else:
                    # No options or stored answer is full text — compare normalized text
                    user_norm = ans.user_answer.strip().lower()
                    correct_norm = stored.lower()
                    correct = user_norm == correct_norm

            score = 1.0 if correct else 0.0
            result_text = "CORRECT" if correct else "WRONG"

            qa = QuizAnswer(
                question_id=q.id,
                user_answer=ans.user_answer,
                score=score,
                result=result_text,
                feedback=None
            )
            db.add(qa)

            results.append(QuestionResult(
                question_id=str(q.id),
                correct_answer=q.correct_answer,
                user_answer=ans.user_answer,
                is_correct=correct,
                score=score
            ))

            if correct:
                correct_count += 1

        db.commit()

        total_questions = len(questions)
        accuracy = round((correct_count / total_questions) * 100, 2) if total_questions > 0 else 0.0

        # Create a quiz summary record
        summary = QuizSummary(
            quiz_id=quiz.id,
            total_questions=total_questions,
            correct_answers=correct_count,
            accuracy=accuracy,
            strength_topics=[],
            weak_topics=[],
            system_verdict="COMPLETED"
        )
        db.add(summary)
        db.commit()

        return SubmitQuizResponse(
            quiz_id=str(quiz.id),
            total_questions=total_questions,
            correct_answers=correct_count,
            accuracy=float(accuracy),
            results=results
        )
