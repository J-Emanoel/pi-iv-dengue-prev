"""Compara extrações SINAN e SESA por notificação, sem somar fontes ou alterar o banco."""

import argparse
import codecs
import csv
import hashlib
import io
import json
import re
import shutil
import tempfile
import warnings
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import requests

from pipelines.arquivos import sha256_arquivo
from pipelines.calendario import ano_semana_epidemiologica, inicio_ano_epidemiologico, semanas_no_ano
from pipelines.etl_ibge import carregar_cadastro
from pipelines.etl_inmet import carregar_clima, gravar_csv
from pipelines.etl_sinan import localizar_zip_anual
from pipelines.vincular_estacoes import carregar_vinculos

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data/raw/sesa"
OUTPUT_DIR = ROOT / "data/processed"
ANOS = tuple(range(2020, 2025))
PAGINA_SESA = "https://app.wiki.saude.es.gov.br/pt-br/vigilanciasaude/sistema-de-informacao-e-dados/microdados"
FONTES_SESA = (
    dict(arquivo="dengue_2020_2022.csv", bytes=40780776,
         url="https://app.wiki.saude.es.gov.br/vigilancia/microdados/dengue_2020_2022.csv",
         sha256="becac621bc87ae855aaa5ba6dedcb3a6e7d8998463676bfd0cee10f6217cbd3e"),
    dict(arquivo="dengue_2023.csv", bytes=106025409,
         url="https://drive.google.com/uc?export=download&id=1_lPTXOPI5yNueNUycxLoWtxngXJQX2uS",
         sha256="b406c21e11152be600354cb4b5222d70937db61653b07e8d88cea7a66b690bf6"),
    dict(arquivo="dengue_2024.csv", bytes=141616430,
         url="https://drive.google.com/uc?export=download&id=1xD79SjDQ4-8i9oO7_7tw7pYf5V_ZqctZ",
         sha256="13f2a12c0421ae9781d82006ce46800bf50121e783cf4ad7ce71126e9cc75b20"),
)
CAMPOS = {
    "sesa": ("UF_PACIENTE", "IBGE_CODE_PACIENTE", "DATA_NOTIFICACAO", "ES"),
    "sinan": ("SG_UF", "ID_MN_RESI", "DT_NOTIFIC", "32"),
}
COLUNAS_SEMANAIS = ("codigo_municipio", "ano_epidemiologico", "semana_epidemiologica", "registos")
CANDIDATA_CSV = OUTPUT_DIR / "sesa_notificacoes_semanais_candidata.csv"
RESUMO_AVALIACAO = OUTPUT_DIR / "avaliacao_fontes_resumo.json"
COLUNAS_BANCO_SESA = (
    "codigo_ibge", "ano", "semana_epidemiologica", "registros_notificados", "data_referencia",
    "fonte_url", "fonte_manifesto_sha256", "fonte_csv_sha256",
)


def manifesto_sesa_sha256():
    return hashlib.sha256(json.dumps(FONTES_SESA, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validar_serie_sesa(registros):
    if not registros:
        raise ValueError("Série estadual vazia.")
    chaves = set()
    for row in registros:
        chave = row["codigo_ibge"], row["ano"], row["semana_epidemiologica"]
        if chave in chaves:
            raise ValueError("Chave municipal/semanal SESA duplicada.")
        chaves.add(chave)
        if (
            not re.fullmatch(r"32\d{4}", row["codigo_ibge"]) or row["ano"] not in ANOS
            or not 1 <= row["semana_epidemiologica"] <= semanas_no_ano(row["ano"])
            or type(row["registros_notificados"]) is not int or row["registros_notificados"] < 0
        ):
            raise ValueError("Código, período ou quantidade inválidos na série estadual.")
        if (
            row["data_referencia"] != "DATA_NOTIFICACAO" or row["fonte_url"] != PAGINA_SESA
            or row["fonte_manifesto_sha256"] != manifesto_sesa_sha256()
            or not re.fullmatch(r"[0-9a-f]{64}", row["fonte_csv_sha256"])
        ):
            raise ValueError("Referência temporal ou versão incompatível na série estadual.")
    if len({row["fonte_csv_sha256"] for row in registros}) != 1:
        raise ValueError("A carga estadual não pode misturar versões do agregado.")


def carregar_serie_sesa(caminho_csv=CANDIDATA_CSV, caminho_resumo=RESUMO_AVALIACAO, *, cadastro=None):
    """Converte somente a candidata validada em registros próprios da fonte estadual."""
    resumo = json.loads(Path(caminho_resumo).read_text(encoding="utf-8"))
    digest = sha256_arquivo(caminho_csv)
    if (
        not isinstance(resumo, dict) or resumo.get("schema_version") != 1
        or resumo.get("tipo") != "avaliacao_fontes" or resumo.get("anos_propostos") != list(ANOS)
        or resumo.get("data_comparacao") != "data_notificacao" or resumo.get("fonte_estadual") != PAGINA_SESA
        or resumo.get("saidas_sha256", {}).get(CANDIDATA_CSV.name) != digest
    ):
        raise ValueError("Candidata SESA e resumo incompatíveis; execute pipelines.avaliar_fontes.")
    fontes = resumo.get("arquivos_sesa", [])
    if [{campo: row.get(campo) for campo in ("arquivo", "url", "bytes", "sha256")} for row in fontes] != list(FONTES_SESA):
        raise ValueError("Arquivos estaduais diferentes da versão fixada.")
    cadastro = carregar_cadastro() if cadastro is None else cadastro
    codigos = {row["codigo_municipio"] for row in cadastro}
    registros = []
    with Path(caminho_csv).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or []) != COLUNAS_SEMANAIS:
            raise ValueError("Esquema da candidata estadual incompatível.")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Quantidade inesperada de campos na candidata estadual.")
            if row["codigo_municipio"] not in codigos or not all(
                re.fullmatch(r"\d+", row[campo]) for campo in COLUNAS_SEMANAIS[1:]
            ):
                raise ValueError("Código ou número inválido na candidata estadual.")
            registros.append(dict(
                codigo_ibge=row["codigo_municipio"], ano=int(row["ano_epidemiologico"]),
                semana_epidemiologica=int(row["semana_epidemiologica"]), registros_notificados=int(row["registos"]),
                data_referencia="DATA_NOTIFICACAO", fonte_url=PAGINA_SESA,
                fonte_manifesto_sha256=manifesto_sesa_sha256(), fonte_csv_sha256=digest,
            ))
    validar_serie_sesa(registros)
    diagnosticos = resumo.get("candidatos_sesa", [])
    if len(diagnosticos) != len(ANOS) or {row["ano"] for row in diagnosticos} != set(ANOS):
        raise ValueError("Período incompleto no resumo estadual.")
    for ano in ANOS:
        linhas = [row for row in registros if row["ano"] == ano]
        diagnostico = next(row for row in diagnosticos if row["ano"] == ano)
        if (
            len(linhas) != diagnostico.get("combinacoes_com_registros")
            or sum(row["registros_notificados"] for row in linhas) != diagnostico.get("registros")
            or len({row["codigo_ibge"] for row in linhas}) != diagnostico.get("municipios_com_registros")
        ):
            raise ValueError("Totais estaduais divergem do resumo de avaliação.")
    return registros


class FormularioDownload(HTMLParser):
    """Confirmação pública de arquivo grande do Drive; não realiza autenticação."""

    def __init__(self):
        super().__init__()
        self.acao = None
        self.parametros = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.acao = attrs.get("action")
        if tag == "input" and attrs.get("name"):
            self.parametros[attrs["name"]] = attrs.get("value", "")


def conferir_arquivo(caminho, fonte):
    if caminho.stat().st_size != fonte["bytes"] or sha256_arquivo(caminho) != fonte["sha256"]:
        raise ValueError(f"Versão de {fonte['arquivo']} diferente da referência fixada; revise antes de processar.")


def baixar_fontes(pasta=RAW_DIR, fontes=FONTES_SESA):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    for fonte in fontes:
        destino = pasta / fonte["arquivo"]
        if destino.exists():
            conferir_arquivo(destino, fonte)
            continue
        with requests.Session() as session:
            response = session.get(fonte["url"], stream=True, timeout=60)
            try:
                response.raise_for_status()
                if "text/html" in response.headers.get("Content-Type", ""):
                    formulario = FormularioDownload()
                    formulario.feed(response.text)
                    response.close()
                    parsed = urlsplit(formulario.acao or "")
                    host = parsed.hostname or ""
                    if parsed.scheme != "https" or not (host.endswith(".google.com") or host.endswith(".googleusercontent.com")):
                        raise ValueError("O download não apresentou o formulário público esperado.")
                    response = session.get(formulario.acao, params=formulario.parametros, stream=True, timeout=60)
                    response.raise_for_status()
                temporario = destino.with_suffix(".part")
                try:
                    tamanho = 0
                    with temporario.open("xb") as stream:
                        for parte in response.iter_content(1024**2):
                            if not parte:
                                continue
                            tamanho += len(parte)
                            if tamanho > fonte["bytes"]:
                                raise ValueError("Download maior que a versão de referência.")
                            stream.write(parte)
                    conferir_arquivo(temporario, fonte)
                    temporario.replace(destino)
                finally:
                    temporario.unlink(missing_ok=True)
            finally:
                response.close()


def mapa_municipal(cadastro):
    return {codigo: row["codigo_municipio"] for row in cadastro
            for codigo in (row["codigo_municipio"], row["codigo_ibge_completo"])}


def agregar_notificacoes(frame, cadastro, fonte):
    """Mesma data de referência nas duas fontes; não usa a data de diagnóstico."""
    uf, municipio, data, estado = CAMPOS[fonte]
    if not {uf, municipio, data}.issubset(frame.columns):
        raise ValueError("Extração sem os campos de residência e data de notificação.")
    metrics = Counter(linhas_lidas=len(frame))
    frame = frame.loc[frame[uf].str.strip().str.upper().eq(estado)].copy()
    metrics["residentes_es"] = len(frame)
    codigos = frame[municipio].str.strip().str.replace(r"\.0+$", "", regex=True).map(mapa_municipal(cadastro))
    metrics["codigo_residencia_invalido"] = int(codigos.isna().sum())
    frame["codigo"] = codigos
    frame = frame.loc[codigos.notna()].copy()
    # Os arquivos fixados usam datas ISO; apenas o componente da data é agregado.
    original = frame[data].str.strip()
    formato = original.str.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T].*)?")
    datas = pd.to_datetime(original.str[:10].where(formato), format="%Y-%m-%d", errors="coerce")
    metrics["data_notificacao_invalida"] = int(datas.isna().sum())
    frame = frame.loc[datas.notna()].copy()
    datas = datas.loc[datas.notna()]
    frame["ano_calendario"], frame["mes"] = datas.dt.year, datas.dt.month
    meses_validos = frame["ano_calendario"].isin(ANOS)
    metrics["fora_periodo_calendario"] = int((~meses_validos).sum())
    mensal = Counter({(int(ano), int(mes)): int(qtd)
                      for (ano, mes), qtd in frame.loc[meses_validos].groupby(["ano_calendario", "mes"]).size().items()})
    periodos = datas.map(lambda dia: ano_semana_epidemiologica(dia.date()))
    frame["ano"] = periodos.map(lambda item: item[0])
    frame["semana"] = periodos.map(lambda item: item[1])
    semanas_validas = frame["ano"].isin(ANOS)
    metrics["fora_periodo_epidemiologico"] = int((~semanas_validas).sum())
    semanal = Counter({(str(codigo), int(ano), int(semana)): int(qtd)
                       for (codigo, ano, semana), qtd in frame.loc[semanas_validas].groupby(["codigo", "ano", "semana"]).size().items()})
    return semanal, mensal, metrics


def processar_sesa(cadastro, pasta=RAW_DIR, fontes=FONTES_SESA, chunksize=50000):
    semanal, mensal, arquivos = Counter(), Counter(), []
    ids = set()
    colunas = list(CAMPOS["sesa"][:3]) + ["NUM_NOTIFICACAO", "C_CLASSIFIC"]
    for fonte in fontes:
        caminho = Path(pasta) / fonte["arquivo"]
        conferir_arquivo(caminho, fonte)
        metrics, classes, repetidos, vazios = Counter(), Counter(), 0, 0
        print(f"Analisando SESA: {fonte['arquivo']}...", flush=True)
        # Estes CSVs têm BOM UTF-8 com conteúdo CP1252. Remover o BOM antes de decodificar.
        with caminho.open("rb") as raw:
            if raw.read(3) != codecs.BOM_UTF8:
                raw.seek(0)
            with io.TextIOWrapper(raw, encoding="cp1252", newline="") as stream, warnings.catch_warnings():
                warnings.simplefilter("error", pd.errors.ParserWarning)
                for frame in pd.read_csv(stream, dtype=str, keep_default_na=False, usecols=colunas,
                                         chunksize=chunksize, on_bad_lines="error", index_col=False):
                    semanas, meses, contadores = agregar_notificacoes(frame, cadastro, "sesa")
                    semanal.update(semanas)
                    mensal.update(meses)
                    metrics.update(contadores)
                    classes.update(frame["C_CLASSIFIC"])
                    for valor in frame["NUM_NOTIFICACAO"]:
                        if not valor.strip() or valor.upper() == "NA":
                            vazios += 1
                            continue
                        identificador = hashlib.sha256(valor.encode()).digest()
                        repetidos += identificador in ids
                        ids.add(identificador)
        arquivos.append({**fonte, "encoding": "cp1252", "contadores": dict(metrics),
                         "classificacoes_brutas": dict(classes), "identificadores_repetidos": repetidos,
                         "identificadores_ausentes": vazios})
    return semanal, mensal, arquivos


def processar_sinan(cadastro, zip_path=ROOT / "arquivos-proj-int-iv.zip", manifesto=ROOT / "docs/inventario-bases.json", chunksize=50000):
    inventario = json.loads(Path(manifesto).read_text(encoding="utf-8"))
    digest = sha256_arquivo(zip_path)
    if digest != inventario["input"]["sha256"]:
        raise ValueError("ZIP SINAN diferente do inventário de originais.")
    semanal, mensal, arquivos = Counter(), Counter(), []
    with zipfile.ZipFile(zip_path) as outer:
        # Ler todos os pacotes recebidos: ano do nome não substitui a data do registro.
        for ano in range(2020, 2027):
            nome = localizar_zip_anual(outer.namelist(), ano)
            metrics = Counter()
            print(f"Analisando SINAN por data de notificação: {ano}...", flush=True)
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024**2) as spool:
                with outer.open(nome) as stream:
                    shutil.copyfileobj(stream, spool, length=1024**2)
                spool.seek(0)
                with zipfile.ZipFile(spool) as inner:
                    nomes = [item for item in inner.namelist() if item.lower().endswith(".csv")]
                    if len(nomes) != 1:
                        raise ValueError("Pacote SINAN com CSV ausente ou ambíguo.")
                    with inner.open(nomes[0]) as stream, warnings.catch_warnings():
                        warnings.simplefilter("error", pd.errors.ParserWarning)
                        for frame in pd.read_csv(stream, encoding="utf-8-sig", dtype=str, keep_default_na=False,
                                                 usecols=list(CAMPOS["sinan"][:3]), chunksize=chunksize,
                                                 on_bad_lines="error", index_col=False):
                            semanas, meses, contadores = agregar_notificacoes(frame, cadastro, "sinan")
                            semanal.update(semanas)
                            mensal.update(meses)
                            metrics.update(contadores)
            arquivos.append(dict(ano_arquivo=ano, arquivo=nome, contadores=dict(metrics)))
    return semanal, mensal, dict(entrada_sha256=digest, arquivos=arquivos)


def diagnosticar_serie(semanal, clima, vinculos, municipios=78):
    """Presença e continuidade observáveis; não certifica a cobertura epidemiológica."""
    por_data, clima_valido = {}, set()
    for (codigo, ano, semana), quantidade in semanal.items():
        inicio = inicio_ano_epidemiologico(ano) + timedelta(weeks=semana - 1)
        por_data[codigo, inicio] = quantidade
        medidas = clima.get((vinculos.get((codigo, ano)), ano, semana))
        if medidas and all(medidas[campo] >= .8 * medidas["horas_previstas"]
                           for campo in ("horas_precipitacao", "horas_temperatura", "horas_umidade")):
            clima_valido.add((codigo, inicio))
    resultado = []
    for ano in ANOS:
        chaves = [chave for chave in semanal if chave[1] == ano]
        com_clima, exemplos, exemplos_clima = 0, 0, 0
        for codigo, _, semana in chaves:
            inicio = inicio_ano_epidemiologico(ano) + timedelta(weeks=semana - 1)
            # Alvo em t+1, quatro semanas consecutivas disponíveis até t.
            anteriores = [(codigo, inicio - timedelta(weeks=lag)) for lag in range(1, 5)]
            janela_completa = all(chave in por_data for chave in anteriores)
            exemplos += janela_completa
            # A qualidade climática exigida está nos lags, nunca na semana futura do alvo.
            exemplos_clima += janela_completa and all(chave in clima_valido for chave in anteriores)
            com_clima += (codigo, inicio) in clima_valido
        resultado.append(dict(
            ano=ano, combinacoes_previstas=municipios * semanas_no_ano(ano),
            combinacoes_com_registros=len(chaves), municipios_com_registros=len({key[0] for key in chaves}),
            registros=sum(semanal[key] for key in chaves), combinacoes_com_clima_80pct=com_clima,
            exemplos_com_4_semanas_anteriores_e_alvo=exemplos,
            exemplos_com_janela_e_clima_80pct=exemplos_clima,
        ))
    return resultado


def avaliar(*, baixar=False, zip_path=ROOT / "arquivos-proj-int-iv.zip", output_dir=OUTPUT_DIR):
    if baixar:
        baixar_fontes()
    cadastro = carregar_cadastro()
    sesa, mensal_sesa, fontes_sesa = processar_sesa(cadastro)
    sinan, mensal_sinan, fontes_sinan = processar_sinan(cadastro, zip_path)
    _, semanas_clima = carregar_clima()
    clima = {(row["codigo_estacao"], row["ano"], row["semana_epidemiologica"]): row for row in semanas_clima}
    vinculos = {(row["codigo_ibge"], row["ano"]): row["codigo_estacao"] for row in carregar_vinculos()}
    output_dir = Path(output_dir)
    comparacao = []
    for ano in ANOS:
        for mes in range(1, 13):
            a, b = mensal_sinan.get((ano, mes)), mensal_sesa.get((ano, mes))
            comparacao.append(dict(ano=ano, mes=mes, registros_sinan=a, registros_sesa=b,
                                   diferenca_sesa_menos_sinan=b - a if a is not None and b is not None else None))
    csv_semanal = output_dir / "sesa_notificacoes_semanais_candidata.csv"
    semanal_hash = gravar_csv(csv_semanal, COLUNAS_SEMANAIS, [
        dict(zip(COLUNAS_SEMANAIS, (*chave, valor))) for chave, valor in sorted(sesa.items())
    ])
    comparacao_hash = gravar_csv(output_dir / "comparacao_fontes_mensal.csv", tuple(comparacao[0]), comparacao)
    resumo = dict(
        schema_version=1, tipo="avaliacao_fontes", gerado_em_utc=datetime.now(timezone.utc).isoformat(),
        fonte_estadual=PAGINA_SESA, anos_propostos=list(ANOS), data_comparacao="data_notificacao",
        candidatos_sesa=diagnosticar_serie(sesa, clima, vinculos, len(cadastro)),
        sinan_mesma_data=diagnosticar_serie(sinan, clima, vinculos, len(cadastro)),
        arquivos_sesa=fontes_sesa, fonte_sinan=fontes_sinan,
        totais_calendario={str(ano): dict(sesa=sum(qtd for (y, _), qtd in mensal_sesa.items() if y == ano),
                                       sinan=sum(qtd for (y, _), qtd in mensal_sinan.items() if y == ano)) for ano in ANOS},
        saidas_sha256={csv_semanal.name: semanal_hash, "comparacao_fontes_mensal.csv": comparacao_hash},
        proposta_ml=dict(alvo="registros_notificados_por_semana_de_notificacao", treino=[2020, 2021, 2022],
                         validacao=[2023], teste=[2024], horizonte_semanas=1, janela_semanas=4,
                         cobertura_minima_clima_pct=80, limiar_exploratorio=True,
                         clima="Somente semanas até t; a qualidade climática da semana do alvo não seleciona exemplos."),
        cobertura_epidemiologica_validada=False, carga_no_banco_realizada=False,
        observacoes=[
            "Os universos, revisões e extrações diferem. Diferença de totais não estima cobertura nem mede sobreposição.",
            "Não somar SINAN e SESA; não há uma chave compartilhada suficiente para deduplicação entre fontes.",
            "A base atual usa primeiros sintomas; esta comparação usa notificação em ambas as fontes.",
            "Os rótulos de ano dos arquivos não substituem os anos das datas. Totais mensais usam ano-calendário; semanais usam ano epidemiológico.",
            "Semanas ausentes permanecem ausentes. A continuidade conta somente registros observados e implica seleção de amostras.",
            "Identificadores repetidos são diagnósticos; não foram eliminadas linhas automaticamente.",
            "Não há link de download de dengue de 2025 ou 2026 na página estadual consultada nesta versão.",
            "O diagnóstico temporal é retrospectivo; não reconstrói o que estava disponível na data original de cada previsão.",
        ],
    )
    (output_dir / "avaliacao_fontes_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resumo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baixar", action="store_true", help="Obtém a versão pública fixada dos arquivos SESA, se ausente.")
    args = parser.parse_args()
    try:
        resumo = avaliar(baixar=args.baixar)
        print(json.dumps({key: resumo[key] for key in ("candidatos_sesa", "sinan_mesma_data", "totais_calendario")}, ensure_ascii=True, indent=2))
        print("Comparação local concluída. Banco preservado; leia data/processed/avaliacao_fontes_resumo.json.")
        return 0
    except requests.RequestException:
        print("Falha no download público; confira conexão e disponibilidade da versão fixada.")
    except (OSError, ValueError, csv.Error, zipfile.BadZipFile, pd.errors.ParserError, pd.errors.ParserWarning) as exc:
        print(f"Erro na avaliação: {exc}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
