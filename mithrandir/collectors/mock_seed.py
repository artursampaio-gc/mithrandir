"""Dados de exemplo para rodar o pipeline sem credenciais (modo mock).

Representa o estado tipico enquanto os acessos (BI, IA, marketplaces) nao foram
liberados. Inclui o caso "Motorola G86" (sucesso de vendas pos-lancamento) para
demonstrar a captura de tracao.
"""
from __future__ import annotations


def marketplace_observations() -> list[dict]:
    """Observacoes de tracao simuladas (como viriam do Mercado Livre/Amazon)."""
    return [
        {"raw_name": "Samsung Galaxy A56 5G 256GB", "source": "mercadolivre",
         "rank": 1, "sold_qty": 5200, "review_count": 1850, "rating": 4.6,
         "price": 1999.0, "offers": 40, "momentum": 55,
         "rankings": [
             {"store": "amazon", "position": "Top #3", "criterio": "Geral", "value": 1999.0, "reviews": 1850},
             {"store": "amazon", "position": "Top #1", "criterio": "entre os Samsung", "value": 1999.0, "reviews": 1850},
             {"store": "mercadolivre", "position": "Top #1", "criterio": "Geral", "value": 1980.0, "reviews": 9800},
             {"store": "magazineluiza", "position": "Top #2", "criterio": "Geral", "value": 1999.0, "reviews": 2100},
         ]},
        {"raw_name": "Motorola Moto G86 5G 256GB", "source": "mercadolivre",
         "rank": 2, "sold_qty": 4800, "review_count": 1620, "rating": 4.7,
         "price": 1799.0, "offers": 33, "momentum": 92,
         "rankings": [
             {"store": "amazon", "position": "Top #7", "criterio": "Geral", "value": 1299.0, "reviews": 722},
             {"store": "amazon", "position": "Top #1", "criterio": "entre os Motorola", "value": 1299.0, "reviews": 722},
             {"store": "mercadolivre", "position": "-", "criterio": "Geral", "value": 1280.0, "reviews": 12189},
             {"store": "magazineluiza", "position": "Top #2", "criterio": "Geral", "value": 1299.0, "reviews": 1601},
             {"store": "magazineluiza", "position": "Top #1", "criterio": "entre os Motorola", "value": 1299.0, "reviews": 1601},
         ]},
        {"raw_name": "Xiaomi Redmi Note 14 Pro", "source": "mercadolivre",
         "rank": 4, "sold_qty": 3100, "review_count": 1240, "rating": 4.5,
         "price": 1699.0, "offers": 28, "momentum": 70,
         "rankings": [
             {"store": "amazon", "position": "Top #5", "criterio": "Geral", "value": 1699.0, "reviews": 1240},
             {"store": "mercadolivre", "position": "Top #3", "criterio": "Geral", "value": 1650.0, "reviews": 8300},
             {"store": "magazineluiza", "position": "Top #4", "criterio": "Geral", "value": 1699.0, "reviews": 980},
         ]},
        {"raw_name": "Realme C75 256GB", "source": "mercadolivre",
         "rank": 9, "sold_qty": 1400, "review_count": 380, "rating": 4.3,
         "price": 1299.0, "offers": 12, "momentum": 48,
         "rankings": [
             {"store": "mercadolivre", "position": "Top #18", "criterio": "Geral", "value": 1299.0, "reviews": 1900},
         ]},
        {"raw_name": "Samsung Galaxy S25 FE 256GB", "source": "mercadolivre",
         "rank": 14, "sold_qty": 900, "review_count": 610, "rating": 4.6,
         "price": 3299.0, "offers": 18, "momentum": 20,
         "rankings": [
             {"store": "amazon", "position": "Top #12", "criterio": "Geral", "value": 3299.0, "reviews": 610},
             {"store": "mercadolivre", "position": "-", "criterio": "Geral", "value": 3250.0, "reviews": 3400},
         ]},
        {"raw_name": "Motorola Moto E15", "source": "mercadolivre",
         "rank": 22, "sold_qty": 700, "review_count": 210, "rating": 4.0,
         "price": 799.0, "offers": 8, "momentum": 15,
         "rankings": [
             {"store": "mercadolivre", "position": "Top #30", "criterio": "Geral", "value": 799.0, "reviews": 210},
         ]},
    ]


def news_headlines() -> list[dict]:
    """Manchetes simuladas de portais de tecnologia."""
    return [
        {"title": "Samsung Galaxy S26 FE aparece em vazamento com nova camera",
         "link": "https://exemplo/s26fe", "source": "mock"},
        {"title": "Motorola Moto G86 vira campeao de vendas na Amazon e Magalu",
         "link": "https://exemplo/g86", "source": "mock"},
        {"title": "Xiaomi Redmi Note 15 deve chegar ao Brasil no fim do ano",
         "link": "https://exemplo/note15", "source": "mock"},
    ]
