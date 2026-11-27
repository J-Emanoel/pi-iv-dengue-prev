"""Transporta os experimentos ativos sem incluir credenciais ou os ZIPs brutos."""

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from pipelines.arquivos import sha256_arquivo

ROOT = Path(__file__).resolve().parents[1]
FONTES = ("sesa", "sinan")
MANIFESTO = "manifesto-modelos.json"
LIMITE_BYTES = 200 * 1024**2


def _pastas(fonte, execucao, dataset):
    if fonte not in FONTES or not re.fullmatch(r"\d{8}T\d{12}Z_[0-9a-f]{16}", execucao):
        raise ValueError("Fonte ou execução inválida no pacote.")
    if not re.fullmatch(r"[0-9a-f]{16}", dataset):
        raise ValueError("Identificador de dataset inválido no pacote.")
    sufixo = "/sinan" if fonte == "sinan" else ""
    return f"ml/models{sufixo}", f"data/processed/ml{sufixo}/{dataset}"


def _caminhos(fonte, info):
    modelos, dados = _pastas(fonte, info["execucao"], info["dataset_id"])
    return [
        f"{modelos}/atual.json",
        f"{modelos}/{info['execucao']}/avaliacao.json",
        f"{modelos}/{info['execucao']}/modelo.joblib",
        f"{dados}/base_{fonte}.csv",
        f"{dados}/exemplos.csv",
        f"{dados}/resumo.json",
    ]


def _ler_json(caminho):
    return json.loads(caminho.read_text(encoding="utf-8"))


def exportar(arquivo, raiz=ROOT):
    """Seleciona apenas o modelo ativo de cada fonte e os snapshots ligados a ele."""
    raiz, arquivo = Path(raiz).resolve(), Path(arquivo)
    fontes, registros = {}, []
    for fonte in FONTES:
        modelos = raiz / "ml/models" / ("sinan" if fonte == "sinan" else "")
        execucao = _ler_json(modelos / "atual.json")["execucao"]
        # Valida o identificador antes de usá-lo num caminho local.
        _pastas(fonte, execucao, "0" * 16)
        avaliacao = _ler_json(modelos / execucao / "avaliacao.json")
        info = {"execucao": execucao, "dataset_id": avaliacao["dataset_id"],
                "ambiente": avaliacao["ambiente"]}
        caminhos = _caminhos(fonte, info)
        resumo = _ler_json(raiz / caminhos[-1])
        if (avaliacao.get("fonte", "sesa") != fonte or avaliacao["execucao"] != execucao
                or resumo["dataset_id"] != info["dataset_id"]
                or resumo.get("fonte", "sesa") != fonte):
            raise ValueError("Modelo e dataset não pertencem à mesma fonte/execução.")
        hashes = {
            caminhos[2]: avaliacao["modelo_sha256"],
            caminhos[3]: resumo["base_sha256"],
            caminhos[4]: resumo["exemplos_sha256"],
        }
        if any(avaliacao[chave] != resumo[chave] for chave in ("base_sha256", "exemplos_sha256")):
            raise ValueError("Avaliação e snapshot divergem.")
        for caminho in caminhos:
            original = (raiz / caminho).resolve()
            if not original.is_relative_to(raiz) or not original.is_file():
                raise ValueError("Arquivo do experimento ausente ou fora do projeto.")
            digest = sha256_arquivo(original)
            if caminho in hashes and hashes[caminho] != digest:
                raise ValueError(f"Arquivo do experimento alterado: {caminho}.")
            registros.append({"caminho": caminho, "bytes": original.stat().st_size, "sha256": digest})
        fontes[fonte] = info
    manifesto = {"schema_version": 1, "fontes": fontes, "arquivos": registros}
    if sum(r["bytes"] for r in registros) > LIMITE_BYTES:
        raise ValueError("O pacote ultrapassa o limite de 200 MiB descompactados.")
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    # Modo x evita substituir acidentalmente um pacote já entregue ao grupo.
    with zipfile.ZipFile(arquivo, "x", compression=zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr(MANIFESTO, json.dumps(manifesto, ensure_ascii=False, indent=2))
        for registro in registros:
            pacote.write(raiz / registro["caminho"], registro["caminho"])
    conferir(arquivo)
    return manifesto


def _conferir_conteudo(pacote):
    """Confere a lista fechada de caminhos e os hashes antes de qualquer restauração."""
    entradas = pacote.infolist()
    nomes = [e.filename for e in entradas]
    if len(nomes) != len(set(nomes)) or len(nomes) != 13:
        raise ValueError("O pacote deve conter o manifesto e os 12 arquivos dos experimentos.")
    if MANIFESTO not in nomes or pacote.getinfo(MANIFESTO).file_size > 65536:
        raise ValueError("Manifesto ausente ou inválido.")
    manifesto = json.loads(pacote.read(MANIFESTO))
    if manifesto["schema_version"] != 1 or set(manifesto["fontes"]) != set(FONTES):
        raise ValueError("Manifesto de modelos incompatível.")
    permitidos = {c for fonte in FONTES for c in _caminhos(fonte, manifesto["fontes"][fonte])}
    registros = manifesto["arquivos"]
    if len(registros) != 12 or {r["caminho"] for r in registros} != permitidos:
        raise ValueError("Arquivos divergentes do manifesto.")
    if set(nomes) != permitidos | {MANIFESTO} or sum(e.file_size for e in entradas) > LIMITE_BYTES:
        raise ValueError("Conteúdo inesperado ou pacote grande demais.")
    for registro in registros:
        entrada = pacote.getinfo(registro["caminho"])
        if entrada.file_size != registro["bytes"] or (entrada.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("Tamanho divergente ou link simbólico no pacote.")
        digest = hashlib.sha256()
        with pacote.open(entrada) as stream:
            for bloco in iter(lambda: stream.read(1024**2), b""):
                digest.update(bloco)
        if digest.hexdigest() != registro["sha256"]:
            raise ValueError(f"Hash divergente: {entrada.filename}.")
    return manifesto


def conferir(arquivo, sha256=None):
    """Não desserializa Joblib: verifica apenas estrutura, tamanhos e integridade."""
    if sha256 is not None and sha256_arquivo(arquivo) != sha256.lower():
        raise ValueError("SHA-256 do ZIP difere do valor informado pelo responsável.")
    with zipfile.ZipFile(arquivo) as pacote:
        try:
            return _conferir_conteudo(pacote)
        except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
            raise ValueError("Manifesto do pacote inválido.") from exc


def restaurar(arquivo, destino, sha256):
    """Reutiliza arquivos idênticos; recusa substituir qualquer conteúdo diferente."""
    manifesto = conferir(arquivo, sha256)
    destino = Path(destino).resolve()
    novos = []
    for registro in manifesto["arquivos"]:
        alvo = (destino / registro["caminho"]).resolve()
        if not alvo.is_relative_to(destino):
            raise ValueError("O destino de um arquivo está fora do projeto.")
        if alvo.exists():
            if not alvo.is_file() or sha256_arquivo(alvo) != registro["sha256"]:
                raise ValueError(f"Destino já contém arquivo diferente: {registro['caminho']}.")
        else:
            novos.append((registro["caminho"], alvo))
    # Só ativa os ponteiros depois de copiar os snapshots e modelos conferidos.
    novos.sort(key=lambda item: item[0].endswith("/atual.json"))
    with tempfile.TemporaryDirectory(prefix="dengueprev-modelos-") as temporario:
        with zipfile.ZipFile(arquivo) as pacote:
            for caminho, _ in novos:
                preparado = Path(temporario) / caminho
                preparado.parent.mkdir(parents=True, exist_ok=True)
                with pacote.open(caminho) as origem, preparado.open("xb") as saida:
                    shutil.copyfileobj(origem, saida)
        for caminho, alvo in novos:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with (Path(temporario) / caminho).open("rb") as origem, alvo.open("xb") as saida:
                shutil.copyfileobj(origem, saida)
    return len(novos)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operacao", choices=("exportar", "conferir", "restaurar"))
    parser.add_argument("arquivo", type=Path)
    parser.add_argument("--destino", type=Path, default=ROOT, help="Raiz do projeto que receberá os modelos.")
    parser.add_argument("--sha256", help="Hash do ZIP, obrigatório para restaurar um pacote de origem conhecida.")
    args = parser.parse_args(argv)
    if args.operacao == "restaurar" and not args.sha256:
        parser.error("--sha256 é obrigatório para restaurar.")
    try:
        if args.operacao == "exportar":
            manifesto = exportar(args.arquivo)
        elif args.operacao == "restaurar":
            print(f"Arquivos restaurados: {restaurar(args.arquivo, args.destino, args.sha256)}")
            manifesto = conferir(args.arquivo, args.sha256)
        else:
            manifesto = conferir(args.arquivo, args.sha256)
        for fonte, info in manifesto["fontes"].items():
            print(f"{fonte}: execução {info['execucao']} | ambiente {json.dumps(info['ambiente'])}")
        print(f"SHA-256: {sha256_arquivo(args.arquivo)}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError):
        print("Falha: confira pacote, hashes, arquivos existentes e permissões. Nenhum dado do banco foi alterado.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
