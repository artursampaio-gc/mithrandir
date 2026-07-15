# 08 — Perguntas em Aberto

Decisões pendentes que precisam de resposta antes/durante a implementação. Atualizar conforme forem resolvidas.

## Dados internos (BI)
- [ ] **Qual é a ferramenta de BI?** (Metabase, Power BI, Looker, Tableau, Qlik…) — define como conectar.
- [ ] O BI expõe **API/dataset** ou só dashboards visuais?
- [ ] Existe uma **taxonomia de família/linha** de aparelho, ou precisamos construir?
- [ ] A base liga SKU de capinha → **modelo de aparelho** de forma limpa?
- [ ] Que métricas de desempenho estão disponíveis (margem? sell-through? devoluções?)?

## Proxy de IA interno
- [ ] Endpoint, formato (compatível com OpenAI?), modelos disponíveis.
- [ ] Quota/rate limit e como o custo é cobrado internamente.
- [ ] Há restrição sobre enviar dados de terceiros (conteúdo de marketplaces/notícias) ao proxy?

## Marketplaces
- [ ] Quais contas de **seller** a Gocase tem e quais expõem API/relatórios de categoria?
- [ ] Para a Amazon BR: usamos afiliado (Product Advertising API), dados de seller, ou scraping?
- [ ] Há tolerância jurídica/SecInfo para scraping onde não houver API?

## Infra e execução
- [ ] Onde os jobs diários vão rodar (cloud interna? servidor? qual)?
- [ ] Onde guardar segredos (cofre corporativo)?
- [ ] Quem mantém o sistema no dia a dia depois de pronto?

## Produto / negócio
- [ ] Quais **pesos iniciais** do score (definir com o time)?
- [ ] Quais marcas/linhas entram no v1 (todas as principais ou um subconjunto)?
- [ ] O que exatamente conta como "sucesso de vendas" para virar candidato pós-lançamento (limiar)?
- [ ] Quem é o **sponsor** do projeto?

## Método de construção
- [ ] O MVP será feito por você (com IA) e depois passado a um time de dev, ou há dev interno desde já?
   *(Ficou entre "eu com apoio de IA" e o proxy obrigatório — confirmar.)*
