# 02 — Requisitos

## Requisitos funcionais

### RF-01 — Detecção de lançamentos futuros (previsão sazonal)
- Manter um **calendário histórico de lançamentos** por modelo/família (ex.: linha Galaxy FE, linha Motorola G).
- Prever a janela provável do próximo modelo com base no ano anterior (S25FE set/2025 → prever S26FE set/2026).
- Gerar candidatos "pré-lançamento" antes de existir qualquer produto à venda.

### RF-02 — Monitoramento de notícias e rumores
- Buscar diariamente notícias/rumores sobre novos modelos (fontes de tech BR e oficiais).
- Extrair, de texto não estruturado, o **modelo do aparelho** e a **data provável** (usar proxy de IA para extração de entidade).

### RF-03 — Coleta diária de tração nos marketplaces
- Coletar diariamente sinais de vendas dos 4 marketplaces (ranking de mais vendidos, nº de avaliações, nota, preço, nº de anúncios/vendedores).
- Calcular **momentum** (velocidade de crescimento de avaliações/posição no ranking).

### RF-04 — Cruzamento com base interna (BI)
- Para cada candidato, identificar o(s) **modelo(s) similar(es)** já existentes na base Gocase.
- Trazer o desempenho de capinha desses similares (unidades, receita, margem, sell-through).
- Sinalizar se **já existe capinha** para o modelo (evita duplicidade).

### RF-05 — Motor de priorização
- Combinar os sinais em um **score de candidato** (ver [06](06-modelo-priorizacao.md)).
- Aplicar penalidades (similar vendeu mal; já temos capinha).
- Diferenciar fase: **pré-lançamento** (peso na previsão + similar interno) vs **pós-lançamento** (peso na tração de marketplace).

### RF-06 — Dashboard
- Ranking de candidatos ordenado por score.
- Drill-down por candidato: sinais, similares internos, evolução no marketplace, fontes/notícias.
- Filtros (marca, faixa de preço, fase, janela de lançamento).

### RF-07 — Alertas
- Notificar quando: um novo candidato ultrapassa um limiar de score, um modelo dispara em vendas, ou uma janela de lançamento prevista se aproxima.

### RF-08 — Loop de feedback
- Permitir marcar a decisão (desenvolveu / descartou) e o resultado real.
- Usar esse histórico para **recalibrar os pesos** do score.

## Requisitos não-funcionais

| ID | Requisito |
|----|-----------|
| RNF-01 | **IA obrigatoriamente via proxy interno de GPT.** Nenhuma chamada direta a APIs externas de LLM. |
| RNF-02 | Coleta **diária** automatizada (execução agendada), resiliente a falha de uma fonte. |
| RNF-03 | Respeitar termos de uso dos marketplaces; preferir APIs oficiais e contas de seller da Gocase a scraping. |
| RNF-04 | Dados históricos preservados (série temporal) para calcular momentum e recalibrar. |
| RNF-05 | Segredos (chaves de API, credenciais) fora do código, em cofre/variáveis de ambiente. |
| RNF-06 | Custo de IA controlado (batch, cache de extrações, respeitar quota do proxy). |
| RNF-07 | Rastreabilidade: todo score deve ser explicável (quais sinais e pesos o compuseram). |
