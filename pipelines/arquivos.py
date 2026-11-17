"""Identificação de arquivos sem carregar seu conteúdo inteiro na memória."""

import hashlib
from pathlib import Path


def sha256_arquivo(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            digest.update(block)
    return digest.hexdigest()
