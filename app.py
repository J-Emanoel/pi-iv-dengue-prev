import streamlit as st
import pandas as pd
import requests

# Configuração da página
st.set_page_config(
    page_title="DenguePrev - Espírito Santo",
    page_icon="🦟",
    layout="wide"
)

st.title("🦟 DenguePrev: Monitorização de Casos de Dengue no ES")
st.markdown("Plataforma analítica baseada nos dados do SINAN para o Estado do Espírito Santo (2020–2026).")

# Função para carregar os dados DIRETAMENTE DA TUA API
@st.cache_data
def carregar_dados():
    # 1. Faz o pedido à tua API local (que está ligada ao Supabase)
    resposta = requests.get("http://127.0.0.1:8000/casos")
    
    if resposta.status_code != 200:
        raise Exception(f"A API respondeu com o código de erro {resposta.status_code}. Certifica-te de que o Uvicorn está a correr.")
        
    # 2. Converte a resposta JSON num DataFrame do Pandas
    dados_json = resposta.json()
    if not dados_json:
        raise Exception("A tabela de casos no banco de dados está vazia.")
        
    df = pd.DataFrame(dados_json)
    
    # 3. Renomeia as colunas da base de dados para os nomes que o teu Dashboard usa
    df = df.rename(columns={
        'codigo_ibge': 'codigo_municipio',
        'ano': 'ano_arquivo',
        'semana_epidemiologica': 'semana_num',
        'quantidade_casos': 'registos'
    })
    
    # Garantir que filtramos estritamente os municípios do Espírito Santo (iniciados por 32)
    df['codigo_municipio'] = df['codigo_municipio'].astype(str)
    df = df[df['codigo_municipio'].str.startswith('32')].copy()
    
    # Tratamento seguro para numéricos
    df['semana_num'] = pd.to_numeric(df['semana_num'], errors='coerce').fillna(0).astype(int)
    df['ano_arquivo'] = pd.to_numeric(df['ano_arquivo'], errors='coerce').fillna(0).astype(int)
    df['registos'] = pd.to_numeric(df['registos'], errors='coerce').fillna(0).astype(int)
    
    return df

# Carregamento com tratamento de erros visíveis no ecrã
try:
    df = carregar_dados()
except Exception as e:
    st.error(f"❌ Erro detalhado ao carregar os dados: {e}")
    st.info("💡 Dica: Verifica se o terminal do FastAPI (Uvicorn) está a correr na porta 8000 e se a rota /casos está ativa.")
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
