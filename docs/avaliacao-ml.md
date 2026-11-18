# Primeira avaliação temporal do DenguePrev

## Resultado

A persistência teve o menor erro de validação entre os cinco candidatos desta
rodada. Ela estima a próxima contagem repetindo a última semana observada.
Random Forest e Gradient Boosting foram treinados e avaliados, mas não
superaram essa referência em 2023. Nenhuma configuração foi escolhida pelo
resultado de 2024. O artefato selecionado implementa a persistência.

O resultado é uma comparação inicial sobre uma extração histórica de
notificações, com lacunas e seleção de amostras. Não valida a cobertura
epidemiológica, a representatividade meteorológica ou uma previsão operacional
da situação atual.

## Dados e protocolo

- Fonte: SESA/e-SUS VS, por residência e semana da notificação, em 2020–2024.
- Snapshot: visão `base_analitica_sesa`, extraída em transação somente de leitura.
- Dataset: `dfa36f02b49291d5`; as bases e os exemplos têm SHA-256 no resumo local.
- Alvo: contagem de registros na próxima semana, incluindo todas as classificações da fonte.
- Entradas: quatro semanas anteriores de registros, chuva, temperatura e umidade,
  médias de duas/quatro semanas, variação anterior, coberturas dos sensores,
  sazonalidade e código municipal categórico. São 40 variáveis de entrada.
- Continuidade: quatro semanas anteriores consecutivas, sem preencher ausência com zero.
- Clima: ao menos 80% das 168 horas em cada sensor das quatro semanas anteriores.
  O clima da semana futura não seleciona o exemplo e não entra na previsão.
- População: metadado para a taxa retrospectiva por 100 mil; não é entrada do modelo.
- Seleção: menor MAE em 2023; RMSE como desempate. Transformações ajustadas somente no treino.
- Teste: candidato escolhido reajustado em 2020–2023, com pesos fixos durante 2024.
  Cada previsão de uma semana usa os registros anteriores observados naquele momento.
  Isso difere de prever recursivamente o ano inteiro a partir de dezembro de 2023.

| Partição pelo ano epidemiológico do alvo | Exemplos | Municípios | Primeira semana | Última semana |
| --- | ---: | ---: | --- | --- |
| Treino: 2020–2022 | 1.795 | 59 | 2020-02-02 | 2022-12-25 |
| Validação: 2023 | 2.774 | 78 | 2023-01-01 | 2023-12-24 |
| Teste: 2024 | 2.449 | 77 | 2023-12-31 | 2024-12-22 |

O início de 2024 epidemiológico cai em dezembro de 2023 civil. O total de
municípios mostra a cobertura dos exemplos selecionados, não o cadastro completo.
Há 19 municípios na validação sem exemplos elegíveis no treino; a codificação
aceita categorias desconhecidas sem aprender com o teste.

## Validação de 2023

Métricas em registros por município/semana, calculadas nos mesmos 2.774 exemplos.
Não há arredondamento das previsões antes de calcular os erros.

| Candidato | MAE | RMSE |
| --- | ---: | ---: |
| Persistência | **17,29** | **38,83** |
| Random Forest, 200 árvores, folha mínima 3 | 30,26 | 106,98 |
| Random Forest, 200 árvores, folha mínima 5, profundidade 8 | 30,35 | 107,80 |
| Gradient Boosting, 150 estágios, profundidade 2 | 31,35 | 108,63 |
| Gradient Boosting, 150 estágios, profundidade 3 | 31,37 | 109,34 |

Os dois Gradient Boosting usam taxa de aprendizado 0,05 e folhas mínimas de
3 e 5, respectivamente. Os modelos usam semente 42. A codificação municipal
fica em uma pipeline Scikit-learn, ajustada junto do modelo nos dados permitidos.

O patamar das contagens muda entre os períodos: a média do alvo no recorte de
treino é 22,92 e seu máximo é 404; na validação, são 67,17 e 1.603. Essa mudança
e a diferença de cobertura contextualizam a dificuldade de generalização.
Não estabelecem uma explicação causal do desempenho.

## Teste reservado de 2024

| Estratégia selecionada antes do teste | MAE | RMSE | Exemplos |
| --- | ---: | ---: | ---: |
| Persistência | **20,45** | **51,40** | 2.449 |

A estratégia selecionada coincide com a referência; portanto, esta rodada
não demonstrou ganho preditivo sobre ela. As árvores não foram reescolhidas
com base no teste. Os erros por município e as previsões individuais agregadas
ficam nos artefatos locais para inspeção.

Na persistência, o clima delimita a amostra comparável, mas não altera o valor
estimado. A previsão mantém a última contagem e, sozinha, não diferencia um
ranking de crescimento futuro. Essa restrição deve aparecer no serviço e nas
explicações da LLM se essa estratégia for apresentada ao usuário.

## Limitações e continuidade

- Os dados incluem registros descartados/indefinidos. O alvo não é caso confirmado.
- A avaliação exclui alvos ausentes e sequências incompletas. Isso pode favorecer
  períodos e municípios com mais registros e não mede desempenho em todas as semanas.
- A extração contém revisões; não foi reconstruída a disponibilidade histórica em tempo real.
- O vínculo à estação mais próxima e o limiar de horas são aproximações, sem validação de representatividade.
- MAE/RMSE globais são calculados por exemplo e não garantem o mesmo erro em cada município.
- O teste de 2024 já foi consultado nesta rodada. Estudos posteriores precisam
  registrar um novo protocolo e não apresentá-lo como teste ainda inédito.
- A próxima etapa é definir o serviço de previsões com a estratégia e suas
  limitações explícitas. Novas hipóteses de modelagem devem ser avaliadas sem
  otimizar parâmetros sobre os resultados deste teste.

## Reprodução e artefatos

Na raiz, com as dependências de `requirements.txt` instaladas:

```powershell
.venv\Scripts\python.exe -B -m ml.preparar_dados
.venv\Scripts\python.exe -B -m ml.treinar
```

O primeiro comando consulta o banco somente para leitura e grava um snapshot
local. Para reproduzir sem rede, use `ml.preparar_dados --input CAMINHO/base_sesa.csv`.
O segundo lê o dataset indicado em `data/processed/ml/atual.json`, verifica hashes,
treina os candidatos, seleciona pela validação e grava a avaliação e o artefato.

O dataset fica em `data/processed/ml/<dataset_id>/`, com snapshot, exemplos e
resumo. O identificador depende dos dados, das variáveis e do protocolo. Cada
treinamento cria uma pasta própria em `ml/models/`, com `modelo.joblib`,
`avaliacao.json`, previsões de validação e previsões de teste. `ml/models/atual.json`
aponta para a execução mais recente. Esses arquivos são locais e ignorados pelo Git.

Execução de referência: `20261118T031036125598Z_dfa36f02b49291d5`.
Ambiente: Python 3.13.12, Scikit-learn 1.9.1, Pandas 2.3.3, NumPy 2.5.5 e
Joblib 1.6.0. O relatório JSON guarda versões, parâmetros, fontes e hashes.
O carregamento verifica o hash e a compatibilidade das versões antes de abrir
um artefato produzido pelo projeto. Somente artefatos locais de origem conhecida
devem ser carregados. A persistência foi conferida contra as previsões em memória.

As previsões ainda não estão expostas na API. O dashboard permanece com seu
histórico existente; a LLM e o RAG continuam nas próximas etapas.
