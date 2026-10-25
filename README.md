# DenguePrev

Projeto Integrador IV: aplicacao academica para analisar dados historicos e
estimar tendencias de dengue nos municipios do Espirito Santo.

## Status

Organizacao inicial do repositorio. A aplicacao, os pipelines e os modelos
ainda nao foram implementados. Nao ha dependencias para instalar nesta etapa.

## Estrutura

| Pasta | Finalidade |
| --- | --- |
| backend/ | API, acesso ao banco e regras da aplicacao. |
| frontend/ | Interface web do usuario. |
| data/ | Dados locais e documentacao das fontes. |
| docs/ | Documentacao tecnica, academica e registro do uso de IA. |
| ml/ | Treinamento, avaliacao e estimativas dos modelos. |
| pipelines/ | Leitura, limpeza e integracao dos dados. |
| scripts/ | Utilitarios auxiliares, como inspecao de CSVs. |
| tests/ | Testes automatizados futuros. |

Os arquivos .gitkeep preservam as pastas vazias no Git. Subdiretorios serao
criados conforme a implementacao exigir.

## Diretrizes

As fontes previstas sao SINAN, INMET e IBGE, com arquivos obtidos previamente
e processados localmente. A base sera organizada por municipio, ano e semana
epidemiologica. Os arquivos reais devem ser inspecionados antes do ETL.

A stack prevista inclui Python, FastAPI, PostgreSQL, React/Vite e Scikit-learn.
O ML estimara tendencias; a LLM consultara e explicara resultados do backend.

## Trabalho em outro computador

Apos o commit e o push, clone este repositorio no outro computador.
As pastas acompanharao o clone por conterem os arquivos .gitkeep.
Datasets, arquivos .env e dependencias locais nao acompanham o repositorio
e deverao ser preparados separadamente quando forem necessarios.

O .gitignore exclui dados locais, segredos, caches, dependencias e artefatos
de modelos. Em data/, apenas arquivos Markdown e .gitkeep sao versionados.

## Aviso

O DenguePrev nao e uma ferramenta epidemiologica oficial. Resultados futuros
serao estimativas do modelo, sem constituir diagnostico ou alerta oficial.
