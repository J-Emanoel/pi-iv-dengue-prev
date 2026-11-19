"""Reproduz a base RAG dos PDFs oficiais fixados no catálogo versionado."""

import argparse
import hashlib
import json
from pathlib import Path

import httpx
import pypdf
from pypdf import PdfReader

from backend.rag import CAMINHO_BASE, ROOT, CorpusDocumental, FonteDocumento, calcular_versao

PASTA_PDFS = ROOT / "data" / "raw" / "rag"


def normalizar_texto(texto):
    return " ".join(texto.replace("\u00ad", "").replace("\x00", "").split())


def dividir_texto(texto, tamanho=900):
    """Conserva a ordem e todos os termos; prefere limites de frases."""
    while len(texto) > tamanho:
        corte = max(texto.rfind(". ", 0, tamanho), texto.rfind("; ", 0, tamanho))
        corte = corte + 1 if corte > tamanho // 2 else texto.rfind(" ", 0, tamanho)
        if corte <= 0:
            raise ValueError("Texto sem separadores adequados.")
        yield texto[:corte].strip()
        texto = texto[corte:].strip()
    if texto:
        yield texto


def recortar_pagina(texto, recorte):
    texto = normalizar_texto(texto)
    if recorte.inicio:
        if recorte.inicio not in texto:
            raise ValueError(f"Marcador inicial não encontrado na página {recorte.pagina_pdf}.")
        texto = texto[texto.index(recorte.inicio):]
    if recorte.fim:
        if recorte.fim not in texto:
            raise ValueError(f"Marcador final não encontrado na página {recorte.pagina_pdf}.")
        texto = texto[:texto.index(recorte.fim)]
    return texto.strip()


def obter_pdf(fonte, pasta=PASTA_PDFS, baixar=False):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / fonte.arquivo_local
    if not caminho.exists() and baixar:
        # URL fixa, HTTPS, sem credenciais ou redirecionamentos; o hash é obrigatório.
        partes, total = [], 0
        with httpx.stream("GET", fonte.url_pdf, timeout=45, follow_redirects=False) as response:
            response.raise_for_status()
            for parte in response.iter_bytes(65536):
                total += len(parte)
                if total > fonte.bytes:
                    raise ValueError("PDF recebido excede o tamanho fixado.")
                partes.append(parte)
        conteudo = b"".join(partes)
        if hashlib.sha256(conteudo).hexdigest() != fonte.sha256:
            raise ValueError("PDF remoto difere da versão fixada. Revise a fonte antes de atualizar.")
        caminho.write_bytes(conteudo)
    if not caminho.is_file():
        raise ValueError(f"PDF {fonte.arquivo_local} ausente; execute com --baixar.")
    conteudo = caminho.read_bytes()
    if len(conteudo) != fonte.bytes or hashlib.sha256(conteudo).hexdigest() != fonte.sha256 or not conteudo.startswith(b"%PDF-"):
        raise ValueError(f"PDF local não confere: {fonte.arquivo_local}.")
    return caminho


def preparar_base(caminho=CAMINHO_BASE, pasta=PASTA_PDFS, *, baixar=False, conferir=False):
    caminho = Path(caminho)
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    fontes = [FonteDocumento.model_validate(f) for f in dados["fontes"]]
    trechos = []
    for fonte in fontes:
        reader = PdfReader(obter_pdf(fonte, pasta, baixar))
        if len(reader.pages) != fonte.total_paginas:
            raise ValueError("Quantidade de páginas diferente do catálogo.")
        for recorte in fonte.recortes:
            texto = recortar_pagina(reader.pages[recorte.pagina_pdf - 1].extract_text() or "", recorte)
            for parte in dividir_texto(texto):
                if len(parte) < 60:
                    raise ValueError("Trecho curto; ajuste o recorte ou a divisão para preservar contexto.")
                trechos.append(dict(id=f"R{len(trechos)+1:03d}", fonte_id=fonte.id,
                    pagina_pdf=recorte.pagina_pdf, tema=recorte.tema, texto=parte,
                    sha256=hashlib.sha256(parte.encode("utf-8")).hexdigest()))
    novos = {**dados, "fontes": [f.model_dump(mode="json") for f in fontes],
        "trechos": trechos, "extrator": f"pypdf {pypdf.__version__}"}
    novos["versao"] = calcular_versao(novos)
    corpus = CorpusDocumental.model_validate(novos)
    if conferir:
        if dados["versao"] != corpus.versao or dados["trechos"] != trechos:
            raise ValueError("A base versionada difere da extração dos PDFs fixados.")
    else:
        temporario = caminho.with_suffix(".json.tmp")
        temporario.write_text(json.dumps(corpus.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        temporario.replace(caminho)
    return dict(fontes=len(fontes), trechos=len(trechos), versao=corpus.versao, conferido=conferir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baixar", action="store_true", help="Baixa PDFs ausentes e verifica os hashes fixados.")
    parser.add_argument("--conferir", action="store_true", help="Compara com a extração original sem alterar a base.")
    args = parser.parse_args()
    try:
        print(json.dumps(preparar_base(baixar=args.baixar, conferir=args.conferir), ensure_ascii=False))
    except (OSError, ValueError, httpx.HTTPError) as exc:
        parser.exit(1, f"Não foi possível preparar o RAG ({type(exc).__name__}). Confira os PDFs, hashes e recortes do catálogo.\n")


if __name__ == "__main__":
    main()
