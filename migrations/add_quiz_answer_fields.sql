-- Migration to add quiz answer key fields
-- Run this SQL to update your database schema

-- Add correct_answer and options columns to quiz_questions table
ALTER TABLE quiz_questions 
ADD COLUMN IF NOT EXISTS correct_answer TEXT,
ADD COLUMN IF NOT EXISTS options TEXT[];

-- Add comments for documentation
COMMENT ON COLUMN quiz_questions.correct_answer IS 'The correct answer - for MCQ: A/B/C/D, for short answer: the answer text';
COMMENT ON COLUMN quiz_questions.options IS 'Array of 4 options for MCQ format, NULL for short answer questions';

-- Verify the changes
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'quiz_questions' 
  AND column_name IN ('correct_answer', 'options');
