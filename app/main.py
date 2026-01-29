from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, kb
from app.db.base import Base
from app.db.sessions import engine
from app.core.config import settings

# Import all models to ensure they're registered with Base
import app.models

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="NotebookLM-inspired document learning and examination platform"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(kb.router)


@app.on_event("startup")
async def startup_event():
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} starting...")
    print("📚 Database connected")
    print("🔐 JWT authentication enabled")


@app.get("/health")
def health():
    return {"status": "ok"}