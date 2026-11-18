"""Configuração de conexão, sem abrir o banco durante imports."""

import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
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
    url = database_url()
    # UPDATE em lote evita uma viagem de rede por linha no PostgreSQL remoto.
    opcoes = (dict(executemany_mode="values_plus_batch", executemany_batch_page_size=500)
              if url.startswith("postgresql+psycopg2://") else {})
    return create_engine(url, pool_pre_ping=True, **opcoes)


def SessionLocal():
    """Mantém o nome usado no projeto, com criação tardia da conexão."""
    factory = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return factory()


def get_db():
    with SessionLocal() as session:
        yield session


@contextmanager
def transacao(alvo):
    """Reutiliza uma transação externa para compor cargas sem commits parciais."""
    if isinstance(alvo, Connection):
        if not alvo.in_transaction():
            raise ValueError("A conexão da carga conjunta precisa de transação ativa.")
        yield alvo
    else:
        with alvo.begin() as connection:
            if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql("BEGIN")
            yield connection
