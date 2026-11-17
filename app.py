"""Dashboard provisório: consulta a API e exibe o histórico agregado do ES."""

import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
COLUNAS_API = {
    "codigo_ibge": "codigo_municipio",
    "ano": "ano_epidemiologico",
    "semana_epidemiologica": "semana_num",
    "quantidade_casos": "registos",
    "nome_municipio": "nome_municipio",
}


@st.cache_data(ttl=60)
def carregar_dados() -> pd.DataFrame:
    """Consulta os agregados e adapta as colunas da API para o dashboard."""
    resposta = requests.get(f"{API_URL}/casos", timeout=30)
    resposta.raise_for_status()
    dados = pd.DataFrame(resposta.json())
    if dados.empty:
        raise ValueError("A API não retornou registros. Confira a carga do banco.")
    if not set(COLUNAS_API).issubset(dados.columns):
        raise ValueError("A resposta da API está sem colunas necessárias ao dashboard.")

    dados = dados.rename(columns=COLUNAS_API)
    dados["codigo_municipio"] = dados["codigo_municipio"].astype(str)
    dados = dados[dados["codigo_municipio"].str.fullmatch(r"32\d{4}")].copy()
    if dados.empty:
        raise ValueError("A API não retornou registros de municípios do Espírito Santo.")
    for coluna in ("semana_num", "ano_epidemiologico", "registos"):
        # Uma resposta inválida deve aparecer como erro, nunca como contagem zero.
        dados[coluna] = pd.to_numeric(dados[coluna], errors="raise").astype(int)
    return dados


def filtrar_dados(dados: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Aplica os filtros da barra lateral sem modificar os dados recebidos."""
    st.sidebar.header("Filtros de Análise")
    anos = sorted(dados["ano_epidemiologico"].unique())
    ano = st.sidebar.selectbox("Selecione o Ano", anos)
    filtrados = dados[dados["ano_epidemiologico"] == ano].copy()

    nomes = filtrados.drop_duplicates("codigo_municipio").set_index("codigo_municipio")["nome_municipio"]
    municipios = sorted(nomes.index, key=lambda codigo: nomes[codigo].casefold())
    todos = st.sidebar.checkbox("Selecionar todos os municípios", value=True)
    if not todos:
        selecionados = st.sidebar.multiselect(
            "Selecione o(s) Município(s)", municipios, default=municipios[:5],
            format_func=lambda codigo: f"{nomes[codigo]} ({codigo})",
        )
        filtrados = filtrados[filtrados["codigo_municipio"].isin(selecionados)]
    return filtrados, int(ano)


def exibir_dashboard(dados: pd.DataFrame, ano: int) -> None:
    """Mostra os indicadores, gráficos e a exportação do recorte selecionado."""
    st.subheader(f"Resumo Geral para o ano de {ano} (Espírito Santo)")
    total, municipios, periodo = st.columns(3)
    total.metric("Total de Registros", f'{int(dados["registos"].sum()):,}')
    municipios.metric("Municípios com Registros", int(dados["codigo_municipio"].nunique()))
    periodo.metric("Ano em Análise", str(ano))

    st.markdown("---")
    st.subheader("📈 Evolução Temporal (Por Semana Epidemiológica)")
    por_semana = dados.groupby("semana_num")["registos"].sum()
    st.line_chart(por_semana)

    st.markdown("---")
    st.subheader("🏆 Top 10 Municípios com Mais Registros")
    por_municipio = dados.groupby(["codigo_municipio", "nome_municipio"])["registos"].sum()
    maiores = por_municipio.sort_values(ascending=False).head(10).reset_index()
    st.bar_chart(maiores.set_index("nome_municipio")["registos"])

    st.markdown("---")
    st.subheader("📋 Dados Detalhados e Exportação")
    st.download_button(
        label="📥 Baixar dados filtrados (CSV)",
        data=dados.to_csv(index=False).encode("utf-8"),
        file_name=f"dengue_es_{ano}.csv",
        mime="text/csv",
    )
    with st.expander("Ver tabela completa de dados"):
        st.dataframe(dados, width="stretch")


def main() -> None:
    st.set_page_config(
        page_title="DenguePrev - Espírito Santo", page_icon="🦟", layout="wide",
    )
    st.title("🦟 DenguePrev: Histórico de Registros de Dengue no ES")
    st.markdown(
        "Plataforma analítica baseada nos dados do SINAN para o Espírito Santo (2020–2026)."
    )
    try:
        dados = carregar_dados()
    except (requests.RequestException, ValueError) as erro:
        st.error(f"❌ Não foi possível carregar os dados: {erro}")
        st.info("Confira se a API está rodando e se a rota /casos consegue consultar o banco.")
        st.stop()

    filtrados, ano = filtrar_dados(dados)
    exibir_dashboard(filtrados, ano)


if __name__ == "__main__":
    main()
