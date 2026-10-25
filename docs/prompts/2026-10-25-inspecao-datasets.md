# Inspeção reproduzível dos datasets

Data: 25/10/2026. Ferramenta: Codex.

Síntese do pedido: incorporar o contexto do DenguePrev e seguir estrutura,
inspeção de CSVs, ETL, base consolidada, PostgreSQL, API, dashboard, ML,
LLM/function calling e RAG. O anexo pede funcionamento incremental, uso dos
arquivos reais e um script inicial de inspeção.

Foram considerados o README, a análise de 24/10/2026, o inventário e o ZIP
original. A ordem da mensagem orientou o escopo: ferramenta de dados primeiro;
API e frontend nas respectivas etapas.

Produzidos: `scripts/inspect_datasets.py`, testes de leitura, `data/README.md`,
marcadores das pastas de dados e o registro de contexto. O README principal
foi atualizado para descrever o estado executável.

O script lê CSVs e ZIPs aninhados, identifica os cabeçalhos das três fontes,
amostra dados e opcionalmente conta linhas em fluxo. A execução inicial no
pacote real encontrou os 82 CSVs esperados com o filtro das estações do ES.

Os testes cobrem encoding/BOM, aspas e quebras de linha, cabeçalhos INMET,
rodapé IBGE, arquivos inválidos, ZIPs sem extração, filtros, contagens e
preservação das entradas. São executáveis com
`python -m unittest discover -s tests -v` e coletáveis pelo pytest.

Limitações: a amostragem não valida todas as linhas e encoding legado usa
heurística. A ferramenta não resolve definição de casos, população anual ou
vínculo município/estação. Esses pontos continuam pendentes para o ETL.
