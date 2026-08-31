import unittest

from mithrandir.normalize import canonicalize


class TestNormalize(unittest.TestCase):
    def test_variantes_mesmo_modelo(self):
        a = canonicalize("Galaxy S26 FE")
        b = canonicalize("Samsung S26FE")
        c = canonicalize("Samsung Galaxy S26 Fan Edition 256GB")
        self.assertEqual(a.canonical, b.canonical)
        self.assertEqual(b.canonical, c.canonical)
        self.assertEqual(a.brand, "SAMSUNG")
        self.assertEqual(a.generation, 26)

    def test_remove_ruido_armazenamento_e_rede(self):
        p = canonicalize("Samsung Galaxy A56 5G 256GB")
        self.assertEqual(p.canonical, "SAMSUNG A56")
        self.assertEqual(p.generation, 56)

    def test_geracao_colada_a_letra(self):
        self.assertEqual(canonicalize("Motorola Moto G86").generation, 86)
        self.assertEqual(canonicalize("Motorola Moto G86").brand, "MOTOROLA")

    def test_familia_com_placeholder_de_geracao(self):
        p = canonicalize("Samsung Galaxy S25 FE")
        self.assertIn("#", p.family)
        self.assertEqual(p.family, "SAMSUNG S# FE")


if __name__ == "__main__":
    unittest.main()


class TestRuidoDeAnuncioAmazon(unittest.TestCase):
    """Casos reais do top 100 da Amazon BR que fragmentavam um modelo em varios."""

    def test_cor_em_espanhol_e_ingles_nao_vira_parte_do_modelo(self):
        from mithrandir.collectors.marketplace import model_from_listing
        casos = [
            ("Smartphone Xiaomi POCO C85 4G Negro 8GB RAM 256GB ROM", "XIAOMI C85"),
            ("Smartphone Xiaomi Redmi Note 14 Pro 5G Coral Green (Verde) 8GB RAM",
             "XIAOMI NOTE 14 PRO"),
            ("Smartphone Xiaomi Redmi Note 14 Ocean Blue (Azul) 8GB RAM", "XIAOMI NOTE 14"),
            ("Smartphone Xiaomi Redmi Note 15 Pro 5G 512GB - 8GB Ram Titanuim",
             "XIAOMI NOTE 15 PRO"),
        ]
        for titulo, esperado in casos:
            with self.subTest(titulo=titulo):
                self.assertEqual(model_from_listing(titulo), esperado)

    def test_armazenamento_escrito_so_com_G(self):
        from mithrandir.collectors.marketplace import model_from_listing
        # "256G/8Gb" gerava a chave "XIAOMI NOTE 15 256 G/"
        self.assertEqual(
            model_from_listing("Smartphone Xiaomi Redmi Note 15 4G 256G/8Gb Ram (Roxo)"),
            "XIAOMI NOTE 15")

    def test_rede_4g_5g_continua_sendo_removida_e_nao_confundida(self):
        self.assertEqual(canonicalize("Galaxy A57 5G 128GB").canonical, "SAMSUNG A57")
        self.assertEqual(canonicalize("Moto G17 4G 128GB").canonical, "MOTOROLA G17")

    def test_marcas_do_mercado_br_reconhecidas(self):
        for nome, marca in (("Smartphone OPPO A5 256GB", "OPPO"),
                            ("Smartphone TCL 50 256GB", "TCL"),
                            ("Smartphone Honor X9", "HONOR")):
            with self.subTest(nome=nome):
                self.assertEqual(canonicalize(nome).brand, marca)
