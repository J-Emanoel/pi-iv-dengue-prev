# DenguePrev

Projeto Integrador IV: aplicação acadêmica para analisar dados históricos e
estimar tendências de dengue nos municípios do Espírito Santo.

## Estado atual

A estrutura inicial e a inspeção das bases estão concluídas. O projeto tem
uma ferramenta de leitura de CSVs e ZIPs, 13 testes automatizados e a análise
dos dados recebidos. A próxima etapa de código é o ETL.

O banco, a API, o dashboard e os componentes de IA ainda serão implementados.
O compartilhamento dos arquivos em GitHub Releases está pendente.

## Dados

Os arquivos são baixados previamente e processados localmente, sem consultas
a APIs externas para obtenção das bases.

| Fonte | Arquivos recebidos | Período |
| --- | --- | --- |
| [SINAN](https://dadosabertos.saude.gov.br/dataset/arboviroses-dengue) | `DENGBR20.csv.zip` a `DENGBR26.csv.zip` | 2020–2026; 2026 parcial. |
| [INMET](https://portal.inmet.gov.br/dadoshistoricos) | `2020.zip` a `2025.zip`, com CSVs por estação | 2020–2025. |
| [IBGE](https://www.ibge.gov.br/cidades-e-estados/es.html) | `c5bc2083e93dda5c9cb358ff3d12fb9b.csv` | Censo 2022 e estimativa com referência a conferir. |

Esses arquivos estão dentro de `arquivos-proj-int-iv.zip`, atualmente na raiz
do projeto. O pacote original é preservado localmente e ignorado pelo Git.
Não é necessário descompactá-lo para executar a inspeção.

Para obter novas cópias, selecione os anos nos portais oficiais e preserve os
nomes originais. No IBGE, selecione todos os municípios do ES e exporte CSV;
o nome gerado pode mudar. Registre a data de obtenção: uma nova extração pode
diferir do pacote atual. A data original de download desse pacote não foi
informada. Os checksums para conferir as cópias estão no inventário em `docs/`.

## Executar a inspeção

Requer Python 3.10 ou superior. Esta etapa utiliza apenas a biblioteca padrão;
não é necessário instalar dependências. Foi verificada com Python 3.13.

Com o pacote recebido na raiz do projeto:

```powershell
python scripts/inspect_datasets.py arquivos-proj-int-iv.zip --inmet-state ES --sample-rows 2 --output data/interim/inspecao-inicial.json
```

O script também aceita arquivos individuais e diretórios. Por padrão, procura
em `data/raw/`. O filtro de UF restringe as estações INMET, sem filtrar linhas
do SINAN. Para o pacote recebido, esse comando inspeciona amostras de 82 CSVs:
sete do SINAN, 74 do INMET no ES e um do IBGE.

Se os arquivos estiverem em `data/raw/`, o caminho de entrada pode ser omitido:

```powershell
python scripts/inspect_datasets.py --inmet-state ES --output data/interim/inspecao.json
```

Para contar todas as linhas dos arquivos INMET do ES:

```powershell
python scripts/inspect_datasets.py arquivos-proj-int-iv.zip --source inmet --inmet-state ES --count-rows --sample-rows 0 --output data/interim/inspecao-inmet.json
```

O JSON informa tamanho, encoding, delimitador, cabeçalho, colunas, metadados
e amostras. `row_count: null` indica que a contagem completa não foi solicitada.
No IBGE, título e rodapé HTML não são contados como municípios. A amostragem
não valida todas as linhas nem o CRC completo de cada CSV; a identificação de
encoding legado é heurística. Os originais não são alterados. ZIPs internos
grandes usam arquivos temporários do sistema, removidos ao fechar.

Consulte `python scripts/inspect_datasets.py --help` para todas as opções.

## Testes

Executar os testes desta etapa:

```powershell
python -B -m unittest discover -s tests -v
```

Os testes também podem ser coletados pelo pytest quando ele estiver
disponível no ambiente. A opção `-B` evita gerar caches de bytecode durante
a execução pelo unittest.

## Estrutura

| Pasta | Finalidade |
| --- | --- |
| backend/ | API, acesso ao banco e regras da aplicação. |
| frontend/ | Interface web com dashboard. |
| data/raw/ | Arquivos originais locais. |
| data/interim/ | Relatórios e resultados intermediários locais. |
| data/processed/ | Base consolidada validada, a implementar. |
| docs/ | Análise, inventário, contexto e registros de desenvolvimento. |
| ml/ | Treinamento, avaliação e estimativas dos modelos. |
| pipelines/ | Ingestão, limpeza e integração dos dados. |
| scripts/ | Ferramentas auxiliares, incluindo inspeção dos arquivos. |
| tests/ | Testes automatizados. |

Os `.gitkeep` preservam somente diretórios ainda vazios. Subdiretórios e
módulos serão criados conforme a implementação exigir.

Código em `scripts/`, testes em `tests/`, documentação e o manifesto das
bases fazem parte da entrega acadêmica. Os JSONs produzidos pela execução da
inspeção ficam em `data/interim/`: são resultados locais, podem ser recriados
e não entram nos commits. O ZIP original é um dado de entrada e deve ser
preservado localmente. Apenas este README reúne as instruções de uso do
repositório; os documentos em `docs/` guardam os resultados e o contexto.

## Diretrizes

A base será organizada por município, ano e semana epidemiológica. O código
IBGE será a chave municipal. O ETL agregará registros individuais e preservará
a diferença entre ausência de dados e zero casos ou zero chuva.

A stack prevista inclui Python, Pandas, NumPy, PostgreSQL, FastAPI,
Pydantic, SQLAlchemy, React/Vite e Scikit-learn. O ML produzirá as estimativas;
a LLM, inicialmente prevista como Llama via Groq, consultará o backend e
explicará os resultados. O RAG utilizará documentos oficiais.

Datasets, modelos grandes e relatórios de execução são ignorados pelo Git.
Configurações e chaves locais ficarão em `.env`, também ignorado.

## Sequência de implementação

Estrutura → inspeção dos CSVs → ETL → base consolidada → PostgreSQL → API →
dashboard → Machine Learning → LLM/function calling → RAG.

Antes de consolidar indicadores no ETL, precisamos:

- Validar a cobertura de dengue no ES e a relação entre SINAN e e-SUS VS.
- Definir se `casos` representa notificações, prováveis ou confirmados.
- Associar os códigos municipais de seis e sete dígitos e fixar o calendário
  epidemiológico, revisando as inconsistências de datas encontradas.
- Obter população municipal anual e esclarecer a referência da estimativa.
- Estabelecer os vínculos entre municípios e estações meteorológicas.

A associação município/estação e a divisão temporal do ML serão definidas
após validar os dados disponíveis, sem presumir relações ainda não verificadas.

## Checkpoints previstos no relatório

| Checkpoint | Data | Entregas previstas |
| --- | --- | --- |
| C1 | 18/09/2026 | Escopo, justificativa, metodologia e estrutura inicial. |
| C2 | 30/10/2026 | Bases integradas, primeiros modelos, aplicação inicial e primeiros testes/evals. |
| C3 | 04/12/2026 | MVP publicado, código, documentação, testes, evals e análise de impacto. |

As entregas são objetivos acadêmicos. O estado implementado está descrito
na seção Estado atual.

## Documentação

- [Análise das bases recebidas](docs/analise-bases.md).
- [Manifesto dos arquivos originais e checksums](docs/inventario-bases.json).
- [Contexto e sequência do projeto](docs/contexto-projeto.md).

## Aviso

O DenguePrev não é uma ferramenta epidemiológica oficial. Resultados futuros
serão estimativas do modelo, sem constituir diagnóstico ou alerta oficial.
