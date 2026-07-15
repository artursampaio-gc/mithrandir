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
