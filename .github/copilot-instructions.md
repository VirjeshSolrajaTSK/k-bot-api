# Copilot / AI Agent Instructions for K-bot API

Purpose: Help an AI coding agent quickly understand and work on the K-bot API (FastAPI + SQLAlchemy).

- **Big picture**: This is a small FastAPI service in `app/`. DB pieces use SQLAlchemy declarative models (`app/db/base.py`) and a session factory (`app/db/sessions.py`). The app boots in `app/main.py` where tables are created at import time.

- **Key files to inspect first**:
  - `app/main.py` — FastAPI app, CORS middleware, and router includes (currently commented).
  - `app/db/base.py` — SQLAlchemy `Base`.
  - `app/db/sessions.py` — DB engine, `SessionLocal`, and `get_db()` generator. Requires `DATABASE_URL` env var.
  - `requirements.txt` — lists runtime dependencies (FastAPI, uvicorn, SQLAlchemy, psycopg2, passlib, python-jose, python-dotenv, etc.).

- **Critical contextual notes & gotchas**:
  - Import name mismatch: `app/main.py` imports `from app.db.session import engine` but the actual file is `app/db/sessions.py`. Verify and fix the import or filename before adding code that depends on it.
  - `Base.metadata.create_all(bind=engine)` is executed on startup in `app/main.py`. This will create DB tables automatically — be careful when modifying this in production-like workflows.
  - `app/db/sessions.py` will raise a `RuntimeError` if `DATABASE_URL` is not provided. CI or local runs must set this env var or mock it.
  - `app/auth/` and `app/exam/` exist but are currently empty; `main.py` has commented router includes for these. When adding route modules, place them at `app/auth/routes.py` and `app/exam/routes.py` and then uncomment the `include_router` lines.

- **Project-specific patterns**:
  - DB session pattern: a `SessionLocal` factory and a `get_db()` generator that yields a session and closes it in `finally` — follow this for new DB-using endpoints.
  - Router registration: create `APIRouter()` in module `app.<feature>.routes` and then call `app.include_router(...)` from `app/main.py`.
  - Config is expected under `app.core.config` (commented). Prefer adding config values there (CORS origins, DATABASE_URL parsing) rather than hard-coding into `main.py`.

- **Dev workflows / commands** (examples to run locally):
  - Run server (development):
    ``
    DATABASE_URL=postgresql://user:pass@localhost:5432/db uvicorn app.main:app --reload --port 8000
    ``
  - The project uses `python-dotenv` in dependencies; prefer loading secrets from a `.env` file or CI secrets.

- **Auth & security clues**:
  - Libraries present: `passlib[bcrypt]`, `argon2-cffi`, and `python-jose` — expect password hashing and JWT-based auth. Look for or add authentication helpers under `app/auth/`.

- **Integration points**:
  - Postgres (psycopg2-binary) via `DATABASE_URL` environment variable.
  - Potential config module `app.core.config` (not present yet) — use it to centralize env parsing and secrets.

- **When you (the agent) make changes**:
  - Always run a quick static sanity check: ensure imports point to real files (watch for `session` vs `sessions`).
  - If you add DB models or make migrations decisions, note that there is no Alembic here; consider `create_all` implications or add migrations with explanation.
  - When scaffolding routes, include minimal tests or a curl example in the PR description showing the endpoint works with a mocked `DATABASE_URL`.

If any part above is unclear or you want the document to emphasize other workflows (tests, CI, migrations), tell me which area to expand. I can iterate on this file.
