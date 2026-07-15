# Mithrandir — Guia de desenvolvimento (MVP)

MVP do sistema de scouting em **Python puro** (biblioteca padrao, sem dependencias
externas). Roda hoje em **modo mock** e aceita as fontes reais via configuracao.

## Como rodar

```powershell
# na pasta do projeto
python -m mithrandir serve        # sobe o app web em http://127.0.0.1:8756
python -m mithrandir serve 9000   # em outra porta
python -m mithrandir agent        # agente: atualiza data/news_cache.json (watchlist)
python -m mithrandir run          # coleta -> score -> gera output/dashboard.html (estatico)
python -m mithrandir top 10       # imprime o top N no terminal
python -m mithrandir info         # mostra o modo/config atual
python -m unittest discover -s tests   # roda os testes
```

O app (`serve`) tem 3 abas: **Calendário** (datas de lançamento), **Candidatos**
(ranking) e **Intel** (input manual que sobrepõe o scouting). O `run` gera um
dashboard estático de candidatos (`output/dashboard.html`) para export/offline.

## Calendário de lançamentos e Intel

- `collectors/websearch.py` — lê sinais de notícias de `data/news_cache.json`
  (hoje semeado por busca manual). **Em produção, o agente diário deve preencher
  esse cache**: buscar notícias online + usar o proxy de IA, gravando no mesmo
  formato. O resto não muda.
- `launch_estimator.py` — decide a data por prioridade: **intel manual > IA sobre
  notícias > heurística de datas > previsão sazonal**. Sem proxy, usa a heurística.
- `overrides.py` + `intel_parser.py` — a intel do analista (em `data/overrides.json`)
  sempre vence. O texto livre do "chat" é estruturado pela IA (ou por regex sem IA).
- `server.py` — app web + API (`/api/state`, `/api/intel`, `/api/refresh`, `/api/agent`, `/api/settings`).

## Análise de viabilidade e configurações

- `viability.py` — calcula receita, margem e breakeven a partir das vendas do
  device de estudo (similar) e dos custos. Breakeven: `qtd = molde / (preço − custo_und)`.
  Clicar num candidato abre o one-pager de viabilidade (aba Candidatos).
- `settings.py` — parâmetros editáveis na aba **Config** (`data/settings.json`):
  valor da capinha, custo do molde, custo por unidade, frequência/horário de
  scouting, meses de histórico. Salvar recalcula a viabilidade.
- Vendas mensais do similar: `data/sample/monthly_sales.json` (exemplo até o BI real).

## Agente de scouting de noticias (RF-02)

- `news_agent.py` — para cada device da watchlist (`data/watchlist.json`), coleta
  sinais de data e grava em `data/news_cache.json`. Rodar: `python -m mithrandir agent`
  ou botao "Buscar noticias (IA)" no app. Agendar diariamente para automatizar.
- Dois modos: **com API de busca** (vasculha a web + IA extrai) e, sem ela, o
  **fallback por conhecimento do proxy** (limitado pelo corte de treino do modelo).
- **Peca que falta para o scouting web real:** uma API de busca. Plugue em
  `collectors/websearch.py::get_search_provider` (hoje retorna None). Feito isso, o
  agente passa a vasculhar a web de verdade sem mudar mais nada.

## Estrutura

```
mithrandir/
  config.py            # configuracao (env / config.json) e deteccao de modo mock
  models.py            # dataclasses do dominio (Candidate, sinais, etc.)
  normalize.py         # normalizacao/dedup de nome de modelo (regras + IA opcional)
  internal_bi.py       # base interna (BI) + casamento com modelo similar + catalogo
  scoring.py           # motor de priorizacao (score explicavel)
  pipeline.py          # orquestracao do fluxo diario
  dashboard.py         # gera o HTML interativo
  cli.py / __main__.py # linha de comando
  ai/proxy.py          # cliente do proxy interno de IA (obrigatorio - RNF-01)
  collectors/
    launch_calendar.py # previsao sazonal de lancamentos
    mercadolivre.py    # tracao no marketplace (API real + fallback mock)
    news.py            # noticias/rumores (RSS + fallback mock)
    mock_seed.py       # dados de exemplo (modo mock)
data/sample/           # CSVs de exemplo (BI, catalogo, historico de lancamentos)
tests/                 # testes (unittest)
```

## Como plugar as fontes reais (quando os acessos sairem)

Copie `config.example.json` para `config.json` e preencha (ou use variaveis
`MITHRANDIR_*`). Assim que qualquer fonte real for configurada, o sistema sai do
modo mock automaticamente.

| Fonte | Onde mexer | O que fazer |
|-------|-----------|-------------|
| **Proxy de IA** | `config.json` (`ai_base_url`, `ai_api_key`, `ai_model`) | Endpoint compativel com a API OpenAI. Ajuste `ai/proxy.py` se o contrato do proxy diferir. |
| **Mercado Livre** | `config.json` (`ml_access_token`) | Token da API. Revise `collectors/mercadolivre.py` (categoria/campos). |
| **BI (base interna)** | `internal_bi.py` (`load_internal_records`) | Trocar a leitura do CSV por consulta a API/dataset do BI, mantendo o mesmo formato de saida. |
| **Noticias** | `collectors/news.py` | Ativar `collect(enabled=True)` e ajustar a lista `FEEDS`. |
| **Outros marketplaces** | novo arquivo em `collectors/` | Seguir o padrao do `mercadolivre.py` (retornar observacoes no mesmo formato). |

## Ajustar a priorizacao

Os pesos por fase e as penalidades ficam em `mithrandir/scoring.py` (`WEIGHTS`,
`PENALTY_*`). Devem ser calibrados com o time (spec 04) e, futuramente, pelo loop
de feedback (RF-08).

## Agendamento diario (Fase 2)

Rodar `python -m mithrandir run` uma vez por dia (Agendador de Tarefas do Windows
ou cron no servidor de TI). O dashboard e regenerado a cada execucao e o historico
fica no SQLite (`data/mithrandir.db`) para calcular momentum.
```
