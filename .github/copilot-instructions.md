# Copilot Instructions for K-Bot API

## System Overview
K-Bot is a **NotebookLM-inspired document learning and examination platform** with three modes:
- **Learn Mode** (Ad-hoc): LLM-powered Q&A with citations and analogies from uploaded documents
- **Teach Mode** (NEW): Guided interactive learning with IVR-style conversation, predefined options, and progress tracking
- **Quiz Mode**: Deterministic, explainable evaluation using keyword matching + embeddings (minimal LLM)

**Architecture**: FastAPI backend → PostgreSQL (AWS RDS) + FAISS vector store → S3 document storage → OpenAI/Bedrock for selective LLM tasks.

## Current State & Critical Context
- **Early POC**: Only `app/main.py`, `app/db/base.py`, and `app/db/sessions.py` exist. Most features are unimplemented.
- **DB Schema Exists**: `DDL.sql` at project root defines full schema (`users`, `knowledge_bases`, `documents`, `chunks`, `quizzes`, `quiz_questions`, `quiz_answers`, `quiz_summaries`) with UUID primary keys and cascading deletes.
- **Hardcoded DATABASE_URL**: `app/db/sessions.py` has a hardcoded local connection string (`postgresql://suresh:P%40ssw0rd@localhost:5432/k-bot`). Replace with env-based config for production.
- **Auto-creates tables**: `Base.metadata.create_all(bind=engine)` runs on startup. No Alembic migrations yet — consider adding when models stabilize.
- **Router stubs**: `app/main.py` has commented imports for `app.auth.routes` and `app.exam.routes` — these directories/files don't exist yet.

## Target Architecture (from requirements.md)
Follow this modular structure when building features:
```
app/
├── main.py
├── core/           # Config, security, DB session logic
├── models/         # SQLAlchemy models (user, kb, chunk, quiz, etc.)
├── routes/         # API endpoints (auth, kb, learn, quiz)
└── services/       # Business logic (parser, chunker, vector_store, examiner, teacher)
```

## Teach Mode Architecture (NEW FEATURE)

### Overview
Teach Mode is an **interactive, state-driven learning system** that guides users through document content using:
- **Teaching Modules**: Auto-generated topic hierarchy from document structure
- **Interactive Flow**: Mixed IVR-style (predefined options) + descriptive (LLM-generated) responses
- **Progress Tracking**: Session state management with completion tracking
- **Adaptive Branching**: Adjust difficulty based on checkpoint performance

### Data Model (New Tables)
1. **`teaching_modules`**: Learning path structure (topics, sequence, difficulty, prerequisites)
2. **`teaching_concepts`**: Granular concepts within modules (explanations, checkpoint questions, citations)
3. **`teaching_sessions`**: User progress (current position, completed modules, weak areas, session state)
4. **`teaching_interactions`**: Detailed interaction logs (checkpoints, time spent, user choices)

### Service Architecture
```python
# services/teach_builder.py - Called during KB build
class TeachingModuleBuilder:
    def extract_structure(self, chunks: List[Chunk]) -> List[TeachingModule]:
        """Parse document structure into teaching modules"""
        # 1. Identify headings/sections from chunks
        # 2. Build parent-child hierarchy
        # 3. Generate learning objectives (LLM, one-time)
        # 4. Create checkpoint questions (LLM, one-time)
        pass

# services/teach_engine.py - Manages interactive sessions
class TeachingEngine:
    def start_session(self, kb_id, user_id, module_id=None) -> TeachingSession:
        """Initialize or resume teaching session"""
        pass
    
    def process_interaction(self, session_id, user_input) -> InteractionResponse:
        """State machine: handle user choice/question, return next step"""
        # Determine current state (content, checkpoint, options, summary)
        # Generate response (deterministic for options, LLM for elaboration)
        # Update session state and progress
        # Return structured response with type + content + options
        pass
    
    def evaluate_checkpoint(self, concept_id, user_answer) -> CheckpointResult:
        """Evaluate checkpoint answers (keyword-first, then LLM)"""
        pass
```

### Interaction Flow Pattern
**Response Types** (returned by `/teach/session/{id}/interact`):
```python
{
    "type": "options",  # or "content", "checkpoint", "summary"
    "content": "Which topic would you like to explore?",
    "options": [
        {"key": "A", "text": "Variables and Data Types"},
        {"key": "B", "text": "Control Flow"},
        {"key": "C", "text": "Functions"}
    ],
    "citations": [],  # Empty for option screens
    "progress": {"module": 0, "overall": 25}
}

{
    "type": "content",
    "content": "Variables store data values. In Python, you don't need to declare types...",
    "citations": [{"chunk_id": "...", "page": 12, "highlight": "..."}],
    "options": [
        {"key": "continue", "text": "✓ Continue"},
        {"key": "example", "text": "📝 Show example"},
        {"key": "simplify", "text": "? Explain differently"}
    ],
    "progress": {"module": 30, "overall": 32}
}

{
    "type": "checkpoint",
    "content": "What is the correct way to assign a value to a variable?",
    "options": [
        {"key": "A", "text": "x = 5"},
        {"key": "B", "text": "5 = x"},
        {"key": "C", "text": "var x = 5"}
    ],
    "is_checkpoint": true,
    "progress": {"module": 45, "overall": 35}
}
```

### KB Build Integration
When `POST /kb/{id}/build` is called:
1. **Existing**: Parse → Chunk → Enrich → FAISS index
2. **NEW**: After chunking, call `TeachingModuleBuilder`:
   ```python
   from app.services.teach_builder import TeachingModuleBuilder
   
   # After chunks are created
   builder = TeachingModuleBuilder(db, llm_service)
   modules = await builder.extract_structure(chunks)
   # Stores in teaching_modules, teaching_concepts tables
   ```

### State Management Pattern
```python
# Store conversation state in teaching_sessions.session_state JSONB
{
    "current_step": "checkpoint",
    "pending_feedback": false,
    "retry_count": 0,
    "last_checkpoint_id": "uuid",
    "navigation_stack": ["module_1", "concept_3"],
    "adaptive_mode": "standard"  # or "simplified", "advanced"
}
```

### Critical Implementation Notes
- **Minimize LLM calls**: Use cached module/concept content; only call LLM for:
  - User asks for elaboration ("explain differently")
  - Custom example requests
  - Ambiguous checkpoint answers
- **Idempotent interactions**: Same session_id + input should return consistent results
- **Progress calculation**: `(completed_concepts / total_concepts) * 100`
- **Adaptive branching**: If `teaching_interactions` shows 2+ wrong checkpoints in module → suggest simplified path

## Critical Patterns & Conventions

### Database Session Pattern
- Use `get_db()` generator from `app.db.sessions.py` for FastAPI dependencies:
  ```python
  from app.db.sessions import get_db
  @router.post("/endpoint")
  def endpoint(db: Session = Depends(get_db)):
      # db session auto-closed on exit
  ```
- SQLAlchemy models inherit from `Base` (declarative_base in `app/db/base.py`).
- **UUID primary keys**: All models use `id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)` per DDL schema.

### Authentication (Planned)
- JWT-based auth with `python-jose`, `passlib[bcrypt]` for password hashing.
- Tokens passed via `Authorization: Bearer <token>` header.
- Routes: `POST /auth/register`, `POST /auth/login`.

### Document Processing Pipeline (Unimplemented)
1. **Upload** → S3 storage + DB record in `documents` table
2. **Parse** → PyMuPDF (PDF), python-docx (DOCX), python-pptx (PPTX), pandas (XLSX)
3. **Chunk** → Heading-based chunking (preferred), sliding window fallback
4. **Enrich** → Extract keywords (TF-IDF/RAKE), topic labels, section names → store in `chunks` table with `keywords TEXT[]`
5. **Index** → FAISS embeddings for retrieval; PostgreSQL remains source of truth

### Quiz Evaluation Strategy (Deterministic-first)
- **Primary**: Keyword matching against expected keywords stored in `chunks.keywords`
- **Secondary**: Embedding cosine similarity
- **Fallback**: LLM for hard/ambiguous answers only
- **Always return**: Score (0.00–1.00), expected keywords, feedback, verdict

### API Naming & Structure
- Prefix routes by domain: `/auth/*`, `/kb/*`, `/learn/*`, `/teach/*`, `/quiz/*`
- **Teach Mode endpoints** use session-based pattern:
  - `/kb/{kb_id}/teach/modules` — List learning path (read-only)
  - `/teach/{kb_id}/start` — Create session
  - `/teach/session/{session_id}/interact` — State-driven interactions
- Return 200 + `{status: "ok"}` for health checks (see `/health` endpoint)
- Use path parameters for IDs: `/kb/{kb_id}/upload`, `/quiz/{quiz_id}/answer`

## Key Files Reference
- **`requirements.md`** (project root): Complete feature specs, API contracts, folder structure
- **`DDL.sql`** (project root): Full PostgreSQL schema with indexes
- **`app/main.py`**: FastAPI app, CORS config (currently `allow_origins="*"`), startup table creation
- **`app/db/sessions.py`**: DB engine with `pool_pre_ping=True` for RDS resilience
- **`requirements.txt`**: Runtime dependencies (FastAPI, SQLAlchemy, psycopg2, JWT libraries)

## Development Workflow
```bash
# Start server (hardcoded DB URL in sessions.py for now)
cd k-bot-api
uvicorn app.main:app --reload --port 8000

# Apply DDL manually (no migrations yet)
psql -h localhost -U suresh -d k-bot -f ../DDL.sql
```

## When Building New Features
1. **Add SQLAlchemy models** in `app/models/<entity>.py` matching DDL schema (use UUID, relationships, `TEXT[]` for arrays).
2. **Create routes** in `app/routes/<domain>.py` with `APIRouter()`, then register in `app/main.py` via `app.include_router()`.
3. **Build services** in `app/services/<feature>.py` for business logic (keep routes thin).
4. **Config externalization**: Move hardcoded values (DATABASE_URL, CORS origins, S3 buckets) to `app/core/config.py` using `python-dotenv`.
5. **Add Alembic** when schema stabilizes — currently using `create_all()` which doesn't track migrations.

## Known Issues & Gotchas
- **Import mismatch fixed**: `app/main.py` imports from `app.db.sessions` (correct).
- **Hardcoded credentials**: Remove the hardcoded `DATABASE_URL` in `sessions.py` before deploying.
- **No error handling**: Add try/except for DB operations and validation (Pydantic schemas).
- **CORS wide open**: `allow_origins="*"` is for dev only — restrict in production.
- **No tests**: Add pytest + mocking for `get_db()` when writing endpoints.

## Next Immediate Steps (Priority Order)
1. Implement SQLAlchemy models:
   - Existing: `app/models/user.py`, `knowledge_base.py`, `chunk.py`, `quiz.py`
   - **NEW**: `teaching_module.py`, `teaching_concept.py`, `teaching_session.py`, `teaching_interaction.py`
2. Build auth system (`app/routes/auth.py`, `app/core/security.py` for JWT)
3. Add KB upload pipeline (`app/routes/kb.py`, `app/services/parser.py`)
4. Implement FAISS indexing (`app/services/vector_store.py`)
5. **Build Teach Mode** (NEW):
   - `app/services/teach_builder.py` — Module extraction during KB build
   - `app/services/teach_engine.py` — Interactive session state machine
   - `app/routes/teach.py` — API endpoints
   - Integration: Call `teach_builder` in KB build pipeline
6. Build quiz engine (`app/services/examiner.py` with keyword matching logic)
