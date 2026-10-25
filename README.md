# DenguePrev

Projeto Integrador IV: aplicação acadêmica para analisar dados históricos e
estimar tendências de dengue nos municípios do Espírito Santo.

## Status

O repositório contém a estrutura inicial, a análise dos arquivos reais e uma
ferramenta executável de inspeção de CSVs e ZIPs. As limitações das bases estão
documentadas. O ETL definitivo, a base consolidada, o banco, a API, o frontend
e os componentes de IA serão implementados nas próximas etapas.

## Executar a inspeção

Requer Python 3.10 ou superior. Esta etapa utiliza apenas a biblioteca padrão;
não é necessário instalar dependências. Foi verificada com Python 3.13.

Com o pacote recebido na raiz do projeto:

```powershell
python scripts/inspect_datasets.py arquivos-proj-int-iv.zip --inmet-state ES --sample-rows 2 --output data/interim/inspecao-inicial.json
```

O script também aceita arquivos individuais e diretórios. Por padrão, procura
em `data/raw/`. O filtro de UF restringe as estações INMET, sem filtrar linhas
do SINAN. Consulte [data/README.md](data/README.md) para fontes, nomes dos
arquivos, contagem completa e limitações.

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
| docs/ | Documentação técnica, acadêmica e registro do uso de IA. |
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
preservado localmente.

## Diretrizes

As fontes são SINAN, INMET e IBGE, obtidas previamente e processadas
localmente. A base será organizada por município, ano e semana epidemiológica.
O ETL agregará os registros individuais e preservará a diferença entre
ausência de dados e zero.

A stack prevista inclui Python, Pandas, NumPy, PostgreSQL, FastAPI,
Pydantic, SQLAlchemy, React/Vite e Scikit-learn. O ML produzirá as estimativas;
a LLM, inicialmente prevista como Llama via Groq, consultará o backend e
explicará os resultados. O RAG utilizará documentos oficiais.

Datasets e modelos grandes são ignorados pelo Git. O pacote
`arquivos-proj-int-iv.zip` permanece local. O compartilhamento por GitHub
Releases foi proposto e ainda não foi publicado. Configurações e chaves
locais ficarão em `.env`, já ignorado.

## Sequência de implementação

Estrutura → inspeção dos CSVs → ETL → base consolidada → PostgreSQL → API →
dashboard → Machine Learning → LLM/function calling → RAG.

O próximo incremento é o ETL. Antes de consolidar indicadores, precisamos
validar a cobertura no ES, definir o numerador de casos, obter população
anual e estabelecer os vínculos entre municípios e estações. Consulte o
[contexto do projeto](docs/contexto-projeto.md).

## Checkpoints previstos no relatório

| Checkpoint | Data | Entregas previstas |
| --- | --- | --- |
| C1 | 18/09/2026 | Escopo, justificativa, metodologia e estrutura inicial. |
| C2 | 30/10/2026 | Bases integradas, primeiros modelos, aplicação inicial e primeiros testes/evals. |
| C3 | 04/12/2026 | MVP publicado, código, documentação, testes, evals e análise de impacto. |

As entregas são objetivos acadêmicos. O estado implementado está descrito
na seção de status.

## Documentação

- [Análise das bases recebidas](docs/analise-bases.md).
- [Manifesto dos arquivos originais e checksums](docs/inventario-bases.json).
- [Contexto e sequência do projeto](docs/contexto-projeto.md).
- [Registro de uso de IA](docs/prompts/README.md).


## Aviso

O DenguePrev não é uma ferramenta epidemiológica oficial. Resultados futuros
serão estimativas do modelo, sem constituir diagnóstico ou alerta oficial.
