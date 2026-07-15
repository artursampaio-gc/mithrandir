# 01 — Visão e Objetivos

## Visão

Substituir o scouting manual de novos modelos de celular por um sistema que, **todo dia**, coleta sinais de lançamento e de vendas, cruza com o histórico interno da Gocase e entrega um **ranking priorizado de candidatos** a desenvolvimento de capinha — com a justificativa por trás de cada posição.

## Objetivos de negócio

1. **Antecipar lançamentos** com semanas/meses de antecedência, para chegar com capinha no lançamento (ou antes dos concorrentes).
2. **Reduzir erro de aposta** — evitar desenvolver capinha para modelo que vai vender pouco, usando o desempenho de modelos similares.
3. **Capturar sucessos inesperados** — detectar rápido quando um modelo "fora do radar" dispara nas vendas do marketplace (caso Motorola G86).
4. **Escalar a cobertura** — monitorar muito mais modelos/marcas do que é viável manualmente.

## Métricas de sucesso

| Métrica | Como medir | Alvo inicial |
|---------|-----------|--------------|
| Cobertura | % de lançamentos relevantes detectados pelo sistema antes de entrarem no radar manual | > 80% |
| Antecedência | Dias entre detecção do candidato e o lançamento real | Ganhar dias vs. hoje |
| Precisão do ranking | Dos candidatos que viraram capinha, % que estava no top do ranking | Acompanhar e calibrar |
| Falsos negativos | Modelos que viraram sucesso e o sistema **não** flagou | Tender a zero |
| Tempo economizado | Horas/semana de scouting manual | Reduzir |

## Escopo (v1)

**Dentro:**
- Celulares vendidos no Brasil, marcas principais (Samsung, Motorola, Xiaomi/Redmi/POCO, Apple, realme, e outras relevantes).
- Marketplaces BR: Amazon BR, Mercado Livre, Magazine Luiza, Americanas/Casas Bahia.
- Cruzamento com base interna de vendas de capinhas (via BI).
- Dashboard de ranking com drill-down.

**Fora (por ora):**
- Precificação/decisão de compra de estoque.
- Design/mockup da capinha.
- Outros acessórios além de capinha.
- Mercados fora do Brasil.

## Não-objetivos

- Não substitui o julgamento do analista — é uma ferramenta de **apoio à decisão**. O ranking sugere; a pessoa decide (e o feedback dela realimenta o modelo).
