# 04 — Acessos e Stakeholders

Esta é a spec mais importante para **destravar o projeto**. Sem acesso a dados, nada roda. Abaixo: o que pedir, por que, e com quem falar.

## Mapa de conversas (por ordem de prioridade)

### 1. BI / Dados / Analytics  — *prioridade máxima*
- **O que pedir:**
  - Acesso de leitura ao BI **ou** um dataset/consulta recorrente com: modelo de aparelho, vendas de capinha (unidades, receita, margem), sell-through, catálogo atual.
  - De preferência acesso via **API/conexão** do BI (ex.: API do Metabase, dataset no data warehouse), não export manual.
  - A **taxonomia** de família/linha de aparelho, se já existir.
- **Por que:** é o que valida "modelo similar vendeu bem/mal" (RF-04) — o coração da priorização.
- **Falar com:** Head/Coordenador de BI ou Analytics (dono da ferramenta de BI).

### 2. E-commerce / Marketplaces  — *prioridade alta*
- **O que pedir:**
  - Acesso (ou extrações) das contas de **seller** da Gocase no Mercado Livre, Amazon, Magalu e Americanas.
  - Saber se já existe **integração/API de seller** configurada e quem a mantém.
  - Insights de categoria de celulares que essas contas já expõem.
- **Por que:** caminho de dados de marketplace mais confiável e alinhado a ToS que scraping (RF-03).
- **Falar com:** Gerente de Marketplaces / E-commerce.

### 3. Dono do proxy de IA (GPT interno)  — *bloqueante técnico*
- **O que pedir:**
  - Endpoint, credenciais e **quota** do proxy interno.
  - Limites de rate, modelos disponíveis, política de uso de dados, custo/cobrança interna.
- **Por que:** uso do proxy é **obrigatório** (RNF-01) para extração de entidade, matching e resumos.
- **Falar com:** time que mantém a IA interna (Inovação / Dados / Plataforma).

### 4. TI / Infraestrutura / DevOps
- **O que pedir:**
  - Onde hospedar os coletores (servidor/cloud interno), **agendamento** (cron/job diário), banco de dados.
  - Cofre de segredos para chaves de API (RNF-05).
  - Whitelist de IP / proxy de saída, se scraping for necessário.
- **Por que:** o sistema precisa rodar sozinho todo dia (RNF-02).
- **Falar com:** TI / DevOps / Plataforma.

### 5. Segurança da Informação / Jurídico
- **O que pedir:**
  - Aval sobre coleta de dados de marketplaces (ToS, scraping) e uso das APIs.
  - Diretrizes de uso de dados internos.
- **Por que:** evitar risco legal/compliance (RNF-03).
- **Falar com:** SecInfo / Jurídico.

### 6. Seu time (Desenvolvimento de Produto / Sourcing) + gestor
- **O que alinhar:**
  - Critérios do que é um "bom candidato" e os **pesos iniciais** do score.
  - Fechar o **loop de feedback** (registrar acertos/erros para calibrar).
  - Priorização do projeto e sponsor.
- **Por que:** garante que o output resolve a dor real e ganha adoção (RF-08).
- **Falar com:** seu gestor direto + pares de scouting.

## Checklist de acessos

- [ ] Acesso de leitura / dataset do BI (com taxonomia de modelos)
- [ ] Credencial de app da **API do Mercado Livre**
- [ ] Definição do caminho de dados Amazon BR (seller / afiliado / scraping)
- [ ] Acesso a contas de seller Magalu e Americanas (ou extrações)
- [ ] Endpoint + credencial + quota do **proxy de IA interno**
- [ ] Ambiente para rodar jobs diários + cofre de segredos (TI)
- [ ] Aval de SecInfo/Jurídico sobre coleta
- [ ] Sponsor e pesos iniciais validados com o gestor

## Sugestão de sequência
Comece por **BI (1)** e **proxy de IA (3)** — são os dois bloqueantes que definem se o MVP é viável. Em paralelo, mapeie com **Marketplaces (2)** o que já existe de acesso de seller.
