"""Alembic environment configuration"""
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys
from pathlib import Path

# 경로: .../<repo>/backend/alembic/env.py
_backend_dir = Path(__file__).resolve().parents[1]
_repo_root = _backend_dir.parent
_v1_domain_path = _backend_dir / "domain" / "v1"
# 순서: domain/v1 먼저 → 패키지 내부의 `from ifrs_agent...` 가 동작
#       그다음 repo 루트 → `from backend.domain.v1.ifrs_agent...` 가 동작
#       backend → 기타 `from domain...` 등 호환
for _p in (_repo_root, _backend_dir, _v1_domain_path):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# Load .env file
from dotenv import load_dotenv
env_path = _repo_root / ".env"
if env_path.exists():
    try:
        load_dotenv(env_path, encoding='utf-8')
    except UnicodeDecodeError:
        try:
            load_dotenv(env_path, encoding='utf-16')
        except Exception:
            load_dotenv(env_path)

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models (제안 6개 테이블 구조)
from backend.core.db import Base
from backend.domain.v1.esg_data.models.bases import (
    DataPoint,
    Glossary,
    Rulebook,
    Standard,
    SynonymGlossary,
    UnifiedColumnMapping,
)

target_metadata = Base.metadata

# Override sqlalchemy.url from environment variable
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
