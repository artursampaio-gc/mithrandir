"""Cliente do proxy interno de IA (obrigatorio - RNF-01).

Assume um endpoint compativel com a API OpenAI (chat/completions), que e o
formato mais comum de proxies internos. Ajuste em `complete()` se o proxy da
empresa usar outro contrato.

Sem credencial configurada, `AIClient.available` e False e o restante do sistema
usa os fallbacks baseados em regras. Nenhuma chamada a LLM externo e feita.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..config import AIConfig


class AIClient:
    def __init__(self, cfg: AIConfig):
        self.cfg = cfg

    @property
    def available(self) -> bool:
        return self.cfg.is_configured

    def complete(self, prompt: str, system: str = "", temperature: float | None = None,
                 timeout: int = 60) -> str:
        """Retorna o texto da resposta do modelo. Lanca RuntimeError se nao configurado."""
        if not self.available:
            raise RuntimeError("Proxy de IA nao configurado (modo mock).")

        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.cfg.model,
            "messages": messages,
        }
        if temperature is not None:  # alguns modelos (ex.: gpt-5.5) nao aceitam temperature
            payload["temperature"] = temperature
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.cfg.api_key}",
                # O gateway bloqueia o User-Agent padrao do Python (403); enviamos um explicito
                "User-Agent": "Mithrandir/0.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip()

    def complete_json(self, prompt: str, system: str = "", timeout: int = 60) -> dict:
        """Igual a complete, mas espera e faz parse de um JSON na resposta."""
        raw = self.complete(prompt, system=system, timeout=timeout)
        # Tolera respostas envoltas em blocos de codigo
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)
