"""Configuração de conexão, sem abrir o banco durante imports."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env")
Base = declarative_base()


class DatabaseConfigurationError(RuntimeError):
    """Configuração local necessária para acessar o banco."""


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseConfigurationError(
            "Configure DATABASE_URL no .env da raiz ou em backend/.env."
        )
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(database_url(), pool_pre_ping=True)


def SessionLocal():
    """Mantém o nome usado no projeto, com criação tardia da conexão."""
    factory = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return factory()


def get_db():
    with SessionLocal() as session:
        yield session
