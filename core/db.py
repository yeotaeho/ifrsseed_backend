"""Shared DB bootstrap (SQLAlchemy Base/engine/session) for backend domains."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# .env lives under backend/
_backend_dir = Path(__file__).resolve().parents[1]
env_path = _backend_dir / ".env"
if env_path.exists():
    try:
        load_dotenv(env_path, encoding="utf-8")
    except UnicodeDecodeError:
        try:
            load_dotenv(env_path, encoding="utf-16")
        except Exception:
            load_dotenv(env_path)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost/ifrs_agent",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session():
    return SessionLocal()


def init_db():
    Base.metadata.create_all(bind=engine)
