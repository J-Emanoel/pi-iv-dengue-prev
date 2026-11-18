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
11.679 linhas agregadas, 362.712 registros e nenhuma chave municipal/semanal
duplicada. O índice único foi instalado e as consultas da API foram validadas
contra esse banco. Todos os agregados retornados coincidem com a fonte corrigida.
Os 78 municípios já possuem nomes do cadastro IBGE, exibidos pela API e pelo
Streamlit. A população foi integrada em `populacoes_municipais`, com 546
referências para os 78 municípios de 2020 a 2026. O clima INMET de 2020–2025
também já foi carregado: 13 estações, 3.873 registros semanais e 468 vínculos
município/ano por proximidade geográfica. As consultas foram conferidas contra
as fontes e repetir as cargas não alterou os dados.

A base integrada também está preparada no Supabase: a visão
`base_analitica_semanal` contém 28.548 combinações de município e semana em
2020–2026, sobre um calendário com 366 semanas. Mantém as 11.679 linhas SINAN
e os 362.712 registros; as demais semanas ficam ausentes, sem preencher com zero.
As seis tabelas de origem foram preservadas e as junções conferidas integralmente.

O indicador implementado é **registros notificados da extração por 100 mil
habitantes**, usando a população do respectivo ano. O alvo escolhido para o ML
é o registro estadual por semana de notificação; a avaliação de cobertura e
suas restrições de interpretação continuam documentadas como pendentes.
O vínculo geográfico é uma aproximação: não comprova que uma estação represente
o clima de todo o município. O pacote não contém clima de 2026.

A série SESA de 2020–2024 por semana de notificação foi adotada para o ML e já
está no Supabase, separada do SINAN: `notificacoes_sesa` contém 13.290 agregados
e 521.193 registros. A visão `base_analitica_sesa` tem 20.358 combinações de
município/semana; 7.068 ficam sem registro, preservadas como nulas. As fontes,
referências e limitações ficam explícitas. A carga foi comparada integralmente
com a saída validada, e sua repetição resultou em zero alterações.

O SINAN permanece como referência em suas tabelas, visão e rotas atuais.
O Streamlit provisório continua exibindo esse histórico SINAN. A série estadual
está disponível nas novas consultas `/base-sesa` e `/cobertura-sesa`.
A primeira avaliação de ML foi executada: 1.795 exemplos de treino, 2.774 de
validação e 2.449 de teste, com 40 variáveis. A persistência teve menor erro de
validação que os quatro candidatos de Random Forest/Gradient Boosting. No
teste de 2024, a estratégia selecionada teve MAE 20,45 e RMSE 51,40 registros
por município/semana do recorte. O [relatório de avaliação](docs/avaliacao-ml.md)
documenta os resultados, as limitações e a reprodução. Previsões ainda não
estão disponíveis pela API; esse é o próximo serviço a implementar.
As decisões ficam no [contexto do projeto](docs/contexto-projeto.md#comparação-de-fontes-e-proposta-para-o-ml).

A conexão real fica somente no `.env` local, ignorado pelo Git. O
`.env.example` contém valores fictícios; cada participante configura seu acesso
localmente. O backup anterior à correção permanece em `data/interim/backups/`,
também fora do versionamento.

O ETL corrigido e a carga foram validados localmente. No pacote atual, o resultado
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
| `app.py` | Dashboard provisório em Streamlit, que consulta a API. |
| `frontend/` | Pasta reservada para a futura interface React/Vite. |
| `ml/preparar_dados.py` | Congela a base SESA e cria lags, médias, sazonalidade e critérios de elegibilidade. |
| `ml/treinar.py` | Compara persistência, Random Forest e Gradient Boosting e grava avaliação/artefato. |
| `scripts/inspect_datasets.py` | Ferramenta auxiliar para inspecionar SINAN, INMET e IBGE. |
| `tests/` | Testes da inspeção, do ETL, da carga e da API. |
| `docs/` | Planejamento, análise inicial das fontes e inventário de arquivos. |

`pipelines/calendario.py` e `pipelines/arquivos.py` contêm funções compartilhadas
de calendário epidemiológico e hash de arquivos; não precisam ser executados
separadamente. `backend/__init__.py` identifica o pacote Python.

A pasta `data/` contém apenas arquivos locais gerados, incluindo backups, e é
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

## Testes e próximos passos

```powershell
.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

Os testes automatizados de banco usam SQLite local. A conexão, a carga e as
consultas da API também foram verificadas diretamente no PostgreSQL da equipe.

As bases SINAN e SESA estão integradas e conferidas no Supabase, com consultas
próprias e sem mistura de contagens. A série adotada para o ML é a estadual por
notificação em 2020–2024. A preparação e a primeira comparação temporal estão
concluídas. A próxima etapa é o serviço de previsões com modelo, versão,
origem e limitações explícitos. Depois seguem LLM com function calling e RAG.
A interface React/Vite, com ferramentas Node.js, fica para a etapa posterior.

- [Planejamento e decisões do projeto](docs/contexto-projeto.md).
- [Análise inicial das fontes e limitações](docs/analise-bases.md).
- [Inventário e hashes dos arquivos originais](docs/inventario-bases.json).
