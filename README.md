# Mithrandir

Sistema de *scouting* de novos modelos de celular para priorização de desenvolvimento de capinhas na Gocase.

> "O Mithrandir busca novos celulares, analisa diariamente as vendas nos maiores marketplaces do Brasil, valida contra modelos similares da nossa base e mostra os melhores candidatos em um dashboard."

## O problema que resolve

Hoje o scouting é **manual**:
1. **Previsão sazonal** — olho o que lançou ano passado para prever o deste ano (ex.: S25FE lançou em set/2025 → S26FE deve lançar em set/2026).
2. **Validação com base interna** — se o modelo similar vendeu bem como capinha, priorizo; se vendeu mal, desclassifico a família.
3. **Tração pós-lançamento** — alguns modelos só entram no radar quando viram sucesso de vendas no marketplace (ex.: Motorola G86 na Amazon e Magazine Luiza).

O Mithrandir automatiza e cruza esses três sinais, gerando um **ranking diário de candidatos**.

## Como este repositório está organizado (spec-driven)

As specs são a fonte da verdade. Escrevemos e aprovamos a spec **antes** de implementar.

| Spec | Conteúdo |
|------|----------|
| [01 — Visão e Objetivos](specs/01-visao.md) | Problema, objetivos, métricas de sucesso, escopo |
| [02 — Requisitos](specs/02-requisitos.md) | Requisitos funcionais e não-funcionais |
| [03 — Fontes de Dados](specs/03-fontes-de-dados.md) | De onde vem cada dado (externo e interno) |
| [04 — Acessos e Stakeholders](specs/04-acessos-stakeholders.md) | O que preciso acessar e **com quem falar na empresa** |
| [05 — Arquitetura](specs/05-arquitetura.md) | Componentes, fluxo de dados, uso do proxy de IA |
| [06 — Modelo de Priorização](specs/06-modelo-priorizacao.md) | Como o score de candidato é calculado |
| [07 — Roadmap](specs/07-roadmap.md) | Fases, entregáveis e sequência |
| [08 — Perguntas em Aberto](specs/08-perguntas-abertas.md) | Decisões pendentes |

## Decisões já tomadas

- **IA:** uso obrigatório do **proxy interno de GPT** da empresa para qualquer LLM.
- **Mercado:** Brasil — Amazon BR, Mercado Livre, Magazine Luiza, Americanas/Casas Bahia.
- **Dados internos:** disponíveis em **ferramenta de BI**.

## Próximo passo

Ler a spec [04 — Acessos e Stakeholders](specs/04-acessos-stakeholders.md) e agendar as conversas de acesso a dados. Sem os acessos, o resto não anda.
