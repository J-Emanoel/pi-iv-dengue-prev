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
referências para os 78 municípios de 2020 a 2026. O clima e os indicadores
ainda precisam ser integrados e validados.

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
| `backend/database.py` | Configura a conexão PostgreSQL a partir do ambiente. |
| `backend/models.py` | Define tabelas, colunas, relacionamentos e restrições SQL. |
| `backend/povoar_banco.py` | Confere a fonte e sincroniza os agregados com o banco. |
| `backend/main.py` | Disponibiliza as consultas pela API FastAPI. |
| `backend/schemas.py` | Define o formato JSON das respostas da API. |
| `app.py` | Dashboard provisório em Streamlit, que consulta a API. |
| `frontend/` | Pasta reservada para a futura interface React/Vite. |
| `ml/` | Pasta reservada para modelos e rotinas de machine learning. |
| `scripts/inspect_datasets.py` | Ferramenta auxiliar para inspecionar SINAN, INMET e IBGE. |
| `tests/` | Testes da inspeção, do ETL, da carga e da API. |
| `docs/` | Planejamento, análise inicial das fontes e inventário de arquivos. |

`pipelines/calendario.py` e `pipelines/arquivos.py` contêm funções compartilhadas
de calendário epidemiológico e hash de arquivos; não precisam ser executados
separadamente. `backend/__init__.py` identifica o pacote Python.

A pasta `data/` contém apenas arquivos locais gerados, incluindo backups, e é
criada conforme a execução. O ZIP, `data/`, `.env` e `.venv/` ficam fora dos
commits. Os CSVs/JSONs do fluxo antigo foram removidos; o agregado atual é o de
`data/processed/`. As pastas `frontend/` e `ml/` permanecem reservadas com um
arquivo `.gitkeep`, pois o Git registra arquivos e não mantém pastas vazias.

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

Valide a fonte antes da carga. Este comando **não conecta nem altera o banco**:

```powershell
.venv\Scripts\python.exe -B -m backend.povoar_banco
```

Para conferir somente o cadastro nominal, use o mesmo comando com `--municipios`.
Para conferir a população anual, use `--populacao`. Esses dois modos de
conferência também não conectam ao banco até receberem `--aplicar`.

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

Dashboard, em outro terminal na raiz:

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

O dashboard consulta a API e renova o cache a cada 60 segundos.

## Testes e próximos passos

```powershell
.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

Os testes automatizados de banco usam SQLite local. A conexão, a carga e as
consultas da API também foram verificadas diretamente no PostgreSQL da equipe.

As próximas etapas são clima INMET, avaliação de cobertura, definição dos indicadores,
ML com validação temporal, LLM com function calling e RAG.
A interface React/Vite, com ferramentas Node.js, fica para a etapa posterior.

- [Planejamento e decisões do projeto](docs/contexto-projeto.md).
- [Análise inicial das fontes e limitações](docs/analise-bases.md).
- [Inventário e hashes dos arquivos originais](docs/inventario-bases.json).
