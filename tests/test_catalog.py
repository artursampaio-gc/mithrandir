"""Catalogo de capinhas vindo do site (`spree_devices`)."""
import unittest
from unittest import mock

from mithrandir import store
from mithrandir.collectors import catalog

# Recorte real do site, com os casos que importam
ROWS = [
    {"id": 1, "name": "Samsung Galaxy A17", "brand": "Samsung", "created_at": "2025-11-03"},
    {"id": 2, "name": "iPhone 16e", "brand": "iPhone", "created_at": "2025-02-25"},
    {"id": 3, "name": "Case Infinite Xiaomi Redmi Note 15 Pro 5G", "brand": "Xiaomi",
     "created_at": "2026-05-20"},
    {"id": 4, "name": "Ecobag Duocolor", "brand": "Gocase", "created_at": "2026-03-26"},
    {"id": 5, "name": "Pulseira Apple Wach 38/40 mm", "brand": "Apple", "created_at": "2022-01-10"},
    {"id": 6, "name": "   ", "brand": "?", "created_at": "2026-01-01"},
    {"id": 7, "name": "Samsung Galaxy A17 5G", "brand": "Samsung", "created_at": "2026-02-01"},
]


class TestParse(unittest.TestCase):
    def test_extrai_modelo_e_data_de_lancamento_da_capinha(self):
        out = catalog.parse_devices(ROWS)
        self.assertEqual(out["SAMSUNG A17"], "2025-11-03")
        self.assertEqual(out["APPLE 16 E"], "2025-02-25")

    def test_mesmo_modelo_em_varios_registros_fica_com_a_data_mais_antiga(self):
        # o site tem o aparelho e variantes ("Case Infinite ...", "A17 5G")
        out = catalog.parse_devices(ROWS)
        self.assertEqual(out["SAMSUNG A17"], "2025-11-03")   # nao 2026-02-01

    def test_o_que_nao_e_celular_fica_de_fora(self):
        fora = []
        out = catalog.parse_devices(ROWS, descartados=fora)
        self.assertNotIn("Ecobag", " ".join(out))
        self.assertTrue(any("Ecobag" in d for d in fora))

    def test_registro_sem_nome_ou_sem_data_e_ignorado(self):
        out = catalog.parse_devices([{"name": "", "created_at": "2026-01-01"},
                                     {"name": "Samsung Galaxy A57", "created_at": ""}])
        self.assertEqual(out, {})

    def test_chave_da_ia_vence_a_regra(self):
        nome = "Case Infinite Xiaomi Redmi Note 15 Pro 5G"
        out = catalog.parse_devices([r for r in ROWS if r["name"] == nome],
                                    chaves={nome: "XIAOMI NOTE 15 PRO"})
        self.assertEqual(list(out), ["XIAOMI NOTE 15 PRO"])

    def test_entrada_invalida_nao_quebra(self):
        self.assertEqual(catalog.parse_devices([]), {})
        self.assertEqual(catalog.parse_devices(None), {})
        self.assertEqual(catalog.parse_devices(["texto", 42]), {})


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.mem = {}
        for nome, fn in (("get_cached", self.mem.get),
                         ("set_cached", lambda k, v: self.mem.__setitem__(k, v))):
            p = mock.patch.object(store, nome, fn)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(catalog, "_chaves_da_ia", return_value={})
        p.start()
        self.addCleanup(p.stop)

    def test_grava_o_catalogo(self):
        res = catalog.ingest(ROWS, reset=True)
        self.assertEqual(res["modelos_no_catalogo"], len(catalog.load_catalog()))
        self.assertIn("SAMSUNG A17", catalog.load_catalog())

    def test_paginas_seguintes_somam_em_vez_de_substituir(self):
        # a ingestao e paginada: normalizar os 735 registros de uma vez leva ~90s
        # e o Vercel corta em 60s
        catalog.ingest(ROWS[:2], reset=True)
        catalog.ingest(ROWS[2:], reset=False)
        cat = catalog.load_catalog()
        self.assertIn("APPLE 16 E", cat)          # veio da pagina 1
        self.assertIn("XIAOMI NOTE 15 PRO", cat)  # veio da pagina 2

    def test_reset_limpa_o_que_havia_antes(self):
        catalog.ingest(ROWS, reset=True)
        catalog.ingest([ROWS[0]], reset=True)
        self.assertEqual(set(catalog.load_catalog()), {"SAMSUNG A17"})

    def test_pagina_vazia_sem_reset_e_recusada(self):
        with self.assertRaises(ValueError):
            catalog.ingest([], reset=False)

    def test_data_mais_antiga_vence_entre_paginas(self):
        catalog.ingest([{"name": "Samsung Galaxy A17", "created_at": "2026-02-01"}], reset=True)
        catalog.ingest([{"name": "Samsung Galaxy A17", "created_at": "2025-11-03"}])
        self.assertEqual(catalog.load_catalog()["SAMSUNG A17"], "2025-11-03")


if __name__ == "__main__":
    unittest.main()
