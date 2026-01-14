from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# from app.auth.routes import router as auth_router
# from app.exam.routes import router as exam_router
from app.db.base import Base
from app.db.sessions import engine
# from app.core.config import CORS_ALLOWED_ORIGINS

Base.metadata.create_all(bind=engine)

app = FastAPI(title="K-bot API")

# CORS configuration: use origins from configuration (loaded from .env files)
# ALLOWED_ORIGINS = [o.strip() for o in CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins= "*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.include_router(auth_router)
# app.include_router(exam_router)


@app.get("/health")
def health():
    return {"status": "ok"}