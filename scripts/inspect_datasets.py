"""Inspeciona CSVs locais e ZIPs aninhados sem extrair os datasets no projeto."""

from __future__ import annotations

import argparse
import codecs
import csv
import html
import io
import json
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import BinaryIO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROBE_BYTES = 64 * 1024
ZIP_MEMORY_BYTES = 8 * 1024 * 1024
MAX_ZIP_DEPTH = 4


def detect_encoding(probe: bytes) -> str:
    """Detecta BOM/UTF-8; CP1252 e Latin-1 são alternativas heurísticas."""
    if probe.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            # Uma amostra pode terminar no meio de um caractere multibyte.
            codecs.getincrementaldecoder(encoding)(errors="strict").decode(
                probe, final=False
            )
        except UnicodeDecodeError:
            continue
        return encoding
    raise ValueError("Não foi possível interpretar o encoding da amostra.")


def detect_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text, delimiters=",;\t|").delimiter
    except csv.Error:
        first = text.splitlines()[0] if text.splitlines() else ""
        return max((",", ";", "\t", "|"), key=first.count)


def source_hint(name: str) -> str | None:
    basename = name.replace("\\", "/").rsplit("/", 1)[-1].upper()
    if basename.startswith("DENGBR"):
        return "sinan"
    if basename.startswith("INMET_") or re.fullmatch(r"20\d{2}\.ZIP", basename):
        return "inmet"
    return None


def inspect_csv(
    stream: BinaryIO,
    label: str,
    size_bytes: int,
    *,
    sample_rows: int = 3,
    count_rows: bool = False,
    source_filter: str = "all",
) -> dict | None:
    """Lê cabeçalho/amostra ou conta a tabela inteira em fluxo.

    O stream deve permitir seek, como arquivos locais e ZipExtFile. O conteúdo
    original é preservado; entidades HTML recebem somente rótulos de exibição.
    """
    if sample_rows < 0:
        raise ValueError("A quantidade de linhas de amostra deve ser não negativa.")
    probe = stream.read(PROBE_BYTES)
    if not probe:
        raise ValueError("Arquivo vazio.")
    encoding = detect_encoding(probe)
    text = codecs.getincrementaldecoder(encoding)(errors="strict").decode(
        probe, final=False
    )
    stream.seek(0)
    lines = text.splitlines()
    metadata: dict[str, str] = {}
    source = "unknown"
    header_line = 1
    first = lines[0] if lines else ""
    if re.match(r"REGI[AÃ]O\s*:;", first, flags=re.IGNORECASE):
        source, delimiter, header_line = "inmet", ";", 9
        for line in lines[:8]:
            key, separator, value = line.partition(";")
            if separator:
                metadata[key.rstrip(":").strip()] = value.strip()
    elif len(lines) > 1 and any(
        field.startswith("Código")
        for field in next(csv.reader([html.unescape(lines[1])], delimiter=","))
    ):
        source, delimiter, header_line = "ibge", ",", 2
        metadata["title"] = html.unescape(first)
    else:
        delimiter = detect_delimiter(text)

    with io.TextIOWrapper(stream, encoding=encoding, newline="") as decoded:
        reader = csv.reader(decoded, delimiter=delimiter)
        for _ in range(header_line - 1):
            next(reader, None)
        columns = next(reader, None)
        if columns is None or not any(columns):
            raise ValueError("Cabeçalho ausente ou vazio.")
        if {"DT_NOTIFIC", "ID_MN_RESI", "SEM_PRI"}.issubset(columns):
            source = "sinan"
        if source_filter != "all" and source != source_filter:
            return None
        profile = {
            "path": label,
            "size_bytes": size_bytes,
            "source": source,
            "encoding": encoding,
            "encoding_detection": "BOM/UTF-8 verificado; CP1252/Latin-1 heurístico",
            "delimiter": delimiter,
            "header_line": header_line,
            "column_count": len(columns),
            "columns": columns,
            "column_labels": [html.unescape(c) for c in columns],
            "empty_column_positions": [i + 1 for i, c in enumerate(columns) if not c],
            "duplicate_named_columns": [
                c for c, count in Counter(columns).items() if c and count > 1
            ],
            "metadata": metadata,
            "sample_rows": [],
            "row_count": None,
            "scan_mode": "full_table" if count_rows else "sample",
            "footer_detected": False,
        }
        rows = 0
        if count_rows or sample_rows:
            for row in reader:
                if not row or not any(cell.strip() for cell in row):
                    continue
                if source == "ibge" and row[0].lstrip().startswith("<"):
                    profile["footer_detected"] = True
                    break
                if len(row) != len(columns):
                    raise ValueError(
                        f"Linha física {reader.line_num}: {len(row)} campos; "
                        f"esperados {len(columns)}."
                    )
                rows += 1
                if len(profile["sample_rows"]) < sample_rows:
                    profile["sample_rows"].append(row)
                if not count_rows and rows >= sample_rows:
                    break
        if count_rows:
            profile["row_count"] = rows
        return profile


def inspect_paths(
    paths: list[Path],
    *,
    sample_rows: int = 3,
    count_rows: bool = False,
    source_filter: str = "all",
    inmet_state: str | None = None,
) -> dict:
    """Percorre arquivos e diretórios; ZIPs internos usam arquivo temporário."""
    result = {
        "format_version": 1,
        "options": {
            "sample_rows": sample_rows,
            "count_rows": count_rows,
            "source": source_filter,
            "inmet_state": inmet_state,
        },
        "files": [],
        "errors": [],
        "skipped_by_filter": 0,
        "notes": [
            "A amostragem não valida todos os registros nem a integridade completa de cada CSV.",
            "row_count nulo significa que a contagem completa não foi solicitada.",
            "O filtro de UF restringe arquivos de estações INMET; não filtra registros SINAN.",
            "No IBGE, a contagem se refere à tabela antes do rodapé HTML.",
        ],
    }

    def excluded(name: str, *, is_archive: bool = False) -> bool:
        hint = source_hint(name)
        if source_filter != "all" and hint and hint != source_filter:
            return True
        if hint == "inmet" and inmet_state and not is_archive:
            match = re.search(r"INMET_[^_]+_([A-Z]{2})_", name, flags=re.IGNORECASE)
            if match and match.group(1).upper() != inmet_state:
                return True
        return False

    def record_csv(stream: BinaryIO, label: str, size: int) -> None:
        try:
            profile = inspect_csv(
                stream, label, size, sample_rows=sample_rows,
                count_rows=count_rows, source_filter=source_filter,
            )
            if profile is None:
                result["skipped_by_filter"] += 1
            else:
                result["files"].append(profile)
        except (OSError, UnicodeError, csv.Error, ValueError, zipfile.BadZipFile) as exc:
            result["errors"].append({"path": label, "error": str(exc)})

    def visit_zip(archive: zipfile.ZipFile, prefix: str, depth: int) -> None:
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            if member.is_dir():
                continue
            suffix = Path(member.filename).suffix.lower()
            if suffix not in (".csv", ".zip"):
                continue
            label = f"{prefix}!{member.filename}"
            if excluded(member.filename, is_archive=suffix == ".zip"):
                result["skipped_by_filter"] += 1
                continue
            try:
                if suffix == ".zip":
                    if depth >= MAX_ZIP_DEPTH:
                        raise ValueError("Limite de profundidade de ZIPs atingido.")
                    # ZipFile requer acesso aleatório. Acima de 8 MiB, o spool
                    # vai para a pasta temporária e é removido ao fechar.
                    with archive.open(member) as source, tempfile.SpooledTemporaryFile(
                        max_size=ZIP_MEMORY_BYTES
                    ) as spool:
                        shutil.copyfileobj(source, spool, length=1024 * 1024)
                        spool.seek(0)
                        with zipfile.ZipFile(spool) as nested:
                            visit_zip(nested, label, depth + 1)
                else:
                    with archive.open(member) as stream:
                        record_csv(stream, label, member.file_size)
            except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
                result["errors"].append({"path": label, "error": str(exc)})

    candidates: set[Path] = set()
    for input_path in paths:
        path = input_path.resolve()
        if path.is_dir():
            candidates.update(
                p for p in path.rglob("*")
                if p.is_file() and p.suffix.lower() in (".csv", ".zip")
            )
        elif path.is_file() and path.suffix.lower() in (".csv", ".zip"):
            candidates.add(path)
        else:
            result["errors"].append(
                {"path": str(path), "error": "Caminho ausente ou formato diferente de CSV/ZIP."}
            )
    for path in sorted(candidates):
        if excluded(path.name, is_archive=path.suffix.lower() == ".zip"):
            result["skipped_by_filter"] += 1
            continue
        try:
            if path.suffix.lower() == ".zip":
                with zipfile.ZipFile(path) as archive:
                    visit_zip(archive, str(path), 1)
            else:
                with path.open("rb") as stream:
                    record_csv(stream, str(path), path.stat().st_size)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            result["errors"].append({"path": str(path), "error": str(exc)})
    result["inspected_csv_count"] = len(result["files"])
    result["source_counts"] = dict(Counter(item["source"] for item in result["files"]))
    return result


def nonnegative_integer(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("O valor deve ser maior ou igual a zero.")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="CSVs, ZIPs ou diretórios; padrão: data/raw.")
    parser.add_argument("--source", choices=("all", "sinan", "inmet", "ibge", "unknown"), default="all")
    parser.add_argument("--inmet-state", type=str.upper, help="UF das estações INMET, por exemplo ES. Não filtra o SINAN.")
    parser.add_argument("--sample-rows", type=nonnegative_integer, default=3)
    parser.add_argument("--count-rows", action="store_true", help="Conta toda a tabela em fluxo; pode demorar.")
    parser.add_argument("--output", type=Path, help="Grava o relatório JSON no caminho informado.")
    args = parser.parse_args(argv)
    if args.inmet_state and not re.fullmatch(r"[A-Z]{2}", args.inmet_state):
        parser.error("--inmet-state deve ter duas letras.")
    if args.output and args.output.suffix.lower() != ".json":
        parser.error("--output deve terminar em .json para preservar os CSVs e ZIPs.")
    paths = args.paths or [PROJECT_ROOT / "data" / "raw"]
    report = inspect_paths(
        paths, sample_rows=args.sample_rows, count_rows=args.count_rows,
        source_filter=args.source, inmet_state=args.inmet_state,
    )
    if not report["files"] and not report["errors"]:
        report["errors"].append(
            {"path": ", ".join(str(p) for p in paths), "error": "Nenhum CSV corresponde aos caminhos e filtros."}
        )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Erro ao gravar relatório: {exc}", file=sys.stderr)
            return 1
        print(f"Relatório: {args.output}")
        print(f"CSVs inspecionados: {report['inspected_csv_count']}; erros: {len(report['errors'])}.")
    else:
        print(payload)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
