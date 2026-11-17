# Contexto e sequência do DenguePrev

Diretrizes recebidas em 25/10/2026 para o Projeto Integrador IV. O produto
será uma aplicação web acadêmica para explorar dados de dengue dos municípios
do Espírito Santo e apresentar tendências estimadas.

## Sequência de desenvolvimento

1. Estrutura do repositório.
2. Inspeção dos CSVs reais.
3. ETL.
4. Base consolidada.
5. PostgreSQL.
6. API.
7. Dashboard.
8. Machine Learning.
9. LLM com function calling.
10. RAG.

Essa é a ordem de implementação adotada. O dashboard começará pelo histórico
e pelos indicadores e receberá posteriormente os resultados preditivos.
O fluxo de execução do produto final poderá ser ETL, banco, resultados de ML,
API e interface.

## Dados

As fontes previstas são SINAN, INMET e IBGE, baixadas previamente e processadas
localmente. A unidade principal é município, ano e semana epidemiológica.
O código IBGE é a chave municipal; nomes isolados não são uma chave suficiente.
Dados individuais de dengue serão agregados antes de alimentar a aplicação.

A incidência será `(casos / populacao) * 100000`, respeitando a definição do
numerador e a referência do denominador. Ainda é necessário escolher entre
notificações, prováveis ou confirmados para definir `casos`.

Estações INMET são entidades próprias. O vínculo entre município e estação
será definido posteriormente com dados geográficos e critérios documentados.
Até essa definição, não atribuir clima aos municípios por suposição.

O período comum recebido é 2020–2025, com limitações documentadas na análise.
O SINAN de 2026 é parcial e não há INMET de 2026 no pacote. A divisão temporal
do ML será escolhida após a validação da base.

## Componentes previstos

O ETL utilizará Python, Pandas e NumPy; PostgreSQL armazenará os agregados.
A API será FastAPI, Pydantic e SQLAlchemy. A interface será React/Vite, com
dashboard como tela principal e assistente dentro dele.

O ML estimará tendências de curto prazo, inicialmente considerando uma ou
duas semanas. Modelos serão comparados com uma previsão de referência e
validação temporal, usando métricas como MAE e RMSE. As variáveis usarão
somente informações disponíveis até a data da previsão. A divisão de treino
e avaliação não será aleatória.

A LLM prevista é Llama via Groq. Ela consultará serviços do backend e
explicará resultados estruturados. Os cálculos e as previsões ficarão no
backend e no ML. O RAG será acrescentado para consultas fundamentadas em
documentos oficiais, separado da previsão.

Os resultados serão apresentados como estimativa do modelo, tendência
estimada ou nível de atenção estimado. A aplicação não oferece diagnóstico
nem alertas oficiais de saúde.

## Acompanhar a implementação

O estado atual, o papel dos arquivos e os comandos de execução ficam no
[README principal](../README.md). Este documento concentra o planejamento
e as decisões que orientam as próximas etapas.

Código, documentação e inventários são versionados. Datasets grandes,
artefatos de modelos, senhas e chaves ficam fora dos commits. O compartilhamento
dos originais será feito por Releases, conforme o README principal; Git LFS
não será usado inicialmente.
