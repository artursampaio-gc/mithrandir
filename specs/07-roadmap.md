# 07 — Roadmap

Sequência por fases. Cada fase entrega valor sozinha e destrava a próxima.

## Fase 0 — Descoberta e acessos  *(bloqueante — começar já)*
**Objetivo:** conseguir os acessos e validar viabilidade.
- Conversas da spec [04](04-acessos-stakeholders.md): BI, proxy de IA, Marketplaces, TI, SecInfo, gestor.
- Confirmar qual é a ferramenta de BI e como conectar.
- Obter credencial do proxy de IA e da API do Mercado Livre.
- Definir sponsor e pesos iniciais do score.
- **Entregável:** checklist de acessos concluído + decisão go/no-go do MVP.

## Fase 1 — MVP assistido  *(prova de valor)*
**Objetivo:** provar o conceito com esforço mínimo, mesmo que semi-manual.
- Montar o **calendário histórico de lançamentos** das linhas principais.
- Puxar do BI o desempenho de capinha por modelo/família.
- Coletar tração via **API do Mercado Livre** (fonte mais fácil e rica).
- Score simples (planilha ou app leve) combinando previsão + similar interno + tração ML.
- **Entregável:** primeiro ranking de candidatos revisado com você. Valida a fórmula.

## Fase 2 — Automação da coleta
**Objetivo:** rodar sozinho todo dia.
- Coletores agendados: notícias/GSMArena, Mercado Livre, e o 2º marketplace (Amazon BR ou Magalu).
- Banco de dados com série temporal + normalização de modelo (regras + proxy de IA).
- Enriquecimento por IA (extração de entidade, matching de similaridade).
- **Entregável:** pipeline diário automatizado alimentando o score.

## Fase 3 — Dashboard e alertas
**Objetivo:** entrega do produto ao usuário final.
- Dashboard com ranking, filtros e drill-down explicável.
- Alertas (limiar de score, disparo de vendas, janela de lançamento próxima).
- Cobrir os 4 marketplaces.
- **Entregável:** dashboard em uso no dia a dia.

## Fase 4 — Calibração e escala
**Objetivo:** ficar mais preciso com o tempo.
- Loop de feedback ligado (decisão + resultado real → recalibra pesos).
- Ampliar marcas/linhas cobertas.
- Medir as métricas de sucesso da spec [01](01-visao.md).
- **Entregável:** modelo de score calibrado + relatório de desempenho.

## Princípio de sequenciamento
> Cada fase depende da anterior **e** dos acessos da Fase 0. Não vale pular a Fase 0 — sem dados internos (BI) e sem proxy de IA, o MVP não fecha.
