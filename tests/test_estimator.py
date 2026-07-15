import tempfile
import unittest
from datetime import date
from pathlib import Path

from mithrandir.config import load_config
from mithrandir.launch_estimator import build_calendar, extract_dates
from mithrandir import overrides as ov


class TestExtractDates(unittest.TestCase):
    def test_dia_mes_ano_pt(self):
        r = extract_dates("lancado em 21 de janeiro de 2026")
        self.assertIn({"iso": "2026-01-21", "precision": "day"}, r)

    def test_mes_ano_pt(self):
        r = extract_dates("chega em setembro de 2026")
        self.assertIn({"iso": "2026-09-01", "precision": "month"}, r)

    def test_mes_ano_en(self):
        r = extract_dates("expected September 2026")
        self.assertIn({"iso": "2026-09-01", "precision": "month"}, r)

    def test_mes_barra_mes(self):
        r = extract_dates("no final do verao, setembro/outubro de 2026")
        self.assertIn({"iso": "2026-09-01", "precision": "month"}, r)


class TestCalendar(unittest.TestCase):
    def test_calendario_gera_estimativas(self):
        cfg = load_config()
        cfg.ai.api_key = ""  # forca a heuristica (deterministico, sem rede)
        cal = build_calendar(cfg, today=date(2026, 7, 9))
        self.assertTrue(cal)
        by_dev = {e["canonical"]: e for e in cal}
        # S26 FE: noticias apontam setembro/2026 -> previsto
        self.assertIn("SAMSUNG S26 FE", by_dev)
        s26 = by_dev["SAMSUNG S26 FE"]
        self.assertEqual(s26["estimated_date"][:7], "2026-09")
        self.assertEqual(s26["status"], "previsto")
        # Note 15 ja lancou em jan/2026 -> corrigido para "lancado"
        self.assertEqual(by_dev["XIAOMI NOTE 15"]["status"], "lancado")


class TestOverrides(unittest.TestCase):
    def test_add_e_precedencia(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ov.json"
            ov.add_override("Samsung Galaxy S26 FE", "2026-09-25", 0.95,
                            "fabrica confirmou", path=p)
            got = ov.override_for("SAMSUNG S26 FE", path=p)
            self.assertIsNotNone(got)
            self.assertEqual(got["date"], "2026-09-25")
            self.assertTrue(ov.delete_override(got["id"], path=p))
            self.assertIsNone(ov.override_for("SAMSUNG S26 FE", path=p))


if __name__ == "__main__":
    unittest.main()
