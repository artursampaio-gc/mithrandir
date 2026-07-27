import json
import tempfile
import unittest
from pathlib import Path

from mithrandir import news_agent
from mithrandir.collectors.websearch import load_news_cache_raw


class FakeAI:
    available = True

    def complete_json(self, prompt, system="", timeout=60):
        return {"signals": [{"source": "TesteVeiculo",
                             "text": "lancamento previsto para setembro de 2026",
                             "url": "https://exemplo/x"}]}


class TestNewsAgent(unittest.TestCase):
    def test_agente_grava_sinais_no_cache(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "news.json"
            watchlist = [{"device": "Samsung Galaxy S26 FE", "query": "s26 fe"}]
            search_fn = lambda q: [{"title": "t", "url": "u", "snippet": "setembro 2026"}]
            updated = news_agent.refresh_news_cache(
                ai=FakeAI(), search_fn=search_fn, watchlist=watchlist, path=path)
            self.assertEqual(updated, ["Samsung Galaxy S26 FE"])
            cache = load_news_cache_raw(path)
            self.assertIn("SAMSUNG S26 FE", cache)
            self.assertEqual(cache["SAMSUNG S26 FE"]["signals"][0]["source"], "TesteVeiculo")
            self.assertIn("mode", cache["_meta"])

    def test_sem_busca_web_nao_sobrescreve(self):
        # Sem search_fn (sem API de busca), o agente e no-op: nao grava nada.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "news.json"
            watchlist = [{"device": "Apple iPhone 18 Pro", "query": "iphone 18"}]
            updated = news_agent.refresh_news_cache(
                ai=FakeAI(), search_fn=None, watchlist=watchlist, path=path)
            self.assertEqual(updated, [])
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
