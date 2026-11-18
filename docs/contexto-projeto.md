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

As fontes iniciais são SINAN, INMET e IBGE. A avaliação posterior acrescentou
os microdados públicos SESA/e-SUS VS, adotados para o ML em 2020–2024 por semana
de notificação. O SINAN é preservado separadamente por primeiros sintomas.
As fontes são processadas localmente; a unidade principal é município, ano e semana epidemiológica.
O código IBGE é a chave municipal; nomes isolados não são uma chave suficiente.
Dados individuais de dengue serão agregados antes de alimentar a aplicação.

O indicador disponível é `registros_por_100_mil`, calculado como
`registros_notificados / populacao_anual * 100000`. Ele descreve os registros
da extração recebida, sem filtro por classificação. Não é apresentado como
incidência de casos confirmados. O alvo escolhido para o ML é o registro SESA
por semana de notificação. A conciliação da cobertura continua pendente e
limita a interpretação dos resultados à extração observada.

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
a população por município/ano, o clima INMET e a base analítica também foram
integrados e conferidos. A comparação de fontes foi executada e encontrou uma
série estadual adicional, adotada e carregada separadamente no Supabase.
A próxima etapa é preparar as variáveis temporais e avaliar os modelos,
respeitando os critérios de uso e limitações documentados.

- [x] C1 e C2 entregues.
- [x] SINAN consolidado, corrigido e validado no PostgreSQL compartilhado.
- [x] Cadastro IBGE com 78 nomes reais, correspondência de códigos e nomes na API/Streamlit.
- [x] População por município/ano com 546 referências documentadas no Supabase.
- [x] Indicador descritivo de registros da extração por 100 mil habitantes, com referência populacional anual.
- [ ] Validação da cobertura epidemiológica e das restrições de interpretação dos resultados.
- [x] ETL INMET e carga no Supabase: 13 estações e 3.873 registros semanais.
- [x] Associação geográfica anual: 468 vínculos com distância, método e referências.
- [ ] Avaliação da cobertura dos sensores e da representatividade dos vínculos.
- [x] Base analítica integrada no Supabase, calendário completo e consultas de indicadores/cobertura na API.
- [x] Comparação reproduzível SINAN/SESA pela mesma data e diagnóstico de continuidade/clima.
- [x] SESA por notificação em 2020–2024 adotada para o ML, importada com fonte/data/versões explícitas.
- [ ] Preparação dos exemplos temporais, previsão de referência e comparação de modelos.
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
- Visão `base_analitica_semanal` com 28.548 combinações e calendário de 366
  semanas; preserva contagens, lacunas e referências. Consultas em
  `/base-analitica` e `/cobertura`, com indicador por população anual.
- Série estadual separada em `notificacoes_sesa`: 13.290 agregados e 521.193
  registros. Visão `base_analitica_sesa` com 20.358 combinações em 2020–2024,
  consultável em `/base-sesa` e `/cobertura-sesa`, sem modificar a série SINAN.
- Streamlit consumindo a API e testes automatizados da inspeção, ETL, carga e API.
- Credenciais locais em `.env`, ignoradas pelo Git; exemplo fictício versionado.

### O que falta

| Etapa | Entrega | Condição para considerar concluída |
| --- | --- | --- |
| 1. Cadastro municipal — concluído | Nomes IBGE, correspondência de códigos e exibição na API/Streamlit. | 78 nomes reais, correspondência completa e contagens/IDs SINAN preservados no Supabase. |
| 2. População e indicador descritivo concluídos | Registros da extração por 100 mil habitantes; alvo do ML definido como notificações estaduais. | Referências anuais preservadas; limitações de cobertura explícitas na avaliação. |
| 3. Clima integrado; adequação pendente | ETL e vínculo geográfico implementados; falta definir critérios de uso dos sensores e das distâncias. | Cobertura verificável e limites de uso documentados antes do ML. |
| 4. Base analítica e backend — concluído | Calendário semanal e visão integrada no Supabase; consultas de indicadores e presença das fontes. | 28.548 chaves únicas, contagens preservadas e ausência diferenciada de zero; conferido no PostgreSQL. |
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
município, valores e referências. O indicador descritivo foi integrado na base
analítica; o alvo do ML foi definido como registros SESA por notificação.
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

**Base analítica e banco — integrada:** `calendario_epidemiologico` tem 366
semanas de 2020–2026. A visão `base_analitica_semanal` cruza esse calendário
com os 78 municípios e associa as fontes por suas chaves, gerando 28.548 linhas.
Preserva as 11.679 linhas SINAN e os 362.712 registros, sem multiplicação nas
junções. Há 16.869 combinações sem linha SINAN; elas permanecem nulas. Isso não
significa necessariamente zero notificações no município.

O numerador é `registros_notificados_sinan`, por residência e semana dos
primeiros sintomas, sem exclusão por classificação. `registros_por_100_mil`
usa a população daquele ano, com data de referência, tipo, fonte e observação.
Sem numerador ou população, o resultado permanece nulo. Zero explícito é
preservado. Não usa o campo legado de população nem interpreta a razão como
incidência de casos confirmados.

A visão mantém o vínculo geográfico anual, sua distância/método e as medidas
da estação com cobertura de cada sensor. Uma linha climática toda ausente e
a falta de linha climática são diferenciadas por `clima_presente` e contagens.
2026 permanece identificado como fonte SINAN parcial, sem vínculo/clima no
pacote atual. Nenhum ano tem cobertura epidemiológica ou representatividade
climática marcada como validada.

`/base-analitica` permite filtros e paginação; `/cobertura` resume presença das
fontes por município/ano. O padrão exploratório climático é 80% das 168 horas
em cada sensor, ajustável na consulta, sem valor normativo. Limiar zero ainda
exige pelo menos uma medição válida em cada variável. Os totais abaixo são de
**combinações de município/semana**, não de semanas distintas nem de casos reais:

| Ano | Combinações previstas | Com linha SINAN | Sem linha SINAN | Registros notificados | Com registros, população e sensores ≥ 80% |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2020 | 4.134 | 111 | 4.023 | 7.544 | 77 |
| 2021 | 4.056 | 1.612 | 2.444 | 15.535 | 894 |
| 2022 | 4.056 | 1.175 | 2.881 | 11.185 | 963 |
| 2023 | 4.056 | 2.919 | 1.137 | 136.925 | 2.844 |
| 2024 | 4.056 | 2.753 | 1.303 | 138.123 | 2.213 |
| 2025 | 4.134 | 1.715 | 2.419 | 34.075 | 1.404 |
| 2026, parcial | 4.056 | 1.394 | 2.662 | 19.325 | 0 |

Presença semanal não estima a proporção de casos capturados nem valida aptidão
para ML. O Ministério da Saúde ressalva que sua extração considera os dados
disponíveis no SINAN, enquanto o ES utiliza e-SUS VS desde 2020. A conciliação
continua necessária. [Notas da fonte nacional](https://dadosabertos.saude.gov.br/dataset/arboviroses-dengue).
[Fonte estadual e-SUS VS](https://dados.es.gov.br/dataset/doencas-e-agravos-de-notificacao).

A tabela de calendário é definida em `backend/models.py`; as junções e cálculos
da visão, em `backend/analitica.py`. O carregador existente prepara ambos com
`--analitica --aplicar`, em transação. Uma visão consulta as fontes em cada
acesso; não exige sincronização de uma cópia de seus resultados. A repetição
foi conferida no Supabase sem alterar as seis tabelas de origem ou duplicar
datas. A visão PostgreSQL usa `security_invoker` quando disponível.

Para mudanças futuras em estruturas existentes, versionar migrações específicas,
pois `create_all()` não altera tabelas. Não manter cópias manuais do esquema
completo. Mudanças em nomes ou tipos de colunas da visão também precisam de
migração; `CREATE OR REPLACE VIEW` não aceita qualquer alteração de estrutura.
[Documentação PostgreSQL](https://www.postgresql.org/docs/current/sql-createview.html).

### Comparação de fontes e proposta para o ML

A análise de 17/11/2026 localizou os microdados estaduais de dengue em uma
página adicional da SESA. Diferentemente do recurso mensal do catálogo,
esses arquivos incluem código do município do paciente, data de notificação
e classificação. A página oferece o pacote 2020–2022 e links para 2023 e 2024
no Google Drive; os campos de 2025 e 2026 estavam sem download. A indicação do
Drive pertence à própria página oficial. [Microdados SESA](https://app.wiki.saude.es.gov.br/pt-br/vigilanciasaude/sistema-de-informacao-e-dados/microdados).

`pipelines/avaliar_fontes.py` baixa/reutiliza versões fixadas por SHA-256,
trata o BOM UTF-8 com conteúdo CP1252 dos três arquivos e agrega por residência
e data de notificação. O município é mapeado pelo cadastro explícito, aceitando
códigos de seis/sete dígitos; não é inferido pelo nome. Os sete pacotes SINAN
foram relidos pela mesma data de notificação para permitir uma comparação
temporal coerente. O banco permanece com o critério anterior por primeiros
sintomas; as duas referências temporais não devem ser confundidas.

| Ano epidemiológico da notificação | Registros SINAN | Registros SESA | Combinações município/semana SINAN | Combinações município/semana SESA |
| --- | ---: | ---: | ---: | ---: |
| 2020 | 7.852 | 39.443 | 127 | 2.332 |
| 2021 | 15.293 | 15.620 | 1.584 | 1.602 |
| 2022 | 11.418 | 20.981 | 1.175 | 2.110 |
| 2023 | 136.241 | 190.339 | 2.887 | 3.580 |
| 2024 | 138.075 | 254.810 | 2.742 | 3.666 |

Os totais diferem dos agrupamentos anteriores por primeiros sintomas. Os totais
mensais do novo relatório também podem diferir destes, pois usam ano-calendário.
O CSV candidato estadual tem 13.290 agregados e 521.193 registros. Seus dados
e os originais permanecem em `data/`, fora do Git. Arquivos brutos de diferentes
fontes não foram somados nem ligados por identificadores de pessoas.

Essas diferenças não quantificam subnotificação, sobreposição ou cobertura real.
O diagnóstico continua marcado como não validado epidemiologicamente. Entre
os residentes ES, 29 linhas têm código sem correspondência e foram excluídas
da candidata, com contadores por arquivo. Há quatro ocorrências adicionais de
identificadores repetidos nos arquivos brutos; nenhuma linha foi removida por
essa razão. Não está estabelecido que o identificador isolado seja uma chave
única suficiente. Há datas fora do período, também contabilizadas. A série
estadual mantém classificações descartadas/indefinidas, portanto o alvo proposto
é registro notificado, não caso confirmado ou provável.

**Definição adotada após a análise:** usar a publicação estadual para uma
avaliação acadêmica retrospectiva de registros por semana de notificação,
armazenando sua origem separadamente e preservando o SINAN para referência.
O ML usará a fonte estadual, a referência de notificação e o período disponíveis:

- Treino: 2020–2022; validação: 2023; teste reservado: 2024.
- Alvo: número de registros notificados uma semana à frente, por município.
- Histórico: quatro semanas anteriores consecutivas; ausência continua nula.
- Clima: variáveis das semanas anteriores, com pelo menos 80% de horas válidas
  em cada sensor. O limiar é exploratório e não garante representatividade.
- Nunca usar clima observado da semana futura nem cortes aleatórios de datas.
- Não apresentar a avaliação como reconstrução do que estava disponível em
  tempo real: as extrações históricas contêm revisões e atrasos de registro.

O diagnóstico encontra 1.795 exemplos de treino, 2.774 de validação e 2.449 de
teste com as quatro semanas anteriores observadas e cobertura climática mínima
nessas semanas. A disponibilidade de clima no alvo futuro não participa da
seleção. Esses totais medem viabilidade técnica, não desempenho de modelo.
A seleção de alvos observados e sequências completas cria um recorte e pode
favorecer períodos/municípios com mais notificações; as métricas precisam
explicitar essa limitação. Nenhum modelo foi treinado nem publicado nesta etapa.

A série estadual foi carregada no Supabase em `notificacoes_sesa`, cuja
estrutura é definida em `backend/models.py`. A referência temporal é
`DATA_NOTIFICACAO`; cada linha registra URL oficial, hash do manifesto das três
fontes e hash do CSV agregado. O modo `--sesa` do carregador valida versões,
totais, códigos e chaves; usa transação e backup antes de revisões.

`base_analitica_sesa` integra essa série à população e ao clima por município,
ano e semana, abrangendo 261 semanas e 20.358 combinações. Preserva os 13.290
agregados e 521.193 registros; 7.068 combinações permanecem nulas. Não usa o
SINAN para completar lacunas. A estrutura da visão compartilha as regras de
junção e indicadores com a visão SINAN, preservando rótulos próprios de fonte
e de presença dos registros. A cobertura epidemiológica e a representatividade
climática seguem marcadas como não validadas.

A carga foi comparada integralmente com o CSV validado; todas as junções da
visão foram conferidas. A repetição não alterou linhas. As sete tabelas
anteriores, incluindo calendário, e a visão SINAN permaneceram iguais.
`/base-sesa` e `/cobertura-sesa` foram verificadas diretamente contra o
PostgreSQL. O Streamlit provisório permanece apresentando a série SINAN;
a apresentação da série adotada e das previsões será integrada posteriormente.

O agregado estadual tem modo de carga próprio e não é aceito no modo SINAN.
O relatório reproduzível fica em
`data/processed/avaliacao_fontes_resumo.json`; a comparação mensal e a candidata
semanal ficam ao lado dele.

**ML — próxima implementação:** preparar o alvo de registros notificados SESA
uma semana à frente e as quatro semanas anteriores, conforme os critérios
acima. Comparar uma
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

A prioridade atual é preparar os exemplos temporais e avaliar a previsão de
referência e os modelos sobre a série estadual adotada. A interpretação deve
respeitar lacunas, seleção de amostras e revisões históricas. Em seguida,
completar serviço de previsões, assistente, RAG, interface e publicação.
O progresso de cada entrega será conferido contra o checklist acima.

## Acompanhar a implementação

O estado atual, o papel dos arquivos e os comandos de execução ficam no
[README principal](../README.md). Este documento concentra o planejamento
e as decisões que orientam as próximas etapas.

Código, documentação e inventários são versionados. Datasets grandes,
artefatos de modelos, senhas e chaves ficam fora dos commits. O compartilhamento
dos originais será feito por Releases, conforme o README principal; Git LFS
não será usado inicialmente.
