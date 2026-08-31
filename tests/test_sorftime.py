import unittest
from unittest import mock

from mithrandir import store
from mithrandir.collectors import sorftime

# Recorte real da coleta do Sorftime (Amazon BR, 2026-08-29), com os casos que
# quebraram na integracao: variantes do mesmo modelo, numero como string,
# online_date nulo e o par iPhone 16 / 16e.
RAW = [
    {"asin": "B0FPYV6K68", "title": "Celular Samsung Galaxy A17, 128GB, 4GB, 50MP - Preto",
     "brand": "Samsung", "monthly_sales_volume": "6285", "monthly_sales_amount": "5651000",
     "price": 899.1, "review_count": "1081", "star_rating": 4.8, "online_date": "2025-09-08"},
    {"asin": "B0FPY0000", "title": "Celular Samsung Galaxy A17 5G, 256GB - Azul",
     "brand": "Samsung", "monthly_sales_volume": "855", "monthly_sales_amount": "800000",
     "price": 999.0, "review_count": "300", "star_rating": 4.7, "online_date": "2025-09-04"},
    {"asin": "B0DJFS7GXV", "title": "Apple iPhone 16 (512 GB) - Preto", "brand": "Apple",
     "monthly_sales_volume": "2401", "monthly_sales_amount": "12531000", "price": 5219.1,
     "review_count": "6026", "star_rating": 4.7, "online_date": None},
    {"asin": "B0DXR7GNWJ", "title": "Apple iPhone 16e de 128 GB - Preto", "brand": "Apple",
     "monthly_sales_volume": "1238", "monthly_sales_amount": "4455000", "price": 3599.0,
     "review_count": "900", "star_rating": 4.6, "online_date": "2025-02-20"},
    {"asin": "SEMTITULO", "title": "   ", "brand": "?", "monthly_sales_volume": "999"},
]


class TestParseEAgregacao(unittest.TestCase):
    def test_descarta_linha_sem_titulo_e_converte_numero_string(self):
        rows = sorftime.parse_products(RAW)
        self.assertEqual(len(rows), 4)                  # a linha sem titulo sai
        self.assertEqual(rows[0]["sales"], 6285)        # "6285" -> int
        self.assertEqual(rows[0]["reviews"], 1081)

    def test_entrada_vazia_ou_invalida_nao_quebra(self):
        self.assertEqual(sorftime.parse_products([]), [])
        self.assertEqual(sorftime.parse_products(None), [])
        self.assertEqual(sorftime.parse_products(["texto solto", 42]), [])

    def test_variantes_do_mesmo_modelo_viram_um_so(self):
        agg = {a["canonical_model"]: a for a in
               sorftime.aggregate_by_model(sorftime.parse_products(RAW))}
        a17 = agg["SAMSUNG A17"]
        self.assertEqual(a17["asins"], 2)
        self.assertEqual(a17["sales"], 6285 + 855)      # venda SOMA
        self.assertEqual(a17["reviews"], 1081)          # review usa o MAIOR, nao soma
        self.assertEqual(a17["price"], 899.1)           # preco vem do ASIN lider
        self.assertEqual(a17["online_date"], "2025-09-04")   # a data mais antiga

    def test_iphone_16e_nao_e_fundido_no_16(self):
        # canonicalize("APPLE 16 E") devolve "APPLE 16" (o "e" solto vira conector),
        # entao a chave do coletor tem que sobreviver inteira ate o pipeline.
        agg = {a["canonical_model"] for a in
               sorftime.aggregate_by_model(sorftime.parse_products(RAW))}
        self.assertIn("APPLE 16", agg)
        self.assertIn("APPLE 16 E", agg)

    def test_rank_e_por_modelo_e_ordenado_por_venda(self):
        agg = sorftime.aggregate_by_model(sorftime.parse_products(RAW))
        self.assertEqual([a["rank"] for a in agg], [1, 2, 3])
        self.assertEqual(agg[0]["canonical_model"], "SAMSUNG A17")   # 7140 no total
        self.assertTrue(agg[0]["sales"] >= agg[1]["sales"] >= agg[2]["sales"])


class TestMomentum(unittest.TestCase):
    def test_escala(self):
        self.assertEqual(sorftime.momentum_from_sales(100, 100), 50.0)   # estavel
        self.assertEqual(sorftime.momentum_from_sales(125, 100), 100.0)  # +25% satura
        self.assertEqual(sorftime.momentum_from_sales(90, 100), 30.0)    # caindo
        self.assertEqual(sorftime.momentum_from_sales(0, 100), 0.0)

    def test_sem_base_anterior_nao_inventa(self):
        self.assertIsNone(sorftime.momentum_from_sales(100, None))
        self.assertIsNone(sorftime.momentum_from_sales(100, 0))


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.mem = {}
        for name, fn in (("get_cached", self.mem.get),
                         ("set_cached", lambda k, v: self.mem.__setitem__(k, v))):
            p = mock.patch.object(store, name, fn)
            p.start()
            self.addCleanup(p.stop)
        # sem isto a ingestao instancia o proxy real e a suite vai para a rede
        p = mock.patch.object(sorftime, "_chaves_da_ia", return_value={})
        p.start()
        self.addCleanup(p.stop)

    def test_grava_snapshot_observacoes_e_historico(self):
        res = sorftime.ingest(RAW, collected_at="2026-08-29")
        self.assertEqual(res["products"], 4)
        self.assertEqual(res["models"], 3)

        snap = self.mem["marketplace_snapshot"]
        self.assertIn("amazon", snap["SAMSUNG A17"]["sites"])
        self.assertEqual(snap["SAMSUNG A17"]["sites"]["amazon"]["rank"], 1)

        obs = {o["canonical_model"]: o for o in self.mem[sorftime.OBS_KEY]}
        self.assertEqual(obs["SAMSUNG A17"]["sold_qty"], 7140)
        self.assertEqual(obs["SAMSUNG A17"]["source"], "amazon")
        self.assertEqual(len(self.mem[sorftime.HISTORY_KEY]), 1)

    def test_coleta_vazia_e_recusada(self):
        with self.assertRaises(ValueError):
            sorftime.ingest([])

    def test_segunda_semana_gera_momentum(self):
        sorftime.ingest(RAW, collected_at="2026-08-24")
        crescendo = [dict(RAW[0], monthly_sales_volume="12570")] + RAW[1:]
        sorftime.ingest(crescendo, collected_at="2026-08-31")

        obs = {o["canonical_model"]: o for o in self.mem[sorftime.OBS_KEY]}
        self.assertGreater(obs["SAMSUNG A17"]["momentum"], 50)   # dobrou de venda
        self.assertEqual(len(self.mem[sorftime.HISTORY_KEY]), 2)

    def test_reprocessar_a_mesma_data_substitui_em_vez_de_duplicar(self):
        sorftime.ingest(RAW, collected_at="2026-08-31")
        sorftime.ingest(RAW, collected_at="2026-08-31")
        hist = self.mem[sorftime.HISTORY_KEY]
        self.assertEqual(len(hist), 1)
        # e nao vira "momentum zero" comparando a coleta consigo mesma
        obs = {o["canonical_model"]: o for o in self.mem[sorftime.OBS_KEY]}
        self.assertNotIn("momentum", obs["SAMSUNG A17"])

    def test_historico_e_limitado(self):
        for d in range(1, sorftime.HISTORY_WEEKS + 5):
            sorftime.ingest(RAW, collected_at=f"2026-01-{d:02d}")
        self.assertEqual(len(self.mem[sorftime.HISTORY_KEY]), sorftime.HISTORY_WEEKS)


class TestPipelineUsaAChaveDoColetor(unittest.TestCase):
    """Regressao: a tracao real nao pode ser perdida por recanonicalizacao."""

    def test_chave_do_coletor_sobrevive_ao_pipeline(self):
        from mithrandir.config import load_config
        from mithrandir.pipeline import run_pipeline

        obs = [{"raw_name": "Apple iPhone 16 (512 GB) - Preto", "brand": "Apple",
                "source": "amazon", "rank": 1, "sold_qty": 3474, "review_count": 6026,
                "rating": 4.7, "price": 5219.1, "offers": 7, "canonical_model": "APPLE 16"},
               {"raw_name": "Apple iPhone 16e de 128 GB - Preto", "brand": "Apple",
                "source": "amazon", "rank": 2, "sold_qty": 1238, "review_count": 900,
                "rating": 4.6, "price": 3599.0, "offers": 1, "canonical_model": "APPLE 16 E"}]

        with mock.patch.object(sorftime, "load_observations", return_value=obs), \
             mock.patch.object(store, "get_cached", lambda k: None), \
             mock.patch.object(store, "set_cached", lambda k, v: None):
            vendas = {c.canonical_model: (c.marketplace.sold_qty if c.marketplace else None)
                      for c in run_pipeline(load_config())}

        # Sem a correcao, "APPLE 16 E" virava "APPLE 16" e a venda do 16e (1238)
        # sobrescrevia a do 16 (3474) — dois aparelhos distintos, capinhas distintas.
        self.assertEqual(vendas.get("APPLE 16"), 3474)
        self.assertEqual(vendas.get("APPLE 16 E"), 1238)


if __name__ == "__main__":
    unittest.main()


class TestFiltroDeNaoCelular(unittest.TestCase):
    """A categoria da Amazon tem intruso; `product_category` do Sorftime nao ajuda."""

    QUEST = {"asin": "B0X", "title": "Meta Quest 3S 128 GB - All-in-one headset",
             "brand": "Meta Quest", "monthly_sales_volume": "166", "price": 2999.0}

    def test_produto_sem_marca_conhecida_fica_de_fora(self):
        fora = []
        rows = sorftime.parse_products([self.QUEST] + RAW, fora)
        self.assertEqual(len(fora), 1)
        self.assertIn("Meta Quest", fora[0])
        self.assertNotIn("META QUEST 3 S", {r["canonical_model"] for r in rows})

    def test_descarte_e_reportado_e_nao_silencioso(self):
        mem = {}
        with mock.patch.object(store, "get_cached", mem.get), \
             mock.patch.object(store, "set_cached", lambda k, v: mem.__setitem__(k, v)), \
             mock.patch.object(sorftime, "_chaves_da_ia", return_value={}):
            res = sorftime.ingest([self.QUEST] + RAW, collected_at="2026-08-29")
        self.assertEqual(res["descartados"], 1)
        self.assertTrue(res["descartados_exemplos"])

    def test_marcas_de_celular_reais_nao_sao_descartadas(self):
        # OPPO e TCL vieram no top 100 e caiam no filtro por nao estarem mapeadas.
        reais = [{"asin": "1", "title": "Smartphone OPPO A5 256GB 6GB Ram", "brand": "OPPO",
                  "monthly_sales_volume": "94"},
                 {"asin": "2", "title": "Smartphone TCL 50 256GB 14GB RAM", "brand": "TCL",
                  "monthly_sales_volume": "80"}]
        fora = []
        rows = sorftime.parse_products(reais, fora)
        self.assertEqual(fora, [])
        self.assertEqual(len(rows), 2)
