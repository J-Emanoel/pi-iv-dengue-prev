# Dados do DenguePrev

Os arquivos são obtidos previamente nos portais oficiais e processados
localmente. A inspeção não consulta APIs de dados nem altera os originais.

| Diretório | Conteúdo |
| --- | --- |
| `raw/` | CSVs e ZIPs originais, preservados como recebidos. |
| `interim/` | Relatórios de inspeção e resultados intermediários locais. |
| `processed/` | Base analítica validada que será produzida pelo ETL. |

Os dados dessas pastas são ignorados pelo Git. Documentação e `.gitkeep`
são versionados. O pacote recebido continua na raiz como
`arquivos-proj-int-iv.zip`, também ignorado; os exemplos não exigem copiá-lo.

## Fontes e arquivos recebidos

| Fonte | Portal oficial | Arquivos dentro do pacote | Período |
| --- | --- | --- | --- |
| SINAN | [Dengue: Dados Abertos do SUS](https://dadosabertos.saude.gov.br/dataset/arboviroses-dengue) | `DENGBR20.csv.zip` a `DENGBR26.csv.zip`. | 2020–2026; 2026 parcial. |
| INMET | [Históricos meteorológicos](https://portal.inmet.gov.br/dadoshistoricos) | `2020.zip` a `2025.zip`. | 2020–2025. |
| IBGE | [Cidades e Estados: ES](https://www.ibge.gov.br/cidades-e-estados/es.html) | `c5bc2083e93dda5c9cb358ff3d12fb9b.csv`. | Censo 2022 e estimativa com referência a conferir. |

O manifesto dos arquivos originais e seus hashes SHA-256 estão em
[`docs/inventario-bases.json`](../docs/inventario-bases.json). Os resultados
e problemas identificados em 24/10/2026 estão em
[`docs/analise-bases.md`](../docs/analise-bases.md). O manifesto contém somente
metadados das entradas, sem perfis intermediários da execução.

Para obter novas cópias manualmente, acesse o portal da fonte, selecione os
anos e baixe os arquivos para `raw/`, preservando os nomes originais. No IBGE,
selecione todos os municípios do ES e exporte CSV; o nome gerado pode mudar.
Uma nova extração pode ter conteúdo diferente do pacote inspecionado.
Registre o período e a data de obtenção. A data original de download do pacote
atual não foi informada e não foi inferida das datas dos arquivos.

O compartilhamento em GitHub Releases foi proposto e ainda não foi publicado.
Não há URL de release disponível. Quando houver, serão documentados a versão,
o download e os hashes. Git LFS não é usado nesta etapa.

## Inspeção

Requer Python 3.10 ou superior. O script usa apenas a biblioteca padrão e foi
verificado com Python 3.13. Execute os comandos na raiz do repositório.

Amostra do pacote atual, restringindo somente as estações INMET ao ES:

```powershell
python scripts/inspect_datasets.py arquivos-proj-int-iv.zip --inmet-state ES --sample-rows 2 --output data/interim/inspecao-inicial.json
```

O resultado esperado para o pacote recebido é de 82 CSVs: sete do SINAN,
74 do INMET e um do IBGE. `--inmet-state ES` filtra nomes de arquivos INMET;
não filtra as linhas individuais do SINAN.

Se os arquivos estiverem em `data/raw/`, o caminho pode ser omitido:

```powershell
python scripts/inspect_datasets.py --inmet-state ES --output data/interim/inspecao.json
```

Contagem completa das linhas das estações INMET do ES:

```powershell
python scripts/inspect_datasets.py arquivos-proj-int-iv.zip --source inmet --inmet-state ES --count-rows --sample-rows 0 --output data/interim/inspecao-inmet.json
```

São aceitos CSVs ou ZIPs individuais, diretórios e vários caminhos na mesma
execução. `--source` aceita `all`, `sinan`, `inmet`, `ibge` ou `unknown`.
Use `--help` para consultar as opções.

O relatório JSON informa caminho, tamanho, fonte, encoding, delimitador,
posição do cabeçalho, nomes das colunas, metadados e amostras. As amostras
preservam os valores originais. No IBGE, `column_labels` também oferece os
cabeçalhos com entidades HTML decodificadas.

A leitura padrão é por amostragem. `row_count: null` significa que a contagem
não foi solicitada. Com `--count-rows`, a tabela inteira é percorrida sem
acumular registros na memória; no IBGE, título e notas HTML não são contados
como municípios. Linhas com quantidade inesperada de campos geram erro.
O código de saída é 1 para erros ou ausência de CSVs correspondentes e 2 para
argumentos inválidos. A saída em arquivo exige extensão `.json`.

Esses relatórios de execução são gerados em `interim/` e não são código-fonte.
Podem ser apagados após a conferência e recriados com os comandos acima.
O `.gitignore` impede sua inclusão nos commits.

A detecção de encoding é heurística: verifica BOM/UTF-8 e tenta CP1252/Latin-1.
A amostragem não valida todas as linhas nem o CRC completo de cada CSV.
ZIPs internos maiores que 8 MiB usam temporariamente o diretório temporário
do sistema para permitir leitura aleatória; os temporários são removidos ao
fechar. Os CSVs não são extraídos em massa para o disco.

## Decisões necessárias ao ETL

- Validar a cobertura de dengue no ES e a relação entre SINAN e e-SUS VS.
- Definir o significado de `casos`: notificações, prováveis ou confirmados.
- Associar os códigos municipais de seis dígitos do SINAN aos sete do IBGE.
- Obter população municipal anual e esclarecer a referência da estimativa.
- Fixar o calendário epidemiológico e documentar inconsistências de datas.
- Definir a associação município/estação, ainda sem inferir vínculos.
- Preservar a diferença entre ausência de dados, zero casos e zero chuva.

A base consolidada de produção por município, ano e semana epidemiológica
ainda não foi gerada.
