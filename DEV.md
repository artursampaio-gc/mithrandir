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
| Tração de marketplace (Mercado Livre etc.) | ⚠️ **mock** (falta token da API) |
| Agente de notícias (busca web) | ⚠️ desligado (falta API de busca; ver §7) |
| Deploy | ✅ Vercel + Supabase |

---

## 2. Rodar local

```powershell
python -m mithrandir serve        # app web em http://127.0.0.1:8756
python -m mithrandir run          # pipeline -> gera output/dashboard.html (estático)
python -m mithrandir agent        # roda o agente de notícias (no-op sem API de busca)
python -m mithrandir info         # mostra config/modo atual
python -m unittest discover -s tests   # testes (28)
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
| **Calendário / notícias** | `collectors/websearch.py` (`news_seed.json`) | ✅ base curada; agente de busca web = pendente |
| **Intel do analista** | `overrides.py` + `intel_parser.py` | ✅ |
| **Marketplace** | `collectors/mercadolivre.py` + `mock_seed.py` | ⚠️ mock (falta token ML) |
| **Previsão sazonal** | `collectors/launch_calendar.py` | ✅ (histórico em `data/sample/`) |

`internal_bi` prioriza os dados da planilha (via `store`) e cai no CSV de exemplo
quando não houver. O calendário prioriza busca web real e cai na base curada
(`news_seed.json`) — o "modo conhecimento" do agente foi desligado (§7).

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
  normalize.py           # normalização de nome de modelo
  overrides.py           # intel (Supabase/arquivo)
  settings.py            # config (Supabase/arquivo)
  news_agent.py          # agente de notícias (watchlist)
  intel_parser.py        # texto livre -> override (IA/regex)
  dashboard.py           # export estático (python -m mithrandir run)
  ai/proxy.py            # cliente do proxy de IA
  collectors/            # sheets, mercadolivre, launch_calendar, news, websearch, mock_seed
data/
  news_seed.json         # base curada de lançamentos (real, versionada)
  watchlist.json         # devices que o agente vigia
  sample/                # exemplos (CSV BI, catálogo, histórico, vendas mensais)
tests/                   # unittest (28)
```

Estado local (gitignored): `config.json`, `data/{overrides,settings,app_cache,news_cache}.json`,
`data/mithrandir.db`, `output/`.

---

## 7. Limitações conhecidas / próximos passos

1. **Marketplace ainda mock.** Ligar a **API do Mercado Livre** (token grátis) em
   `collectors/mercadolivre.py` — vira a maior fonte real de tração. Amazon/Magalu
   não têm API pública gratuita (ver spec 03).
2. **Agente de notícias desligado.** O `gpt-5.5` não conhece datas de 2026 (corte de
   treino), então o "modo conhecimento" só degradava os dados. Falta uma **API de
   busca web**: plugar em `collectors/websearch.py::get_search_provider` (hoje `None`);
   feito isso, o agente volta a atualizar sozinho e sobrepõe a base curada.
3. **Timeline de vendas.** A tabela `daily_ranking` existe mas ainda não é populada;
   quando o marketplace for real, gravar o top-N diário para a curva "bombou no
   lançamento vs engrenou depois".
4. **Loop de feedback (RF-08)** — registrar decisão + resultado real para recalibrar
   os pesos do score (`scoring.py::WEIGHTS`).
5. **Custos por device** — hoje globais na aba Config; poderiam ser por modelo.
