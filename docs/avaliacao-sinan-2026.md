# Atualização SINAN e INMET de 2026

Análise, integração e avaliação executadas em 18/11/2026. Escopo: os 78 municípios
do Espírito Santo, por residência e semana epidemiológica. As contagens incluem
as classificações publicadas e representam registros da extração, não incidência
de casos confirmados. O estudo SESA anterior permanece separado.

## Compatibilidade das fontes

Os dois arquivos adicionais têm tamanho e SHA-256 fixados em `fontes-2026.json`.
Os originais recebidos foram copiados para `data/raw/`, ignorado pelo Git.
O ZIP original do projeto não foi modificado.

O CSV SINAN novo tem as mesmas 121 colunas, na mesma ordem, dos pacotes
conferidos de 2020, 2024, 2025 e da versão anterior de 2026. Não há colunas novas
ou ausentes nesse comparativo. O formato textual dos códigos e datas usados
no ETL é compatível: UF 32, município de seis dígitos, datas ISO e semana AAAASS.
Nenhuma mudança de significado foi inferida apenas pela igualdade dos cabeçalhos.

O adaptador aceita o ZIP anual avulso, além dos ZIPs anuais dentro do pacote
original. Mantém SG_UF/ID_MN_RESI como residência e DT_SIN_PRI como referência.
SEM_PRI é conferido com o calendário calculado; não houve divergências nas
20.570 linhas ES. DT_NOTIFIC continua validando a ordem das datas. Não foram
atribuídos significados clínicos aos códigos CLASSI_FIN/CRITERIO nem removidas
linhas individuais por semelhança.

Resultados recalculados, sem números fixados como filtros:

| Item | Resultado |
| --- | ---: |
| Linhas nacionais SINAN lidas | 489.197 |
| Registros de residentes ES | 20.570 |
| Municípios conhecidos com registros | 77 |
| Agregados municipais semanais | 1.559 |
| Semanas epidemiológicas de 2026 | 1–43 |
| Código municipal desconhecido no recorte ES | 0 |
| Data inválida ou sintomas após notificação no recorte ES | 0 |

Sintomas vão de 04/01 a 31/10/2026. As notificações vão de 05/01 a 02/11/2026;
essa extração contém registros comunicados depois da data dos sintomas.
O backtest não reconstrói o que estava disponível em tempo real em 31/10.
97 registros de residentes ES foram notificados em outras UFs e permanecem
incluídos, pois o critério é residência.

Rio Novo do Sul, código 320440, não aparece nessa extração nem na versão
anterior de 2026. Não é possível determinar a causa somente com esses arquivos.
Seu cadastro permanece; ausência não foi transformada em zero.

O pacote INMET contém 634 CSVs nacionais. Foram lidos somente os 11 ES:
A612 Vitória, A613 Santa Teresa, A614 Linhares, A616 São Mateus, A617 Alegre,
A622 Presidente Kennedy, A631 Ecoporanga, A632 Marilândia, A633 Venda Nova do
Imigrante, A634 Vila Velha e A657 Afonso Cláudio. O parser existente aceitou
metadados, separador, decimais e horas: 80.256 linhas, de 01/01/2026 00h a
31/10/2026 23h UTC. No fuso local, a última observação é 31/10 às 20h.

As horas foram combinadas ao histórico antes da agregação. A semana 2025/53
recebe as horas do começo de 2026; 11 agregados de borda foram recalculados.
Na semana final, existem até 165 das 168 horas previstas. As lacunas de sensores
continuam contabilizadas. Os valores climáticos anteriores fora da borda
permaneceram iguais; os hashes de proveniência agora descrevem o conjunto
combinado. Os vínculos seguem o centroide IBGE e a estação mais próxima no
pacote anual, sem certificação de representatividade meteorológica.

## Carga e conferência no Supabase

A carga conjunta usou backup, bloqueios e uma transação para SINAN 2026, clima,
estações e vínculos. Um teste provoca falha no último componente e verifica a
reversão dos anteriores. Atualizações PostgreSQL são enviadas em lotes.

Na carga real, foram inseridos 289 agregados SINAN, revisados 235 e removidos
124 que não aparecem na extração nova. Não houve soma entre versões nem
duplicação de chaves. Os IDs dos agregados mantidos foram preservados.
A repetição da carga não alterou dados.

O banco contém agora 11.844 agregados SINAN e 363.957 registros em 2020–2026,
13 estações, 4.346 semanas de estação e 546 vínculos anuais. Os 78 municípios,
546 referências populacionais, 13.290 agregados/521.193 registros SESA e todo
o SINAN de 2020–2025 foram preservados. Na visão SESA, valores, datas e demais
metadados permaneceram iguais, com exceção do hash INMET combinado. O snapshot
e os artefatos do experimento SESA não foram substituídos.

A visão SINAN mantém 28.548 linhas de calendário, incluindo semanas futuras
sem dados. O ML usa um snapshot limitado à última semana SINAN observada:
27.846 combinações em 357 semanas. Não usa o fim do calendário de dezembro
como se houvesse observações até lá.

## Avaliação SINAN independente

O protocolo foi definido para essa fonte antes de comparar candidatos. Os
dados SESA não foram concatenados, usados para preencher ausências ou para
treinar o experimento SINAN. O resultado SESA anterior não valida esta série.

| Partição | Período | Exemplos avaliáveis | Municípios |
| --- | --- | ---: | ---: |
| Treino | 2020–2023 | 2.871 | 78 |
| Validação | 2024 | 1.533 | 78 |
| Teste | 2025 | 741 | 44 |
| Aplicação histórica, fora da seleção | 2026, até semana 43 | 670 | Ver artefatos locais |

Entradas: as mesmas 40 variáveis de quatro semanas anteriores, identificação
municipal e sazonalidade. Exige registros presentes e ao menos 80% das horas
válidas nos três sensores em cada semana anterior. Ausência não vira zero.
População só normaliza a apresentação retrospectiva, fora das entradas.

Foram comparadas as mesmas quatro configurações de árvores e a persistência.
MAE de 2024 seleciona o candidato; RMSE desempata. O vencedor é reajustado em
2020–2024 e avaliado em 2025. Alvos de 2026 não participam do ajuste/seleção.

| Candidato | MAE validação 2024 | RMSE validação 2024 |
| --- | ---: | ---: |
| Persistência | **16,0170** | 39,0948 |
| Random Forest, folha 3 | 16,2861 | 38,7142 |
| Random Forest, folha 5, profundidade 8 | 16,5088 | 40,5019 |
| Gradient Boosting, profundidade 2 | 16,2925 | 38,6413 |
| Gradient Boosting, profundidade 3 | 16,2057 | 37,8152 |

A persistência venceu pelo critério predefinido de MAE, embora outros
candidatos tenham RMSE menor. No teste de 2025: **MAE 9,6937 e RMSE 19,1534**,
em 741 exemplos, coincidindo com a referência. Não foi demonstrado ganho sobre
a persistência nem capacidade de antecipar crescimento. Esses valores não
devem ser comparados diretamente com os erros SESA, pois fonte, referência
temporal, períodos e coortes diferem. O teste de 2025 já foi consultado; novas
hipóteses precisam de protocolo documentado, sem seleção sobre esse teste.

Dataset: `ba50c752b7bebcbb`.
Execução: `20261118T051108061378Z_ba50c752b7bebcbb`.
Os JSONs locais guardam parâmetros, hashes, versões, métricas e coortes.

## Serviço e limites

`/modelo?fonte=sinan` e `/previsoes?fonte=sinan` consultam esse experimento.
O padrão sem parâmetro continua SESA para preservar consultas anteriores.
Os ponteiros SINAN ficam sob `data/processed/ml/sinan/` e `ml/models/sinan/`.

O período comum final é 25–31/10/2026. O próximo alvo é 01–07/11/2026,
semana 44. Na janela anterior, 20 municípios têm os registros exigidos, 53
têm clima qualificado e **15 atendem ambos os critérios**. Os outros 63 são
retornados com estimativa nula e motivos, sem ocultar o cadastro de 78 cidades.
Não é uma previsão da semana atual. Notificações revisadas e atraso de
publicação impedem interpretar a origem simulada como disponibilidade real.

A fonte SINAN no ES continua exigindo conciliação com e-SUS VS. Ter registros
de 77 municípios não comprova completude clínica ou captura de todos os casos.
Não há diagnóstico nem alerta epidemiológico oficial. O RAG e a LLM deverão
preservar fonte, data de referência, limitações e origem dos números.

Os comandos de reprodução, aplicação e consulta ficam no README principal.
