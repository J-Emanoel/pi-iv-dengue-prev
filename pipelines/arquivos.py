"""Identificação de arquivos sem carregar seu conteúdo inteiro na memória."""

import hashlib
import json
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path


def sha256_arquivo(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def abrir_zip_anual(pacote, membro=None):
    """Abre um ZIP anual avulso ou um membro comprimido do pacote original."""
    if membro is None:
        yield pacote
        return
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024**2) as spool:
        with pacote.open(membro) as source:
            shutil.copyfileobj(source, spool, length=1024**2)
        spool.seek(0)
        with zipfile.ZipFile(spool) as anual:
            yield anual


def conferir_atualizacao_2026(caminho, tipo, manifesto=None):
    """Revisões novas exigem atualizar conscientemente o inventário separado."""
    manifesto = Path(manifesto) if manifesto else Path(__file__).resolve().parents[1] / "docs/fontes-2026.json"
    fonte = json.loads(manifesto.read_text(encoding="utf-8"))[tipo]
    caminho = Path(caminho)
    if caminho.stat().st_size != fonte["bytes"] or sha256_arquivo(caminho) != fonte["sha256"]:
        raise ValueError(f"Pacote {tipo} 2026 diferente da versão conferida em docs/fontes-2026.json.")
    return fonte
