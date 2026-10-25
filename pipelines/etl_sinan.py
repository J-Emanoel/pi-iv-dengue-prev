import zipfile
import io
import json
import argparse
import gc
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

ANOS_PADRAO = [2020, 2021, 2022, 2023, 2024, 2025, 2026]

def localizar_zip_anual(nomes, ano):
    sufixo = str(ano)[-2:]
    for nome in nomes:
        if f"DENGBR{sufixo}" in nome.upper() and nome.endswith('.zip'):
            return nome
    return None

def escolher_csv_interno(zip_anual):
    for nome in zip_anual.namelist():
        if nome.lower().endswith('.csv'):
            return nome
    return zip_anual.namelist()[0]

def ler_e_filtrar_es_em_blocos(conteudo_csv):
    """Lê o CSV em blocos de 100k linhas, filtrando o ES instantaneamente para poupar RAM."""
    try:
        df_teste = pd.read_csv(io.BytesIO(conteudo_csv), sep=';', encoding='latin1', nrows=5)
        sep = ';' if len(df_teste.columns) > 1 else ','
    except Exception:
        sep = ';'

    chunks_es = []
    total_linhas_bruto = 0

    # Ler em blocos para evitar congelar o PC
    for chunk in pd.read_csv(
        io.BytesIO(conteudo_csv), 
        sep=sep, 
        encoding='latin1', 
        on_bad_lines='skip',
        engine='python',
        chunksize=100000
    ):
        total_linhas_bruto += len(chunk)
        chunk.columns = [str(c).strip().replace('\ufeff', '').replace('\r', '').replace('"', '') for c in chunk.columns]
        
        col_uf = next((c for c in chunk.columns if c.upper() in ['SG_UF_NOT', 'UF_NOT']), None)
        if col_uf:
            # Filtrar imediatamente o Espírito Santo (32) neste bloco
            df_es_chunk = chunk[chunk[col_uf].astype(str).str.contains('32', na=False)]
            if not df_es_chunk.empty:
                chunks_es.append(df_es_chunk)

    if chunks_es:
        df_es = pd.concat(chunks_es, ignore_index=True)
    else:
        df_es = pd.DataFrame()

    return df_es, total_linhas_bruto

def agregar_arquivo(df_es, ano, nome_interno, total_linhas_bruto):
    col_mun = None
    for cand in ['ID_MN_RESI', 'ID_MUNICIP', 'MUNICIPIO']:
        if cand in df_es.columns:
            col_mun = cand
            break
            
    col_sem = None
    for cand in ['SEM_PRI', 'SEM_NOT']:
        if cand in df_es.columns:
            col_sem = cand
            break

    resumo = {
        "ano_arquivo": ano,
        "arquivo": nome_interno,
        "status": "processado",
        "linhas_bruto": total_linhas_bruto,
        "linhas_es": len(df_es)
    }

    if df_es.empty or not col_mun or not col_sem:
        resumo["status"] = "erro_colunas_ou_vazio"
        return pd.DataFrame(), resumo

    df_es['codigo_municipio'] = pd.to_numeric(df_es[col_mun], errors='coerce')
    df_es['semana_epidemiologica'] = pd.to_numeric(df_es[col_sem], errors='coerce')
    df_es = df_es.dropna(subset=['codigo_municipio', 'semana_epidemiologica'])

    agrupado = df_es.groupby(['codigo_municipio', 'semana_epidemiologica'], as_index=False).size()
    agrupado.rename(columns={'size': 'registos'}, inplace=True)
    agrupado['ano_arquivo'] = ano
    agrupado['arquivo_origem'] = nome_interno

    return agrupado, resumo

def processar_pacote(zip_path: Path, anos: list, output_csv: Path, output_json: Path):
    print(f"A abrir o pacote principal de dados: {zip_path}")
    partes = []
    resumos = []

    with zipfile.ZipFile(zip_path, 'r') as pacote:
        nomes = pacote.namelist()

        for ano in anos:
            nome_interno = localizar_zip_anual(nomes, ano)
            if not nome_interno:
                print(f"AVISO: não encontrei o ZIP para o ano {ano}; a saltar.")
                resumos.append({"ano_arquivo": ano, "arquivo": None, "status": "ausente"})
                continue

            print(f"\nA processar blocos de {ano}: {nome_interno}")
            bytes_zip_anual = pacote.read(nome_interno)

            with zipfile.ZipFile(io.BytesIO(bytes_zip_anual), "r") as zip_anual:
                nome_csv = escolher_csv_interno(zip_anual)
                conteudo_csv = zip_anual.read(nome_csv)
                
                # Executar leitura em blocos e filtro imediato
                df_es, total_bruto = ler_e_filtrar_es_em_blocos(conteudo_csv)

            agrupado, resumo = agregar_arquivo(df_es, ano, nome_interno, total_bruto)
            resumo["csv_interno"] = nome_csv
            resumos.append(resumo)

            if not agrupado.empty:
                partes.append(agrupado)

            # Limpar memória agressivamente após cada ano
            del df_es, conteudo_csv, bytes_zip_anual
            gc.collect()

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    if partes:
        final = pd.concat(partes, ignore_index=True)
        final = final.sort_values(
            ["ano_arquivo", "codigo_municipio", "semana_epidemiologica"],
            kind="stable",
            na_position="last",
        )
        final.to_csv(output_csv, index=False, encoding="utf-8-sig")
        print(f"\n[SUCESSO] Consolidado guardado em: {output_csv}")
        print(f"Total de linhas agregadas: {len(final):,}")
    else:
        print("\nAVISO: não houve dados agregados.")

    documento = {
        "projeto": "DenguePrev",
        "etapa": "ETL inicial SINAN",
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "arquivo_entrada": str(zip_path),
        "arquivo_saida_csv": str(output_csv),
        "anos_solicitados": anos,
        "arquivos": resumos,
    }

    with output_json.open("w", encoding="utf-8") as f:
        json.dump(documento, f, ensure_ascii=False, indent=2)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="arquivos-proj-int-iv.zip")
    parser.add_argument("--years", nargs="+", type=int, default=ANOS_PADRAO)
    parser.add_argument("--output-csv", default="data/interim/sinan_es_municipio_semana.csv")
    parser.add_argument("--output-json", default="data/interim/sinan_es_resumo.json")
    return parser.parse_args()

def main():
    args = parse_args()
    processar_pacote(
        zip_path=Path(args.input),
        anos=args.years,
        output_csv=Path(args.output_csv),
        output_json=Path(args.output_json),
    )

if __name__ == "__main__":
    main()