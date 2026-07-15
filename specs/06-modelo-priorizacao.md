# 06 — Modelo de Priorização

O coração do Mithrandir: transformar sinais em um **score de candidato** ordenável e explicável.

## Fórmula (v1 — proposta para calibrar)

```
Score = w1·SinalLancamento
      + w2·DesempenhoSimilarInterno
      + w3·TracaoMarketplace
      + w4·MomentumNoticias
      − Penalidades
```

Cada componente é normalizado 0–100. Pesos (`w`) somam 1 e são **ajustáveis** e recalibrados pelo loop de feedback (RF-08).

## Componentes

### SinalLancamento (previsão sazonal — RF-01)
- Proximidade da janela prevista de lançamento (baseada no ano anterior).
- Confiança da previsão (histórico consistente da linha aumenta).
- Ex.: S25FE em set/2025 → alta pontuação para S26FE conforme set/2026 se aproxima.

### DesempenhoSimilarInterno (base BI — RF-04)
- Quão bem o(s) modelo(s) similar(es) venderam **como capinha** (unidades, receita, margem, sell-through).
- Peso maior quando há similar direto e forte na base.

### TracaoMarketplace (RF-03)
- Posição no ranking de mais vendidos + nº de avaliações (proxy de volume) + nota.
- Só existe **pós-lançamento** (o modelo já está à venda).

### MomentumNoticias / MomentumVendas
- Velocidade de crescimento: subida no ranking, aceleração de avaliações, volume de notícias.
- **É o sinal que teria pego o Motorola G86 cedo.**

## Penalidades
- **Já temos capinha** para o modelo → forte penalidade (evita duplicidade).
- **Família similar vendeu mal** → penalidade / desclassificação (a regra que você já usa hoje).
- Modelo de nicho / fora do perfil de público → penalidade leve.

## Ponderação por fase do ciclo

O peso relativo muda conforme o modelo está antes ou depois do lançamento:

| Fase | Peso maior em | Racional |
|------|---------------|----------|
| **Pré-lançamento** | SinalLancamento + DesempenhoSimilarInterno | Ainda não há vendas reais; aposta-se no histórico. |
| **Pós-lançamento** | TracaoMarketplace + Momentum | Dados reais de mercado disponíveis; caso G86. |

## Explicabilidade (RNF-07)
Cada score guarda a decomposição: quanto veio de cada componente e quais penalidades incidiram. O dashboard mostra isso no drill-down — a pessoa entende *por que* o candidato está ali.

## Calibração (loop de feedback — RF-08)
1. Registrar a decisão (desenvolveu / descartou) e o resultado real (vendeu bem / mal).
2. Comparar com o que o score previu.
3. Ajustar pesos e penalidades periodicamente.
4. Meta: reduzir falsos negativos (sucessos não flagados) e melhorar a precisão do top do ranking.

> Os pesos iniciais devem ser definidos junto com você e o time (ver [04](04-acessos-stakeholders.md), conversa 6), não chutados pelo sistema.
