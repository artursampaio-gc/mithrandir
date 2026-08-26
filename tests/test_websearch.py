import unittest

from mithrandir.collectors.websearch import (LAUNCH_KEYWORDS, build_queries,
                                             enrich_query, queries_for,
                                             search_all)


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


if __name__ == "__main__":
    unittest.main()
