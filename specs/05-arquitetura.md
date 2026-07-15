# 05 — Arquitetura

## Visão geral do fluxo

```
  FONTES                COLETA (diária)         PROCESSAMENTO            ENTREGA
  ┌──────────────┐      ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
  │ GSMArena     │      │ Coletor       │        │ Normalização │        │              │
  │ Tech news    │─────▶│ lançamentos/  │───────▶│ + dedup de   │        │              │
  │ (RSS)        │      │ notícias      │        │ modelo       │        │              │
  ├──────────────┤      ├──────────────┤        │ (regras+IA)  │        │              │
  │ Mercado Livre│      │ Coletor       │        ├──────────────┤        │  DASHBOARD   │
  │ Amazon BR    │─────▶│ marketplaces  │───────▶│ Enriquecimento│──────▶│  (ranking +  │
  │ Magalu       │      │ (API/seller/  │        │ por IA (proxy)│        │  drill-down) │
  │ Americanas   │      │  scraping)    │        │ - extração    │        │              │
  ├──────────────┤      ├──────────────┤        │ - matching    │        │  + ALERTAS   │
  │ BI Gocase    │─────▶│ Conector BI   │───────▶│ - resumo      │        │              │
  │ (interno)    │      │               │        ├──────────────┤        │              │
  └──────────────┘      └──────────────┘        │ Motor de      │        │              │
                              │                  │ priorização   │───────▶│              │
                              ▼                  │ (score)       │        └──────▲───────┘
                        ┌──────────────┐         └──────┬───────┘               │
                        │ Banco de dados (série temporal de sinais + scores)     │
                        └───────────────────────────────────────────────────────┘
                                        ▲  loop de feedback (decisão + resultado real)
```

## Componentes

### 1. Coletores (ingestão)
- Um coletor por tipo de fonte, agendado (job diário).
- Cada coletor é isolado: falha de um não derruba os outros (RNF-02).
- Preferência: **API oficial > conta de seller > scraping**.

### 2. Normalização e deduplicação de modelo
- Resolve o mesmo aparelho escrito de formas diferentes ("Galaxy S26 FE" / "S26FE" / "Samsung S26 Fan Edition").
- Regras determinísticas + **proxy de IA** para casos ambíguos.
- Chave canônica de modelo → liga sinais externos ao registro interno.

### 3. Camada de IA (via proxy interno — RNF-01)
Usos:
- **Extração de entidade** — tirar modelo/data de notícias não estruturadas.
- **Matching de similaridade** — casar modelo novo com similar da base Gocase.
- **Resumo diário** — texto explicativo do porquê de cada candidato subir.
- Cache das respostas para controlar quota/custo (RNF-06).

### 4. Banco de dados
- Entidades: `modelo`, `sinal_diario`, `desempenho_interno`, `score_historico`, `decisao_feedback`.
- Série temporal preservada para calcular **momentum** e recalibrar (RNF-04).

### 5. Motor de priorização
- Calcula o score por candidato (ver [06](06-modelo-priorizacao.md)).
- Explicável: guarda a decomposição do score (RNF-07).

### 6. Dashboard + alertas
- Ranking, filtros, drill-down por candidato.
- Alertas por limiar de score / disparo de vendas / janela de lançamento próxima.

## Notas de decisão de arquitetura

- **IA:** somente via proxy interno. Toda a camada de IA fala com um único cliente configurável (endpoint/credencial do proxy).
- **Agendamento:** job diário (definir horário com TI). Idempotente — reprocessar o mesmo dia não duplica.
- **Build:** favorecer componentes simples e substituíveis, dado que o proxy de IA é o padrão obrigatório da empresa. Detalhe de stack fica para a fase de implementação, após validar acessos (ver [07](07-roadmap.md)).
