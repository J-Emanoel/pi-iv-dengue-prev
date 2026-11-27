"""Cota persistente do chat público, compartilhada entre processos da API."""

import math
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database import DatabaseConfigurationError, SessionLocal, get_engine
from backend.models import ControleUsoAssistente

ORIGENS_PADRAO = (
    "https://pi-iv-dengue-prev.vercel.app",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)
_TRAVA_SQLITE = RLock()  # SQLite local usa esta trava; PostgreSQL bloqueia a linha no próprio banco.
_CHAVE = "projeto"
_RESERVA_SEGUNDOS = 600


def origens_permitidas():
    valor = os.getenv("CORS_ORIGINS", ",".join(ORIGENS_PADRAO))
    origens = tuple(o.strip().rstrip("/") for o in valor.split(",") if o.strip())
    if not origens or any(o == "*" or not o.startswith(("https://", "http://")) for o in origens):
        raise ValueError("CORS_ORIGINS deve listar origens HTTP/HTTPS explícitas, separadas por vírgula.")
    return origens


def validar_origem(request: Request):
    # Acesso público: chamadas sem Origin também passam pela mesma cota persistente.
    origem = request.headers.get("origin")
    if origem and origem not in origens_permitidas():
        raise HTTPException(status_code=403, detail="Origem não permitida para o assistente.")


@dataclass(frozen=True)
class LimitesUso:
    por_minuto: int = 3
    por_dia: int = 20

    @classmethod
    def do_ambiente(cls):
        try:
            minuto = int(os.getenv("ASSISTENTE_LIMITE_MINUTO", "3"))
            dia = int(os.getenv("ASSISTENTE_LIMITE_DIA", "20"))
            if not 1 <= minuto <= 60 or not 1 <= dia <= 1000:
                raise ValueError
            return cls(minuto, dia)
        except ValueError:
            raise ErroControleUso(
                "Os limites do assistente precisam ser configurados no servidor.", 503,
            ) from None


class ErroControleUso(RuntimeError):
    def __init__(self, mensagem, status_code=429, retry_after=None):
        super().__init__(mensagem)
        self.status_code = status_code
        self.retry_after = retry_after


def _utc(valor):
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor.astimezone(timezone.utc)


def preparar_controle(engine=None):
    """Cria somente a tabela de cota e sua linha inicial, sem alterar as fontes do projeto."""
    alvo = engine if engine is not None else get_engine()
    ControleUsoAssistente.__table__.create(alvo, checkfirst=True)
    if alvo.dialect.name == "postgresql":
        with alvo.begin() as conn:
            conn.execute(text("ALTER TABLE controle_uso_assistente ENABLE ROW LEVEL SECURITY"))
    with Session(alvo) as session, session.begin():
        if session.get(ControleUsoAssistente, _CHAVE) is None:
            agora = datetime.now(timezone.utc)
            session.add(ControleUsoAssistente(
                chave=_CHAVE,
                minuto=agora.replace(second=0, microsecond=0),
                dia=agora.date(),
                pedidos_minuto=0,
                pedidos_dia=0,
            ))


class ControleUso:
    def __init__(self, session_factory=SessionLocal, limites=None, relogio=None):
        self.session_factory = session_factory
        self.limites = limites or LimitesUso.do_ambiente()
        self.relogio = relogio or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def reservar(self):
        """Conta a tentativa antes da LLM e libera a reserva mesmo em caso de falha."""
        identificador = self._admitir()
        try:
            yield
        finally:
            self._finalizar(identificador)

    @contextmanager
    def _registro_bloqueado(self):
        """Centraliza a transação curta; nenhuma chamada à LLM ocorre com o banco travado."""
        with _TRAVA_SQLITE, self.session_factory() as session, session.begin():
            consulta = (
                select(ControleUsoAssistente)
                .where(ControleUsoAssistente.chave == _CHAVE)
                .with_for_update()
            )
            yield session.execute(consulta).scalar_one_or_none()

    def _admitir(self):
        try:
            with self._registro_bloqueado() as registro:
                if registro is None:
                    raise ErroControleUso(
                        "O controle de uso do assistente ainda não foi preparado no servidor.", 503,
                    )
                agora = _utc(self.relogio())
                minuto = agora.replace(second=0, microsecond=0)
                if registro.dia != agora.date():
                    registro.dia, registro.pedidos_dia = agora.date(), 0
                if _utc(registro.minuto) != minuto:
                    registro.minuto, registro.pedidos_minuto = minuto, 0
                if registro.pedidos_dia >= self.limites.por_dia:
                    amanha = (agora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    raise ErroControleUso(
                        "A cota diária compartilhada do assistente foi atingida. "
                        "Tente novamente amanhã (horário UTC).",
                        retry_after=max(1, math.ceil((amanha - agora).total_seconds())),
                    )
                if registro.pedidos_minuto >= self.limites.por_minuto:
                    proximo_minuto = minuto + timedelta(minutes=1)
                    raise ErroControleUso(
                        "O limite de perguntas por minuto foi atingido. "
                        "Aguarde antes de enviar outra pergunta.",
                        retry_after=max(1, math.ceil((proximo_minuto - agora).total_seconds())),
                    )
                if registro.reserva_ate and _utc(registro.reserva_ate) > agora:
                    raise ErroControleUso(
                        "Já há uma pergunta em processamento no projeto. "
                        "Aguarde a resposta antes de tentar novamente.",
                        retry_after=10,
                    )
                identificador = uuid4().hex
                registro.pedidos_minuto += 1
                registro.pedidos_dia += 1
                registro.reserva_id = identificador
                registro.reserva_ate = agora + timedelta(seconds=_RESERVA_SEGUNDOS)
            return identificador
        except (DatabaseConfigurationError, SQLAlchemyError):
            raise ErroControleUso("O controle de uso está indisponível. Tente novamente mais tarde.", 503) from None

    def _finalizar(self, identificador):
        try:
            with self._registro_bloqueado() as registro:
                if registro and registro.reserva_id == identificador:
                    registro.reserva_id = None
                    registro.reserva_ate = None
        except (DatabaseConfigurationError, SQLAlchemyError):
            # A reserva expira sozinha caso o banco falhe durante a liberação.
            # A tentativa permanece contada: erros do provedor também podem consumir tokens.
            pass


def get_controle_uso():
    return ControleUso()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Prepara a tabela persistente de cota do assistente.")
    parser.add_argument("--preparar", action="store_true", required=True)
    parser.parse_args()
    try:
        preparar_controle()
        print("Controle de uso preparado. Nenhuma fonte epidemiológica foi alterada.")
    except (DatabaseConfigurationError, SQLAlchemyError):
        parser.exit(1, "Não foi possível preparar o controle de uso. Confira a conexão e as permissões do banco.\n")
