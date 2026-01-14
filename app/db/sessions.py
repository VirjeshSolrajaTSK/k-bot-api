import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
# from app.core.config import DATABASE_URL

logger = logging.getLogger("app.db.session")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

DATABASE_URL = "postgresql://virjeshsolraja:@localhost:5432/k-bot"
logger.info("Initializing DB session (checking configuration)")
logger.info("DATABASE_URL present: %s %s", bool(DATABASE_URL), os.getenv("DATABASE_URL"))

if not DATABASE_URL:
    logger.error(
        "DATABASE_URL is not configured. Set the DATABASE_URL env var or provide DB_* secret fields."
    )
    raise RuntimeError(
        "DATABASE_URL is not configured. Set the DATABASE_URL env var or provide DB_* secret fields."
    )

# enable pool_pre_ping to avoid stale/closed connections with RDS
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()