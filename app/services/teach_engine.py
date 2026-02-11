"""Teaching engine service.

Manages teaching sessions, processes user interactions, and evaluates checkpoints.
This is a lightweight state machine suitable for POC and local testing.
"""
from typing import Optional, Dict, Any
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    TeachingModule,
    TeachingConcept,
    TeachingSession,
    TeachingInteraction,
    Chunk,
)

logger = logging.getLogger(__name__)


class SimpleLLMFallback:
    """Very small LLM fallback used only for elaboration in POC.

    In production, inject a proper LLM service implementing `generate_explanation`.
    """

    def generate_explanation(self, prompt: str, max_chars: int = 800) -> str:
        return (prompt or "").strip()[:max_chars]


class TeachingEngine:
    def __init__(self, db: Session, llm_service: Optional[Any] = None):
        self.db = db
        self.llm = llm_service or SimpleLLMFallback()

    def start_session(self, kb_id, user_id, module_id: Optional[str] = None, resume: bool = True) -> TeachingSession:
        """Create or resume a teaching session for a user and KB.

        If `resume` is True and an active (non-completed) session exists, return it.
        Otherwise create a new session and initialize current module/concept.
        """
        # Try to resume
        if resume:
            existing = self.db.query(TeachingSession).filter(
                TeachingSession.user_id == user_id,
                TeachingSession.kb_id == kb_id,
                TeachingSession.completed_at == None
            ).order_by(TeachingSession.last_active_at.desc()).first()
            if existing:
                return existing

        # Create new session
        session = TeachingSession(
            user_id=user_id,
            kb_id=kb_id,
            progress_percentage=0.0,
            completed_modules=[],
            weak_concepts=[],
            session_state={},
        )
        self.db.add(session)
        self.db.flush()

        # Initialize current module and concept
        if module_id:
            module = self.db.query(TeachingModule).filter(TeachingModule.id == module_id, TeachingModule.kb_id == kb_id).first()
        else:
            module = self.db.query(TeachingModule).filter(TeachingModule.kb_id == kb_id).order_by(TeachingModule.sequence_order).first()

        if module:
            session.current_module_id = module.id
            # pick first concept in module
            first_concept = self.db.query(TeachingConcept).filter(TeachingConcept.module_id == module.id).order_by(TeachingConcept.created_at).first()
            if first_concept:
                session.current_concept_id = first_concept.id

        session.started_at = datetime.utcnow()
        session.last_active_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(session)
        return session

    def _get_module_concepts(self, module_id):
        return self.db.query(TeachingConcept).filter(TeachingConcept.module_id == module_id).order_by(TeachingConcept.created_at).all()

    def _advance_to_next_concept(self, session: TeachingSession) -> Optional[TeachingConcept]:
        if not session.current_module_id:
            return None
        concepts = self._get_module_concepts(session.current_module_id)
        if not concepts:
            return None
        # find index of current
        idx = next((i for i, c in enumerate(concepts) if c.id == session.current_concept_id), None)
        if idx is None:
            # set to first
            next_concept = concepts[0]
        elif idx + 1 < len(concepts):
            next_concept = concepts[idx + 1]
        else:
            # module finished
            next_concept = None

        if next_concept:
            session.current_concept_id = next_concept.id
        else:
            # mark module completed
            completed = session.completed_modules or []
            if session.current_module_id and session.current_module_id not in completed:
                completed.append(session.current_module_id)
                session.completed_modules = completed

            # move to next module
            next_module = self.db.query(TeachingModule).filter(TeachingModule.kb_id == session.kb_id, TeachingModule.sequence_order > (self.db.query(TeachingModule.sequence_order).filter(TeachingModule.id == session.current_module_id).scalar() or 0)).order_by(TeachingModule.sequence_order).first()
            if next_module:
                session.current_module_id = next_module.id
                # set first concept of next module
                first_concept = self.db.query(TeachingConcept).filter(TeachingConcept.module_id == next_module.id).order_by(TeachingConcept.created_at).first()
                session.current_concept_id = first_concept.id if first_concept else None

        session.last_active_at = datetime.utcnow()
        self.db.commit()
        return self.db.query(TeachingConcept).filter(TeachingConcept.id == session.current_concept_id).first() if session.current_concept_id else None

    def process_interaction(self, session_id, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process a user interaction payload and return a response dict.

        Payload can be:
          - {"choice": "A"}  # checkpoint option selection or control strings ('continue','checkpoint')
          - {"question": "Explain X differently"}  # free-text request
        """
        session = self.db.query(TeachingSession).filter(TeachingSession.id == session_id).first()
        if not session:
            raise ValueError("Session not found")

        # Ensure we have a current concept
        if not session.current_concept_id:
            # try to set from module
            if session.current_module_id:
                first = self.db.query(TeachingConcept).filter(TeachingConcept.module_id == session.current_module_id).order_by(TeachingConcept.created_at).first()
                if first:
                    session.current_concept_id = first.id
                    self.db.commit()
        concept = self.db.query(TeachingConcept).filter(TeachingConcept.id == session.current_concept_id).first() if session.current_concept_id else None

        choice = payload.get("choice")
        question = payload.get("question")

        # If user asked a free-text question, return elaboration (LLM fallback)
        if question:
            resp_text = self.llm.generate_explanation(concept.explanation if concept else question)
            # log interaction
            interaction = TeachingInteraction(
                session_id=session.id,
                module_id=session.current_module_id,
                concept_id=session.current_concept_id,
                interaction_type="question_ask",
                user_input=question,
                system_response=resp_text,
                checkpoint_correct=None,
                time_spent_seconds=None,
            )
            self.db.add(interaction)
            self.db.commit()
            return {"type": "content", "content": resp_text, "citations": [], "options": [
                {"key": "continue", "text": "✓ Continue"},
                {"key": "example", "text": "📝 Show example"},
                {"key": "simplify", "text": "? Explain differently"}
            ], "progress": {"module": float(session.progress_percentage or 0), "overall": float(session.progress_percentage or 0)}}

        # Handle control choices first
        if choice:
            c_lower = str(choice).lower()
            # Continue / next
            if c_lower in ("continue", "next"):
                next_concept = self._advance_to_next_concept(session)
                if next_concept:
                    return self._make_content_response(session, next_concept)
                else:
                    return {"type": "summary", "content": "Module complete. Well done!", "options": [{"key": "next_module", "text": "Continue to next module"}], "progress": {"module": float(session.progress_percentage or 100), "overall": float(session.progress_percentage or 100)}}

            # Take checkpoint
            if c_lower in ("checkpoint", "test"):
                if not concept:
                    return {"type": "content", "content": "No concept available for checkpoint."}
                return self._make_checkpoint_response(session, concept)

            # Otherwise assume it's an answer key (A/B/C...)
            if len(str(choice)) == 1 and concept and concept.checkpoint_options:
                # evaluate
                result = self.evaluate_checkpoint(concept.id, str(choice))
                # log interaction
                interaction = TeachingInteraction(
                    session_id=session.id,
                    module_id=session.current_module_id,
                    concept_id=concept.id,
                    interaction_type="checkpoint",
                    user_input=str(choice),
                    system_response=result.get("feedback"),
                    checkpoint_correct=result.get("correct"),
                    time_spent_seconds=None,
                )
                self.db.add(interaction)
                # advance depending on correctness
                if result.get("correct"):
                    # advance
                    next_concept = self._advance_to_next_concept(session)
                    self.db.commit()
                    if next_concept:
                        return {"type": "feedback", "content": result.get("feedback"), "next": self._make_content_response(session, next_concept)}
                    else:
                        return {"type": "feedback", "content": result.get("feedback"), "next": {"type": "summary", "content": "Module complete."}}
                else:
                    # increment retry in session_state
                    state = session.session_state or {}
                    state["retry_count"] = state.get("retry_count", 0) + 1
                    session.session_state = state
                    self.db.commit()
                    return {"type": "feedback", "content": result.get("feedback"), "options": [{"key": "review", "text": "Review concept"}, {"key": "retry", "text": "Try again"}]}

        # Default: show current content
        if concept:
            return self._make_content_response(session, concept)

        return {"type": "content", "content": "No teaching content available."}

    def _make_content_response(self, session: TeachingSession, concept: TeachingConcept) -> Dict[str, Any]:
        # Build content with citations (map chunk_ids to minimal citation info)
        citations = []
        for cid in (concept.chunk_ids or []):
            chunk = self.db.query(Chunk).filter(Chunk.id == cid).first()
            if chunk:
                citations.append({"chunk_id": str(chunk.id), "page": chunk.page_number, "highlight": (chunk.text or "")[:200]})

        # update last_active
        session.last_active_at = datetime.utcnow()
        self.db.commit()

        return {
            "type": "content",
            "content": concept.explanation,
            "citations": citations,
            "options": [
                {"key": "continue", "text": "✓ Continue"},
                {"key": "checkpoint", "text": "📝 Test my understanding"},
                {"key": "simplify", "text": "? Explain differently"}
            ],
            "progress": {"module": float(session.progress_percentage or 0), "overall": float(session.progress_percentage or 0)}
        }

    def _make_checkpoint_response(self, session: TeachingSession, concept: TeachingConcept) -> Dict[str, Any]:
        options = []
        if concept.checkpoint_options:
            for k, v in concept.checkpoint_options.items():
                if k == "correct":
                    continue
                options.append({"key": k, "text": v})

        # set session state
        state = session.session_state or {}
        state["current_step"] = "checkpoint"
        state["last_checkpoint_id"] = str(concept.id)
        session.session_state = state
        session.last_active_at = datetime.utcnow()
        self.db.commit()

        return {"type": "checkpoint", "content": concept.checkpoint_question or "", "options": options, "is_checkpoint": True, "progress": {"module": float(session.progress_percentage or 0), "overall": float(session.progress_percentage or 0)}}

    def evaluate_checkpoint(self, concept_id, user_answer: str) -> Dict[str, Any]:
        """Evaluate checkpoint answer. Returns {correct: bool, feedback: str}.

        Strategy: if checkpoint_options has explicit 'correct' key, compare. Otherwise fallback to keyword matching.
        """
        concept = self.db.query(TeachingConcept).filter(TeachingConcept.id == concept_id).first()
        if not concept:
            return {"correct": False, "feedback": "Concept not found."}

        # If MCQ stored with 'correct' key
        opts = concept.checkpoint_options or {}
        correct_key = opts.get("correct")
        if correct_key:
            is_correct = str(user_answer).upper() == str(correct_key).upper()
            feedback = "Correct!" if is_correct else f"Incorrect. Correct answer: {correct_key}"
            return {"correct": is_correct, "feedback": feedback}

        # Keyword matching fallback
        answer_text = str(user_answer).lower()
        kws = [k.lower() for k in (concept.keywords or [])]
        if not kws:
            return {"correct": False, "feedback": "No keywords available for evaluation."}

        matches = sum(1 for kw in kws if kw in answer_text)
        score = matches / max(len(kws), 1)
        is_correct = score >= 0.33
        feedback = "Correct" if is_correct else "Partial or incorrect. Expected keywords: " + ", ".join(kws[:5])
        return {"correct": is_correct, "feedback": feedback, "score": score}
