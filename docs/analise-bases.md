# Análise das bases do DenguePrev

Análise realizada em 24/10/2026 sobre `arquivos-proj-int-iv.zip`. A proposta é tecnicamente executável, mas a cobertura epidemiológica do Espírito Santo precisa ser validada antes do treinamento. Este documento registra observações e propostas; não define a fonte final nem publica bases no GitHub.

O pacote tem 956.346.013 bytes (912,04 MiB), contém 13 ZIPs e um CSV avulso e reúne 3.478 CSVs. O conteúdo final ocuparia 6.300.884.379 bytes (5,87 GiB) descompactado. SHA-256 do pacote: `fdfeabaa760343234ee0ebcfe1bdaebe6c69766a851858907967c0e900b5d26c`.

A análise leu integralmente os sete CSVs do SINAN, todas as 121 colunas, contabilizando os registros nacionais e examinando todas as colunas do recorte de residentes no ES. No INMET, verificou o CRC de todos os 3.470 arquivos nacionais e examinou integralmente os 74 CSVs do ES, com foco em precipitação, temperatura do ar e umidade relativa. O CSV populacional foi lido integralmente, incluindo notas e fontes. Os ZIPs internos foram abertos em memória; os CSVs originais não foram descompactados em massa nem alterados. Cópias temporárias do recorte estadual em Parquet ficaram em `.tools/data-audit/`, ignorada pelo Git.

**Inventário dos arquivos recebidos**

| Arquivo | Fonte | Tamanho do arquivo (MiB) | CSV descompactado(s) (MiB) | CSVs |
| --- | --- | --- | --- | --- |
| c5bc2083e93dda5c9cb358ff3d12fb9b.csv | IBGE | 0,01 | 0,01 | 1 |
| 2020.zip | INMET | 98,85 | 393,46 | 589 |
| 2021.zip | INMET | 76,84 | 337,44 | 588 |
| 2022.zip | INMET | 86,18 | 354,67 | 567 |
| 2023.zip | INMET | 102,11 | 396,31 | 567 |
| 2024.zip | INMET | 98,01 | 386,69 | 565 |
| 2025.zip | INMET | 86,69 | 359,22 | 594 |
| DENGBR20.csv.zip | SINAN | 42,56 | 381,07 | 1 |
| DENGBR21.csv.zip | SINAN | 28,24 | 271,32 | 1 |
| DENGBR22.csv.zip | SINAN | 39,93 | 374,76 | 1 |
| DENGBR23.csv.zip | SINAN | 37,67 | 442,20 | 1 |
| DENGBR24.csv.zip | SINAN | 178,59 | 1755,14 | 1 |
| DENGBR25.csv.zip | SINAN | 39,72 | 435,65 | 1 |
| DENGBR26.csv.zip | SINAN | 14,06 | 121,05 | 1 |

As somas dos tamanhos internos diferem do tamanho externo porque o pacote recomprime os ZIPs. O manifesto dos arquivos originais e seus checksums estão em [inventario-bases.json](inventario-bases.json). Os resultados relevantes dos perfis estão registrados neste relatório; os arquivos intermediários usados na análise foram removidos na limpeza do projeto. Não há erro de CRC nos membros lidos na análise. Isso verifica integridade de leitura, sem certificar a correção dos valores de origem.

**SINAN: estrutura e cobertura observada**

Os sete arquivos têm o mesmo esquema de 121 colunas, separador vírgula e conteúdo compatível com UTF-8. Foram lidos 14.232.340 registros nacionais. O filtro `SG_UF = 32` encontrou 363.020 registros de residentes do ES, com códigos municipais compatíveis com os 78 municípios do CSV do IBGE.

| Pacote | Registros nacionais | Registros de residentes ES | Municípios com registros | Linhas idênticas adicionais |
| --- | --- | --- | --- | --- |
| DENGBR20.csv.zip | 1.495.117 | 7.852 | 35/78 | 1 |
| DENGBR21.csv.zip | 1.024.635 | 15.479 | 76/78 | 3 |
| DENGBR22.csv.zip | 1.405.095 | 11.241 | 73/78 | 2 |
| DENGBR23.csv.zip | 1.645.956 | 136.925 | 78/78 | 88 |
| DENGBR24.csv.zip | 6.564.924 | 138.123 | 78/78 | 77 |
| DENGBR25.csv.zip | 1.643.215 | 34.075 | 78/78 | 22 |
| DENGBR26.csv.zip | 453.398 | 19.325 | 77/78 | 15 |

Essas contagens representam linhas presentes em cada pacote, sem exclusão por classificação, sem remoção de linhas idênticas e sem reatribuição temporal. O ano do nome do arquivo não deve substituir o ano epidemiológico calculado a partir da data escolhida. Datas de notificação podem ser posteriores ao ano do pacote por atrasos de registro.

Há uma limitação de fonte que afeta diretamente o projeto: o Ministério da Saúde informa que o ES passou a usar o e-SUS Vigilância em Saúde em 2020 e ressalva que sua base contempla os registros disponíveis no SINAN. Assim, a ausência de registros nessa extração não demonstra ausência de dengue no município. [Notas do conjunto nacional de dengue](https://dadosabertos.saude.gov.br/dataset/arboviroses-dengue).

Como verificação externa de ordem de grandeza, um relatório da SESA registra 44.306 notificações no ES em 2020 e 255.957 em 2024, usando e-SUS VS. Os pacotes recebidos têm, respectivamente, 7.852 e 138.123 registros de residentes. Não são universos automaticamente equivalentes: definição, tempo de referência, revisão e filtros podem diferir. A divergência justifica conciliação, sem calcular uma taxa de cobertura a partir desses totais. [Relatório oficial da SESA](https://saude.es.gov.br/Media/sesa/Presta%C3%A7%C3%A3o%20de%20Contas/PRESTA%C3%87%C3%83O%20DE%20CONTAS%20-%201%C2%BA%20QUADRIMESTRE%202025.pdf).

Pontos concretos para o tratamento:

- Em 2020, 43 municípios não aparecem no recorte e só 26 semanas de notificação estão representadas. Isso exige tratar a cobertura como desconhecida, em vez de preencher automaticamente com zero.

- Há 1.206 registros de residentes do ES notificados em outras UFs. Filtrar apenas `SG_UF_NOT = 32` ou usar `ID_MUNICIP` como residência mudaria o universo. Para o indicador por residência, o campo municipal pertinente é `ID_MN_RESI`.

- O município de residência, a data dos primeiros sintomas e a semana dos primeiros sintomas estão preenchidos em todos os registros do recorte. Isso permite a agregação técnica, mas não resolve o problema de cobertura.

- Há 208 linhas adicionais exatamente iguais dentro dos arquivos. A exportação não traz `NU_NOTIFIC`; não é possível concluir que sejam pacientes duplicados. Não remover essas linhas sem uma regra justificável e sem avaliar o campo `NDUPLIC_N`.

- No arquivo de 2020, sete datas de início de sintomas são anteriores a 2019, incluindo uma de 1987. São inconsistências ou registros atípicos a revisar e documentar, sem corrigi-los silenciosamente.

- A conferência entre data e calendário epidemiológico encontrou 56 divergências em `SEM_PRI` no pacote de 2022 e 688 em `SEM_NOT` no total: uma em 2022 e 687 em 2023. Exemplo agregado: `DT_SIN_PRI = 2021-12-31` aparece com `SEM_PRI = 202252`. Recalcular em campo separado e guardar a versão original.

- Há 213 registros com data de digitação anterior à notificação e atrasos de notificação que podem atravessar anos. O backtest precisa explicitar que usa uma extração histórica revisada, sem reconstrução garantida do que era conhecido em cada semana.

- O arquivo de 2026 é parcial: no recorte, a última notificação é de 07/09/2026 e o último início de sintomas é de 05/09/2026. Não comparar seu total com anos completos.

As classificações observadas são `10` (333.170), `11` (7.812), `12` (330), `5` (7.013), `8` (888), `0` (13.740) e vazia (67). O dicionário oficial associa 10, 11 e 12 a dengue, dengue com sinais de alarme e dengue grave. Para a implementação, definir se o alvo será notificação, caso provável ou confirmado e validar também o critério de confirmação. Os códigos 0 e 8 precisam de interpretação compatível com a versão exportada. [Dicionário SINAN](https://portalsinan.saude.gov.br/images/documentos/Agravos/Dengue/DIC_DADOS_ONLINE.pdf).

Consulte o [calendário epidemiológico oficial](https://www.portalsinan.saude.gov.br/calendario-epidemiologico/) para fixar semanas de domingo a sábado e o ano epidemiológico nas transições de dezembro/janeiro. Não usar automaticamente a semana ISO.

**INMET: cobertura, qualidade e integração**

Os seis ZIPs nacionais cobrem 2020 a 2025. O recorte do ES reúne 74 arquivos anuais de estação, 13 códigos de estação e 648.840 linhas horárias. Os horários vão de 01/01/2020 00:00 UTC a 31/12/2025 23:00 UTC. Todos os arquivos do ES têm o número esperado de linhas do respectivo ano; não foram encontrados timestamps inválidos ou pares estação/horário duplicados. A existência da linha horária não significa que seus sensores estejam preenchidos.

| Ano | Estações/CSVs ES | Linhas horárias | Chuva ausente | Temperatura ausente | Umidade ausente |
| --- | --- | --- | --- | --- | --- |
| 2020 | 13 | 114.192 | 29,62% | 25,60% | 31,15% |
| 2021 | 13 | 113.880 | 23,39% | 16,01% | 25,45% |
| 2022 | 13 | 113.880 | 8,58% | 2,15% | 9,98% |
| 2023 | 12 | 105.120 | 4,14% | 4,14% | 5,00% |
| 2024 | 12 | 105.408 | 12,66% | 12,66% | 15,68% |
| 2025 | 11 | 96.360 | 5,89% | 5,84% | 18,65% |

No conjunto das linhas existentes, faltam 14,43% dos valores de chuva, 11,29% de temperatura e 17,83% de umidade. Esses percentuais não incluem anos sem arquivo de determinada estação. Não foram encontrados valores negativos de precipitação, umidade fora de 0 a 100%, falhas de conversão numérica ou sentinelas +9999/-9999 nas três variáveis do recorte. As ausências observadas estão em branco. Os demais sensores não receberam avaliação de plausibilidade física.

| Código | Estação | Anos com arquivo | Chuva ausente | Temperatura ausente | Umidade ausente |
| --- | --- | --- | --- | --- | --- |
| A612 | VITORIA | 2020, 2021, 2022, 2023, 2024, 2025 | 16,02% | 15,87% | 16,26% |
| A613 | SANTA TERESA | 2020, 2021, 2022, 2023, 2024, 2025 | 4,37% | 4,11% | 65,00% |
| A614 | LINHARES | 2020, 2021, 2022, 2023, 2024, 2025 | 0,01% | 0,01% | 9,24% |
| A615 | ALFREDO CHAVES | 2020, 2021, 2022, 2023, 2024 | 35,91% | 12,20% | 12,19% |
| A616 | SAO MATEUS | 2020, 2021, 2022, 2023, 2024, 2025 | 10,10% | 0,24% | 8,59% |
| A617 | ALEGRE | 2020, 2021, 2022, 2023, 2024, 2025 | 14,32% | 9,95% | 9,95% |
| A622 | PRES. KENNEDY / PRESIDENTE KENNEDY | 2020, 2021, 2022, 2023, 2024, 2025 | 13,35% | 13,17% | 13,16% |
| A623 | NOVA VENECIA | 2020, 2021, 2022 | 21,26% | 17,42% | 17,42% |
| A631 | ECOPORANGA | 2020, 2021, 2022, 2023, 2024, 2025 | 34,18% | 33,68% | 33,68% |
| A632 | MARILANDIA | 2020, 2021, 2022, 2023, 2024, 2025 | 12,99% | 12,95% | 13,03% |
| A633 | VENDA NOVA DO IMIGRANTE | 2020, 2021, 2022, 2023, 2024, 2025 | 6,95% | 5,32% | 5,32% |
| A634 | VILA VELHA | 2020, 2021, 2022, 2023, 2024, 2025 | 6,99% | 6,98% | 7,03% |
| A657 | AFONSO CLAUDIO | 2020, 2021, 2022, 2023, 2024, 2025 | 18,10% | 18,05% | 19,72% |

Santa Teresa tem 100% de ausência de umidade em 2021 e em 2025. Nova Venécia não tem arquivo nos ZIPs de 2023 a 2025; Alfredo Chaves não tem arquivo em 2025. Isso descreve o pacote recebido, sem concluir desativação das estações. O mesmo código A622 aparece como `PRES. KENNEDY` e `PRESIDENTE KENNEDY`; usar o código de estação como identificador.

O formato dos 74 CSVs do ES é consistente: oito linhas de metadados, cabeçalho na nona linha, separador ponto e vírgula, decimal com vírgula e texto lido com CP1252. São 19 colunas nomeadas e uma coluna final vazia. Os metadados oferecem latitude, longitude e altitude da estação, mas não o código IBGE do município. Há pequenas variações de precisão das coordenadas em alguns anos.

A integração exige uma associação explícita entre municípios e estações: 13 estações não cobrem diretamente 78 municípios. Será necessário obter coordenadas ou geometria municipal, considerar distância, altitude e qualidade dos sensores e registrar a origem da informação meteorológica usada para cada município. Não juntar as bases por igualdade do nome da cidade.

Para agregar, somar a precipitação disponível e calcular médias das temperaturas e umidades válidas, acompanhadas da contagem de horas válidas. Uma semana toda ausente deve continuar ausente, em vez de virar chuva zero. Qualquer limite mínimo de cobertura ou método de imputação precisa ser escolhido e avaliado. Uma verificação exploratória de 75% das 168 horas, ainda sem valor normativo, encontrou 2.948 de 3.873 grupos estação/semana com essa cobertura simultaneamente nas três variáveis; há semanas parciais nos extremos da série.

O INMET esclarece que os horários são UTC e que os dados automáticos são brutos. A definição da semana deve considerar o fuso de referência, preservando o timestamp original; uma hora UTC próxima à meia-noite pode pertencer ao dia anterior no ES. [Orientações do INMET](https://portal.inmet.gov.br/noticias/saiba-como-acessar-os-dados-meteorol%C3%B3gicos-dispon%C3%ADveis-no-site-do-inmet). Não há meteorologia de 2026 no material enviado.

**IBGE: cadastro municipal e denominadores populacionais**

O CSV avulso reúne os 78 municípios, com 78 códigos de sete dígitos únicos. Os primeiros seis dígitos também são únicos e correspondem a todos os códigos de residência do recorte SINAN. Usar essa tabela explícita de correspondência entre código de seis e sete dígitos; preservar os identificadores como texto.

A população do Censo 2022 soma 3.833.712 pessoas. A coluna intitulada população estimada [2026] soma 4.150.692. Há uma divergência de metadados: as notas finais dessa coluna citam estimativas com referência em julho de 2024. O total estimado coincide com o apresentado atualmente pelo portal para o ES, mas isso não substitui a conferência da tabela anual de referência. A divergência não comprova erro nos valores. [Portal do IBGE](https://www.ibge.gov.br/cidades-e-estados/es.html).

O arquivo tem uma linha de título antes do cabeçalho, coluna final vazia, notas HTML após as 78 linhas e entidades HTML nos nomes de 33 municípios. O tratamento precisa isolar as linhas municipais e decodificar essas entidades. Há também indicadores com anos diferentes; não considerar toda a linha como uma observação anual única.

O cadastro é útil, mas não é uma série de população municipal por ano para 2020-2026. Para incidência histórica, obter os denominadores anuais compatíveis e documentar o tratamento do ano censitário e das revisões. Aplicar a mesma população recente a todos os anos só deve ocorrer como aproximação explicitamente assumida. [Publicação de estimativas municipais do IBGE](https://www.ibge.gov.br/estatisticas/sociais/populacao/9103-estimativas-de-populacao.html).

**Fonte estadual encontrada para a próxima verificação**

A SESA mantém um conjunto oficial extraído do e-SUS VS a partir de 2020 e de registros legados do SINAN antes disso. O recurso público de dengue inspecionado, porém, expõe somente `ano`, `mes`, `agravo` e `notificacao`. Ele serve para conciliação estadual mensal; seu esquema não atende à análise por município e semana. É necessário localizar uma exportação estadual com a granularidade pretendida antes de decidir pela substituição ou complementação do SINAN. Não somar as duas fontes sem examinar sobreposição. [Conjunto estadual](https://dados.es.gov.br/dataset/doencas-e-agravos-de-notificacao), [esquema do recurso de dengue](https://dados.es.gov.br/dataset/doencas-e-agravos-de-notificacao/resource/2aa339ae-b1b3-437f-b1d4-cc00239fbbbe).

**Proposta de armazenamento no GitHub, pendente de decisão**

O ZIP externo tem 912,04 MiB. Individualmente, `2023.zip` tem 102,11 MiB e `DENGBR24.csv.zip` tem 178,59 MiB. Os três ultrapassam o limite de 100 MiB do Git convencional no GitHub. [Limites de arquivos](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).

A proposta é manter código, documentação, inventário e checksums em commits; preservar os originais compactados em uma release `dados-originais-v1`; e, depois de resolver as definições, disponibilizar um pacote estadual reproduzível em outra release. Cada integrante baixaria a versão necessária para `data/raw/`, ignorada pelo Git. Um futuro script verificaria SHA-256 e pularia arquivos já válidos.

O pacote externo já cabe como um anexo único de release: a documentação atual permite arquivos com menos de 2 GiB e informa ausência de limite total de tamanho e banda para releases. A divisão nos 14 arquivos originais facilitaria baixar apenas uma fonte ou ano, sem recomprimir os dados. [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

O volume de trabalho estadual é muito menor: os 74 CSVs originais do INMET ES somam 53,82 MiB descompactados e seus membros ZIP somam aproximadamente 13,91 MiB comprimidos. O recorte SINAN ES em Parquet, ainda com as 121 colunas e sem limpeza, ocupou 5,41 MiB. A cópia meteorológica temporária normalizada, contendo estação, timestamp e apenas três variáveis, ocupou 2,65 MiB. Esses tamanhos são de formatos e conteúdos diferentes; demonstram viabilidade, sem substituir a preservação dos originais nem constituir um pacote final aprovado.

O `.gitignore` já protege `data/` e `.tools/`. Nesta análise foi acrescentada a regra específica `/arquivos-proj-int-iv.zip`, pois o arquivo foi colocado na raiz. Não houve commit, push ou criação de release.

**Ordem de trabalho sugerida para discussão**

1. Conciliar a cobertura de dengue no ES com a SESA, definir a fonte e escolher o significado do alvo: notificação, provável ou confirmado. Esta decisão vem antes da comparação de modelos.

2. Fixar período e granularidade. O intervalo comum enviado é 2020-2025, mas 2020 tem problemas fortes de cobertura. Os anos de 2023-2025 apresentam registros de todos os municípios e são candidatos à exploração inicial, ainda sujeitos à conciliação. Para usar 2026 com clima, obter o INMET desse ano.

3. Documentar um esquema analítico com código IBGE, início da semana epidemiológica, ano/semana, contagens e sua definição, população/ano/fonte, incidência por 100 mil, clima e indicadores de cobertura. Manter valores ausentes e zero separados.

4. Implementar a ingestão em lotes, a normalização dos códigos e datas, o relatório de inconsistências e a agregação por município/semana. Criar testes de calendários, códigos, limites de ano, cálculo de incidência e preservação de ausência meteorológica.

5. Construir uma previsão de referência, como repetir o valor da semana anterior, e comparar Random Forest e Gradient Boosting somente com separações temporais. Usar um único corte de datas para todos os municípios; ajustar imputação e transformações apenas no treino. Definir o horizonte antes de preparar o alvo. Não usar o clima observado da semana futura como se estivesse disponível no momento da previsão.

6. Após validar a base e a previsão de referência, desenvolver API e dashboard apoiados nos agregados. Integrar a LLM às funções da API e avaliar a fidelidade das respostas. Acrescentar RAG e refinamentos conforme a necessidade do MVP.

As decisões pendentes são a fonte epidemiológica, a definição do alvo, o período utilizável, a associação município/estação, o tratamento das lacunas e o formato da release. A publicação do pacote e a implementação da aplicação ficam para a etapa seguinte à discussão desses resultados.
