# Contexto e sequência do DenguePrev

Diretrizes recebidas em 25/10/2026 para o Projeto Integrador IV. O produto
será uma aplicação web acadêmica para explorar dados de dengue dos municípios
do Espírito Santo e apresentar tendências estimadas.

Situação atual do cronograma: C1 e C2 já foram entregues. O objetivo é a
entrega final completa e funcional no fim de novembro de 2026. A sequência
abaixo organiza o trabalho técnico restante até essa entrega.

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

Estações INMET são entidades próprias. O vínculo geográfico anual usa o
centroide oficial do município e a estação ES mais próxima entre as presentes
no pacote de cada ano. Distância, coordenadas e método ficam registrados.
Essa aproximação ainda exige avaliação de representatividade meteorológica;
não corresponde a uma medição direta do clima municipal.

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

## Checklist da entrega final

O desenvolvimento segue para a entrega final, conforme a orientação recebida.
O cadastro nominal IBGE foi implementado e aplicado no Supabase com backup;
a população por município/ano e o clima INMET também foram integrados e
conferidos. As próximas pendências são cobertura, indicadores e a base analítica.

- [x] C1 e C2 entregues.
- [x] SINAN consolidado, corrigido e validado no PostgreSQL compartilhado.
- [x] Cadastro IBGE com 78 nomes reais, correspondência de códigos e nomes na API/Streamlit.
- [x] População por município/ano com 546 referências documentadas no Supabase.
- [ ] Definição dos indicadores e validação da cobertura epidemiológica.
- [x] ETL INMET e carga no Supabase: 13 estações e 3.873 registros semanais.
- [x] Associação geográfica anual: 468 vínculos com distância, método e referências.
- [ ] Avaliação da cobertura dos sensores e da representatividade dos vínculos.
- [ ] Base analítica integrada e consultas de indicadores no backend.
- [ ] ML avaliado e previsões disponíveis pela API.
- [ ] LLM com function calling e RAG fundamentado em documentos.
- [ ] Interface React/Vite integrada e aplicação publicada e testada.

### O que já funciona

- ZIP original preservado, com inventário e hashes; dados grandes fora do Git.
- ETL SINAN por município de residência e ano/semana epidemiológica.
- PostgreSQL no Supabase com 78 municípios, 11.679 linhas agregadas e 362.712
  registros, conferidos contra a fonte corrigida; chave única sem duplicações.
- Carga com validação, backup, transação e repetição sem duplicar registros.
- API FastAPI com `/health`, `/municipios` e `/casos`, incluindo filtros.
- Cadastro IBGE com os 78 nomes oficiais; `/casos` inclui `nome_municipio`.
- Populações de 2020 a 2026 com origem, data de referência e tipo, consultáveis
  em `/populacoes`; casos, IDs e cadastro preservados após a carga.
- Clima de 2020–2025 em `/clima` e catálogo em `/estacoes`, com horas válidas,
  cobertura por sensor, fuso e origem; ausência diferenciada de zero.
- Vínculos municipais por ano em `/vinculos-estacoes`, usando centroides IBGE
  e metadados anuais INMET; adequação meteorológica ainda não validada.
- Streamlit consumindo a API e testes automatizados da inspeção, ETL, carga e API.
- Credenciais locais em `.env`, ignoradas pelo Git; exemplo fictício versionado.

### O que falta

| Etapa | Entrega | Condição para considerar concluída |
| --- | --- | --- |
| 1. Cadastro municipal — concluído | Nomes IBGE, correspondência de códigos e exibição na API/Streamlit. | 78 nomes reais, correspondência completa e contagens/IDs SINAN preservados no Supabase. |
| 2. População concluída; indicadores pendentes | Série populacional integrada; faltam definição do numerador e avaliação da cobertura. | Fontes e referências documentadas; indicador ainda precisa ser validado. |
| 3. Clima integrado; adequação pendente | ETL e vínculo geográfico implementados; falta definir critérios de uso dos sensores e das distâncias. | Cobertura verificável e limites de uso documentados antes do ML. |
| 4. Base analítica e backend | Integração semanal, migrações SQL e consultas de indicadores/clima. | Chaves únicas, junções sem multiplicar linhas e ausência diferenciada de zero. |
| 5. Machine Learning | Previsão de referência, comparação de modelos e serviço de previsões. | Avaliação temporal, métricas e limitações publicadas; modelo comparado à referência. |
| 6. LLM/function calling | Assistente consultando funções reais do backend. | Respostas conferidas contra resultados das funções, com parâmetros validados. |
| 7. RAG | Consulta a documentos oficiais com recuperação de trechos e referências. | Fontes rastreáveis e avaliação de respostas fundamentadas. |
| 8. Interface web e publicação | React/Vite em `frontend/`, integração e publicação dos serviços. | Fluxo completo testado no ambiente publicado, com configuração documentada. |

Cada etapa será implementada e verificada antes da seguinte. A etapa 2 define
o significado dos indicadores e as restrições de cobertura antes do treinamento.
O banco já está na nuvem; a publicação da API e da interface ainda faz parte
da entrega final. A interface definitiva permanece para depois da parte
funcional e dos recursos de IA, conforme solicitado.

### Cadastro municipal: implementação e critérios

**Objetivo:** substituir os rótulos `ES - código` por nomes reais e permitir
consultas e filtros legíveis, preservando os identificadores e os agregados.
Entrega concluída e conferida no Supabase. O procedimento implementado é:

1. Ler o CSV IBGE diretamente do ZIP existente, sem modificar os originais.
   Separar título, cabeçalho, 78 linhas municipais e notas finais. Decodificar
   entidades HTML e preservar acentos dos nomes.
2. Gerar uma correspondência explícita entre o código usado no SINAN/banco,
   de seis dígitos, e o código IBGE completo, de sete dígitos. Validar prefixo
   do ES, unicidade, nomes preenchidos e cobertura dos 78 códigos existentes.
   A correspondência não será feita por semelhança de nomes.
3. Gerar cadastro e resumo de validação em `data/processed/`, ignorados pelo
   Git, registrando os hashes da origem e da saída. A presença de códigos sem
   correspondência ou colisões deve interromper a carga.
4. Acrescentar a carga cadastral ao carregador existente, com conferência antes
   de aplicar. Atualizar somente `municipios.nome` nesta etapa, usando backup
   dos municípios e transação. Preservar os códigos atuais, as chaves estrangeiras,
   a população existente e todas as linhas de `casos_dengue`.
5. Manter `/municipios` e acrescentar `nome_municipio` à resposta de `/casos`
   por uma junção SQL, preservando os campos e filtros atuais. O nome permanece
   armazenado em `municipios`, sem cópia física em cada linha de casos.
6. Ajustar filtros, rótulos dos gráficos e exportação do Streamlit para mostrar
   os nomes. O código continua sendo a chave de filtro e agrupamento. Esta
   alteração não inclui redesenho visual nem criação do frontend React.
7. Validar localmente, aplicar no Supabase com backup, conferir o resultado
   e atualizar o README.

Os códigos completos do IBGE são compostos por sete dígitos; a correspondência
com os códigos de seis dígitos foi observada no pacote recebido e será validada
na carga. Não haverá troca das chaves atuais nesta primeira etapa.
[Referência do IBGE](https://www.ibge.gov.br/explica/codigos-dos-municipios.php).

**Arquivos da entrega:** `pipelines/etl_ibge.py` e seu teste em
`tests/test_etl_ibge.py`; alterações em `backend/povoar_banco.py`,
`backend/main.py`, `backend/schemas.py`, `app.py`, testes existentes e README.
O campo `nome` já existe; essa entrega não exige alterar o esquema SQL.

**Verificações de aceite:**

- 78 códigos distintos, com 78 nomes da fonte IBGE e nenhuma correspondência
  faltante ou ambígua.
- Permanência das 11.679 linhas e dos 362.712 registros da base atual;
  comparação por chave e quantidade, preservando também os IDs existentes.
- Backup dos municípios antes da atualização, rollback em falha e repetição
  da carga sem novas alterações quando a fonte for igual.
- API retornando os nomes junto dos campos atuais, com os filtros preservados.
- Streamlit exibindo nomes nos filtros, gráficos e exportação sem mudar o
  resultado das contagens.
- ZIP e credenciais preservados e ausentes do versionamento.

### Decisões e dependências das etapas seguintes

**Indicadores e cobertura:** a contagem atual inclui todas as classificações
da fonte. Definir se o alvo final representa registros notificados, casos
prováveis ou confirmados e avaliar a cobertura SINAN/e-SUS VS no ES. A igualdade
com o CSV comprova a carga, mas não resolve a representatividade da fonte.
Documentar o período utilizável, o caráter parcial de 2026 e as lacunas antes
de tratar ausência como zero ou iniciar a comparação de modelos.

**População — integrada:** o CSV recebido contém Censo 2022 e uma coluna
estimada de 2026 com nota de 2024. A conferência posterior mostrou que seus
78 valores estimados coincidem com a publicação oficial de 2026. Foram obtidas
as fontes oficiais específicas de cada ano, com versões e hashes fixados em
`pipelines/etl_populacao.py`. O Censo 2022 veio da exportação recebida.

`populacoes_municipais` tem chave município/ano, código completo, população,
data de referência, tipo, fonte, hash e observação. São 546 linhas para 78
municípios em 2020–2026. A estrutura é definida em `backend/models.py`, que
o SQLAlchemy usa para criar a tabela ausente. A carga é transacional, não altera
casos nem cadastro e não modifica linhas já iguais; revisões recebem backup.

2020, 2021 e 2024–2026 são estimativas com referência em julho. 2022 é censitário,
com referência em agosto de 2022. Para 2023 foi usada a relação oficial enviada
ao TCU baseada no Censo 2022 e malha 2023, identificada separadamente. Não é uma
estimativa independente de 2023. A quebra metodológica e as revisões precisam
ser consideradas nos indicadores e na avaliação temporal do ML.

O campo legado `municipios.populacao` permanece como estava; a série anual é
a fonte para os denominadores. O endpoint `/populacoes` permite consultar ano,
município, valores e referências. Os indicadores continuam pendentes.
[Estimativas municipais do IBGE](https://www.ibge.gov.br/estatisticas/sociais/populacao/9103-estimativas-de-populacao.html).
[Relação municipal publicada em 2023](https://agenciadenoticias.ibge.gov.br/agencia-sala-de-imprensa/2013-agencia-de-noticias/releases/37758-ibge-divulga-relacao-da-populacao-dos-municipios).

**Clima — integrado, com limitações:** `pipelines/etl_inmet.py` processou os
74 CSVs ES dos pacotes de 2020–2025: 648.840 horas de estação e 3.873 agregados.
Os horários originais permanecem em UTC; a semana epidemiológica é calculada
em `America/Sao_Paulo`. A chuva soma horas válidas; as médias usam medições
válidas, combinando os arquivos antes da agregação. Os três sensores têm
contagens de horas e cobertura sobre 168 horas, inclusive nas bordas parciais.
Ausência não é convertida em zero; não há imputação.

`pipelines/vincular_estacoes.py` usa os centroides oficiais da API de malhas
IBGE, fixados por hash, e os metadados INMET de cada ano. A menor distância
de Haversine entre as estações ES presentes no pacote anual define um vínculo
por município/ano. Há 13 estações candidatas em 2020–2022, 12 em 2023–2024 e
11 em 2025; são 468 vínculos, com distância máxima de 74,030 km. O método
não usa altitude ou barreiras do relevo e não prova representatividade
meteorológica. Não seleciona automaticamente outra estação pela cobertura dos
sensores. O vínculo é retrospectivo: antes de usá-lo no ML, verificar também
a disponibilidade da estação e das medições na data de cada previsão.

As tabelas `estacoes_inmet`, `clima_semanal` e `municipios_estacoes` estão no
Supabase, com consultas na API. A carga foi conferida integralmente contra as
fontes; a repetição não alterou linhas. Municípios, casos/IDs e populações
permaneceram iguais. As definições SQL continuam em `backend/models.py`.

Há 316 semanas sem chuva válida, 161 sem temperatura válida e 349 sem umidade
válida. Os valores nulos e as coberturas permitem definir critérios explícitos
de uso na base analítica. O pacote não contém clima de 2026: obter essa fonte
ou delimitar o período comum. Avaliar essas limitações antes do treinamento.
[Orientações do INMET](https://portal.inmet.gov.br/noticias/saiba-como-acessar-os-dados-meteorol%C3%B3gicos-dispon%C3%ADveis-no-site-do-inmet).
[API de malhas do IBGE](https://servicodados.ibge.gov.br/api/docs/malhas?versao=3).

**Base analítica e banco:** integrar calendário epidemiológico, contagens,
população anual, clima e indicadores de cobertura. Os modelos Python definem
as tabelas usadas pela aplicação. Para mudanças em estruturas existentes,
versionar migrações específicas, pois `create_all()` não atualiza tabelas
existentes. Não manter cópias manuais do esquema completo. Acrescentar endpoints conforme os dados e cálculos
ficarem disponíveis, com respostas e filtros validados.

**ML:** definir o alvo e o horizonte de uma ou duas semanas. Comparar uma
referência simples, como o último valor observado, com os modelos previstos no
planejamento. Separar treino e avaliação por datas, com cortes comuns aos
municípios; preparar variáveis e transformações sem usar dados futuros.
Registrar MAE/RMSE, período, versão dos dados e limitações. Publicar previsões
pela API somente depois dessa avaliação.

**LLM e RAG:** conectar o assistente aos serviços implementados para consultar
histórico, indicadores e previsões. Cálculos permanecem no backend; a LLM
explica resultados. Na etapa RAG, selecionar documentos oficiais, preparar a
recuperação e apresentar referências. Avaliar separadamente respostas de
consulta de dados e respostas fundamentadas em documentos.

**Interface e publicação:** criar a interface React/Vite com ferramentas
Node.js, consumindo a API Python. Integrar histórico, indicadores, previsões e
assistente, e depois validar a publicação da API e da interface com o banco
compartilhado. Credenciais e chaves dos provedores permanecem no backend.

### Continuidade até a entrega final

A prioridade atual é avaliar a cobertura, definir os indicadores e consolidar
a base semanal usando as fontes já integradas. As decisões metodológicas precedem
o treinamento. Em seguida, completar ML, assistente, RAG, interface e publicação.
O progresso de cada entrega será conferido contra o checklist acima.

## Acompanhar a implementação

O estado atual, o papel dos arquivos e os comandos de execução ficam no
[README principal](../README.md). Este documento concentra o planejamento
e as decisões que orientam as próximas etapas.

Código, documentação e inventários são versionados. Datasets grandes,
artefatos de modelos, senhas e chaves ficam fora dos commits. O compartilhamento
dos originais será feito por Releases, conforme o README principal; Git LFS
não será usado inicialmente.
