import streamlit as st
import pandas as pd
from pathlib import Path

# Configuração da página
st.set_page_config(
    page_title="DenguePrev - Espírito Santo",
    page_icon="🦟",
    layout="wide"
)

st.title("🦟 DenguePrev: Monitorização de Casos de Dengue no ES")
st.markdown("Plataforma analítica baseada nos dados do SINAN para o Estado do Espírito Santo (2020–2026).")

# Função para carregar e filtrar rigorosamente os dados do ES
@st.cache_data
def carregar_dados():
    caminho = Path("data/interim/sinan_es_municipio_semana.csv")
    if not caminho.exists():
        caminho = Path("../data/interim/sinan_es_municipio_semana.csv")
    
    if not caminho.exists():
        raise FileNotFoundError("O ficheiro consolidado não foi encontrado.")
        
    df = pd.read_csv(caminho)
    
    # Garantir que filtramos estritamente os municípios do Espírito Santo (iniciados por 32)
    df['codigo_municipio'] = pd.to_numeric(df['codigo_municipio'], errors='coerce')
    df = df[df['codigo_municipio'].astype(str).str.startswith('32')].copy()
    
    # Tratamento seguro para extrair o número correto da semana (1 a 52)
    df['semana_epidemiologica'] = pd.to_numeric(df['semana_epidemiologica'], errors='coerce').fillna(0).astype(int)
    df['semana_num'] = df['semana_epidemiologica'].astype(str).str.zfill(6).str.slice(-2).astype(int)
    
    return df

# Carregamento com tratamento de erros visíveis no ecrã
try:
    df = carregar_dados()
except Exception as e:
    st.error(f"Erro ao carregar os dados: {e}")
    st.info("Certifica-te de que o ficheiro consolidado existe na pasta 'data/interim/'.")
    st.stop()

# --- BARRA LATERAL (FILTROS) ---
st.sidebar.header("Filtros de Análise")

anos_disponiveis = sorted(df['ano_arquivo'].unique())
ano_selecionado = st.sidebar.selectbox("Selecione o Ano", anos_disponiveis)

# Filtrar dados pelo ano escolhido
df_filtrado = df[df['ano_arquivo'] == ano_selecionado].copy()

# Filtro opcional por Município
municipios_disponiveis = sorted(df_filtrado['codigo_municipio'].unique())
todos_municipios = st.sidebar.checkbox("Selecionar todos os municípios", value=True)

if not todos_municipios:
    municipios_selecionados = st.sidebar.multiselect(
        "Selecione o(s) Município(s) (Código)", 
        municipios_disponiveis, 
        default=municipios_disponiveis[:5] if len(municipios_disponiveis) >= 5 else municipios_disponiveis
    )
    df_filtrado = df_filtrado[df_filtrado['codigo_municipio'].isin(municipios_selecionados)]

# --- MÉTRICAS PRINCIPAIS ---
st.subheader(f"Resumo Geral para o ano de {ano_selecionado} (Espírito Santo)")
col1, col2, col3 = st.columns(3)

total_registos = int(df_filtrado['registos'].sum())
municipios_afetados = int(df_filtrado['codigo_municipio'].nunique())

col1.metric("Total de Registos", f"{total_registos:,}")
col2.metric("Municípios com Registos", municipios_afetados)
col3.metric("Anos em Análise", str(ano_selecionado))

st.markdown("---")

# --- GRÁFICO TEMPORAL ---
st.subheader("📈 Evolução Temporal (Por Semana Epidemiológica)")

df_semana = df_filtrado.groupby('semana_num', as_index=False)['registos'].sum()
st.line_chart(df_semana.set_index('semana_num')['registos'])

st.markdown("---")

# --- TOP 10 MUNICÍPIOS ---
st.subheader("🏆 Top 10 Municípios com Mais Registos")
df_mun = df_filtrado.groupby('codigo_municipio', as_index=False)['registos'].sum()
df_mun = df_mun.sort_values(by='registos', ascending=False).head(10)
df_mun['codigo_municipio'] = df_mun['codigo_municipio'].astype(str)

st.bar_chart(df_mun.set_index('codigo_municipio')['registos'])

st.markdown("---")

# --- EXPORTAÇÃO E TABELA DE DADOS ---
st.subheader("📋 Dados Detalhados e Exportação")

# Botão para descarregar o CSV filtrado
csv_data = df_filtrado.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Descarregar dados filtrados (CSV)",
    data=csv_data,
    file_name=f"dengue_es_{ano_selecionado}.csv",
    mime="text/csv",
)

with st.expander("Ver tabela completa de dados"):
    st.dataframe(df_filtrado, use_container_width=True)