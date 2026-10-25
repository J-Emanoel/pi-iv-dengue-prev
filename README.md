# DenguePrev

Projeto Integrador IV: aplicação acadêmica para analisar dados históricos e estimar tendências de dengue nos municípios do Espírito Santo (2020–2026).

## Estado Atual (Entrega C2 - Protótipo & Viabilidade Técnica)

A fase de prototipagem e validação de viabilidade técnica para o Checkpoint C2 está concluída. O pipeline de dados do SINAN (Espírito Santo) foi integrado e a interface analítica interativa em Streamlit está totalmente funcional na raiz do projeto (`app.py`), acompanhada por uma suíte de testes automatizados validados via `pytest`.

### O que já foi implementado:

1. **Pipeline ETL & Filtro Estrito do ES**:
   * Processamento dos datasets epidemiológicos do SINAN em blocos (`chunksize`) para gestão eficiente de memória.
   * Filtragem rigorosa para manter apenas dados de municípios do Espírito Santo (códigos IBGE iniciados pelo prefixo `32`).
   * Normalização e extração segura da Semana Epidemiológica (1 a 52).

2. **Dashboard Interativo em Streamlit (`app.py`)**:
   * **Métricas Principais**: Indicadores gerais do ano selecionado (Total de Registros, Municípios Atingidos e Ano em Análise).
   * **Filtros Dinâmicos**: Seleção por Ano (2020–2026) e por Municípios do Espírito Santo.
   * **Evolução Temporal**: Gráfico de linha com o comportamento da curva epidêmica ao longo das semanas epidemiológicas.
   * **Top 10 Municípios**: Gráfico de barras com as cidades com maior número de notificações acumuladas.
   * **Tabela Detalhada & Download**: Tabela interativa expansível e botão de exportação dos dados filtrados para CSV.

3. **Testes Automatizados de Software (`tests/`)**:
   * **13 testes automatizados** (unitários e de integração) executados e 100% aprovados via `pytest` em 0,13s.
   * Validação de integridade de schemas, codificações de arquivo (UTF-8, CP1252), descompactação segura de arquivos ZIP e consistência dos códigos municipais do ES.

## Como Executar o Projeto

### Pré-requisitos

* Python 3.10 ou superior instalado.

### 1. Instalar Dependências

No terminal, dentro do diretório raiz do projeto, instale os pacotes necessários:

```bash
pip install -r requirements.txt
```

### 2. Executar o Dashboard (Streamlit)

Para rodar a interface interativa do DenguePrev:

```bash
streamlit run app.py
```

O Streamlit abrirá automaticamente no seu navegador no endereço `http://localhost:8501`.

### 3. Executar os Testes Automatizados

Para rodar a suíte completa de testes com o `pytest`:

```bash
python -m pytest
```

## Dados

Os arquivos são baixados previamente e processados localmente, sem consultas a APIs externas para obtenção das bases.

| Fonte | Arquivos recebidos | Período |
| --- | --- | --- |
| [SINAN](https://dadosabertos.saude.gov.br/dataset/arboviroses-dengue) | `DENGBR20.csv.zip` a `DENGBR26.csv.zip` | 2020–2026; 2026 parcial. |
| [INMET](https://portal.inmet.gov.br/dadoshistoricos) | `2020.zip` a `2025.zip`, com CSVs por estação | 2020–2025. |
| [IBGE](https://www.ibge.gov.br/cidades-e-estados/es.html) | `c5bc2083e93dda5c9cb358ff3d12fb9b.csv` | Censo 2022 e estimativa populacional. |

Esses arquivos estão preservados localmente em `data/raw/` e são ignorados pelo Git.

## Ferramenta de Inspeção de Datasets

O projeto conta com um script dedicado para auditoria e inspeção de CSVs e ZIPs locais sem necessidade de extração prévia:

```bash
python scripts/inspect_datasets.py --inmet-state ES --output data/interim/inspecao.json
```

Para consultar todas as opções da ferramenta:

```bash
python scripts/inspect_datasets.py --help
```

## Estrutura do Repositório

| Pasta / Arquivo | Finalidade |
| --- | --- |
| `app.py` | Dashboard interativo principal desenvolvido em Streamlit. |
| `backend/` | API, acesso ao banco de dados e regras da aplicação. |
| `frontend/` | Componentes da interface web. |
| `data/raw/` | Arquivos brutos originais locais. |
| `data/interim/` | Dados processados, relatórios e resultados intermediários. |
| `data/processed/` | Base consolidada validada. |
| `docs/` | Análises, inventário, contexto e registros de desenvolvimento. |
| `ml/` | Treinamento, avaliação e estimativas dos modelos preditivos. |
| `pipelines/` | Scripts de ingestão, limpeza e tratamento dos dados (ETL). |
| `scripts/` | Ferramentas auxiliares e inspeção dos arquivos. |
| `tests/` | Suíte de testes automatizados (`pytest` / `unittest`). |

## Checkpoints do Projeto (FAESA 2026/2)

| Checkpoint | Data | Entregas Previstas | Status |
| --- | --- | --- | --- |
| **C1** | 18/09/2026 | Escopo, justificativa, metodologia, comunidade e estrutura inicial. | **Concluído** |
| **C2** | 30/10/2026 | Protótipo funcional (Streamlit), ETL do SINAN-ES, suíte de testes (`pytest`) e vídeo no YouTube. | **Pronto para Entrega** |
| **C3** | 04/12/2026 | MVP publicado na nuvem (Render/Railway), componente de IA (Groq/LLM), documentação final e avaliação de impacto. | *Próxima Etapa* |

## Documentação Técnica

- [Análise das bases recebidas](docs/analise-bases.md)
- [Manifesto dos arquivos originais e checksums](docs/inventario-bases.json)
- [Contexto e sequência do projeto](docs/contexto-projeto.md)

## Aviso Legal

O DenguePrev é uma aplicação acadêmica desenvolvida no âmbito do Projeto Integrador IV da FAESA. Não constitui uma ferramenta epidemiológica oficial do Ministério da Saúde ou SESA-ES. Os dados e estimativas apresentados servem exclusivamente para fins de análise técnica e educacional.
