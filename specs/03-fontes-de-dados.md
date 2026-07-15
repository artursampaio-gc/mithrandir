# 03 — Fontes de Dados

Onde cada dado vem, o método de coleta e a confiabilidade. Legenda de método: **API** (oficial), **Seller** (conta de vendedor da Gocase no marketplace), **Scraping** (extração da página), **Feed** (RSS/notícias).

## A. Lançamentos e especificações de celulares (externo)

| Fonte | O que dá | Método | Observações |
|-------|----------|--------|-------------|
| GSMArena | Specs, data de anúncio/lançamento, "rumor mill" | Scraping / dataset | Melhor base de calendário de lançamentos. Sem API oficial. |
| Sites oficiais dos fabricantes | Anúncios confirmados | Scraping / Feed | Samsung, Motorola, Xiaomi, Apple, realme, etc. |
| Tech BR: Tecnoblog, Tudocelular, Canaltech, Adrenaline, Olhar Digital | Rumores, prévias, datas BR | Feed (RSS) | Ótimo para o timing do lançamento **no Brasil**. |
| Google News / Bing News | Cobertura ampla por marca+modelo | API/Feed | Consulta por termos; requer deduplicação. |

➡️ Desses dados construímos o **calendário histórico** que alimenta a previsão sazonal (RF-01).

## B. Tração de vendas nos marketplaces (externo — Brasil)

| Marketplace | O que dá | Método preferido | Observações |
|-------------|----------|------------------|-------------|
| **Mercado Livre** | Busca de produtos, preço, `sold_quantity`, avaliações | **API oficial** | Fonte estruturada mais rica. `developers.mercadolivre.com.br`. Requer app/credencial. |
| **Amazon BR** | Ranking "Mais Vendidos" por categoria, nº avaliações, nota | Seller / API / Scraping | Product Advertising API exige conta de afiliado aprovada. Best Sellers também via scraping do ranking. |
| **Magazine Luiza** | Busca, vitrine, avaliações | Seller / Scraping | Magalu tem API de **marketplace para sellers**. |
| **Americanas / Casas Bahia** | Busca, ranking, avaliações | Scraping | Sem API pública ampla. |

### ⭐ Insight importante — usar as contas de *seller* da Gocase
A Gocase **já vende** nesses marketplaces. As contas de seller (e as APIs de seller / relatórios de categoria) são uma fonte de dados **legítima e alinhada aos ToS** — muito melhor que scraping. Vale confirmar com o time de Marketplaces o que já existe (ver [04](04-acessos-stakeholders.md)).

### Sinais úteis por produto (derivados)
- Posição no ranking de mais vendidos.
- Nº de avaliações (proxy de volume de vendas).
- Nota média.
- Nº de anúncios/vendedores ofertando o modelo.
- Variação de preço.
- **Momentum**: velocidade de acúmulo de avaliações / subida no ranking (o sinal do "G86").

## C. Base interna Gocase (via BI)

| Dado | Uso |
|------|-----|
| Vendas históricas de capinha por **modelo de aparelho** (SKU → modelo) | Desempenho do similar |
| Receita, margem, unidades, sell-through, curva de vida | Qualidade da aposta |
| Devoluções / reclamações | Ajuste de risco |
| Catálogo atual (modelos que já têm capinha) | Evitar duplicidade (penalidade) |
| Taxonomia de família/linha de aparelho | Casar novo modelo ao "similar" |

➡️ Acesso via ferramenta de BI (confirmar qual — ver [08](08-perguntas-abertas.md)). Idealmente uma **conexão/dataset recorrente**, não export manual.

## D. Dado derivado/gerado pelo próprio sistema

- **Mapa de similaridade** modelo novo → modelo(s) existente(s), gerado com apoio do proxy de IA (casamento semântico de nome/linha/faixa).
- **Calendário de previsão** de janelas de lançamento.
- **Histórico de sinais** (série temporal por modelo) para momentum e recalibração.

## Riscos de dados
- Scraping pode quebrar quando o site muda; APIs oficiais e contas de seller reduzem o risco.
- Normalização de nome de modelo é não-trivial (ex.: "Galaxy S26 FE" vs "S26FE" vs "Samsung S26 Fan Edition") — tratado com IA + regras.
