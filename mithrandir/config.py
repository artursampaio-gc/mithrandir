"""Configuracao central do Mithrandir.

Le de variaveis de ambiente e, opcionalmente, de um arquivo config.json na raiz.
Se nada estiver configurado, o sistema roda em MODO MOCK (dados de exemplo),
que e o estado atual enquanto os acessos nao sao liberados.

Precedencia: variavel de ambiente > config.json > default.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# Raiz do projeto (pasta que contem o pacote mithrandir/)
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SAMPLE_DIR = DATA_DIR / "sample"
OUTPUT_DIR = ROOT / "output"
DB_PATH = DATA_DIR / "mithrandir.db"


def _load_json_config() -> dict:
    cfg_file = ROOT / "config.json"
    if cfg_file.exists():
        try:
            return json.loads(cfg_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


_JSON = _load_json_config()


def _get(key: str, default=None):
    """Busca em env (MITHRANDIR_<KEY>) e depois no config.json."""
    env_key = "MITHRANDIR_" + key.upper()
    if env_key in os.environ and os.environ[env_key] != "":
        return os.environ[env_key]
    return _JSON.get(key, default)


@dataclass
class AIConfig:
    """Proxy interno de GPT da empresa (compativel com API OpenAI).

    Uso de IA e OBRIGATORIO via este proxy (RNF-01). Sem credencial -> modo mock.
    """
    base_url: str = ""
    api_key: str = ""
    model: str = "gpt-4o-mini"

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)


@dataclass
class MercadoLivreConfig:
    access_token: str = ""
    site_id: str = "MLB"  # MLB = Brasil

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)


@dataclass
class SheetsConfig:
    """Planilha de vendas internas (Google Sheets) via API key + link publico."""
    api_key: str = ""
    sheet_id: str = ""
    gid: str = ""     # id do tab (da URL ...#gid=XXXX)
    range: str = ""   # opcional; se vazio, resolve o nome do tab pelo gid

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.sheet_id)


@dataclass
class Config:
    ai: AIConfig = field(default_factory=AIConfig)
    mercadolivre: MercadoLivreConfig = field(default_factory=MercadoLivreConfig)
    sheets: SheetsConfig = field(default_factory=SheetsConfig)
    # Forca modo mock mesmo que haja credencial (util para testes locais)
    force_mock: bool = False

    @property
    def mock_mode(self) -> bool:
        """True enquanto os dados de scouting (marketplace) forem de exemplo.

        Independe da IA: o proxy pode estar ligado e o marketplace ainda ser mock.
        """
        if self.force_mock:
            return True
        return not self.mercadolivre.is_configured


def load_config() -> Config:
    ai = AIConfig(
        base_url=_get("ai_base_url", "") or "",
        api_key=_get("ai_api_key", "") or "",
        model=_get("ai_model", "gpt-4o-mini") or "gpt-4o-mini",
    )
    ml = MercadoLivreConfig(
        access_token=_get("ml_access_token", "") or "",
        site_id=_get("ml_site_id", "MLB") or "MLB",
    )
    sheets = SheetsConfig(
        api_key=_get("sheets_api_key", "") or "",
        # sheet_id e gid ja vem preenchidos com a planilha de vendas da Gocase
        sheet_id=_get("sheets_id", "1zmkOtSz2MkPmqkfw-_y1Qt2vq4ZpmCITILREQ4ySNsE") or "",
        gid=str(_get("sheets_gid", "113330236") or ""),
        range=_get("sheets_range", "") or "",
    )
    force_mock = str(_get("force_mock", "")).lower() in ("1", "true", "yes")
    return Config(ai=ai, mercadolivre=ml, sheets=sheets, force_mock=force_mock)
