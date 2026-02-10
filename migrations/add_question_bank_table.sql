-- Migration: Add question_bank table for pre-generated questions
-- Created: 2026-02-09
-- Description: This migration creates a question_bank table to store pre-generated questions
--              for each knowledge base, optimizing quiz generation by avoiding repeated LLM calls

---------------------------------------------------
-- QUESTION BANK
---------------------------------------------------
CREATE TABLE question_bank (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kb_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE NOT NULL,
    question_text TEXT NOT NULL,
    correct_answer TEXT NOT NULL,
    options TEXT[],                   -- Array of 4 options for MCQ format
    difficulty VARCHAR(20) NOT NULL,  -- EASY / MEDIUM / HARD
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add index for efficient querying by KB and difficulty
CREATE INDEX idx_question_bank_kb ON question_bank(kb_id);
CREATE INDEX idx_question_bank_difficulty ON question_bank(kb_id, difficulty);

-- Add comments for documentation
COMMENT ON TABLE question_bank IS 'Pre-generated question bank for knowledge bases to optimize quiz generation';
COMMENT ON COLUMN question_bank.kb_id IS 'Reference to the knowledge base this question belongs to';
COMMENT ON COLUMN question_bank.difficulty IS 'Question difficulty: EASY, MEDIUM, or HARD';
COMMENT ON COLUMN question_bank.options IS 'Array of 4 options for MCQ format';
