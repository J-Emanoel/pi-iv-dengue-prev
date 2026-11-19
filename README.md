# DenguePrev — Espírito Santo

Projeto Integrador IV para analisar o histórico de dengue nos municípios do ES
e desenvolver estimativas de tendência de curto prazo.

## Onde paramos

C1 e C2 já foram entregues. O objetivo atual é concluir a aplicação completa
para a entrega final no fim de novembro de 2026. O checklist técnico fica no
[contexto do projeto](docs/contexto-projeto.md#checklist-da-entrega-final).

O fluxo atual é **ZIP original → ETL → CSV agregado → PostgreSQL → API → Streamlit**.

O acesso ao PostgreSQL compartilhado no Supabase foi configurado nesta máquina.
**A carga corrigida já foi aplicada e conferida no banco online**: 78 municípios,
11.844 linhas agregadas, 363.957 registros e nenhuma chave municipal/semanal
duplicada. O índice único foi instalado e as consultas da API foram validadas
contra esse banco. Todos os agregados retornados coincidem com a fonte corrigida.
Os 78 municípios já possuem nomes do cadastro IBGE, exibidos pela API e pelo
Streamlit. A população foi integrada em `populacoes_municipais`, com 546
referências para os 78 municípios de 2020 a 2026. O clima INMET de 2020–2026
também já foi carregado: 13 estações, 4.346 registros semanais e 546 vínculos
município/ano por proximidade geográfica. As consultas foram conferidas contra
as fontes e repetir as cargas não alterou os dados.

A base integrada também está preparada no Supabase: a visão
`base_analitica_semanal` contém 28.548 combinações de município e semana em
2020–2026, sobre um calendário com 366 semanas. Mantém as 11.844 linhas SINAN
e os 363.957 registros; as demais semanas ficam ausentes, sem preencher com zero.
As seis tabelas de origem foram preservadas e as junções conferidas integralmente.

O indicador implementado é **registros notificados da extração por 100 mil
habitantes**, usando a população do respectivo ano. Há experimentos separados
para SESA por notificação e SINAN por primeiros sintomas; a avaliação de cobertura e
suas restrições de interpretação continuam documentadas como pendentes.
O vínculo geográfico é uma aproximação: não comprova que uma estação represente
o clima de todo o município. A atualização recebida contém clima até 31/10/2026.

A série SESA de 2020–2024 por semana de notificação foi adotada para o ML e já
está no Supabase, separada do SINAN: `notificacoes_sesa` contém 13.290 agregados
e 521.193 registros. A visão `base_analitica_sesa` tem 20.358 combinações de
município/semana; 7.068 ficam sem registro, preservadas como nulas. As fontes,
referências e limitações ficam explícitas. A carga foi comparada integralmente
com a saída validada, e sua repetição resultou em zero alterações.

O SINAN tem tabelas, visão e rotas próprias, sem mistura com SESA.
O Streamlit provisório continua exibindo esse histórico SINAN. A série estadual
está disponível nas novas consultas `/base-sesa` e `/cobertura-sesa`.
A primeira avaliação de ML foi executada: 1.795 exemplos de treino, 2.774 de
validação e 2.449 de teste, com 40 variáveis. A persistência teve menor erro de
validação que os quatro candidatos de Random Forest/Gradient Boosting. No
teste de 2024, a estratégia selecionada teve MAE 20,45 e RMSE 51,40 registros
por município/semana do recorte. O [relatório de avaliação](docs/avaliacao-ml.md)
documenta os resultados, as limitações e a reprodução. O serviço de previsões
já está implementado em `/modelo` e `/previsoes`, usando o experimento local
congelado. A consulta padrão projeta somente a semana de 29/12/2024 a
04/01/2025, seguinte ao snapshot; não é uma previsão atual de 2026.
As decisões ficam no [contexto do projeto](docs/contexto-projeto.md#comparação-de-fontes-e-proposta-para-o-ml).

Em 18/11/2026, os ZIPs adicionais SINAN e INMET foram integrados ao Supabase
em transação única, com backups e conferência de preservação da SESA, cadastro,
população e SINAN de 2020–2025. A série SINAN 2026 contém 20.570 registros de
77 municípios, em 1.559 agregados. Rio Novo do Sul não aparece na extração;
isso não foi interpretado como zero. O clima de 2026 usa 11 estações do ES.

A avaliação própria SINAN usa treino em 2020–2023, validação em 2024 e teste
em 2025. A persistência foi selecionada; no teste, MAE 9,69 e RMSE 19,15 em
741 exemplos de 44 municípios. Esses erros não são diretamente comparáveis
aos do estudo SESA. `/modelo?fonte=sinan` identifica esse experimento, e
`/previsoes?fonte=sinan` estima 01–07/11/2026 com referência até 31/10/2026:
15 municípios têm dados suficientes e 63 recebem estimativa nula com motivos.
Não é uma previsão da semana atual nem um ganho demonstrado sobre a persistência.
Consulte a [avaliação da atualização](docs/avaliacao-sinan-2026.md).

A conexão real fica somente no `.env` local, ignorado pelo Git. O
`.env.example` contém valores fictícios; cada participante configura seu acesso
localmente. O backup anterior à correção permanece em `data/interim/backups/`,
também fora do versionamento.

O ETL corrigido e a carga foram validados localmente. No pacote original, o resultado
é **11.679 linhas agregadas e 362.712 registros**, por município de residência,
ano e semana epidemiológica calculados pela data dos primeiros sintomas.
Dos 363.020 registros de residentes do ES, 308 ficam fora do período
epidemiológico de 2020 a 2026. O resumo do ETL registra essas exclusões e
56 divergências de semana em relação à fonte.

As contagens incluem todas as classificações da fonte; ainda não representam
casos confirmados nem incidência. A cobertura do SINAN no ES exige validação.
Ausência de registro não foi convertida em zero.

## Como o código está organizado

| Local | Responsabilidade |
| --- | --- |
| `pipelines/etl_sinan.py` | Lê o ZIP em blocos e gera os agregados semanais. |
| `pipelines/etl_ibge.py` | Extrai os nomes e valida a correspondência dos códigos municipais. |
| `pipelines/etl_populacao.py` | Consolida referências populacionais por município/ano e registra a origem. |
| `pipelines/etl_inmet.py` | Lê as estações ES dos ZIPs anuais e agrega clima com cobertura por sensor. |
| `pipelines/vincular_estacoes.py` | Usa centroides IBGE para escolher a estação mais próxima em cada pacote anual. |
| `pipelines/avaliar_fontes.py` | Obtém e compara microdados SESA/SINAN por notificação e valida a série estadual para carga. |
| `backend/database.py` | Configura a conexão PostgreSQL a partir do ambiente. |
| `backend/models.py` | Define tabelas, colunas, relacionamentos e restrições SQL. |
| `backend/analitica.py` | Gera o calendário, define a visão integrada e calcula o diagnóstico de presença das fontes. |
| `backend/povoar_banco.py` | Confere a fonte e sincroniza os agregados com o banco. |
| `backend/main.py` | Disponibiliza as consultas pela API FastAPI. |
| `backend/schemas.py` | Define o formato JSON das respostas da API. |
| `backend/previsoes.py` | Confere o experimento salvo e serve estimativas com datas, elegibilidade e limitações. |
| `backend/ferramentas_ia.py` | Define consultas permitidas à LLM e valida argumentos, fontes, períodos e municípios. |
| `backend/assistente.py` | Conecta a LLM via Groq ao function calling, trata erros e contabiliza uso. |
| `backend/rag.py` | Busca trechos locais e confere fontes, páginas e versão da base documental. |
| `pipelines/preparar_rag.py` | Reproduz os trechos a partir dos PDFs oficiais com hashes fixados. |
| `docs/base-documental.json` | Base pequena de conhecimento e catálogo das fontes que acompanham o código. |
| `app.py` | Dashboard provisório em Streamlit, que consulta a API. |
| `frontend/` | Pasta reservada para a futura interface React/Vite. |
| `ml/preparar_dados.py` | Congela a fonte selecionada e cria lags, médias, sazonalidade e critérios de elegibilidade. |
| `ml/treinar.py` | Compara persistência, Random Forest e Gradient Boosting e grava avaliação/artefato. |
| `scripts/inspect_datasets.py` | Ferramenta auxiliar para inspecionar SINAN, INMET e IBGE. |
| `tests/` | Testes da inspeção, do ETL, da carga e da API. |
| `docs/` | Planejamento, análise inicial das fontes e inventário de arquivos. |

`pipelines/calendario.py` e `pipelines/arquivos.py` contêm funções compartilhadas
de calendário epidemiológico e hash de arquivos; não precisam ser executados
separadamente. `backend/__init__.py` identifica o pacote Python.

A pasta `data/` contém originais locais, derivados e backups, e é
criada conforme a execução. O ZIP, `data/`, `.env` e `.venv/` ficam fora dos
commits. Os CSVs/JSONs do fluxo antigo foram removidos; o agregado atual é o de
`data/processed/`. A pasta `frontend/` permanece reservada com `.gitkeep`.
`ml/` agora contém as rotinas de preparação e treinamento; seus dados e
artefatos gerados ficam ignorados pelo Git.

## Preparar o ambiente

Use Python 3.10 ou superior e execute os comandos PowerShell na raiz do projeto.
Reutilize a `.venv` se ela já existir.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` reúne as dependências da aplicação e dos testes, separadas
por comentários. Um único comando prepara o ambiente de desenvolvimento.

Crie `.env` a partir de `.env.example` **se ainda não houver um `.env`**.
Preencha `DATABASE_URL` com a conexão PostgreSQL do projeto. Para usar o banco
compartilhado, obtenha o acesso com o colega que criou o projeto Supabase.
A mesma configuração permite apontar para um PostgreSQL local.

Caracteres especiais da senha precisam ser codificados na URL.
Variáveis do ambiente têm prioridade; o `.env` da raiz precede o antigo
`backend/.env`, que continua aceito por compatibilidade.
`API_URL` configura o endereço usado pelo dashboard, com padrão
`http://127.0.0.1:8000`.

## Compartilhar os arquivos brutos

O ZIP original tem 956.346.013 bytes (aproximadamente 912 MiB) e permanece
preservado localmente. O local definido para distribuição é um anexo da release
[dados-originais-v1](https://github.com/J-Emanoel/pi-iv-dengue-prev/releases/tag/dados-originais-v1)
deste repositório. Para disponibilizar o download, a release precisa estar
publicada com o anexo; apenas concluir o upload no formulário não publica a release.

O GitHub bloqueia arquivos acima de 100 MiB em commits comuns. Em Releases,
cada anexo deve ter menos de 2 GiB; o pacote atual cabe nesse limite.
Veja as [regras de arquivos grandes](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
e os [limites de Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

Para disponibilizar o pacote:

1. Faça o commit e o push do código e da documentação que descrevem esta base.
2. No GitHub, abra **Releases → Draft a new release**.
3. Crie a tag `dados-originais-v1`, apontando para o commit enviado.
4. Anexe manualmente `arquivos-proj-int-iv.zip` e publique a release.

Cada participante clona o código normalmente, abre essa release e baixa o
anexo `arquivos-proj-int-iv.zip` para a raiz do projeto, sem descompactar.
Os arquivos automáticos **Source code (zip/tar.gz)** contêm o código; o pacote
de dados é o anexo enviado manualmente. O `git clone` não baixa esse anexo.

O ZIP fica fora dos pushes seguintes. Só é necessário baixá-lo novamente
quando houver outra versão dos dados. Preserve a versão anterior e crie outra
release para um novo pacote. Quem apenas consulta a API pode usar os agregados
no banco compartilhado; o ZIP é necessário para reproduzir a inspeção e o ETL.

O [inventário](docs/inventario-bases.json) registra nomes, tamanhos e hashes dos
originais. Após baixar, confira se recebeu exatamente o mesmo pacote:

```powershell
$hashEsperado = (Get-Content -Raw docs/inventario-bases.json | ConvertFrom-Json).input.sha256
(Get-FileHash arquivos-proj-int-iv.zip -Algorithm SHA256).Hash.ToLower() -eq $hashEsperado
```

O resultado deve ser `True`.

## Gerar e conferir os dados

Mantenha `arquivos-proj-int-iv.zip` na raiz, sem descompactar:

```powershell
.venv\Scripts\python.exe -B -m pipelines.etl_sinan
```

O ETL gera `data/processed/dengue_semanal.csv` e
`data/processed/dengue_semanal_resumo.json`. O resumo contém critérios, totais,
exclusões e hashes para conferir a origem. Se esse par já foi gerado pelo ETL
corrigido, não é necessário repetir o processamento.

Para gerar o cadastro nominal do IBGE a partir do mesmo ZIP:

```powershell
.venv\Scripts\python.exe -B -m pipelines.etl_ibge
```

O resultado fica em `data/processed/municipios_ibge.csv`, acompanhado de
`municipios_ibge_resumo.json`, com hashes da origem e da saída. O cadastro
relaciona os códigos de seis e sete dígitos e os nomes oficiais. Esta carga não
preenche população: a série histórica tem seu próprio ETL e tabela anual.

Para obter as publicações oficiais de população e gerar a série:

```powershell
.venv\Scripts\python.exe -B -m pipelines.etl_populacao --baixar
```

O comando reutiliza os arquivos de `data/raw/populacao/` quando seus hashes
conferem; não baixa tudo novamente. Sem `--baixar`, usa somente as cópias locais.
As saídas são `data/processed/populacao_municipal.csv` e seu resumo JSON.

A série mantém o ano de aplicação e a data de referência separados:

- 2020, 2021 e 2024–2026: estimativas oficiais com referência em julho do ano.
- 2022: população censitária da exportação IBGE recebida, referência em agosto de 2022.
- 2023: relação enviada ao TCU baseada no Censo 2022 e malha territorial 2023,
  identificada como `relacao_censitaria`, com referência em agosto de 2022.

Essas referências não formam uma série de estimativas com metodologia uniforme.
2023 não é apresentado como uma estimativa independente. O tipo, a fonte e o
hash acompanham cada registro. A coluna estimada de 2026 do CSV recebido foi
conferida: os 78 valores coincidem com a publicação oficial de 2026, enquanto
a nota do arquivo menciona 2024. O ETL usa a fonte anual oficial para essa série.

Para gerar o clima e os vínculos geográficos, depois do cadastro IBGE:

```powershell
.venv\Scripts\python.exe -B -m pipelines.etl_inmet
.venv\Scripts\python.exe -B -m pipelines.vincular_estacoes --baixar
```

O primeiro comando lê 74 CSVs das estações ES diretamente dos seis ZIPs INMET,
sem extrair o pacote inteiro. Gera `estacoes_inmet.csv`, `clima_semanal_inmet.csv`
e `clima_inmet_resumo.json` em `data/processed/`. O resumo registra metadados
anuais, hashes e contagens de medições ausentes e inválidas.

Os horários originais permanecem em UTC; a semana de domingo a sábado é
calculada em `America/Sao_Paulo`, para acompanhar as datas locais do SINAN.
Chuva é a soma das horas válidas; temperatura e umidade são médias das medições
válidas. Há contagens por sensor e cobertura em relação às 168 horas da semana,
inclusive nas semanas parciais das bordas do período. Ausência permanece nula;
chuva zero continua zero. Não há preenchimento automático de lacunas.
[Orientações do INMET sobre os dados](https://portal.inmet.gov.br/noticias/saiba-como-acessar-os-dados-meteorol%C3%B3gicos-dispon%C3%ADveis-no-site-do-inmet).

O segundo comando obtém os centroides oficiais dos 78 municípios pela API de
malhas do IBGE e guarda o snapshot em `data/raw/geografia/`. A versão dos pontos
é conferida por hash; execuções seguintes reutilizam o arquivo. Sem `--baixar`,
usa somente a cópia local. Gera `vinculos_municipios_estacoes.csv` e seu resumo.
Para cada município/ano, escolhe a menor distância ao centroide entre as estações
ES presentes naquele pacote anual, usando as coordenadas da estação naquele ano.
O cadastro de estações, por sua vez, mostra o último metadado disponível.
[API de malhas do IBGE](https://servicodados.ibge.gov.br/api/docs/malhas?versao=3).

São 468 associações em 2020–2025, com distância máxima de 74,030 km. Não são
escolhidas estações ausentes do pacote anual nem são considerados altitude e
relevo. A adequação meteorológica e os limites mínimos de cobertura serão
avaliados antes do ML. Entre as 3.873 semanas de estação, 316 não têm chuva
válida, 161 não têm temperatura válida e 349 não têm umidade válida.

Valide a fonte antes da carga. Este comando **não conecta nem altera o banco**:

```powershell
.venv\Scripts\python.exe -B -m backend.povoar_banco
```

Para conferir somente o cadastro nominal, use o mesmo comando com `--municipios`.
Para conferir a população anual, use `--populacao`; para o clima, `--clima`;
para as associações geográficas, `--vinculos`. Todos os modos de conferência
funcionam sem conexão ao banco até receberem `--aplicar`.

## Aplicar no banco

Com a conexão configurada e o banco de destino conferido:

```powershell
.venv\Scripts\python.exe -B -m backend.povoar_banco --aplicar
```

O script cria tabelas ausentes e sincroniza os anos cobertos pela fonte em uma
transação: corrige quantidades, remove cópias e linhas fora do agregado e insere
chaves faltantes. Não soma as cópias. Preserva os demais anos, o primeiro ID de
cada chave mantida e os nomes/populações já cadastrados. Em banco novo, os nomes
municipais ficam como códigos até a integração do IBGE.

Antes de corrigir ou excluir linhas existentes, grava os agregados em
`data/interim/backups/`. Falha no backup interrompe a operação; falha no banco
reverte a transação. Duplicados em anos fora da fonte interrompem a carga para
revisão. Um índice único impede novas cópias por município, ano e semana.
Repetir a mesma carga mantém os IDs e deve resultar em zero alterações de dados.

Para aplicar os nomes do IBGE, depois de gerar e conferir o cadastro:

```powershell
.venv\Scripts\python.exe -B -m backend.povoar_banco --municipios --aplicar
```

Essa operação atualiza somente os nomes, preserva códigos/populações e todos
os casos de dengue, e salva um backup dos municípios antes de modificá-los.

Para carregar a série populacional:

```powershell
.venv\Scripts\python.exe -B -m backend.povoar_banco --populacao --aplicar
```

O carregador cria `populacoes_municipais` quando necessário e sincroniza por
município/ano, preservando casos e cadastro. Na primeira carga insere 546 linhas;
repetir a mesma fonte mantém os dados. Revisões de linhas existentes recebem
backup antes da atualização. A definição das tabelas fica em `backend/models.py`;
o SQLAlchemy gera o DDL necessário ao criar tabelas ausentes. Alterações futuras
em tabelas existentes precisarão de migrações próprias; não mantemos uma cópia
manual do DDL que apenas repita os modelos.

O antigo campo `municipios.populacao` é mantido por compatibilidade e não deve
ser usado como denominador de todos os anos. Consulte a tabela anual e sua
`data_referencia`, `tipo` e `observacao`. A definição dos indicadores e a
avaliação de cobertura do SINAN continuam pendentes.

Para carregar as estações e o clima, seguidos dos vínculos municipais:

```powershell
.venv\Scripts\python.exe -B -m backend.povoar_banco --clima --aplicar
.venv\Scripts\python.exe -B -m backend.povoar_banco --vinculos --aplicar
```

São criadas as tabelas `estacoes_inmet`, `clima_semanal` e `municipios_estacoes`,
conforme os modelos Python. Os vínculos exigem municípios e estações previamente
cadastrados. Cada comando usa transação, validação de chaves e backup antes de
revisar dados existentes. Repetir a mesma fonte mantém as linhas; divergências
fora da fonte no período coberto interrompem a carga para revisão. Casos,
nomes e populações existentes são preservados. Esta carga já foi aplicada e
conferida no Supabase compartilhado; não é necessário repeti-la para usar a API.

Para preparar a base analítica após carregar as fontes:

```powershell
.venv\Scripts\python.exe -B -m backend.povoar_banco --analitica
.venv\Scripts\python.exe -B -m backend.povoar_banco --analitica --aplicar
```

O primeiro comando confere o calendário sem conectar. O segundo acrescenta
366 linhas em `calendario_epidemiologico` e cria a visão `base_analitica_semanal`
em uma transação. A tabela de calendário é definida em `backend/models.py`;
a consulta da visão fica em `backend/analitica.py`, e seu SQL é gerado pelo
SQLAlchemy. Não há outro arquivo manual reproduzindo essas definições.

A visão consulta as tabelas de origem a cada acesso, sem manter uma cópia física
dos resultados. Revisões nas fontes aparecem nela automaticamente. Repetir a
preparação não duplica o calendário nem modifica as fontes. Datas de calendário
divergentes ou perda/multiplicação das contagens interrompem a preparação.
No PostgreSQL 15 ou superior, usa `security_invoker` para respeitar as permissões
de quem consulta as tabelas. [Documentação de visões PostgreSQL](https://www.postgresql.org/docs/current/sql-createview.html).

A integração usa município, ano e semana epidemiológica; população e vínculo
são associados pelo respectivo ano. Cada linha mantém as referências
populacionais, estação, método/distância do vínculo e cobertura dos sensores.
`registros_notificados = null` indica ausência na extração; zero exige uma
linha com zero explicitamente gravada na origem. Sem registros ou denominador,
`registros_por_100_mil` permanece nulo. O campo legado `municipios.populacao`
não participa desse cálculo.

`cobertura_epidemiologica_validada` e `representatividade_climatica_validada`
permanecem falsos. 2026 é identificado como fonte SINAN parcial; seu calendário
completo permite visualizar lacunas, inclusive após os últimos registros do
pacote, sem apresentar essas semanas como observações completas.

Para uma consulta no SQL Editor do Supabase:

```sql
SELECT nome_municipio, ano, semana_epidemiologica,
       registros_notificados, registros_por_100_mil,
       precipitacao_mm, cobertura_precipitacao_pct
FROM public.base_analitica_semanal
WHERE codigo_ibge = '320530' AND ano = 2025
ORDER BY semana_epidemiologica;
```

Para conferir e carregar a série estadual, após executar a comparação de fontes:

```powershell
.venv\Scripts\python.exe -B -m backend.povoar_banco --sesa
.venv\Scripts\python.exe -B -m backend.povoar_banco --sesa --aplicar
.venv\Scripts\python.exe -B -m backend.povoar_banco --analitica-sesa --aplicar
```

O modo `--sesa` valida CSV, resumo, totais anuais, cadastro e versões dos três
arquivos públicos. Com `--aplicar`, sincroniza somente `notificacoes_sesa` em
transação, com backup antes de revisões. Cada agregado registra a referência
`DATA_NOTIFICACAO`, a URL oficial e os hashes do conjunto de fontes e do CSV.
Chaves antigas fora da fonte no período coberto interrompem a carga para revisão.

O modo `--analitica-sesa` prepara a visão estadual com 261 semanas em 2020–2024,
usando as mesmas regras de população e vínculo/clima anuais. Sem `--aplicar`,
somente confere o calendário. A estrutura física está em `backend/models.py`;
as duas visões são geradas em `backend/analitica.py`, com fonte explícita.
SINAN e SESA nunca são somados ou usados para preencher lacunas um do outro.

Essa carga e a visão estadual já foram aplicadas e conferidas no Supabase.
Para consultar a série adotada para o ML, use `public.base_analitica_sesa`,
por exemplo com o mesmo filtro municipal/ano do SQL anterior.

## Executar API e dashboard

API, em um terminal na raiz:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Consulte `http://127.0.0.1:8000/docs` para testar as rotas:

- `GET /health`: verifica a API, sem testar a conexão com o banco.
- `GET /municipios`: lista municípios cadastrados.
- `GET /casos`: consulta o histórico, com filtros opcionais `ano`,
  `codigo_municipio` e `semana`; inclui `nome_municipio` na resposta.
- `GET /populacoes`: referências populacionais e suas fontes, com filtros
  opcionais `ano` e `codigo_municipio`.
- `GET /estacoes`: catálogo INMET com coordenadas e último metadado disponível.
- `GET /clima`: observações semanais por estação e cobertura por sensor, com
  filtros opcionais `ano`, `codigo_estacao` e `semana`.
- `GET /vinculos-estacoes`: associação geográfica, distância, referências e
  limitações, com filtros opcionais `ano` e `codigo_municipio`.
- `GET /base-analitica`: calendário e fontes integradas, com filtros `ano`,
  `codigo_municipio` e `semana`. Retorna até 500 linhas por padrão; use `limite`
  (máximo 5.000) e `deslocamento` para paginar, na ordem de data e código municipal.
- `GET /cobertura`: diagnóstico por município/ano, com filtros `ano` e
  `codigo_municipio`. Informa semanas com/sem registros, presença de população,
  vínculo, clima e cobertura horária dos três sensores.
- `GET /base-sesa`: série estadual de 2020–2024 por notificação com população,
  clima e versões, usando os mesmos filtros e paginação de `/base-analitica`.
- `GET /cobertura-sesa`: diagnóstico da série estadual, com filtros `ano`,
  `codigo_municipio` e `cobertura_minima_clima_pct`.
- `GET /modelo`: estratégia selecionada, versão do experimento, fonte, período,
  métricas de validação/teste e limitações.
- `GET /previsoes`: estimativas de uma semana para os municípios, com filtros
  opcionais `data_inicio` (domingo do alvo) e `codigo_municipio`.
- `GET /assistente/status`: configuração local do Groq, sem exibir a chave nem testar acesso ao provedor.
- `POST /assistente`: pergunta em linguagem natural, fonte e histórico opcional; retorna explicação e consultas executadas.
- `GET /documentos`: fontes e versão da base documental local.
- `GET /documentos/busca?pergunta=...`: recupera até três trechos, sem chamar o Groq.

Exemplo: `/vinculos-estacoes?ano=2025&codigo_municipio=320530` retorna o vínculo
de Vitória à estação A612, a aproximadamente 1,248 km do centroide municipal.
`/clima?ano=2025&codigo_estacao=A612` consulta suas observações e coberturas.
Essas medidas são da estação, sem atribuição de medição municipal direta.

Exemplos integrados:

- `/base-analitica?ano=2025&codigo_municipio=320530`: 53 semanas de Vitória.
- `/cobertura?ano=2025&codigo_municipio=320530&cobertura_minima_clima_pct=80`:
  diagnóstico com pelo menos 80% das 168 horas válidas em cada sensor.
- `/base-sesa?ano=2024&codigo_municipio=320530`: as 52 semanas de Vitória
  na série estadual, com `fonte_serie=sesa_esus_vs` e referência explícita.

O limiar de clima é ajustável de 0 a 100 e tem padrão exploratório de 80%, sem
valor normativo ou seleção automática para ML. Mesmo com limiar zero, é exigida
ao menos uma medição válida por sensor. `presenca_semanas_sinan_pct` mede somente
semanas com alguma linha na extração, não a proporção dos casos reais capturados.
`semanas_com_fontes_e_cobertura` conta coincidências técnicas de registros,
população e sensores acima do limiar; não valida completude ou aptidão preditiva.

Dashboard, em outro terminal na raiz:

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

O dashboard consulta a API e renova o cache a cada 60 segundos.

## Comparar fontes antes do ML

Além do recurso mensal do catálogo estadual, a [página oficial de microdados
SESA](https://app.wiki.saude.es.gov.br/pt-br/vigilanciasaude/sistema-de-informacao-e-dados/microdados)
oferece arquivos individuais de dengue. Foram analisados os pacotes de
2020–2022, 2023 e 2024. As entradas de 2025 e 2026 não têm link nessa página
na versão consultada em 17/11/2026.

```powershell
.venv\Scripts\python.exe -B -m pipelines.avaliar_fontes --baixar
```

O comando reutiliza arquivos locais quando seus hashes conferem. Sem
`--baixar`, usa apenas os arquivos já presentes em `data/raw/sesa/`.
Requer também o cadastro, clima e vínculos gerados nas etapas anteriores.
As versões dos três arquivos estaduais estão fixadas por tamanho e SHA-256
no código. Uma alteração da publicação exige revisão da referência.

O processamento lê os sete pacotes SINAN recebidos e os três arquivos SESA,
compara residentes do ES com códigos conhecidos e usa **data de notificação
nas duas fontes**. A série atual do banco, por primeiros sintomas, permanece
como estava. Não somamos fontes nem estimamos uma taxa de cobertura a partir
de suas diferenças; universos, revisões e datas de extração também diferem.

Saídas locais, fora do Git:

- `data/processed/avaliacao_fontes_resumo.json`: versões, critérios, exclusões,
  presença semanal e diagnóstico de continuidade para o ML.
- `data/processed/comparacao_fontes_mensal.csv`: totais por mês de notificação.
- `data/processed/sesa_notificacoes_semanais_candidata.csv`: 13.290 agregados
  por município e semana de notificação, somando 521.193 registros em 2020–2024.

O resumo distingue ano-calendário dos meses e ano epidemiológico das semanas.
O agregado estadual não é aceito pelo carregador SINAN; tem modo próprio `--sesa`. O script de comparação não
conecta ao banco, não modifica fontes e não exporta identificadores individuais.
Mantém semanas ausentes e informa códigos inválidos e identificadores repetidos,
sem deduplicação automática.

A definição adotada para a série estadual é prever registros notificados uma semana à
frente, usando quatro semanas anteriores: treino em 2020–2022, validação em
2023 e teste em 2024. O diagnóstico exige continuidade sem inventar zeros e,
para os exemplos com clima, pelo menos 80% de horas válidas em cada variável
das quatro semanas anteriores. O clima da semana futura não seleciona esses
exemplos. O limiar é exploratório, e a seleção de semanas observadas precisa
ser documentada ao interpretar as métricas. A comparação de fontes não treina
modelos; o treinamento tem comandos próprios, descritos a seguir.

## Preparar e avaliar o ML

Os comandos sem `--fonte` mantêm o experimento SESA de 2020–2024.

```powershell
.venv\Scripts\python.exe -B -m ml.preparar_dados
.venv\Scripts\python.exe -B -m ml.treinar
```

O primeiro comando consulta a visão estadual em transação somente de leitura.
Gera `data/processed/ml/<dataset_id>/base_sesa.csv`, `exemplos.csv` e `resumo.json`.
O identificador inclui os hashes do snapshot, dos exemplos e do protocolo.
`data/processed/ml/atual.json` aponta para o dataset preparado mais recentemente.
Para repetir sem conexão, use `ml.preparar_dados --input CAMINHO/base_sesa.csv`.

O segundo comando confere os hashes, ajusta os candidatos em 2020–2022,
seleciona por MAE/RMSE de 2023 e reajusta o escolhido em 2020–2023 para o teste
final de 2024. Cada exemplo usa quatro semanas anteriores ao alvo, com lags
por município e calendário consecutivo. O clima da semana futura não entra.
População é metadado para normalização retrospectiva, fora das entradas do modelo.

Cada execução grava `modelo.joblib`, `avaliacao.json`, `previsoes_validacao.csv`
e `previsoes_teste.csv` em uma pasta própria sob `ml/models/`. O ponteiro
`ml/models/atual.json` identifica a execução mais recente. Dados e artefatos
permanecem fora do Git; o código, os testes e o relatório de avaliação são versionados.
Somente artefatos locais de origem conhecida devem ser carregados.

As bibliotecas usadas são Pandas, NumPy, Scikit-learn e Joblib, declaradas no
único `requirements.txt`. Nesta rodada, a estratégia selecionada foi a
persistência; ela repete a última contagem e não demonstrou antecipação de
mudanças. Os resultados dos modelos de árvores permanecem registrados na
avaliação. Consulte o [relatório completo](docs/avaliacao-ml.md) antes de interpretar
as métricas como desempenho em todos os municípios ou períodos.

## Atualização SINAN e INMET de 2026

A carga já foi aplicada no Supabase compartilhado. Para consultar e treinar
usando esse banco, não é necessário reaplicar os dados. Cada integrante gera
seus artefatos locais com:

```powershell
.venv\Scripts\python.exe -B -m ml.preparar_dados --fonte sinan
.venv\Scripts\python.exe -B -m ml.treinar --fonte sinan
```

SINAN mantém `DT_SIN_PRI`, conferido com `SEM_PRI`, e município de residência.
O protocolo seleciona em 2024 e avalia em 2025. Alvos de 2026 não entram no
treinamento nem na seleção. O snapshot termina na última semana SINAN observada,
mantendo as lacunas municipais. Dados ficam em `data/processed/ml/sinan/` e
modelos/avaliações em `ml/models/sinan/`, com ponteiros próprios. Para reprodução
offline, use `--input CAMINHO/base_sinan.csv --fonte sinan` na preparação.

Para reproduzir as fontes ou configurar outro banco, baixe os ZIPs das URLs de
[fontes-2026.json](docs/fontes-2026.json). Guarde-os sem extrair em
`data/raw/sinan/DENGBR26.csv.zip` e `data/raw/inmet/2026.zip`. Tamanho e SHA-256
precisam corresponder às versões conferidas. Uma publicação revisada exige
revisar esse inventário. O ZIP original continua intacto.

```powershell
.venv\Scripts\python.exe -B -m pipelines.etl_sinan
.venv\Scripts\python.exe -B -m pipelines.etl_sinan --input data/raw/sinan/DENGBR26.csv.zip --years 2026 --conferir-2026 --output-csv data/processed/atualizacao_2026/dengue_semanal.csv --output-json data/processed/atualizacao_2026/dengue_semanal_resumo.json
.venv\Scripts\python.exe -B -m pipelines.etl_inmet --atualizacao-2026 data/raw/inmet/2026.zip
.venv\Scripts\python.exe -B -m pipelines.vincular_estacoes
.venv\Scripts\python.exe -B -m backend.povoar_banco --atualizacao-2026
```

O primeiro comando gera somente SINAN 2020–2025 do pacote original, evitando
reaplicar a versão antiga de 2026. O segundo gera um CSV anual separado com a
versão nova. O INMET combina as horas antes de agregar: a semana 53 de 2025
atravessa os dois pacotes e é recalculada sem somar médias nem duplicar linhas.
A associação geográfica usa a mesma regra anual de proximidade. Não há imputação.

O último comando apenas confere, sem conectar. Para aplicar no banco configurado:

```powershell
.venv\Scripts\python.exe -B -m backend.povoar_banco --atualizacao-2026 --aplicar
```

Esse modo atualiza SINAN 2026, estações, clima e vínculos numa transação única.
Falha em qualquer componente reverte todos. Faz backup antes das revisões e
confere preservação do cadastro, população, SESA e demais anos SINAN. Repetir
a mesma carga não altera registros. Os hashes INMET/vínculos refletem o conjunto
de pacotes combinado; fora da borda 2025/53, os valores climáticos anteriores
foram preservados. Não há alteração de DDL.

## Consultar previsões

As rotas aceitam `fonte=sesa` (padrão, preservando consultas anteriores) ou
`fonte=sinan`. Para a versão integrada de 2026, use:

- `/modelo?fonte=sinan`: período, origem, estratégia, métricas e versão SINAN.
- `/previsoes?fonte=sinan`: próxima semana após o snapshot, 01–07/11/2026.
- `/previsoes?fonte=sinan&data_inicio=2026-10-25&codigo_municipio=320530`:
  simulação histórica SINAN para Vitória.

SINAN retorna contextos `backtest_2025`, `simulacao_2026` ou
`projecao_apos_snapshot`, com `fim_historico=2026-10-31`. As métricas genéricas
`validacao` e `teste` vêm com `ano_validacao=2024` e `ano_teste=2025`. Os campos
legados `validacao_2023` e `teste_2024` só têm valores no estudo SESA. Datas
posteriores à próxima semana disponível continuam recusadas com 422.
Os exemplos a seguir sem `fonte` pertencem ao estudo SESA original.

Depois de preparar e treinar o ML, inicie ou reinicie a API. Abra
`http://127.0.0.1:8000/docs` e teste:

- `/modelo`: mostra a estratégia efetiva e a avaliação que acompanha a estimativa.
- `/previsoes?data_inicio=2024-02-04&codigo_municipio=320530`: simulação de uma
  semana histórica para Vitória, com observado e previsto separados.
- `/previsoes`: projeta a semana imediatamente seguinte ao snapshot, de
  29/12/2024 a 04/01/2025, semana epidemiológica 1 de 2025. Essa projeção fica
  fora do teste de 2024 e não tem desempenho aferido.

O serviço permite os domingos de início das semanas epidemiológicas de 2024
e somente a semana seguinte ao snapshot. Recusa datas de treino, dias que não
sejam domingo e datas posteriores, inclusive semanas atuais de 2026, com HTTP
422. O campo `contexto` distingue `backtest_2024` e `projecao_apos_snapshot`.
`data_origem` é o sábado anterior ao alvo no protocolo simulado; não comprova
que todos os registros revisados estavam disponíveis naquela data.

Cada resposta inclui modelo, versão, dataset, fonte, referência temporal e
limitações. Por município, informa a última contagem, a estimativa, o observado
(quando existe) e o status. Sem as quatro semanas consecutivas de registros e
clima qualificado, retorna `dados_insuficientes`, motivos e previsão `null`.
Zero explícito continua zero. Não usa o clima nem a contagem do alvo como entrada.
Não calcula taxas futuras usando uma população anual presumida.

Na conferência desta execução, as 2.449 estimativas avaliáveis de 2024
coincidiram com o arquivo do teste salvo. A projeção seguinte tem 52 municípios
elegíveis e 26 sem dados suficientes; todos os 78 aparecem na resposta sem
filtro municipal. A persistência repete a última contagem, sem antecipar
crescimento; não produzimos um ranking de crescimento com essa estratégia.

A API lê `ml/models/atual.json` e abre o dataset identificado na avaliação
daquele modelo, conferindo hashes, protocolo e versões. Não usa automaticamente
outro snapshot preparado mais recentemente. Os artefatos são carregados apenas
no primeiro acesso às rotas de previsão e ficam fixos por processo; reinicie a
API depois de gerar outro experimento. Sem eles, essas rotas retornam HTTP 503
com orientação; `/health` e as consultas existentes continuam disponíveis.

O serviço não consulta nem grava o PostgreSQL para gerar essas respostas.
Cada integrante precisa reproduzir a preparação e o treinamento locais para
usar as previsões. Os dados e modelos gerados continuam fora dos commits.

## Assistente via Groq

O backend implementa function calling local: envia as definições das funções ao
Groq, recebe solicitações da LLM, valida os argumentos, executa consultas de
leitura e devolve os resultados ao modelo para explicação. A chave fica no
backend. A LLM não recebe conexão SQL nem executa comandos ou previsões próprias.

As funções disponíveis resolvem municípios, consultam histórico, comparam cidades,
identificam o modelo, consultam previsões e buscam documentos oficiais. A comparação usa semanas observadas
em comum e calcula totais/diferenças no backend, sem preencher lacunas com zero.
As fontes permanecem separadas. O assistente usa SINAN por padrão; o campo
`fonte` da solicitação permite selecionar SESA e cada consulta registra a fonte
efetiva. As rotas anteriores de previsão mantêm seu padrão SESA.

**Estado atual:** fluxo e ferramentas implementados, com testes simulados e
primeiras respostas reais pelo GPT-OSS 120B no Groq. Estratégia/data do modelo,
previsão de Vitória e comparação Vitória/Vila Velha foram conferidas contra
os resultados do backend. Resultados, falhas e limites da avaliação ficam em
[avaliacao-assistente.md](docs/avaliacao-assistente.md).

Para configurar:

1. Crie ou acesse sua conta no [console Groq](https://console.groq.com/).
2. Confira no Playground o modelo e os limites disponíveis na conta. A configuração
   adotada é `openai/gpt-oss-120b`, servido pelo Groq e com function calling.
3. Crie a chave em [API Keys](https://console.groq.com/keys).
4. Preencha somente o `.env` local e reinicie a API:

```dotenv
GROQ_API_KEY=SUA_CHAVE_GROQ
GROQ_MODEL=openai/gpt-oss-120b
```

O modelo precisa estar habilitado na conta. A chave não deve ser enviada pelo
chat nem copiada para `.env.example`. A configuração desta máquina foi atualizada
preservando a chave e a conexão do banco; outros participantes usam suas próprias chaves.

O planejamento original citava Llama. A documentação atual do Groq informa a
[retirada de Llama 3.1/3.3 dos planos Free e Developer em 16/08/2026](https://console.groq.com/docs/deprecations).
GPT-OSS mantém o provedor Groq e o fluxo de function calling descrito no material
de apoio do professor; a mudança é na família do modelo de linguagem. Não há
fallback automático. O código também admite GPT-OSS 20B e os dois IDs Llama
legados, caso exista acesso Enterprise; os parâmetros específicos de reasoning
são enviados apenas para GPT-OSS.

Abra `/assistente/status`: `configuracao_local_completa` indica somente que os
campos estão preenchidos no formato esperado. Não verifica chave válida, saldo,
permissão, disponibilidade ou qualidade das respostas. Sem configuração,
`POST /assistente` retorna 503 e as consultas existentes continuam funcionando.

Em `http://127.0.0.1:8000/docs`, teste `POST /assistente` com:

```json
{
  "pergunta": "Qual a estratégia do modelo SINAN e até quando vão os dados?",
  "fonte": "sinan"
}
```

A resposta contém `resposta`, `provedor`, `modelo_llm`, `consultas`, `uso` e
`referencias` (vazio quando não há citação documental). Cada consulta
registra nome da ferramenta, argumentos, sucesso e resultado agregado. Isso
permite conferir o texto contra os dados efetivamente retornados. Não garante
automaticamente que toda frase da LLM seja correta; os casos de avaliação estão
em [avaliacao-assistente.md](docs/avaliacao-assistente.md).

O histórico opcional aceita até oito mensagens `user`/`assistant`. O módulo não
armazena conversas no banco. Pergunta, histórico enviado e agregados necessários
compõem as requisições ao Groq; a chave aparece somente na autenticação HTTP.
Dados individuais das fontes, senhas do banco e arquivos locais não entram nas
ferramentas. O ciclo tem limites de rodadas/chamadas e trata falta de acesso,
limite de uso, timeout e respostas incompletas sem repassar o erro bruto do provedor.

A resposta inclui `uso`: tentativas HTTP (`chamadas_api`), quantidade de respostas
com contagem informada (`respostas_com_uso`) e tokens de entrada, saída e total.
As contagens somam somente o uso informado pelo provedor; sem esse dado, tokens
ficam nulos. Erros podem consumir recursos não informados nesse resumo, portanto
o painel Usage do Groq continua sendo a referência para o consumo da conta.
Essa etapa não persiste prompts nem métricas de uso no banco.

Erros 429 e falhas HTTP transitórias admitem uma nova tentativa por rodada,
respeitando `retry-after` numérico de até cinco segundos. Esperas maiores são
devolvidas como erro controlado, sem repetir antes do prazo. O cliente limita
cada resposta a 2.048 tokens; no GPT-OSS solicita reasoning baixo e não retorna
o raciocínio interno. A disponibilidade e os limites do plano devem ser
conferidos no [console Groq](https://console.groq.com/settings/limits).

Uma falha `tool_use_failed` também admite uma única nova geração, dentro das
mesmas duas tentativas HTTP por rodada. O cliente repete os nomes permitidos
e pode exigir o nome canônico da comparação quando o modelo usa a variação
`compare_municipios`. Não executa nem repassa os argumentos da geração recusada:
a nova resposta ainda passa pelo catálogo e pela validação Pydantic.
O ciclo aceita até cinco rodadas e seis funções por conversa.

Sem consulta válida, o backend só aceita motivos enumerados para recusa ou
esclarecimento e devolve mensagens fixas; texto livre com números continua
bloqueado. Se o GPT-OSS falhar antes de consultar dados, a segunda tentativa
pode usar [JSON Schema estrito](https://console.groq.com/docs/structured-outputs),
sem ferramentas e com no máximo 256 tokens, apenas para classificar o pedido.
A classificação `consulta_necessaria` continua sendo erro de dados não obtidos,
sem autorizar uma resposta factual. A primeira rodada permite escolher entre
consultar funções e responder por esse protocolo de recusa.

O cliente usa HTTPX, já presente nas dependências, conforme o [protocolo oficial
de tool calling](https://console.groq.com/docs/tool-use/local-tool-calling).
A recuperação documental está descrita abaixo. A interface definitiva ainda está pendente.
Antes de publicar a rota, será necessário definir controle de acesso e limites
de uso do provedor; nesta etapa o uso é local.

## RAG com documentos oficiais

O assistente usa `consultar_documentos` para perguntas conceituais e preventivas
e devolve referências como `[R009]`. O backend fornece título, ano/edição, trecho,
hash do documento e link para a página exata. Estatísticas e estimativas municipais
continuam sendo consultadas pelas funções de dados e de ML.

A base inicial tem **18 trechos de dois documentos do Ministério da Saúde**:

- [Diretrizes de vigilância entomológica e controle vetorial, 2025](https://bvsms.saude.gov.br/bvs/publicacoes/diretrizes_nacionais_arboviroses_urbanas.pdf).
- [Guia de Vigilância em Saúde, volume 2, 6ª edição revisada, 2024](https://bvsms.saude.gov.br/bvs/publicacoes/guia_vigilancia_saude_v2_6edrev.pdf).

Foram selecionadas partes sobre controle mecânico, participação da população,
vetores e conceitos de vigilância. A edição dos documentos permanece explícita;
os trechos não constituem um boletim atual nem um serviço de diagnóstico,
prescrição ou atualização de normas e calendários de vacinação.

`docs/base-documental.json` tem aproximadamente 20 KB e é versionado: os integrantes
recebem os textos necessários ao clonar o repositório. Os PDFs completos ficam
em `data/raw/rag/`, ignorados pelo Git. O catálogo fixa URL, tamanho, SHA-256,
páginas e marcadores de extração, permitindo reproduzir a base.

Os trechos são disponibilizados sob **CC BY-NC-SA 4.0**, conforme as licenças das
obras originais, com atribuição ao Ministério da Saúde. Essa indicação refere-se
ao conteúdo documental; não altera a licença do código do projeto.

Com a API em execução, abra `http://127.0.0.1:8000/docs` e teste primeiro
`GET /documentos` e `GET /documentos/busca`. Essas rotas funcionam localmente,
sem credencial Groq ou conexão ao banco. Depois, em `POST /assistente`, use:

```json
{
  "pergunta": "O que é controle mecânico contra o Aedes? Cite os documentos oficiais.",
  "fonte": "sinan"
}
```

A busca usa TF-IDF de palavras/bigramas e de caracteres, com scikit-learn,
cache em memória e limite de três trechos, priorizando páginas diferentes.
A função da LLM tem limite padrão de dois trechos. A recuperação não consome
tokens; somente as chamadas de geração ao Groq usam a cota da conta.
Não há download de PDFs durante uma pergunta nem chamadas de embeddings externos.

Citações ausentes, IDs não recuperados e links fora das fontes retornadas são
bloqueados. Uma única correção de referências pode ser solicitada com os mesmos
trechos, sem repetir a busca. Sem evidência suficiente, a resposta é uma mensagem
fixa. Esses controles validam a origem das referências; a fidelidade de cada frase
aos trechos ainda precisa ser avaliada. A busca é lexical e pode falhar com sinônimos
ou formulações pouco próximas do texto, como registrado na avaliação.

Para reproduzir ou conferir os trechos a partir dos PDFs:

```powershell
# Baixa apenas PDFs ausentes, verifica os hashes e recompõe a base pequena.
.venv\Scripts\python.exe -B -m pipelines.preparar_rag --baixar

# Com os PDFs já presentes, confere sem modificar a base versionada.
.venv\Scripts\python.exe -B -m pipelines.preparar_rag --conferir
```

Essa preparação usa `pypdf`, incluído no requirements. Um arquivo remoto com hash
diferente é recusado; atualizar a fonte exige revisar o catálogo e os recortes.
Após alterar a base, reinicie a API para recarregar o cache.

## Testes e próximos passos

```powershell
.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

Os testes automatizados de banco usam SQLite local. A conexão, a carga e as
consultas da API também foram verificadas diretamente no PostgreSQL da equipe.

As bases SINAN e SESA estão integradas e conferidas no Supabase, com consultas
próprias e sem mistura de contagens. A integração de 2026 e a avaliação própria
SINAN foram concluídas, mantendo a avaliação SESA de 2020–2024 e o serviço
anterior. As previsões têm modelo, versão, origem e limitações explícitos.
O fluxo de function calling, a inferência GPT-OSS e o RAG inicial já funcionam,
com respostas reais conferidas, referências verificáveis e limitações registradas.
A avaliação continuará nas próximas integrações.
A interface React/Vite, com ferramentas Node.js, fica para a etapa posterior.

- [Planejamento e decisões do projeto](docs/contexto-projeto.md).
- [Análise inicial das fontes e limitações](docs/analise-bases.md).
- [Inventário e hashes dos arquivos originais](docs/inventario-bases.json).
- [Compatibilidade e avaliação SINAN 2026](docs/avaliacao-sinan-2026.md).
