# Guia dos fontes do DenguePrev

Este relatório explica os arquivos mantidos no projeto após a organização de
18/11/2026. O objetivo é permitir que cada integrante acompanhe o caminho dos
dados e encontre o código responsável por cada tarefa. A visão geral e a
arquitetura ficam no [README principal](../README.md); os comandos completos
de instalação, preparação e execução estão no [guia de execução](execucao.md).

## 1. O que já existe e como as partes se conectam

O projeto tem processamento de dados, PostgreSQL compartilhado no Supabase,
API FastAPI, experimentos de Machine Learning e assistente com Groq, consultas
controladas e recuperação de documentos. A visualização atual é um dashboard
provisório em Streamlit. `frontend/` contém a interface inicial React/Vite e
TypeScript, com panorama, estimativas e assistente conectados à API.

Há três fluxos principais:

1. **Preparação dos dados:** arquivos originais → rotinas de ETL → CSVs e
   resumos validados → sincronização com PostgreSQL → visões analíticas.
2. **Previsões:** visão analítica → snapshot local → variáveis históricas →
   comparação de modelos → artefato salvo → serviço de previsões → API.
3. **Assistente:** pergunta → Groq → solicitação de ferramenta permitida →
   consulta feita pelo backend → resposta da LLM → validação e referências.

Os dados numéricos do assistente vêm das funções do backend. Para perguntas
documentais, a busca local recupera trechos oficiais que fundamentam o texto
gerado pelo Groq. O modelo de linguagem não treina o previsor epidemiológico.

### Termos usados no código

| Termo | Significado neste projeto |
| --- | --- |
| ETL | Ler uma fonte, transformar seus dados e preparar a saída para carga. |
| Agregado | Contagem por município, ano e semana, em lugar de registros individuais. |
| API | Serviço HTTP que entrega dados estruturados às interfaces e integrações. |
| ORM | Mapeamento de classes Python para tabelas SQL, feito pelo SQLAlchemy. |
| Schema Pydantic | Contrato que valida os campos recebidos ou devolvidos pela API. |
| View ou visão | Consulta SQL salva que combina tabelas sem criar outra cópia dos registros de origem. |
| Snapshot | Cópia congelada de uma extração para reproduzir um experimento de ML. |
| Artefato de ML | Modelo salvo e informações que permitem conferir e reproduzir sua execução. |
| Hash SHA-256 | Identificação do conteúdo de um arquivo, usada para detectar alterações. |
| Function calling | A LLM pede uma função; o backend valida e executa somente as operações autorizadas. |
| RAG | Recuperação de trechos de documentos para fundamentar a resposta da LLM. |

## 2. Pastas e arquivos que compõem o repositório

| Local | Responsabilidade |
| --- | --- |
| `backend/` | Banco, API, serviço de previsões e assistente. |
| `pipelines/` | Preparação e validação das fontes de dados e documentos. |
| `ml/` | Preparação dos exemplos e comparação dos modelos. |
| `scripts/` | Inspeção auxiliar dos CSVs e ZIPs. |
| `tests/` | Verificação automatizada das regras e integrações locais. |
| `docs/` | Planejamento, avaliações, catálogos das fontes e este guia. |
| `frontend/` | Interface React/Vite com componentes, páginas, contratos e acesso à API. |
| `.vscode/` | Configuração de visualização do projeto no VS Code. |
| `app.py` | Dashboard provisório em Streamlit. |
| `README.md` | Apresentação do produto, arquitetura e início rápido. |
| `requirements.txt` | Dependências Python da aplicação e dos testes. |
| `.env.example` | Modelo fictício das configurações locais. |
| `.gitignore` | Regras que mantêm credenciais, dados grandes e arquivos gerados fora dos commits. |

O arquivo `ml/.gitkeep` é um marcador vazio mantido da estrutura inicial.
O marcador de `frontend/` foi substituído pelos arquivos da interface.

## 3. Fontes de dados utilizadas

| Fonte | O que fornece | Onde é tratada | Importância e limite |
| --- | --- | --- | --- |
| SINAN | Registros de dengue agregados por residência e semana dos primeiros sintomas. | `etl_sinan.py` | Histórico e experimento próprio, incluindo a extração parcial de 2026. A contagem inclui as classificações presentes na extração. |
| SESA/e-SUS VS | Registros estaduais por residência e semana da notificação, de 2020–2024. | `avaliar_fontes.py` | Série estadual e experimento separado. Não é somada ao SINAN. |
| INMET | Observações meteorológicas e metadados das estações. | `etl_inmet.py` | Chuva, temperatura, umidade e cobertura de observações por semana. Estação próxima não garante representatividade de todo o município. |
| IBGE | Códigos e nomes municipais, referências populacionais e centroides. | `etl_ibge.py`, `etl_populacao.py` e `vincular_estacoes.py` | Identificação dos municípios, denominadores das taxas e associação geográfica às estações. |
| Ministério da Saúde | Documentos oficiais selecionados sobre dengue e vigilância. | `preparar_rag.py` e `backend/rag.py` | Base documental do assistente, com edição, página e origem verificáveis. Não fornece estatísticas municipais atuais. |

A data de notificação e a data dos primeiros sintomas representam momentos
diferentes. O código mantém essa distinção. Ausência de registro também
permanece diferente de uma contagem observada igual a zero.

## 4. Arquivos da interface e da API

### `frontend/`: a interface React/Vite

Node.js executa o servidor de desenvolvimento e as ferramentas de compilação.
A interface renderizada no navegador é React; o acesso ao banco e ao Groq
continua no backend Python. TypeScript descreve os contratos e ajuda a detectar
incompatibilidades antes da execução.

| Arquivo ou grupo em `frontend/` | Responsabilidade |
| --- | --- |
| `index.html` e `src/main.tsx` | Documento inicial e montagem do React com o roteador. |
| `src/App.tsx` | Rotas, filtros compartilhados no endereço e carregamento do cadastro municipal. As páginas são importadas sob demanda. |
| `src/components/AppLayout.tsx` | Marca, navegação, localização da página e rodapé comuns. O acesso “Como usar” abre as instruções da página. |
| `src/components/Filtros.tsx` | Seletores de município, ano e intervalo de semanas, escolha expansível da base e retorno à consulta estadual. Adapta os controles a cada página. |
| `src/components/AjudaPagina.tsx` | Instruções expansíveis de uso, reutilizadas nas páginas. |
| `src/components/CopiarConsulta.tsx` | Copia o endereço com filtros, informa sucesso e orienta a cópia manual quando o navegador não permite acesso à área de transferência. |
| `src/components/Painel.tsx` | Cabeçalhos, cartões de indicadores e painéis reutilizáveis. |
| `src/components/EstadoConsulta.tsx` | Estados de carregamento, erro, tentativa manual e ausência de dados. |
| `src/hooks/useApi.ts` | Ciclo das leituras HTTP; cancela consultas antigas e evita mostrar dados de outro filtro. |
| `src/services/api.ts` | Prefixo da API, requisições, erros, timeouts, caminhos das fontes e envio explícito de perguntas. |
| `src/types/api.ts` | Contratos TypeScript consumidos da API, incluindo valores opcionais e ausência. A referência completa continua em `backend/schemas.py`. |
| `src/features/panorama/PanoramaPage.tsx` | Consulta uma grade anual estadual e deriva as seleções locais de município/semana. Organiza Histórico, Mapa municipal e População e clima, exportação e atalhos. |
| `src/features/panorama/resumo.ts` e `analise.ts` | Resumos de registros e cobertura; população anual contada uma vez por município; taxas descritivas e filtragem de sensores por cobertura. Preservam ausência e zero. |
| `src/features/panorama/MapaMunicipios.tsx`, `geografia.ts` e `municipios-es.json` | Mapa selecionável por mouse/teclado, projeção local e malha simplificada do IBGE. O JSON é um recurso necessário da interface, com origem, data de obtenção e hash do arquivo original. |
| `src/features/panorama/IndicadoresContexto.tsx` | População e taxa no intervalo; clima de uma cidade com seleção de sensor, cobertura, gráfico e tabela. Evita somar estações repetidas num total estadual. |
| `src/features/panorama/GraficoSemanal.tsx` e `RankingMunicipios.tsx` | Gráfico semanal com lacunas e ranking com busca por nome e seleção de cidade. |
| `src/features/comparacao/ComparacaoPage.tsx` | Duas cidades, período comum, totais/diferenças calculados pelo backend, gráfico de contagens ou taxas, tabela, inversão da referência e CSV. |
| `src/features/estimativas/EstimativasPage.tsx` | Datas do snapshot e do alvo, avaliação do modelo, estimativas e motivos por município. Usa o ano epidemiológico retornado pela API. |
| `src/features/assistente/AssistentePage.tsx` e `MensagemResposta.tsx` | Formulário com envio explícito, sugestões, biblioteca e apresentação das respostas e referências. |
| `src/features/assistente/useConversa.ts` | Histórico em memória, município enviado como contexto, limite de texto, cancelamento e bloqueio de envios duplicados. Reinicia a conversa ao trocar fonte ou cidade. |
| `src/lib/formatacao.ts` e `csv.ts` | Formatação de números/datas, configuração das fontes, URLs permitidas e exportação de dados. |
| `src/lib/filtros.ts` | Valida e restaura os filtros do endereço; serializa as consultas e aplica o calendário epidemiológico de 52 ou 53 semanas. |
| `src/styles.css` | Paleta em variáveis CSS, tipografia, layouts, estados de foco e regras responsivas. Azul identifica navegação e consultas; violeta acompanha previsões e assistente. |
| Arquivos `*.test.ts` e `*.test.tsx` em `src/` | Ausência/zero, somas parciais, cobertura, CSV e requisições. Os testes de interação verificam filtros e conversa com respostas simuladas: sugestão sem envio, contexto municipal, envio único e recuperação de falhas. Não chamam o Groq. |
| `vite.config.ts` | Plugin React e proxy local `/api` para o backend; lê a configuração do próprio frontend. |
| `package.json`, `package-lock.json` e `tsconfig.json` | Comandos, dependências fixadas e regras de verificação de tipos. |
| `.env.example` e `.npmrc` | Exemplo de configuração pública e cache npm local ignorado pelo Git. |

**Importância:** a interface recebe dados pelos serviços, usa componentes
comuns e mantém as regras de cada página em sua funcionalidade. As somas do
panorama são descritivas e identificam a cobertura de observações; previsões
e comparações solicitadas pela LLM são calculadas nos serviços do backend.
O frontend não possui dados fictícios de fallback e não treina modelos.

A composição visual usa navegação branca, cabeçalho em azul e violeta e
indicadores com divisórias, concentrando o destaque de cor no cabeçalho e
nas ações. Gráfico, marca e ícone da aba acompanham a identidade da interface.
As instruções ficam no fim de cada página e podem ser abertas pelo topo.

O contexto da conversa fica apenas em memória e é reiniciado quando muda a
fonte ou o município. Não existe envio automático de sugestões. Os testes de
interação usam um DOM simulado com jsdom e Testing Library. A revisão visual
foi bloqueada pelo controle de navegador disponível nesta máquina; o layout
e a responsividade ainda precisam de conferência no navegador.

### `app.py`

É a interface provisória. `carregar_dados()` consulta `/casos` pela API;
`filtrar_dados()` aplica os filtros de ano e município; `exibir_dashboard()`
mostra indicadores, gráficos, tabela e exportação CSV. `main()` monta a página
e apresenta erros de acesso.

**Importância:** permite visualizar o histórico com a estrutura atual do
backend. Esse dashboard consulta o SINAN; ainda não apresenta todos os recursos
de previsões, assistente e RAG disponíveis na API. A interface React/Vite
consulta esses recursos diretamente pelos serviços de `frontend/src/services/`.

### `backend/main.py`

Cria a aplicação FastAPI, declara as rotas, recebe os filtros e encaminha as
operações aos módulos responsáveis. Também converte falhas conhecidas em
respostas HTTP controladas. Ao iniciar a API, `/docs` disponibiliza a interface
interativa para explorar os parâmetros e testar as rotas.

| Rotas principais | Dados ou função |
| --- | --- |
| `/health` | Indica que o processo da API está respondendo; não comprova sozinho o acesso ao banco. |
| `/municipios`, `/populacoes` | Cadastro nominal e referências populacionais. |
| `/casos` | Agregados SINAN, com nomes dos municípios. |
| `/estacoes`, `/clima`, `/vinculos-estacoes` | Estações, observações semanais e vínculos geográficos. |
| `/base-analitica`, `/cobertura` | Série SINAN integrada e diagnóstico de presença das fontes. |
| `/base-sesa`, `/cobertura-sesa` | Série SESA integrada e seu diagnóstico próprio. |
| `/modelo`, `/previsoes` | Experimento selecionado e estimativas da fonte solicitada. |
| `/assistente/status`, `POST /assistente` | Estado da configuração local e conversa com o assistente. |
| `/documentos`, `/documentos/busca` | Catálogo documental e recuperação de trechos. |

**Importância:** oferece um contrato único para o dashboard e para o futuro
frontend. O código de processamento e treinamento fica nos serviços próprios.

### `backend/schemas.py`

Define classes Pydantic como `MunicipioResponse`, `PrevisoesResponse`,
`AssistenteRequest` e `AssistenteResponse`. Elas descrevem campos, tipos,
limites, valores opcionais e estruturas de entrada e saída.

**Importância:** evita que cada rota invente um formato diferente e documenta
o que a interface pode enviar ou receber. Esses contratos JSON têm uma função
distinta das definições das tabelas SQL em `models.py`.

## 5. Conexão, estrutura e carga do banco

### `backend/database.py`

Lê a configuração local, prepara a conexão SQLAlchemy e fornece sessões e
transações. `database_url()` interpreta `DATABASE_URL`; `get_engine()` cria
o gerenciador da conexão quando necessário; `get_db()` entrega uma sessão às
rotas; `transacao()` permite compor cargas em uma operação única.

**Importância:** concentra a configuração de acesso. O mesmo backend pode
apontar para PostgreSQL no Supabase ou para PostgreSQL local. O Supabase é o
serviço que hospeda o banco compartilhado; as credenciais continuam no `.env`.

### `backend/models.py`

Define as tabelas com SQLAlchemy, incluindo chaves, relacionamentos, índices
e restrições. É a referência da estrutura SQL usada pelas rotinas de carga.

| Classe | Tabela | Informação armazenada |
| --- | --- | --- |
| `Municipio` | `municipios` | Código e nome oficial do município. |
| `CasoDengue` | `casos_dengue` | Contagem SINAN por município, ano e semana. |
| `PopulacaoMunicipal` | `populacoes_municipais` | População por ano de aplicação, com referência e origem. |
| `SemanaEpidemiologica` | `calendario_epidemiologico` | Datas inicial e final de cada semana. |
| `NotificacaoEstadual` | `notificacoes_sesa` | Contagem SESA por semana de notificação, com identificação da extração. |
| `EstacaoMeteorologica` | `estacoes_inmet` | Cadastro e localização das estações. |
| `ClimaSemanal` | `clima_semanal` | Medidas e cobertura de observações por estação e semana. |
| `VinculoMunicipioEstacao` | `municipios_estacoes` | Estação associada ao município em cada ano, com distância e método. |

**Importância:** protege a integridade do banco. Por exemplo, o índice único
dos agregados SINAN impede duas linhas para a mesma chave municipal/semanal.
O nome legado `quantidade_casos` continua representando registros da extração;
o nome da coluna não comprova confirmação diagnóstica.

### `backend/povoar_banco.py`

Confere os arquivos processados e sincroniza cada conjunto com o banco.
`main()` seleciona o modo; `_preparar_carga()` associa a fonte validada à
função de sincronização e ao resumo de conferência. `FonteCarga` carrega os
agregados SINAN e seus anos; `CargaPreparada` reúne a operação pronta para uso.

As funções `sincronizar_casos()`, `sincronizar_municipios()`,
`sincronizar_populacoes()`, `sincronizar_clima()`, `sincronizar_vinculos()` e
`sincronizar_sesa()` cuidam dos respectivos conjuntos. `salvar_backup()`
preserva o estado anterior quando a operação exige backup.
`sincronizar_atualizacao_2026()` integra SINAN anual, clima e vínculos numa
transação conjunta, verificando a preservação das outras séries.

**Importância:** aplica a carga de forma controlada e evita duplicações em
reexecuções. Por padrão, o comando apenas confere os arquivos. A sincronização
exige `--aplicar`. Esse arquivo não precisa ser executado sempre que a API inicia.

### `backend/analitica.py`

`gerar_calendario()` monta as semanas. `consulta_base()` combina cadastro,
calendário, registros, população e clima. `preparar_base_analitica()` prepara
as visões no banco e verifica se as junções preservaram as contagens.
`consulta_cobertura()` calcula diagnósticos de presença e disponibilidade.

**Importância:** entrega uma base consistente para consultas e ML, com uma
linha por município/semana no período de cada fonte. Semanas sem registro
continuam visíveis como ausência. O diagnóstico mede presença na extração;
ele não valida por si só a cobertura epidemiológica.

### `backend/__init__.py`

Identifica o pacote `backend` e contém sua descrição. **Importância:** apoia
a organização dos imports; não é um programa que os integrantes precisam executar.

## 6. Processamento das fontes: `pipelines/`

### `pipelines/etl_sinan.py`

`agregar_bloco()` filtra residentes do ES, valida município e datas, calcula
a semana pelos primeiros sintomas e agrupa as contagens. `processar_pacote()`
lê os ZIPs em blocos e grava `dengue_semanal.csv` e seu resumo com contadores e hash.

**Importância:** transforma o volume grande de registros em agregados adequados
à aplicação. O processamento em blocos limita o uso de memória. As exclusões
ficam documentadas no resumo. A rotina não presume uma chave individual para
eliminar registros de pessoas supostamente repetidas.

### `pipelines/etl_ibge.py`

Extrai os códigos e nomes municipais do pacote IBGE. `processar_pacote()`
gera o cadastro; `validar_cadastro()` verifica sua consistência;
`carregar_cadastro()` confere o par CSV/resumo antes de disponibilizá-lo.

**Importância:** liga os códigos dos dados de dengue aos nomes oficiais.
Preserva a relação entre o código completo IBGE e o código de seis dígitos
utilizado nas séries do projeto.

### `pipelines/etl_populacao.py`

Lê publicações populacionais fixadas por versão e o Censo 2022, valida a
cobertura dos municípios e gera população por município/ano com sua origem.
`processar_populacao()` consolida as referências; `carregar_populacao()`
confere a saída para a carga.

**Importância:** fornece o denominador de `registros_por_100_mil`. Registra as
diferenças entre censo, relação censitária e estimativas anuais. A referência
aplicada a 2023 tem uma ressalva própria, preservada nos registros. A população
não entra como variável no modelo preditivo atual.

### `pipelines/etl_inmet.py`

`ler_arquivo()` interpreta os CSVs de estações; `agregar_horas()` consolida
observações em semanas locais; `processar_pacote()` gera os arquivos de
estações e clima; `carregar_clima()` valida a saída para a carga.

**Importância:** produz chuva, temperatura, umidade e cobertura por sensor.
Datas e fusos são tratados para alinhar as semanas de domingo a sábado.
Medições ausentes permanecem identificadas, com contagem das horas válidas.

### `pipelines/vincular_estacoes.py`

Obtém centroides municipais e calcula a distância até as estações disponíveis
em cada pacote anual. `distancia_haversine()` calcula distâncias;
`gerar_vinculos()` escolhe as estações; `processar_vinculos()` grava a saída;
`validar_vinculos()` e `carregar_vinculos()` conferem os resultados.

**Importância:** permite associar a série municipal ao clima de uma estação,
preservando coordenadas, distância e método. Essa associação geográfica exige
validação de representatividade meteorológica para interpretações mais amplas.

### `pipelines/avaliar_fontes.py`

Prepara a série SESA e compara as extrações SINAN e SESA usando a data de
notificação em ambas para essa comparação. `processar_sesa()` e
`processar_sinan()` montam os recortes; `avaliar()` produz a comparação e os
diagnósticos; `carregar_serie_sesa()` valida os agregados estaduais para carga.

**Importância:** fundamenta a escolha e as limitações das séries. Apesar do
nome do CSV `sesa_notificacoes_semanais_candidata.csv`, ele é usado como entrada
da carga SESA atual. Diferença entre totais não mede automaticamente cobertura
ou sobreposição. As fontes permanecem separadas no banco e nos experimentos.

### `pipelines/calendario.py`

Implementa `inicio_ano_epidemiologico()`, `ano_semana_epidemiologica()` e
`semanas_no_ano()`. **Importância:** faz ETL, banco e ML utilizarem a mesma
definição de semana, inclusive nas bordas em que ano civil e epidemiológico diferem.

### `pipelines/arquivos.py`

`sha256_arquivo()` calcula hashes em fluxo; `abrir_zip_anual()` abre o pacote
anual, inclusive quando está dentro do ZIP original;
`conferir_atualizacao_2026()` valida os pacotes adicionais pelo catálogo.

**Importância:** compartilha a verificação dos arquivos e o acesso aos ZIPs
sem duplicar essas regras em cada pipeline. É uma biblioteca auxiliar.

### `pipelines/preparar_rag.py`

Confere os PDFs oficiais e extrai as páginas e recortes definidos no catálogo.
`normalizar_texto()`, `recortar_pagina()` e `dividir_texto()` preparam os
trechos; `preparar_base()` monta e valida a base documental. A opção
`--conferir` compara a extração com a versão existente.

**Importância:** permite reproduzir a origem dos textos do RAG. O comando
`--baixar` obtém PDFs ausentes e confere seus hashes. A consulta normal do
assistente usa o JSON preparado, sem precisar baixar novamente os PDFs.

## 7. Machine Learning: preparação, avaliação e uso

### `ml/preparar_dados.py`

`extrair_snapshot()` obtém a base agregada selecionada; `validar_base()`
confere estrutura, datas, valores e ausência de mistura das fontes.
`construir_variaveis()` e `_calcular_variaveis()` criam atrasos, médias,
variação, sazonalidade e indicadores de cobertura. `construir_proxima_semana()`
prepara o alvo seguinte ao snapshot. `preparar()` grava a base, os exemplos e
o resumo em uma pasta identificada pelo conteúdo.

**Importância:** mantém treinamento e inferência com a mesma transformação.
As variáveis usam quatro semanas anteriores ao alvo. Janelas incompletas ou
sem cobertura suficiente ficam inelegíveis; lacunas não viram contagens zero.

Os protocolos são separados: SESA treina em 2020–2022, valida em 2023 e testa
em 2024; SINAN treina em 2020–2023, valida em 2024 e testa em 2025. A extração
SINAN de 2026 alimenta o histórico disponível para a estimativa posterior.

### `ml/treinar.py`

`separar_particoes()` aplica os cortes temporais; `criar_pipeline()` prepara
os candidatos; `executar_experimento()` compara persistência, Random Forest
e Gradient Boosting; `metricas()` calcula os erros. `treinar()` salva o modelo,
as previsões e a avaliação; `carregar_modelo()` confere o artefato e as versões.

**Importância:** seleciona a estratégia pela validação antes de avaliar o teste,
compara o resultado com a persistência e registra o ambiente de reprodução.
Nos experimentos ativos, a persistência foi selecionada: repetir a última
contagem não demonstra ganho na antecipação de crescimento.

### `backend/previsoes.py`

`carregar_servico()` confere se modelo, avaliação, dataset, hashes e versões
correspondem. `ServicoPrevisoes` prepara a consulta e devolve estimativas,
datas e motivos de indisponibilidade. `get_servico_previsoes()` mantém o
experimento carregado em cache por processo e por fonte.

**Importância:** disponibiliza pela API o experimento salvo, sem retreinar a
cada pergunta. A data da previsão segue o snapshot. Na versão SINAN atual,
a referência termina em 31/10/2026 e o alvo seguinte é 01–07/11/2026. Isso não
representa automaticamente a semana corrente do dia em que a API é acessada.

## 8. Assistente, ferramentas e RAG

### `backend/assistente.py`

`ClienteGroq.completar()` monta e envia uma rodada, aplica retentativas
limitadas, valida o retorno e contabiliza os tokens informados pelo provedor.
`conversar()` organiza histórico, consultas, resposta final e limites das
rodadas. `referencias_recuperadas()` reúne a evidência documental;
`validar_referencias()` confere os IDs citados e os links autorizados.

**Importância:** conecta a LLM ao projeto e controla sua interação com os
resultados. As instruções e validações restringem o escopo, distinguem fontes
e datas e tratam falhas. A verificação de referências não comprova sozinha a
fidelidade semântica de cada frase; essa dimensão também exige avaliação.

### `backend/ferramentas_ia.py`

Declara `CATALOGO`, os esquemas dos argumentos e as operações de leitura.
`FerramentasIA.executar()` verifica nome e argumentos antes do encaminhamento.
As operações são `listar_municipios`, `consultar_historico`,
`comparar_municipios`, `consultar_modelo`, `consultar_previsao` e
`consultar_documentos`.

**Importância:** limita o acesso da LLM a consultas explícitas. Comparações e
totais são calculados no backend, preservando ausências e a fonte selecionada.
Uma solicitação da LLM não se transforma em SQL arbitrário ou código Python.

### `backend/rag.py`

Valida o catálogo, a origem dos trechos e seus hashes. `BaseDocumental.carregar()`
lê a base versionada; `listar_fontes()` expõe o catálogo;
`buscar()` recupera até três trechos por similaridade textual.

**Importância:** fornece a evidência documental ao assistente e os dados
necessários para referências verificáveis. A implementação atual combina
TF-IDF de palavras e caracteres com critérios mínimos de recuperação. Essa
busca local tem limitações de vocabulário e não usa um modelo neural de embeddings.

## 9. Inspeção auxiliar

### `scripts/inspect_datasets.py`

`inspect_paths()` encontra os CSVs e ZIPs; `_FileInspector` percorre arquivos e
pacotes aninhados; `inspect_csv()` identifica o layout e faz amostragem ou
contagem completa. As funções auxiliares separam detecção de encoding,
cabeçalho, perfil e leitura das linhas.

**Importância:** permite conhecer uma fonte antes de escrever ou executar seu
ETL. Ajuda a identificar colunas, separadores e erros de leitura. A amostragem
inspeciona somente parte da tabela; a opção de contagem completa tem outro custo.
O relatório gerado é uma saída local, distinta do código dessa ferramenta.

## 10. O que cada arquivo de teste protege

Os testes automatizados usam dados controlados, SQLite e provedores simulados.
Eles não substituem a avaliação semântica da IA nem a conferência de uma nova
extração real. A suíte local não exige consumir tokens do Groq.

| Arquivo em `tests/` | Regras verificadas e importância |
| --- | --- |
| `test_inspect_datasets.py` | Leitura dos CSVs, encoding, metadados, filtros e ZIPs aninhados. Protege a inspeção das fontes. |
| `test_etl_sinan.py` | Calendário, residência, datas e agregação SINAN. Protege as contagens e exclusões. |
| `test_etl_ibge.py` | Correspondência e validação dos códigos e nomes. Protege o cadastro municipal. |
| `test_populacao.py` | Referências populacionais e sincronização. Protege os denominadores e sua origem. |
| `test_inmet.py` | Clima semanal, vínculos geográficos e carga. Protege fusos, cobertura e ausência de medições. |
| `test_avaliar_fontes.py` | Comparação e validação das séries estaduais. Protege a separação dos universos e referências temporais. |
| `test_database_loading.py` | Validação, duplicações, reexecução, backups e modos do comando de carga. Protege a integridade e a conferência sem conexão. |
| `test_analitica.py` | Calendário e integração SINAN/SESA, com preservação de contagens e lacunas. Protege as junções. |
| `test_api.py` | Configuração e consultas HTTP aos dados agregados. Protege os contratos das rotas do banco. |
| `test_atualizacao_2026.py` | ETL anual e sincronização conjunta, com preservação das demais bases. Protege o upgrade de 2026. |
| `test_ml.py` | Variáveis, elegibilidade, cortes temporais, modelos e métricas. Protege contra uso indevido de informações futuras e mistura de fontes. |
| `test_previsoes.py` | Carregamento dos artefatos, estimativas e respostas da API. Protege a correspondência entre experimento e inferência. |
| `test_assistente.py` | Ferramentas permitidas, argumentos, rodadas, falhas HTTP e consumo informado. Protege a integração com a LLM. |
| `test_rag.py` | Integridade documental, recuperação, citações e correção limitada. Protege a fundamentação e os links retornados. |

## 11. Documentação, JSONs e configuração

| Arquivo | Função e importância |
| --- | --- |
| `docs/contexto-projeto.md` | Planejamento e decisões gerais; registra a sequência e os limites do produto. |
| `docs/analise-bases.md` | Diagnóstico inicial das fontes; ajuda a entender as decisões do ETL. |
| `docs/avaliacao-ml.md` | Protocolo e resultados do estudo SESA; documenta a escolha do modelo e suas limitações. |
| `docs/avaliacao-sinan-2026.md` | Atualização de 2026 e avaliação própria SINAN; documenta compatibilidade, datas e resultados. |
| `docs/avaliacao-assistente.md` | Roteiro e resultados do assistente e do RAG, incluindo uso informado e limitações. |
| `docs/inventario-bases.json` | Catálogo do pacote original, seus arquivos e hashes; permite conferir a extração recebida. |
| `docs/fontes-2026.json` | Identificação e hashes dos ZIPs adicionais de 2026; fixa a versão usada. |
| `docs/base-documental.json` | Textos, fontes, páginas e hashes utilizados pelo RAG; é parte funcional da aplicação. |
| `docs/guia-codigo.md` | Este relatório; orienta a leitura dos fontes e distingue código, dados e histórico. |
| `docs/execucao.md` | Procedimentos de instalação, ETL, carga, treinamento e execução dos serviços. |
| `.vscode/settings.json` | Oculta arquivos locais gerados no Explorador do VS Code; não modifica as regras do Git nem o funcionamento da aplicação. |
| `.env.example` | Mostra os nomes das configurações e valores fictícios. Cada integrante prepara seu `.env` confidencial. |
| `requirements.txt` | Reúne as dependências Python necessárias para instalar o ambiente. |
| `.gitignore` | Exclui dos commits credenciais, ambiente virtual, dados brutos, caches e artefatos locais. |

JSON é um formato de dados. Sua extensão não determina se um arquivo pode ser
apagado: o catálogo documental é necessário ao RAG, enquanto respostas antigas
de teste são histórico. `atual.json`, `resumo.json` e `avaliacao.json` dos
experimentos ativos também têm funções no carregamento das previsões.

## 12. Limpeza realizada e arquivos locais preservados

Foram removidos 11 arquivos `.pyc` e seus três diretórios `__pycache__`, além
da pasta `.tools/`, que estava vazia. O Python pode recriar caches em execuções
futuras; eles continuam ignorados pelo Git e ocultos no editor.

O histórico foi consolidado em
`data/interim/historico-desenvolvimento.zip`, fora do versionamento. O ZIP
contém 50 arquivos: backups, três scripts pontuais da atualização, suas
verificações, respostas de avaliação do assistente/RAG e um experimento SESA
substituído com seu dataset. O manifesto interno registra os caminhos e hashes.
Cada conteúdo foi conferido antes da retirada das cópias soltas.

As evidências documentadas continuam preservadas nesse histórico, incluindo
resultados insatisfatórios e correções. Os resumos acadêmicos permanecem em
`docs/`. Os scripts arquivados são registros de intervenções anteriores; os
comandos mantidos para continuidade estão no [guia de execução](execucao.md).

### O que continua disponível para execução

| Local, ignorado pelo Git | Por que foi preservado |
| --- | --- |
| `.venv/` | Ambiente Python já instalado; evita reinstalar as dependências nesta máquina. |
| `.env` | Acesso local ao banco e ao Groq; o conteúdo é confidencial. |
| ZIP original e `data/raw/` | Fontes para reproduzir o processamento, incluindo dados e PDFs oficiais. |
| `data/processed/` | CSVs validados e snapshots ativos usados pela carga e pelo ML. |
| `ml/models/` | Experimentos ativos SINAN e SESA, com modelos, avaliações e ponteiros. |
| `data/interim/historico-desenvolvimento.zip` | Histórico anterior compactado para consulta e eventual recuperação. |

O Explorador do VS Code oculta dependências, dados gerados, modelos e ZIPs
conforme `.vscode/settings.json`. Para visualizar um deles, abra esse arquivo
e altere a regra correspondente de `true` para `false`. Também é possível
acessar os caminhos pelo Explorador de Arquivos do Windows ou pelo terminal.
Essa configuração não interfere no carregamento dos arquivos pelo Python.

Para listar ou extrair uma cópia do histórico, execute na raiz do projeto:

```powershell
.venv\Scripts\python.exe -B -m zipfile -l data/interim/historico-desenvolvimento.zip
Expand-Archive -LiteralPath data/interim/historico-desenvolvimento.zip -DestinationPath data/interim/historico-restaurado
```

O primeiro comando apenas lista. O segundo extrai uma cópia para consulta,
mantendo os caminhos originais dentro da pasta de destino. A extração não é
necessária para iniciar a API. Novos backups de cargas
futuras continuam sendo gravados em `data/interim/backups/`.

## 13. O que é necessário para executar ou entregar

As rotinas de ETL, carga e treinamento preparam os recursos da aplicação.
Elas são executadas quando uma fonte ou experimento precisa ser preparado
ou atualizado. Para usar o que já foi preparado, iniciam-se a API e a interface.

| Recurso | Condição de funcionamento |
| --- | --- |
| Rotas que consultam tabelas | Banco preparado e `DATABASE_URL` configurada. |
| Rotas de previsões | Experimentos e snapshots locais correspondentes, com ambiente compatível. |
| Busca documental | `docs/base-documental.json` válido e dependências instaladas. |
| Assistente real | Configuração Groq válida; cada ferramenta depende dos dados que consulta. |
| Interface React/Vite | Dependências npm instaladas e API acessível pelo proxy local ou pelo endereço configurado. |
| Dashboard provisório | API acessível no endereço definido por `API_URL`. |

O código, os testes, a documentação e os catálogos acompanham o Git. Os dados
grandes têm distribuição separada pelo pacote de fontes e pela Release indicada
no guia de execução. Os artefatos de ML são locais: quem clona o repositório precisa
reproduzir a preparação/treinamento ou receber um pacote compatível. Essa
distribuição deve fazer parte da preparação do ambiente da demonstração final.

A organização dos arquivos não conclui as etapas funcionais restantes.
A interface React/Vite inclui mapa, comparação municipal, população, clima e
filtros compartilháveis. A validação visual e dos fluxos completos no navegador,
a ampliação da avaliação da IA e a publicação continuam pendentes.
A avaliação do assistente/RAG precisa ser ampliada, e as limitações de
cobertura das fontes, representatividade do clima e desempenho preditivo
precisam acompanhar a apresentação dos resultados.

## 14. Ordem sugerida para estudar os fontes

1. Leia as seções 1–3 deste guia para situar as partes e as fontes.
2. Abra `backend/models.py` e depois `backend/schemas.py`: veja como os dados
   são armazenados e como aparecem nas respostas da API.
3. Acompanhe uma consulta simples em `backend/main.py`, como `/municipios` ou
   `/casos`, e veja seu uso em `app.py`.
4. Leia `etl_sinan.py`, `povoar_banco.py` e `analitica.py` para seguir uma
   contagem desde o ZIP até a visão integrada.
5. Siga `ml/preparar_dados.py`, `ml/treinar.py` e `backend/previsoes.py` para
   entender a diferença entre preparar, treinar e servir o experimento.
6. Leia `backend/assistente.py`, `backend/ferramentas_ia.py` e `backend/rag.py`
   para acompanhar uma pergunta com consultas ou documentos.
7. Consulte o teste correspondente ao módulo: ele contém exemplos pequenos
   de entradas válidas, erros esperados e resultados conferidos.

Funções e classes com prefixo `_` são auxiliares internas. `main()` costuma
ser o ponto de entrada de um comando. Arquivos como `models.py` e `schemas.py`
são importados pelos demais módulos e não precisam de execução individual.
