"""Teach builder service.

Creates teaching modules and concepts from existing chunks during KB build.
This is a lightweight, idempotent implementation suitable for POC use.
"""
from typing import Optional, List, Dict
import logging
import uuid
import re
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Chunk, TeachingModule, TeachingConcept

logger = logging.getLogger(__name__)


class SimpleLLMStub:
    """Fallback LLM-like stub for summary and question generation.

    This is used when no real `llm_service` is provided. It keeps costs
    and external dependencies out of the basic build flow.
    """

    def generate_summary(self, text: str, max_chars: int = 300) -> str:
        return (text or "").strip()[:max_chars]

    def generate_question(self, concept_name: str) -> Dict:
        # Returns a simple checkpoint question structure
        q = f"Which statement best describes {concept_name}?"
        opts = {"A": f"{concept_name} is important.", "B": f"{concept_name} is irrelevant.", "C": f"{concept_name} depends on context.", "correct": "A"}
        return {"question": q, "options": opts}


class TeachingModuleBuilder:
    """Build teaching modules and concepts for a given KB.

    Usage:
        builder = TeachingModuleBuilder(db, llm_service)
        builder.build_for_kb(kb_id, force=False)
    """

    def __init__(self, db: Session, llm_service: Optional[object] = None):
        self.db = db
        self.llm = llm_service or SimpleLLMStub()

    def _group_chunks_by_section(self, chunks: List[Chunk]) -> Dict[str, List[Chunk]]:
        groups: Dict[str, List[Chunk]] = {}
        for c in chunks:
            key = c.section or c.topic or "_untitled"
            groups.setdefault(key, []).append(c)
        return groups

    def _extract_heading(self, text: str) -> Optional[str]:
        if not text:
            return None
        # Markdown heading
        m = re.search(r"^#{1,6}\s*(.+)$", text, flags=re.MULTILINE)
        if m:
            return m.group(1).strip()
        # Lines that look like headings: short, titlecase, not a sentence
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if len(s.split()) <= 8 and len(s) < 80 and s[0].isupper() and not s.endswith("."):
                return s
        return None

    def _friendly_title(self, chunk: Chunk, fallback: str) -> str:
        # Prefer section/topic if meaningful
        for candidate in (chunk.section, chunk.topic):
            if candidate and candidate.strip() and not candidate.lower().startswith("chunk ") and candidate != "_untitled":
                return candidate.strip()

        # Try extracting a heading from the chunk text
        h = self._extract_heading(chunk.text or "")
        if h:
            return h

        # Use first sentence or first 6 words
        txt = (chunk.text or "").strip()
        if not txt:
            return fallback
        # Split into sentences
        sents = re.split(r'[\.\!\?]\s+', txt)
        first = sents[0] if sents else txt
        words = first.split()
        if len(words) <= 6:
            return first.strip()[:120]
        return " ".join(words[:6]).strip()[:120]

    def build_for_kb(self, kb_id: uuid.UUID, force: bool = False) -> None:
        """Build modules and concepts for the given KB.

        If `force` is True, existing modules for the KB will be removed
        before rebuilding.
        """
        # Optionally remove existing modules for idempotency
        if force:
            deleted = self.db.query(TeachingModule).filter(TeachingModule.kb_id == kb_id).delete(synchronize_session=False)
            logger.info("Deleted %d existing teaching modules for kb_id=%s", deleted, kb_id)
            self.db.commit()

        # If modules already exist and not forcing, skip build
        exists = self.db.query(func.count(TeachingModule.id)).filter(TeachingModule.kb_id == kb_id).scalar()
        if exists and not force:
            logger.info("Teaching modules already exist for kb_id=%s; skipping build", kb_id)
            return

        # Fetch chunks for KB ordered by created_at (document order)
        chunks = self.db.query(Chunk).filter(Chunk.kb_id == kb_id).order_by(Chunk.created_at).all()
        if not chunks:
            logger.warning("No chunks found for kb_id=%s; nothing to build", kb_id)
            return

        groups = self._group_chunks_by_section(chunks)

        sequence = 1
        for section, chks in sorted(groups.items()):
            # derive a friendly module title: prefer section if meaningful, else infer from first chunk
            if section and section != "_untitled" and not section.lower().startswith("chunk "):
                title = section
            else:
                title = self._friendly_title(chks[0], fallback=f"Module {sequence}")
            # create module
            module = TeachingModule(
                kb_id=kb_id,
                parent_module_id=None,
                title=title,
                description=self.llm.generate_summary("\n\n".join([c.text for c in chks])[:1000]),
                sequence_order=sequence,
                estimated_minutes=max(1, int(sum((len(c.text or "") for c in chks)) / 800)),
                difficulty_level="beginner",
                prerequisites=[],
                learning_objectives=[],
            )
            self.db.add(module)
            self.db.flush()  # populate module.id for FK references

            # Create simple concepts from each chunk (dedupe by small text hash)
            for c in chks:
                # pick a friendly concept name from chunk metadata or text
                raw_concept = c.topic or (c.text or "").split("\n")[0][:120]
                concept_name = self._friendly_title(c, fallback=raw_concept)
                explanation = self.llm.generate_summary(c.text or "", max_chars=800)
                # build a checkpoint question via LLM stub/service
                q = self.llm.generate_question(concept_name)
                concept = TeachingConcept(
                    module_id=module.id,
                    concept_name=concept_name,
                    explanation=explanation,
                    chunk_ids=[c.id],
                    keywords=c.keywords or [],
                    related_concept_ids=[],
                    checkpoint_question=q.get("question"),
                    checkpoint_options=q.get("options"),
                )
                self.db.add(concept)

            sequence += 1

        # commit all created modules/concepts
        self.db.commit()
        logger.info("Built %d teaching modules for kb_id=%s", sequence - 1, kb_id)
