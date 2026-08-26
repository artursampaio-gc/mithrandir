import unittest
from unittest import mock

from mithrandir.collectors import websearch
from mithrandir.collectors.websearch import (LAUNCH_KEYWORDS, build_queries,
                                             enrich_query, queries_for,
                                             search_all)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Samsung Galaxy S26 FE Release Date Set for Next Week - Tech Advisor</title>
<link>https://exemplo/1</link><pubDate>Fri, 21 Aug 2026 09:30:00 GMT</pubDate>
<source url="https://tech">Tech Advisor</source>
<description>&lt;a href="x"&gt;evento&lt;/a&gt; em 27 de agosto</description></item>
<item><title>Sem data aqui - Blog</title><link>https://exemplo/2</link>
<pubDate>data invalida</pubDate><description>nada</description></item>
</channel></rss>"""


class TestQueryBuilder(unittest.TestCase):
    def test_toda_consulta_leva_palavra_chave_de_data(self):
        qs = build_queries("Samsung Galaxy S26 FE")
        self.assertTrue(qs)
        self.assertTrue(any("release date" in q for q in qs))
        for q in qs:
            self.assertIn("Samsung Galaxy S26 FE", q)

    def test_enriquece_query_manual_sem_duplicar(self):
        # query manual antiga: ganha "release date"
        q = enrich_query("iPhone 18 Pro lancamento Brasil")
        self.assertIn("release date", q)
        self.assertIn("iPhone 18 Pro", q)
        # rodar de novo nao duplica
        self.assertEqual(enrich_query(q), q)
        # query que ja tem a palavra-chave fica intacta
        pronta = 'Moto G86 "release date" data de lancamento'
        self.assertEqual(enrich_query(pronta), pronta)

    def test_enriquece_ignora_acento(self):
        q = enrich_query("Galaxy A57 data de lançamento")
        self.assertIn("release date", q)
        self.assertEqual(q.lower().count("data de lan"), 1)

    def test_query_vazia_continua_vazia(self):
        self.assertEqual(enrich_query(""), "")
        self.assertEqual(build_queries("   "), [])

    def test_queries_for_poe_a_manual_primeiro_e_nao_repete(self):
        qs = queries_for("Moto G86", 'Moto G86 "release date"')
        self.assertEqual(qs[0], 'Moto G86 "release date"')
        self.assertEqual(len(qs), len(set(q.lower() for q in qs)))
        self.assertTrue(any(k in " ".join(qs).lower() for k in LAUNCH_KEYWORDS))

    def test_search_all_dedup_por_url_e_tolera_falha(self):
        chamadas = []

        def fake_search(q):
            chamadas.append(q)
            if "preco" in q:
                raise RuntimeError("provedor fora do ar")
            return [{"title": "t", "url": "https://x/1", "snippet": "setembro de 2026"}]

        out = search_all(fake_search, queries_for("Galaxy S26 FE"))
        self.assertEqual(len(chamadas), 3)          # roda as 3 consultas
        self.assertEqual(len(out), 1)               # mesma URL nas duas que deram certo
        self.assertIn("query", out[0])              # guarda de qual consulta veio


class TestGoogleNewsProvider(unittest.TestCase):
    """O provedor real (RSS do Google Noticias) — sem tocar a rede."""

    def setUp(self):
        websearch.clear_search_cache()

    def test_nenhuma_consulta_usa_aspas(self):
        # Medido: frase exata derruba o recall do Google Noticias a quase zero.
        for q in build_queries("Samsung Galaxy S26 FE"):
            self.assertNotIn('"', q)
        self.assertNotIn('"', enrich_query("Galaxy A57 lancamento"))

    def test_consulta_em_ingles_vai_para_o_indice_americano(self):
        self.assertEqual(websearch._locale_for("Galaxy S26 FE release date")["gl"], "US")
        self.assertEqual(websearch._locale_for("Galaxy S26 FE data de lancamento Brasil")["gl"], "BR")

    def test_le_titulo_veiculo_e_data_de_publicacao(self):
        with mock.patch.object(websearch, "request_text", return_value=RSS) as req:
            out = websearch.google_news_search("Galaxy S26 FE release date")
            url = req.call_args[0][0]
        self.assertIn("hl=en-US", url)                     # consulta EN -> Google US
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["published"], "2026-08-21")
        self.assertEqual(out[0]["source"], "Tech Advisor")
        self.assertNotIn("<a href", out[0]["snippet"])     # HTML da description sai
        self.assertEqual(out[1]["published"], "")          # pubDate invalido nao quebra

    def test_cache_evita_repetir_a_mesma_consulta(self):
        with mock.patch.object(websearch, "request_text", return_value=RSS) as req:
            websearch.google_news_search("Galaxy S26 FE release date")
            websearch.google_news_search("Galaxy S26 FE release date")
            self.assertEqual(req.call_count, 1)
            websearch.clear_search_cache()
            websearch.google_news_search("Galaxy S26 FE release date")
            self.assertEqual(req.call_count, 2)

    def test_flag_desliga_a_busca(self):
        with mock.patch.object(websearch, "_get_setting", return_value="off"):
            self.assertIsNone(websearch.get_search_provider())
        self.assertIsNotNone(websearch.get_search_provider())


if __name__ == "__main__":
    unittest.main()
