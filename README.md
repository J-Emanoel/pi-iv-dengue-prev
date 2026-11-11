# 🦟 DenguePrev - Espírito Santo

Projeto Integrador IV: aplicação acadêmica para analisar dados históricos e estimar tendências de dengue nos municípios do Espírito Santo (2020–2026).

## Estado Atual (Rumo à Entrega C3 - Nuvem, API & IA)

O projeto evoluiu da fase de prototipagem local para uma arquitetura de microsserviços em nuvem. O pipeline de dados foi processado e migrado para um banco de dados relacional (PostgreSQL via Supabase). A comunicação entre a interface interativa (Streamlit) e os dados agora ocorre exclusivamente através de uma API RESTful construída em FastAPI.

### O que já foi implementado:

1. **Banco de Dados em Nuvem (Supabase / PostgreSQL)**:
   * Modelagem de tabelas (`Municípios` e `Casos de Dengue`) utilizando SQLAlchemy.
   * Migração de 11.622 registros históricos processados do SINAN (apenas ES) para a nuvem via script de povoamento (bulk insert).

2. **Backend / API (FastAPI)**:
   * Servidor Uvicorn rodando rotas RESTful integradas ao banco de dados.
   * Endpoints criados (`/municipios`, `/casos`) para servir os dados de forma rápida e escalável ao frontend.

3. **Dashboard Interativo em Streamlit (`app.py`)**:
   * O dashboard foi totalmente desacoplado dos arquivos CSV locais e agora consome os dados diretamente da API via biblioteca `requests`.
   * **Filtros Dinâmicos**: Seleção por Ano (2020–2026) e por Municípios do Espírito Santo.
   * **Visualizações**: Gráficos de evolução temporal por semana epidemiológica, top 10 municípios com mais notificações e métricas gerais consolidadas.

4. **Testes Automatizados de Software (`tests/`)**:
   * Suíte de testes automatizados validados via `pytest`, assegurando integridade de schemas, codificações de arquivos brutos e lógicas de filtragem.

## Como Executar o Projeto

### Pré-requisitos

- Python 3.10 ou superior.
- Conta no Supabase (com a `DATABASE_URL` configurada).

### 1. Instalar Dependências e Configurar o Banco

No terminal, instale os pacotes necessários:

```bash
pip install -r requirements.txt
