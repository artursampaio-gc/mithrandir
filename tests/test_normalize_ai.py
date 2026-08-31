import unittest

from mithrandir import normalize_ai
from mithrandir.collectors import sorftime


class FakeAI:
    """Responde o que o teste mandar, por titulo."""

    available = True

    def __init__(self, respostas: dict, falha: bool = False):
        self.respostas, self.falha, self.chamadas = respostas, falha, 0

    def complete_json(self, prompt, system="", timeout=60):
        self.chamadas += 1
        if self.falha:
            raise RuntimeError("proxy fora do ar")
        itens = []
        for n, linha in enumerate(prompt.split("Titulos:\n")[1].split("\n\n")[0].splitlines(), 1):
            titulo = linha.split(". ", 1)[1]
            if titulo in self.respostas:
                itens.append({"n": n, "chave": self.respostas[titulo]})
        return {"itens": itens}


class TestFormato(unittest.TestCase):
    def test_desmembra_digito_colado_em_letra(self):
        # "XIAOMI 15C" quebraria o join: o BI e a regra usam "XIAOMI 15 C"
        self.assertEqual(normalize_ai._formatar("XIAOMI 15C"), "XIAOMI 15 C")

    def test_nao_mexe_no_que_ja_esta_no_formato(self):
        for k in ("APPLE 16 E", "SAMSUNG S24 ULTRA", "SAMSUNG S23 +", "MOTOROLA G84"):
            with self.subTest(k=k):
                self.assertEqual(normalize_ai._formatar(k), k)


class TestGuardRail(unittest.TestCase):
    TITULO = "Smartphone Motorola Moto G86 5G 256GB Preto"

    def test_aceita_limpeza_coerente_com_a_regra(self):
        self.assertTrue(normalize_ai._compativel("MOTOROLA G86", self.TITULO))

    def test_rejeita_troca_de_marca(self):
        self.assertFalse(normalize_ai._compativel("SAMSUNG G86", self.TITULO))

    def test_rejeita_troca_de_geracao(self):
        self.assertFalse(normalize_ai._compativel("MOTOROLA G87", self.TITULO))

    def test_aceita_geracao_que_a_regra_nao_achou_mas_esta_no_titulo(self):
        # Caso real: o modelo vinha no fim do titulo e a regra devolvia so "TCL"
        titulo = "Smartphone TCL 256GB 50MP 14GB RAM 6.7 HD+ Octa-Core 5.200 mAh TCL 605"
        self.assertTrue(normalize_ai._compativel("TCL 605", titulo))

    def test_rejeita_geracao_inventada(self):
        titulo = "Smartphone TCL 256GB 50MP 14GB RAM Octa-Core"
        self.assertFalse(normalize_ai._compativel("TCL 999", titulo))


class TestCleanTitles(unittest.TestCase):
    SUJO = "Smartphone Motorola Edge 70 Crystals by Swarovski 512GB Lavanda"

    def test_limpa_ruido_que_a_regra_nao_conhece(self):
        ai = FakeAI({self.SUJO: "MOTOROLA EDGE 70"})
        self.assertEqual(normalize_ai.clean_titles(ai, [self.SUJO])[self.SUJO],
                         "MOTOROLA EDGE 70")

    def test_chave_vazia_marca_nao_celular(self):
        t = "Tablet Samsung Galaxy Tab S10 FE 128GB Cinza"
        ai = FakeAI({t: ""})
        self.assertEqual(normalize_ai.clean_titles(ai, [t])[t], "")

    def test_resposta_incompativel_nao_entra(self):
        ai = FakeAI({self.SUJO: "SAMSUNG S24"})     # marca trocada
        self.assertNotIn(self.SUJO, normalize_ai.clean_titles(ai, [self.SUJO]))

    def test_falha_do_proxy_nao_derruba(self):
        ai = FakeAI({}, falha=True)
        self.assertEqual(normalize_ai.clean_titles(ai, [self.SUJO]), {})

    def test_sem_proxy_nao_chama_nada(self):
        class SemIA:
            available = False
        self.assertEqual(normalize_ai.clean_titles(SemIA(), [self.SUJO]), {})

    def test_cache_evita_nova_chamada(self):
        ai = FakeAI({self.SUJO: "MOTOROLA EDGE 70"})
        cache = {self.SUJO: "MOTOROLA EDGE 70"}
        out = normalize_ai.clean_titles(ai, [self.SUJO], cache)
        self.assertEqual(ai.chamadas, 0)
        self.assertEqual(out[self.SUJO], "MOTOROLA EDGE 70")


class TestIngestaoUsaAsChaves(unittest.TestCase):
    def test_chave_da_ia_vence_a_regra(self):
        raw = [{"asin": "A", "title": "Smartphone Motorola Moto G86 5G + Fone Bluetooth Buds",
                "brand": "Motorola", "monthly_sales_volume": "2309"}]
        rows = sorftime.parse_products(raw, chaves={raw[0]["title"]: "MOTOROLA G86"})
        self.assertEqual(rows[0]["canonical_model"], "MOTOROLA G86")

    def test_chave_vazia_da_ia_descarta_mesmo_com_marca_valida(self):
        # O filtro por marca NAO pega este: "Samsung" e marca legitima de celular
        raw = [{"asin": "T", "title": "Tablet Samsung Galaxy Tab S10 FE 128GB",
                "brand": "Samsung", "monthly_sales_volume": "500"}]
        fora = []
        rows = sorftime.parse_products(raw, fora, chaves={raw[0]["title"]: ""})
        self.assertEqual(rows, [])
        self.assertEqual(len(fora), 1)

    def test_sem_opiniao_da_ia_cai_na_regra(self):
        raw = [{"asin": "A", "title": "Celular Samsung Galaxy A17, 128GB - Preto",
                "brand": "Samsung", "monthly_sales_volume": "6285"}]
        rows = sorftime.parse_products(raw, chaves={})
        self.assertEqual(rows[0]["canonical_model"], "SAMSUNG A17")


if __name__ == "__main__":
    unittest.main()
