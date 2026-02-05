"""OpenAI LLM service for quiz generation and teaching."""
import json
from typing import List, Dict, Optional
from openai import OpenAI
from app.core.config import settings


class OpenAIService:
    """Service for interacting with OpenAI API."""
    
    def __init__(self):
        """Initialize OpenAI client with API key from settings."""
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
    
    def generate_quiz_questions(
        self,
        chunks_content: List[Dict[str, str]],
        num_questions: int = 5,
        difficulty: str = "MEDIUM",
        custom_prompt: Optional[str] = None
    ) -> List[Dict]:
        """
        Generate quiz questions from knowledge base chunks using OpenAI.
        
        Args:
            chunks_content: List of chunk dictionaries with 'text', 'topic', 'source_file'
            num_questions: Number of questions to generate
            difficulty: EASY, MEDIUM, HARD, or MIXED
            custom_prompt: Optional custom instructions for question generation
            
        Returns:
            List of question dictionaries with structure:
            {
                "question_text": str,
                "correct_answer": str,
                "options": List[str] (for MCQ) or None (for short answer),
                "difficulty": str,
                "chunk_index": int  # Index in chunks_content for linking
            }
        """
        # Prepare context from chunks
        context = self._prepare_context(chunks_content)
        
        # Build the prompt
        system_prompt = self._build_system_prompt(difficulty)
        user_prompt = self._build_user_prompt(
            context=context,
            num_questions=num_questions,
            difficulty=difficulty,
            custom_prompt=custom_prompt
        )
        
        # Call OpenAI API
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            content = response.choices[0].message.content
            result = json.loads(content)
            
            return result.get("questions", [])
            
        except Exception as e:
            raise ValueError(f"Error generating questions from OpenAI: {str(e)}")
    
    def _prepare_context(self, chunks_content: List[Dict[str, str]]) -> str:
        """Prepare context string from chunks."""
        context_parts = []
        
        for idx, chunk in enumerate(chunks_content):
            text = chunk.get('text', '')
            topic = chunk.get('topic', 'Unknown')
            source = chunk.get('source_file', 'Unknown')
            
            context_parts.append(
                f"[Chunk {idx}] (Source: {source}, Topic: {topic})\n{text}\n"
            )
        
        return "\n---\n".join(context_parts)
    
    def _build_system_prompt(self, difficulty: str) -> str:
        """Build the system prompt for quiz generation."""
        difficulty_guidelines = {
            "EASY": "Focus on recall and identification questions. Use simple multiple choice.",
            "MEDIUM": "Focus on explanation and comparison questions. Mix MCQ and short answers.",
            "HARD": "Focus on application and reasoning questions. Prefer short answer format.",
            "MIXED": "Create a mix of easy, medium, and hard questions with varied formats."
        }
        
        guideline = difficulty_guidelines.get(difficulty, difficulty_guidelines["MEDIUM"])
        
        return f"""You are an expert quiz creator for educational content. 
Your task is to generate high-quality quiz questions based on provided document chunks.

Guidelines:
- {guideline}
- Questions must be clear, unambiguous, and directly answerable from the content
- For MCQ questions, provide 4 options (labeled A, B, C, D) with exactly one correct answer
- For short answer questions, set options to null and provide the expected answer
- Each question should reference specific content from the chunks
- Ensure questions test understanding, not just memorization
- Return ONLY valid JSON in the specified format

Output format:
{{
  "questions": [
    {{
      "question_text": "The question text",
      "correct_answer": "The correct answer (for MCQ: A/B/C/D, for short: the answer text)",
      "options": ["Option A text", "Option B text", "Option C text", "Option D text"] or null,
      "difficulty": "EASY|MEDIUM|HARD",
      "chunk_index": 0
    }}
  ]
}}"""
    
    def _build_user_prompt(
        self,
        context: str,
        num_questions: int,
        difficulty: str,
        custom_prompt: Optional[str]
    ) -> str:
        """Build the user prompt with context and requirements."""
        base_prompt = f"""Based on the following content, generate {num_questions} quiz questions with difficulty level: {difficulty}

CONTENT:
{context}

REQUIREMENTS:
- Generate exactly {num_questions} questions
- Difficulty: {difficulty}
- Each question must include:
  * question_text (clear and specific)
  * correct_answer (A/B/C/D for MCQ, or full answer text for short answer)
  * options (array of 4 options for MCQ, or null for short answer)
  * difficulty (EASY, MEDIUM, or HARD)
  * chunk_index (0-based index of the chunk this question is based on)
"""
        
        if custom_prompt:
            base_prompt += f"\n\nADDITIONAL INSTRUCTIONS:\n{custom_prompt}"
        
        base_prompt += "\n\nReturn your response as valid JSON following the specified format."
        
        return base_prompt
