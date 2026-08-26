"""Estimador de data de lancamento (aba Calendario).

Para cada device combina, em ordem de prioridade:
  1) Intel do analista (override) -> SEMPRE vence
  2) IA sobre noticias (proxy de GPT), quando configurada
  3) Heuristica: datas extraidas das noticias
  4) Previsao sazonal (mesmo mes do ano anterior)

Produz uma LaunchEstimate com data, confianca, status, justificativa e evidencias.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional

from .ai.proxy import AIClient
from .collectors.launch_calendar import load_launch_history, predict_upcoming
from .collectors.websearch import (get_search_provider, known_devices,
                                   load_news_cache, queries_for, search_all,
                                   signals_for)
from .config import Config, load_config
from .news_miner import clear_cache as clear_mine_cache
from .news_miner import expand_signals
from .normalize import canonicalize
from .overrides import override_for

# Memo das respostas da IA (por prompt) para nao repetir chamada a cada rebuild.
# Limpo por clear_ai_cache() no /api/refresh (para buscar dados frescos).
_AI_CACHE: dict = {}


def clear_ai_cache() -> None:
    _AI_CACHE.clear()
    clear_mine_cache()


MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_RE = "|".join(MONTHS)


@dataclass
class LaunchEstimate:
    canonical: str
    device: str
    brand: str = ""
    family: str = ""
    estimated_date: Optional[str] = None   # "YYYY-MM-DD" ou None
    date_precision: str = "month"          # "day" | "month"
    confidence: float = 0.0
    status: str = "incerto"                # "previsto" | "lancado" | "incerto"
    source: str = "incerto"               # "intel" | "ia" | "noticias" | "sazonal" | "incerto"
    rationale: str = ""
    evidence: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _strip(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def extract_dates(text: str) -> list[dict]:
    """Extrai datas candidatas de um texto (pt/en). Retorna {iso, precision}."""
    t = _strip(text)
    out: list[dict] = []
    # dd de mes de aaaa
    for m in re.finditer(rf"\b(\d{{1,2}})\s+de\s+({_MONTH_RE})\s+de\s+(\d{{4}})", t):
        d, mon, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
        out.append({"iso": f"{y:04d}-{mon:02d}-{min(d,28):02d}", "precision": "day"})
    # mes de aaaa  |  mes/mes de aaaa  |  mes aaaa (en)
    for m in re.finditer(rf"\b({_MONTH_RE})(?:\s*/\s*(?:{_MONTH_RE}))?\s+(?:de\s+)?(\d{{4}})", t):
        mon, y = MONTHS[m.group(1)], int(m.group(2))
        out.append({"iso": f"{y:04d}-{mon:02d}-01", "precision": "month"})
    # dd/mm/aaaa
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t):
        d, mon, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mon <= 12:
            out.append({"iso": f"{y:04d}-{mon:02d}-{min(d,28):02d}", "precision": "day"})
    return out


def _status_for(iso: Optional[str], today: date) -> str:
    if not iso:
        return "incerto"
    try:
        return "lancado" if date.fromisoformat(iso) < today else "previsto"
    except ValueError:
        return "incerto"


def _heuristic(signals: list[dict], seasonal_iso: Optional[str],
               today: date) -> tuple[Optional[str], str, float, str, str]:
    """Retorna (iso, precision, confidence, source, rationale)."""
    # Pistas de que a data citada NAO e um lancamento BR confirmado
    NEG = ("nao confirmad", "not confirmed", "sem data", "no official", "rumor de")
    dated = []
    for s in signals:
        text = s.get("text", "")
        if any(cue in _strip(text) for cue in NEG):
            continue  # ignora datas de sinais sem confirmacao (ex.: anuncio em outro pais)
        dated.extend(extract_dates(text))
    if dated:
        # escolhe o (ano, mes) mais citado; empate -> mais cedo
        keys = Counter((d["iso"][:7]) for d in dated)
        best_ym, count = keys.most_common(1)[0]
        # se houver precisao de dia para esse mes, usa o dia
        day_dates = [d["iso"] for d in dated if d["iso"].startswith(best_ym) and d["precision"] == "day"]
        iso = sorted(day_dates)[0] if day_dates else f"{best_ym}-01"
        precision = "day" if day_dates else "month"
        conf = min(0.9, 0.5 + 0.13 * count)
        return iso, precision, round(conf, 2), "noticias", \
            f"{count} noticia(s) apontando {best_ym}."
    if seasonal_iso:
        return seasonal_iso, "month", 0.4, "sazonal", \
            "Sem data em noticias; estimativa pelo padrao do ano anterior."
    return None, "month", 0.2, "incerto", "Sem data em noticias nem histor. sazonal."


def _ai_estimate(ai: AIClient, device: str, brand: str, family: str,
                 signals: list[dict], seasonal_iso: Optional[str], today: date):
    """Usa o proxy de IA para decidir a data. Retorna dict ou None em falha."""
    evidence = "\n".join(f"- ({s.get('source','?')}) {s.get('text','')}" for s in signals) or "(sem noticias)"
    prompt = (
        f"Hoje e {today.isoformat()}.\n"
        f"Device: {device} (marca {brand}, familia {family}).\n"
        f"Baseline sazonal (mesmo mes do ano anterior): {seasonal_iso or 'nenhum'}.\n"
        f"Noticias coletadas:\n{evidence}\n\n"
        "Estime a data de lancamento NO BRASIL seguindo estas regras:\n"
        "1) Baseie-se nas noticias acima.\n"
        "2) Nunca use status 'lancado' sem uma noticia confirmando o lancamento no Brasil.\n"
        "3) Se as noticias disserem que NAO ha data/confirmacao para o Brasil, "
        "retorne date=null e status='incerto'.\n"
        "4) Se so houver baseline sazonal (sem noticias), a data e uma estimativa: "
        "status 'previsto' se a janela for futura; se ja passou, status='incerto'.\n"
        "5) Use 'YYYY-MM' quando nao souber o dia e 'YYYY' quando souber apenas o "
        "ano (ex.: noticia diz 'apenas em 2027'). Seja conservador na confianca.\n"
        'Responda SOMENTE um JSON: {"date":"YYYY-MM-DD|YYYY-MM|YYYY|null","confidence":0..1,'
        '"status":"previsto|lancado|incerto","rationale":"1 frase"}'
    )
    if prompt in _AI_CACHE:
        return _AI_CACHE[prompt]
    try:
        data = ai.complete_json(
            prompt, system="Voce estima datas de lancamento de smartphones no Brasil.")
        iso, precision = data.get("date"), None
        if isinstance(iso, str):
            iso = iso.strip()
            if len(iso) == 4 and iso.isdigit():        # "2027" -> ano estimado
                iso, precision = f"{iso}-01-01", "year"
            elif len(iso) == 7:                        # "2027-03"
                iso, precision = iso + "-01", "month"
            elif len(iso) == 10:
                precision = "day"
            else:
                iso = None
        else:
            iso = None
        status = data.get("status")
        if status not in ("previsto", "lancado", "incerto"):
            status = None
        result = {
            "iso": iso,
            "precision": precision,
            "confidence": float(data.get("confidence", 0.5)),
            "status": status,
            "rationale": data.get("rationale", ""),
        }
        _AI_CACHE[prompt] = result
        return result
    except Exception:
        return None


def build_calendar(cfg: Config | None = None, today: date | None = None,
                   with_overrides: bool = True) -> list[dict]:
    """Monta o calendario. Com with_overrides=False gera a base (sem intel), para
    depois aplicar a intel de forma barata via apply_overrides_to()."""
    cfg = cfg or load_config()
    today = today or date.today()
    ai = AIClient(cfg.ai)
    # Minera as noticias: uma noticia pode citar varios aparelhos com datas
    # diferentes -> vira um sinal por aparelho (ex.: Pro Max e o base de 2027).
    cache = expand_signals(ai, load_news_cache())

    # Universo de devices: previsao sazonal + noticias + intel manual
    devices: dict[str, dict] = {}

    for p in predict_upcoming(load_launch_history(), today=today,
                              horizon_days=400, lookback_days=250):
        parsed = canonicalize(p["canonical_model"])
        devices.setdefault(parsed.canonical, {
            "device": p["canonical_model"].title(),
            "brand": parsed.brand, "family": parsed.family,
            "seasonal": p["predicted_launch"],
        })

    for canon, name in known_devices(cache).items():
        parsed = canonicalize(name)
        d = devices.setdefault(canon, {"device": name, "brand": parsed.brand,
                                       "family": parsed.family, "seasonal": None})
        d["device"] = name

    if with_overrides:
        from .overrides import load_overrides
        for ov in load_overrides():
            canon = ov["canonical"]
            devices.setdefault(canon, {"device": ov["device"],
                                       "brand": canonicalize(ov["device"]).brand,
                                       "family": canonicalize(ov["device"]).family,
                                       "seasonal": None})

    items = list(devices.items())
    sig_map = {canon: signals_for(canon, cache) for canon, _ in items}

    # Chamadas de IA em paralelo (o gpt-5.5 e lento; sequencial seria ~N x mais devagar)
    if ai.available:
        with ThreadPoolExecutor(max_workers=6) as ex:
            res_list = list(ex.map(
                lambda it: _ai_estimate(ai, it[1]["device"], it[1]["brand"],
                                        it[1]["family"], sig_map[it[0]],
                                        it[1].get("seasonal"), today),
                items))
    else:
        res_list = [None] * len(items)

    estimates: list[LaunchEstimate] = []
    for (canon, d), res in zip(items, res_list):
        signals = sig_map[canon]
        seasonal = d.get("seasonal")

        if res:
            iso, conf, src, rationale = res["iso"], res["confidence"], "ia", res["rationale"]
            precision = res.get("precision") or (
                "day" if (iso and len(iso) == 10 and not iso.endswith("-01")) else "month")
            status = res["status"] or _status_for(iso, today)
            # nunca afirmar 'lancado' sem evidencia de noticia
            if status == "lancado" and not signals:
                status = "incerto"
        else:
            iso, precision, conf, src, rationale = _heuristic(signals, seasonal, today)
            status = _status_for(iso, today)

        # Fallback sazonal: sem data confirmada (IA/heuristica devolveram nulo),
        # mas ha previsao pelo antecessor caindo no futuro -> mostra como estimativa
        # 'previsto' (rotulo claro) em vez de jogar em "sem data confirmada".
        if not iso and seasonal:
            try:
                seasonal_future = date.fromisoformat(seasonal) >= today
            except ValueError:
                seasonal_future = False
            if seasonal_future:
                iso, precision, conf = seasonal, "month", 0.4
                src, status = "sazonal", "previsto"
                rationale = ("Sem data confirmada; estimativa pelo lancamento do "
                             "antecessor no ano anterior.")

        ov = override_for(canon) if with_overrides else None

        # Lancamentos de anos anteriores nao pertencem ao calendario de scouting
        # (a mineracao de noticias costuma citar geracoes passadas como referencia).
        if iso and not ov:
            try:
                if date.fromisoformat(iso).year < today.year:
                    continue
            except ValueError:
                pass

        # Descarta ruido: device so-sazonal (sem noticia e sem intel) que nao aponta
        # para uma data futura -> ou ja passou, ou nem data tem. Mantem noticias/intel.
        if not signals and not ov:
            future = False
            if iso:
                try:
                    future = date.fromisoformat(iso) >= today
                except ValueError:
                    future = False
            if not future:
                continue

        # Intel do analista sobrepoe tudo
        if ov:
            iso = ov.get("date") or iso
            conf = ov.get("confidence", 0.9)
            src = "intel"
            rationale = ov.get("note") or "Informado pelo analista."
            precision = "day" if (iso and len(iso) == 10) else "month"
            status = _status_for(iso, today)

        estimates.append(LaunchEstimate(
            canonical=canon, device=d["device"], brand=d["brand"], family=d["family"],
            estimated_date=iso, date_precision=precision, confidence=round(conf, 2),
            status=status, source=src, rationale=rationale,
            evidence=[{"source": s.get("source"), "url": s.get("url"),
                       "text": s.get("text")} for s in signals],
        ))

    # ordena: com data primeiro (cronologico), incertos por ultimo
    estimates.sort(key=lambda e: (e.estimated_date is None, e.estimated_date or "9999"))
    return [e.to_dict() for e in estimates]


def _web_signals(ai: AIClient, device: str, cfg: Config) -> list[dict]:
    """Sinais vindos de busca web ao vivo. Lista vazia se nao houver provedor."""
    search_fn = get_search_provider(cfg)
    if not search_fn or not ai.available:
        return []
    from .news_agent import _signals_from_search
    try:
        results = search_all(search_fn, queries_for(device))
        if not results:
            return []
        return _signals_from_search(ai, device, results) or []
    except Exception as e:
        print(f"[estimator] busca web falhou para {device}: {e}")
        return []


def estimate_device(device: str, cfg: Config | None = None,
                    today: date | None = None) -> dict:
    """Pesquisa sob demanda a data de lancamento de UM device especifico.

    Junta as evidencias que temos para ele: busca web (quando ha provedor),
    noticias mineradas, previsao sazonal do antecessor e a coleta de marketplace
    (se esta a venda, ja foi lancado).
    """
    cfg = cfg or load_config()
    today = today or date.today()
    ai = AIClient(cfg.ai)
    parsed = canonicalize(device)
    canon = parsed.canonical

    signals = list(signals_for(canon, expand_signals(ai, load_news_cache())))

    # Busca web ao vivo para ESTE device, com palavra-chave de data na query
    # ("release date" & cia.) — e o que separa a data real do resto do ruido.
    signals = _web_signals(ai, device, cfg) + signals

    # Evidencia forte: esta a venda em marketplace -> ja lancado
    try:
        from .collectors.marketplace import load_snapshot
        entry = load_snapshot().get(canon)
    except Exception:
        entry = None
    if entry:
        for site, d in (entry.get("sites") or {}).items():
            pos = f" na posicao #{d['rank']}" if d.get("rank") else ""
            signals.append({"source": site, "url": "",
                            "text": f"Ja esta a venda em {site}{pos} — portanto ja foi lancado."})

    # Baseline sazonal: o antecessor desta linha, se estiver no historico
    seasonal = None
    if parsed.generation:
        from .collectors.launch_calendar import _next_gen_name
        for rec in load_launch_history():
            nxt = _next_gen_name(rec["canonical_model"], rec["generation"])
            if canonicalize(nxt).canonical == canon:
                try:
                    base = date.fromisoformat(rec["launch_date"])
                    seasonal = base.replace(year=base.year + 1).isoformat()
                except ValueError:
                    pass
                break

    res = _ai_estimate(ai, device, parsed.brand, parsed.family, signals, seasonal, today) \
        if ai.available else None
    if res:
        iso, conf, src, rationale = res["iso"], res["confidence"], "ia", res["rationale"]
        precision = res.get("precision") or (
            "day" if (iso and len(iso) == 10 and not iso.endswith("-01")) else "month")
        status = res["status"] or _status_for(iso, today)
    else:
        iso, precision, conf, src, rationale = _heuristic(signals, seasonal, today)
        status = _status_for(iso, today)

    est = LaunchEstimate(
        canonical=canon, device=device.strip(), brand=parsed.brand, family=parsed.family,
        estimated_date=iso, date_precision=precision, confidence=round(conf, 2),
        status=status, source=src, rationale=rationale,
        evidence=[{"source": s.get("source"), "url": s.get("url"), "text": s.get("text")}
                  for s in signals],
    ).to_dict()

    ov = override_for(canon)   # intel do analista continua tendo precedencia
    return _apply_override(est, ov, today) if ov else est


def _norm_iso(iso):
    return (iso + "-01") if (iso and len(iso) == 7) else iso


def _apply_override(est: dict, ov: dict, today: date) -> dict:
    iso = _norm_iso(ov.get("date") or est.get("estimated_date"))
    est["estimated_date"] = iso
    est["confidence"] = round(ov.get("confidence", 0.9), 2)
    est["source"] = "intel"
    est["rationale"] = ov.get("note") or "Informado pelo analista."
    est["date_precision"] = "day" if (iso and len(iso) == 10 and not iso.endswith("-01")) else "month"
    est["status"] = _status_for(iso, today)
    return est


def _estimate_from_override(ov: dict, today: date) -> dict:
    p = canonicalize(ov["device"])
    iso = _norm_iso(ov.get("date"))
    return {
        "canonical": ov["canonical"], "device": ov["device"],
        "brand": p.brand, "family": p.family,
        "estimated_date": iso,
        "date_precision": "day" if (iso and len(iso) == 10 and not iso.endswith("-01")) else "month",
        "confidence": round(ov.get("confidence", 0.9), 2),
        "status": _status_for(iso, today), "source": "intel",
        "rationale": ov.get("note") or "Informado pelo analista.", "evidence": [],
    }


def apply_overrides_to(base: list[dict], today: date | None = None) -> list[dict]:
    """Aplica a intel atual sobre um calendario base (sem chamar IA). Barato."""
    from .overrides import load_overrides
    today = today or date.today()
    by = {e["canonical"]: dict(e) for e in (base or [])}
    for ov in load_overrides():
        c = ov["canonical"]
        if c in by:
            _apply_override(by[c], ov, today)
        else:
            by[c] = _estimate_from_override(ov, today)
    out = list(by.values())
    out.sort(key=lambda e: (e["estimated_date"] is None, e["estimated_date"] or "9999"))
    return out
