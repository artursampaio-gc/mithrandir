# Mithrandir — Handoff técnico

Sistema de scouting de novos modelos de celular para priorizar o desenvolvimento
de capinhas na Gocase. Python (biblioteca padrão + `requests` na nuvem). Roda
**local** (arquivos) ou na **nuvem** (Vercel serverless + Supabase) — o mesmo código.

> Visão de produto e specs: `README.md` e `specs/`. Este arquivo é o guia técnico.

---

## 1. Como está hoje (estado real)

| Peça | Status |
|------|--------|
| App web (Calendário, Candidatos, Intel, Config) | ✅ funcionando |
| Proxy de IA (`gpt-5.5`) | ✅ real (via env) |
| Vendas internas (Google Sheets) | ✅ real **quando a API key estiver setada**; senão CSV de exemplo |
| Calendário de lançamentos | ✅ base curada (`news_seed.json`) + IA + intel |
| Intel manual (overrides) | ✅ real (Supabase/arquivo) |
| Tração de marketplace | ✅ **real** (Amazon BR via Sorftime/MCP, ingestão semanal); Mercado Livre segue mock |
| Agente de notícias (busca web) | ✅ real (Google Notícias RSS, sem chave); ver §7.2 |
| Deploy | ✅ Vercel + Supabase |

---

## 2. Rodar local

```powershell
python -m mithrandir serve        # app web em http://127.0.0.1:8756
python -m mithrandir run          # pipeline -> gera output/dashboard.html (estático)
python -m mithrandir agent        # roda o agente de notícias (busca web real)
python -m mithrandir info         # mostra config/modo atual
python -m unittest discover -s tests   # testes (82)
```

Local sem credenciais = tudo em **arquivos** (`data/`) e dados de **exemplo**.
Basta ter Python 3.11+; `requests` é opcional local (usa `urllib` como fallback).

O app tem 4 abas: **Calendário** (linha do tempo por ano, paginada), **Candidatos**
(ranking → clique abre o one-pager de viabilidade), **Intel** (input que sobrepõe o
scouting) e **Config** (custos, frequência de scouting).

---

## 3. Arquitetura

```
Google Sheets (vendas) ─┐
Proxy de IA (gpt-5.5) ───┤→  compute (pipeline + calendário)  →  Supabase (app_cache)
base curada / intel ─────┘                                           │
                                                                     ▼
                             navegador  ←  função serverless (lê do Supabase)
```

- **`store.py`** é o ponto único de I/O. Se `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`
  existem → usa **Supabase** (REST); senão → **arquivos locais**. `overrides`,
  `settings`, o cache de notícias e o cache do app passam por ele.
- **Sem estado em memória** (serverless): o compute grava no Supabase (`app_cache`)
  e a leitura da web só consulta o banco. Nada de threads/caches entre requisições.
- **`_http.py`** — usa `requests` na nuvem (o `urllib` falha no Vercel com
  `[Errno 16]`), `urllib` no local.

### Fluxo de compute (importante)
- **Candidatos** (`_rebuild_candidates`) = `pipeline.run_pipeline` → rápido, **sem IA**.
- **Calendário** (`_rebuild_calendar`) = `build_calendar(with_overrides=False)` (IA,
  ~20-30s) grava `calendar_base`; depois `apply_overrides_to` aplica a intel (barato).
- **Intel** (add/delete) só re-aplica sobre `calendar_base` → **sem chamar IA**.
- **`/api/refresh`** e **`/api/cron`** fazem o compute pesado + sincronizam a planilha.

---

## 4. Deploy (Vercel + Supabase)

- **`api/index.py`** — entrypoint serverless (`class handler(Handler)`).
- **`vercel.json`** — `builds` (@vercel/python) + `routes` (catch-all `/(.*)` →
  `api/index.py`) + **cron** diário `0 8 * * *` em `/api/cron` + `maxDuration: 60`.
- **Repo:** github.com/artursampaio-gc/mithrandir (deploy automático a cada push).

### Variáveis de ambiente (Vercel → Settings → Environment Variables)
| Variável | Para quê |
|----------|----------|
| `MITHRANDIR_AI_BASE_URL` | proxy de IA (`https://ai-proxy.gogroupbr.com/v1`) |
| `MITHRANDIR_AI_API_KEY` | chave do proxy de IA (secreta) |
| `MITHRANDIR_AI_MODEL` | `gpt-5.5` |
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_SERVICE_KEY` | **service_role** (bypassa RLS; secreta) |
| `MITHRANDIR_SHEETS_API_KEY` | Google Sheets API key (planilha compartilhada por link) |
| `MITHRANDIR_WEBSEARCH` | `off` desliga a busca web (default: ligada) |
| `MITHRANDIR_INGEST_TOKEN` | **obrigatória** para a ingestão de marketplace (secreta; sem ela o endpoint recusa) |

`sheets_id` e `sheets_gid` já têm default no código (planilha atual); sobrescreva
com `MITHRANDIR_SHEETS_ID` / `MITHRANDIR_SHEETS_GID` se trocar de planilha.

> ⚠️ Chaves secretas só como env var no Vercel — nunca no git. `config.json` (local)
> está no `.gitignore`.

### Primeira carga
O app abre vazio até o primeiro compute. Clique **🔄 Recalcular** (ou espere o cron).

### Supabase — tabelas
`app_cache` (blobs: candidates/calendar/calendar_base/news_cache/internal_records/
monthly_sales), `intel`, `settings`, `daily_ranking`, `device`, `device_launch`,
`candidate_snapshot`, `news_signal`, `watchlist`. RLS ligado (a service_role passa
por cima). SQL em `specs/` / histórico do chat.

---

## 5. Fontes de dados

| Fonte | Módulo | Real? |
|-------|--------|-------|
| **Vendas internas** (planilha) | `collectors/sheets.py` → `internal_bi.py` | ✅ com API key; extrai o modelo após o último ` / `, soma por modelo, gera total + série mensal |
| **Proxy de IA** | `ai/proxy.py` | ✅ (formato OpenAI) |
| **Calendário / notícias** | `collectors/websearch.py` | ✅ busca web (Google Notícias RSS) + base curada (`news_seed.json`) como fallback |
| **Intel do analista** | `overrides.py` + `intel_parser.py` | ✅ |
| **Marketplace** | `collectors/sorftime.py` (real) + `mercadolivre.py`/`mock_seed.py` (mock) | ✅ Amazon BR via Sorftime; ML ainda mock |
| **Previsão sazonal** | `collectors/launch_calendar.py` | ✅ (histórico em `data/sample/`) |

`internal_bi` prioriza os dados da planilha (via `store`) e cai no CSV de exemplo
quando não houver. O calendário prioriza busca web real e cai na base curada
(`news_seed.json`) quando a busca não render — o "modo conhecimento" do agente
(pedir a data ao próprio modelo) segue desligado: o `gpt-5.5` não conhece datas
novas e só degradava os dados.

---

## 6. Estrutura

```
api/index.py             # entrypoint Vercel (handler)
vercel.json              # build + rotas + cron
requirements.txt         # requests (nuvem)
mithrandir/
  store.py               # I/O: Supabase REST ou arquivos locais
  _http.py               # HTTP (requests / urllib)
  config.py              # env / config.json (AI, ML, Sheets, Supabase)
  server.py              # app web + API + serve() local
  pipeline.py            # candidatos (score + viabilidade)
  scoring.py             # motor de priorização
  viability.py           # receita / breakeven
  launch_estimator.py    # calendário (intel > IA > heurística > sazonal) + apply_overrides_to
  internal_bi.py         # vendas internas (planilha/CSV) + similar + catálogo
  normalize.py           # normalização de nome de modelo (regras)
  normalize_ai.py        # limpeza de título de anúncio pela IA (com guard-rail)
  overrides.py           # intel (Supabase/arquivo)
  settings.py            # config (Supabase/arquivo)
  news_agent.py          # agente de notícias (watchlist)
  intel_parser.py        # texto livre -> override (IA/regex)
  dashboard.py           # export estático (python -m mithrandir run)
  ai/proxy.py            # cliente do proxy de IA
  collectors/            # sheets, sorftime, marketplace, mercadolivre, launch_calendar,
                         # news, websearch, mock_seed
data/
  news_seed.json         # base curada de lançamentos (real, versionada)
  watchlist.json         # devices que o agente vigia
  sample/                # exemplos (CSV BI, catálogo, histórico, vendas mensais)
tests/                   # unittest (82)
```

Estado local (gitignored): `config.json`, `data/{overrides,settings,app_cache,news_cache}.json`,
`data/mithrandir.db`, `output/`.

---

## 7. Limitações conhecidas / próximos passos

1. **Marketplace: Amazon real, ML ainda mock.** A tração real chega pelo Sorftime
   (ver §8). Falta o **Mercado Livre** (token grátis) em `collectors/mercadolivre.py`;
   enquanto isso ele devolve mock, que a ingestão da Amazon sobrescreve quando as
   chaves coincidem.
2. **Busca web: rate limit do Google.** O agente agora busca de verdade
   (`get_search_provider` → Google Notícias RSS, sem chave). Duas regras que vieram
   de medição, não de intuição: **sem aspas** na query (frase exata derrubou o
   resultado de 100 para 3 itens) e **consulta em inglês vai para o índice
   americano** (`hl=en-US`), que é onde a data oficial aparece cravada.
   O ponto fraco é o **429 (Too Many Requests)**: varrer a watchlist inteira dispara
   dezenas de buscas do mesmo IP. Mitigado com passo mínimo entre chamadas
   (`_MIN_INTERVAL`), 1 retentativa e `BULK_QUERIES=2` (a pesquisa de um device só
   usa as 3), mas ainda cai parte da watchlist em rodadas ruins. Falha é **segura**:
   o device mantém o sinal anterior (a base curada), e como cada rodada parte do
   cache anterior, a cobertura acumula entre execuções. Uma API de busca paga
   (Brave/Serper) resolveria — é só trocar o retorno de `get_search_provider`.
   Desligar: `MITHRANDIR_WEBSEARCH=off`.
   ⚠️ A rodada do agente leva ~45s, perto do `maxDuration: 60` do Vercel.
3. **Timeline de vendas.** A tabela `daily_ranking` existe mas ainda não é populada;
   quando o marketplace for real, gravar o top-N diário para a curva "bombou no
   lançamento vs engrenou depois".
4. **Loop de feedback (RF-08)** — registrar decisão + resultado real para recalibrar
   os pesos do score (`scoring.py::WEIGHTS`).
5. **Custos por device** — hoje globais na aba Config; poderiam ser por modelo.

---

## 8. Ingestão de marketplace (Sorftime → app)

O Sorftime **só é acessível via MCP**, dentro de uma sessão do Claude — o app no
Vercel não consegue chamar a ferramenta. Por isso o desenho é *produtor externo →
endpoint de ingestão*, e toda a transformação mora em código testado no repo
(`collectors/sorftime.py`), não no prompt do agente.

```
tarefa agendada (seg, 08h)  ──MCP──>  Sorftime (Amazon BR, node 16243890011)
        │
        └── python -m mithrandir ingest coleta.json
                    │  (token do config local, nunca no prompt)
                    ▼
        POST /api/marketplace/ingest  ──>  agrega por modelo  ──>  store
                                                │
                                    marketplace_snapshot (rankings da UI)
                                    marketplace_observations (tração do pipeline)
                                    marketplace_history (momentum semana a semana)
```

**Por que semanal:** a venda que o Sorftime devolve é estimativa **mensal**. Coleta
diária mediria ruído; semanal ainda dá 4 pontos por mês para o momentum.

**O que a agregação faz** (o ponto que importa): um modelo aparece em vários ASINs
— o iPhone 16 tinha 7 na coleta de 2026-08-29. Venda e faturamento **somam**;
avaliações usam o **maior** (na Amazon as variantes compartilham as reviews do ASIN
pai, somar contaria duas vezes); preço/nota/título vêm do ASIN líder; `online_date`
é a mais antiga (é quando o modelo apareceu na loja). 99 anúncios → 68 modelos.

### Configuração necessária
| Onde | O quê |
|------|-------|
| Vercel (env) | `MITHRANDIR_INGEST_TOKEN` — sem ela o endpoint responde 503 |
| Máquina local (`config.json`) | `ingest_token` (o mesmo valor) e `app_url` (URL do app no Vercel) |

### Armadilha registrada: `canonicalize` não é idempotente
`canonicalize("APPLE 16 E")` devolve `"APPLE 16"` — o `"e"` solto é tratado como
conector do português (`_CONECTOR` em `normalize.py`, que existe para limpar
"Moto g86 5G **e** Câmera"). Consequência: recanonicalizar uma chave já canônica
**funde o iPhone 16e no iPhone 16** e a tração de um sobrescreve a do outro — dois
aparelhos distintos, capinhas distintas.

Por isso o pipeline usa `o["canonical_model"]` quando a coleta traz a chave pronta,
em vez de passar o título cru por `canonicalize` de novo. Há teste de regressão em
`tests/test_sorftime.py::TestPipelineUsaAChaveDoColetor`. **Não** recanonicalize
chaves de coleta.

### "Já temos capinha" vem da base de vendas, não do CSV
`load_catalog()` lia só `data/sample/catalog_sample.csv` — 4 linhas de exemplo.
Resultado: a penalidade `already_have_case` (que em `scoring.py` também ordena:
"já temos → não é candidato") **nunca disparava**, e o app recomendava iPhone 16
(41 mil capinhas vendidas na Gocase) como novidade. Agora o catálogo é a união de:

1. **a base interna de vendas** (158 modelos reais) — se vendemos capinha do
   modelo, temos capinha dele;
2. o CSV, para capinha que existe mas ainda não vendeu.

### Limpeza de título pela IA (`normalize_ai.py`)
As regras de `normalize.py` são enxuga-gelo: cada coleta traz cor/edição inédita
("Awesome Lavender", "Pantone Greener Pastures", "Crystals by Swarovski") e cada
uma vira um candidato duplicado com a venda fatiada. Medido em ruído inédito: a
**regra errou 7 de 8, a IA acertou 8 de 8**.

A IA **não** substitui as regras — elas são o piso. Ordem:

1. a regra sempre roda;
2. a IA só vence quando **não contradiz** a regra na **marca** (sempre) e na
   **geração** (quando a regra achou uma). Se a regra não achou geração, o número
   que a IA usou precisa aparecer no título — foi assim que `"Smartphone TCL
   256GB ... mAh TCL 605"` (modelo no fim do título, regra devolvia só `TCL`)
   passou a virar `TCL 605`;
3. sem proxy, falha de rede ou JSON torto → tudo cai na regra e a ingestão segue.

⚠️ A saída da IA passa por `_formatar` para respeitar o invariante da casa
(**dígito nunca colado em letra**): a IA devolvia `XIAOMI 15C` onde o BI e a regra
usam `XIAOMI 15 C`. Não dá para simplesmente passar a chave por `canonicalize` —
ela não é idempotente e refaria a fusão do 16e no 16 (ver acima).

Custo: ~20s na primeira coleta (3 lotes de 40 títulos, em paralelo — em série
eram 53s, perto demais do teto de 60s do Vercel). O resultado é cacheado por
título (`title_keys`), e como a coleta semanal repete quase tudo, da segunda
rodada em diante são ~3s.

### Filtro de não-celular na ingestão
A categoria "Celulares e Smartphones" da Amazon traz intruso (o **Meta Quest 3S**
veio no top 100) e o `product_category` do Sorftime vem **vazio em 72 dos 99**
anúncios — não serve de filtro. Dois critérios, nesta ordem: a **IA** devolve chave vazia para o que não é
celular — pega até o que a marca não pega, porque um `Galaxy Tab S10 FE` tem
marca Samsung legítima e passaria batido. Sem IA, o piso é ter **marca
reconhecida** (`normalize.BRANDS`).

⚠️ **O custo é uma marca nova sumir calada.** Aconteceu na primeira rodada: OPPO e
TCL — celulares de verdade — foram descartados por não estarem no `BRANDS`. Foram
adicionados (junto de Honor, Nokia, ZTE, Multilaser, Philco). Se um modelo
relevante não aparecer no scouting, **o primeiro lugar a olhar é o `BRANDS`**; a
contagem de descartados vem no retorno da ingestão e no log (`descartados`).
