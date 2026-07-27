import unittest

from mithrandir.collectors import sheets

VALUES = [
    ["SUM de Quantidade", "Mês"],
    ["Produto", "1", "2", "3", "4", "5", "6", "7", "Total geral"],
    ["Case Anti Impacto Slim Air / iPhone 15", "5.707", "5.604", "3.058", "55", "", "", "", "14.424"],
    ["Case Anti Impacto Slim Air / Samsung Galaxy A56", "", "", "288", "", "", "", "", "288"],
    ["Case Anti Impacto Slim Air - JOVI Y29 / JOVI Y29", "48", "51", "38", "56", "44", "22", "", "259"],
    ["", "", "", "", "", "", "", "", ""],
]


class TestSheetsParser(unittest.TestCase):
    def test_parse_agrega_por_modelo(self):
        p = sheets.parse(VALUES)
        self.assertIn("APPLE 15", p)
        self.assertEqual(p["APPLE 15"]["total"], 14424)
        self.assertEqual(p["APPLE 15"]["months"][1], 5707)
        self.assertEqual(p["SAMSUNG A56"]["total"], 288)
        self.assertEqual(p["SAMSUNG A56"]["months"][3], 288)

    def test_modelo_apos_ultima_barra(self):
        p = sheets.parse(VALUES)
        self.assertIn("JOVI Y29", p)   # "Case ... - JOVI Y29 / JOVI Y29" -> JOVI Y29

    def test_build_monthly_alinha_meses_fechados(self):
        p = sheets.parse(VALUES)
        m = sheets.build_monthly(p, current_month=7)  # meses fechados: 1..6
        self.assertEqual(m["APPLE 15"], [5707, 5604, 3058, 55, 0, 0])
        self.assertEqual(m["JOVI Y29"], [48, 51, 38, 56, 44, 22])

    def test_build_records_usa_total_como_unidades(self):
        recs = {r["canonical_model"]: r for r in sheets.build_records(sheets.parse(VALUES))}
        self.assertEqual(recs["APPLE 15"]["units"], 14424)
        self.assertEqual(recs["APPLE 15"]["brand"], "APPLE")

    def test_num(self):
        self.assertEqual(sheets._num("5.707"), 5707)
        self.assertEqual(sheets._num(""), 0)
        self.assertEqual(sheets._num("288"), 288)


if __name__ == "__main__":
    unittest.main()
