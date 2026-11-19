"""Recuperação documental local: TF-IDF, fontes fixadas e páginas verificáveis."""

import hashlib
import json
import re
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
CAMINHO_BASE = ROOT / "docs" / "base-documental.json"
LIMIAR_SIMILARIDADE = 0.10
PALAVRAS_VAZIAS = set("""
a o as os de da do das dos em na no nas nos um uma uns umas e ou para por que
qual quais como quando onde porque ao aos com sem se ser sao foi esta estao
eu meu minha me seu sua seus suas isso isto esse essa esses essas pode podem
deve devem devo tem ter toda todo todas todos feito feita feitos feitas so
apenas serve servem pelo pela pelos pelas entre sobre quem fazer contra
segundo documento documentos oficial oficiais referencia referencias cite citar
explique explicar significa significado favor
""".split())


def familias_palavras(texto):
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))
    termos = set(re.findall(r"\b\w{2,}\b", texto)) - PALAVRAS_VAZIAS
    return {t[:5] if len(t) >= 5 else t for t in termos}


class BaseDocumentalIndisponivelError(RuntimeError):
    pass


class ModeloDocumento(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecorteDocumento(ModeloDocumento):
    pagina_pdf: int = Field(ge=1)
    tema: str = Field(min_length=3, max_length=150)
    inicio: str = ""
    fim: str = ""


class FonteDocumento(ModeloDocumento):
    id: str = Field(pattern=r"^[A-Z0-9-]{3,40}$")
    titulo: str = Field(min_length=3, max_length=250)
    orgao: str = Field(min_length=3, max_length=100)
    ano: int = Field(ge=2000, le=2100)
    edicao: str
    url_pdf: str
    arquivo_local: str = Field(pattern=r"^[a-z0-9_]+\.pdf$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(gt=0, le=20_000_000)
    total_paginas: int = Field(gt=0, le=2000)
    deslocamento_pagina_impressa: int
    consultado_em: date
    licenca: Literal["CC-BY-NC-SA-4.0"]
    recortes: list[RecorteDocumento] = Field(min_length=1, max_length=30)

    @field_validator("url_pdf")
    @classmethod
    def conferir_url(cls, valor):
        url = urlsplit(valor)
        if (url.scheme != "https" or url.hostname not in ("bvsms.saude.gov.br", "www.gov.br")
                or url.username or url.password or url.port or url.query or url.fragment
                or not url.path.endswith(".pdf")):
            raise ValueError("A fonte precisa ser um PDF HTTPS dos domínios oficiais permitidos.")
        return valor

    @model_validator(mode="after")
    def conferir_paginas(self):
        if any(r.pagina_pdf > self.total_paginas for r in self.recortes):
            raise ValueError("Recorte fora do documento.")
        return self


class TrechoDocumento(ModeloDocumento):
    id: str = Field(pattern=r"^R\d{3}$")
    fonte_id: str
    pagina_pdf: int = Field(ge=1)
    tema: str
    texto: str = Field(min_length=60, max_length=1000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class CorpusDocumental(ModeloDocumento):
    schema_version: Literal[1]
    licenca: Literal["CC-BY-NC-SA-4.0"]
    versao: str = Field(pattern=r"^[a-f0-9]{16}$")
    extrator: str
    fontes: list[FonteDocumento] = Field(min_length=1, max_length=20)
    trechos: list[TrechoDocumento] = Field(min_length=1, max_length=999)

    @model_validator(mode="after")
    def conferir_integridade(self):
        fontes = {f.id: f for f in self.fontes}
        if len(fontes) != len(self.fontes) or len({t.id for t in self.trechos}) != len(self.trechos):
            raise ValueError("Identificadores duplicados na base documental.")
        for trecho in self.trechos:
            fonte = fontes.get(trecho.fonte_id)
            if not fonte or not any(r.pagina_pdf == trecho.pagina_pdf and r.tema == trecho.tema for r in fonte.recortes):
                raise ValueError("Trecho sem recorte de origem.")
            if hashlib.sha256(trecho.texto.encode("utf-8")).hexdigest() != trecho.sha256:
                raise ValueError("Texto do trecho não confere com seu hash.")
        if calcular_versao(self.model_dump(mode="json")) != self.versao:
            raise ValueError("Versão da base documental não confere.")
        return self


def calcular_versao(dados):
    corpo = {k: dados[k] for k in ("schema_version", "licenca", "fontes", "trechos")}
    return hashlib.sha256(json.dumps(corpo, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


class BaseDocumental:
    def __init__(self, corpus):
        self.corpus = corpus
        self.fontes = {f.id: f for f in corpus.fontes}
        textos = [t.tema + ". " + t.texto for t in corpus.trechos]
        self.familias = [familias_palavras(t) for t in textos]
        self.palavras = TfidfVectorizer(strip_accents="unicode", ngram_range=(1, 2), sublinear_tf=True,
            stop_words=sorted(PALAVRAS_VAZIAS))
        self.caracteres = TfidfVectorizer(strip_accents="unicode", analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        self.matriz_palavras = self.palavras.fit_transform(textos)
        self.matriz_caracteres = self.caracteres.fit_transform(textos)

    @classmethod
    def carregar(cls, caminho=CAMINHO_BASE):
        try:
            return cls(CorpusDocumental.model_validate_json(Path(caminho).read_text(encoding="utf-8")))
        except (OSError, ValueError, ValidationError):
            raise BaseDocumentalIndisponivelError("Base documental local ausente ou inválida.") from None

    def listar_fontes(self):
        return dict(versao_base=self.corpus.versao, licenca=self.corpus.licenca,
            fontes=[f.model_dump(mode="json", exclude={"arquivo_local", "recortes"}) for f in self.corpus.fontes],
            total_trechos=len(self.corpus.trechos))

    def buscar(self, pergunta, limite=3):
        if not 1 <= limite <= 3 or not 3 <= len(pergunta.strip()) <= 500:
            raise ValueError("Informe uma pergunta de 3 a 500 caracteres e até três trechos.")
        # Os vetores têm norma L2: o produto corresponde à similaridade de cosseno.
        palavras = (self.matriz_palavras @ self.palavras.transform([pergunta]).T).toarray().ravel()
        caracteres = (self.matriz_caracteres @ self.caracteres.transform([pergunta]).T).toarray().ravel()
        escores = 0.7 * palavras + 0.3 * caracteres
        termos = familias_palavras(pergunta)
        # Termos ausentes do vocabulário não podem desaparecer e inflar o cosseno.
        for i, familias in enumerate(self.familias):
            if not termos or len(termos & familias) / len(termos) < 0.5:
                escores[i] = 0
        resultados, paginas = [], set()
        for i in np.argsort(-escores, kind="stable"):
            if escores[i] < LIMIAR_SIMILARIDADE or len(resultados) == limite:
                break
            trecho = self.corpus.trechos[int(i)]
            pagina = (trecho.fonte_id, trecho.pagina_pdf)
            if pagina in paginas:
                continue
            paginas.add(pagina)
            fonte = self.fontes[trecho.fonte_id]
            resultados.append(dict(id=trecho.id, titulo=fonte.titulo, orgao=fonte.orgao,
                ano=fonte.ano, edicao=fonte.edicao, pagina_pdf=trecho.pagina_pdf,
                pagina_impressa=trecho.pagina_pdf + fonte.deslocamento_pagina_impressa,
                url=fonte.url_pdf + f"#page={trecho.pagina_pdf}", documento_sha256=fonte.sha256,
                licenca=fonte.licenca, tema=trecho.tema, trecho=trecho.texto,
                similaridade=round(float(escores[i]), 6)))
        return dict(versao_base=self.corpus.versao, metodo="tfidf_palavras_caracteres",
            encontrado=bool(resultados), trechos=resultados)


@lru_cache(maxsize=1)
def get_base_documental():
    return BaseDocumental.carregar()
