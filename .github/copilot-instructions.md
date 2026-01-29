# Copilot Instructions for K-Bot API

## System Overview
K-Bot is a **NotebookLM-inspired document learning and examination platform** with two modes:
- **Learn Mode**: LLM-powered teaching with citations and analogies from uploaded documents
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
- Prefix routes by domain: `/auth/*`, `/kb/*`, `/learn/*`, `/quiz/*`
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
1. Implement SQLAlchemy models (`app/models/user.py`, `knowledge_base.py`, `chunk.py`, `quiz.py`)
2. Build auth system (`app/routes/auth.py`, `app/core/security.py` for JWT)
3. Add KB upload pipeline (`app/routes/kb.py`, `app/services/parser.py`)
4. Implement FAISS indexing (`app/services/vector_store.py`)
5. Build quiz engine (`app/services/examiner.py` with keyword matching logic)
