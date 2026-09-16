"""Interface de linha de comando do Mithrandir.

Uso tipico (1 comando por dia):
    python -m mithrandir run       # coleta -> score -> gera dashboard
    python -m mithrandir top 10    # imprime o top N no terminal
    python -m mithrandir info      # mostra a configuracao/modo atual
"""
from __future__ import annotations

import sys
import webbrowser

from .config import load_config
from .dashboard import generate
from .pipeline import run_pipeline


def _print_top(candidates, n=10):
    print(f"\n{'#':>2}  {'SCORE':>6}  {'FASE':<14} MODELO")
    print("-" * 64)
    for i, c in enumerate(candidates[:n], 1):
        flags = ""
        if c.already_have_case:
            flags += " [já temos]"
        if c.similar_sold_poorly:
            flags += " [similar fraco]"
        print(f"{i:>2}  {c.score:>6.1f}  {c.phase:<14} {c.canonical_model}{flags}")
    print()


def cmd_run(args):
    from .collectors.marketplace import has_real_data
    cfg = load_config()
    mock = cfg.mock_mode and not has_real_data()
    mode = "MOCK (dados de exemplo)" if mock else "REAL"
    print(f"Mithrandir · modo {mode}")
    candidates = run_pipeline(cfg)
    out = generate(candidates, mock)
    _print_top(candidates)
    print(f"Dashboard gerado: {out}")
    if "--open" in args:
        webbrowser.open(out.as_uri())


def cmd_top(args):
    n = 10
    for a in args:
        if a.isdigit():
            n = int(a)
    cfg = load_config()
    candidates = run_pipeline(cfg)
    _print_top(candidates, n)


def cmd_info(args):
    cfg = load_config()
    print("Mithrandir — configuracao")
    print(f"  modo mock:        {cfg.mock_mode}")
    print(f"  IA configurada:   {cfg.ai.is_configured} (model={cfg.ai.model})")
    print(f"  Mercado Livre:    {cfg.mercadolivre.is_configured}")


def cmd_serve(args):
    """Sobe o app web (Candidatos, Calendario, Intel)."""
    from .server import serve
    port = 8756
    for a in args:
        if a.isdigit():
            port = int(a)
    serve(port=port)


def cmd_agent(args):
    """Roda o agente de scouting de noticias (atualiza o news_cache)."""
    from .ai.proxy import AIClient
    from .news_agent import refresh_news_cache
    cfg = load_config()
    ai = AIClient(cfg.ai)
    if not ai.available:
        print("Proxy de IA nao configurado — o agente precisa do proxy (config.json).")
        return
    print("Agente vasculhando/atualizando noticias de lancamento...")
    updated = refresh_news_cache(ai=ai)
    print(f"Atualizado ({len(updated)}): {', '.join(updated) or 'nada'}")
    print("Rode 'python -m mithrandir serve' para ver no calendario.")


def cmd_ingest(args):
    """Envia uma coleta de marketplace (JSON do Sorftime) para o app.

        python -m mithrandir ingest coleta.json [--url https://...] [--dry-run]

    O arquivo pode ser a resposta crua do `category_report` do Sorftime (com
    `data.top100_products`) ou so a lista de produtos.

    Existe para a tarefa agendada nao precisar carregar o token: ele fica no
    config.json/env desta maquina, nunca no prompt.
    """
    import json
    from pathlib import Path

    from ._http import request_json
    from .config import get_setting

    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print("Uso: python -m mithrandir ingest <arquivo.json> [--url URL] [--dry-run]")
        return
    raw = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    if isinstance(raw, dict):   # aceita a resposta crua do MCP
        raw = raw.get("data", raw).get("top100_products", raw)
    if not isinstance(raw, list):
        print("Arquivo invalido: esperava uma lista de produtos.")
        return

    if "--dry-run" in args:     # so mostra o que seria enviado
        from .collectors import sorftime
        agg = sorftime.aggregate_by_model(sorftime.parse_products(raw))
        print(f"{len(raw)} anuncios -> {len(agg)} modelos. Top 5:")
        for a in agg[:5]:
            print(f"  #{a['rank']:<3} {a['canonical_model']:<24} {a['sales']:>6} un/mes")
        return

    url = next((a.split("=", 1)[1] for a in args if a.startswith("--url=")), None) \
        or (args[args.index("--url") + 1] if "--url" in args else None) \
        or str(get_setting("app_url", "http://127.0.0.1:8756") or "")
    token = str(get_setting("ingest_token", "") or "")
    if not token:
        print("Sem token: configure MITHRANDIR_INGEST_TOKEN (ou ingest_token no config.json).")
        return

    res = request_json("POST", url.rstrip("/") + "/api/marketplace/ingest",
                       headers={"Authorization": f"Bearer {token}"},
                       json_body={"products": raw}, timeout=120)
    ing = (res or {}).get("ingested") or {}
    print(f"Enviado para {url}: {ing.get('products')} anuncios -> {ing.get('models')} modelos "
          f"({ing.get('with_momentum', 0)} com momentum).")
    for t in ing.get("top", []):
        print(f"  {t['model']:<24} {t['sales']:>6} un/mes")


def cmd_ingest_catalog(args):
    """Envia o catalogo de capinhas (spree_devices do site) para o app.

        python -m mithrandir ingest-catalog devices.json [--url URL] [--dry-run]

    Vai PAGINADO: normalizar os 735 registros de uma vez leva ~90s e o Vercel
    corta em 60s. Cada pagina cabe; o cache de titulos faz as rodadas seguintes
    saírem quase de graca.
    """
    import json
    from pathlib import Path

    from ._http import request_json
    from .config import get_setting

    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print("Uso: python -m mithrandir ingest-catalog <arquivo.json> [--url URL] [--dry-run]")
        return
    raw = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    if isinstance(raw, dict):            # aceita a resposta crua do runQuery
        raw = raw.get("rows", raw)
    if not isinstance(raw, list):
        print("Arquivo invalido: esperava uma lista de devices.")
        return

    if "--dry-run" in args:
        from .collectors.catalog import parse_devices
        fora = []
        canon = parse_devices(raw, descartados=fora)
        print(f"{len(raw)} registros -> {len(canon)} modelos ({len(fora)} nao sao celular)")
        for c, d in sorted(canon.items(), key=lambda kv: kv[1], reverse=True)[:8]:
            print(f"  {c:24} capinha desde {d}")
        return

    url = (args[args.index("--url") + 1] if "--url" in args else None) \
        or str(get_setting("app_url", "http://127.0.0.1:8756") or "")
    token = str(get_setting("ingest_token", "") or "")
    if not token:
        print("Sem token: configure MITHRANDIR_INGEST_TOKEN (ou ingest_token no config.json).")
        return

    alvo, pagina, total = url.rstrip("/") + "/api/catalog/ingest", 150, 0
    for i in range(0, len(raw), pagina):
        lote = raw[i:i + pagina]
        res = request_json("POST", alvo, headers={"Authorization": f"Bearer {token}"},
                           json_body={"devices": lote, "reset": i == 0}, timeout=180)
        ing = (res or {}).get("ingested") or {}
        total = ing.get("modelos_no_catalogo", total)
        print(f"  pagina {i // pagina + 1}: {len(lote)} registros -> "
              f"catalogo com {total} modelos")
    print(f"Catalogo enviado para {url}: {total} modelos com capinha.")


def cmd_ingest_case_sales(args):
    """Envia a curva de largada das capinhas (primeiros 6 meses por modelo).

        python -m mithrandir ingest-case-sales vendas.json [--url URL] [--dry-run]
    """
    import json
    from pathlib import Path

    from ._http import request_json
    from .config import get_setting

    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print("Uso: python -m mithrandir ingest-case-sales <arquivo.json> [--dry-run]")
        return
    raw = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    if isinstance(raw, dict):            # aceita a resposta crua do runQuery
        raw = raw.get("rows", raw)
    if not isinstance(raw, list):
        print("Arquivo invalido: esperava uma lista.")
        return

    if "--dry-run" in args:
        from .collectors.case_sales import parse_rows
        fora = []
        d = parse_rows(raw, descartados=fora)
        print(f"{len(raw)} registros -> {len(d)} modelos ({len(fora)} fora)")
        for k, v in sorted(d.items(), key=lambda kv: -sum(kv[1]["serie"]))[:8]:
            print(f"  {k:24} desde {v['m0'][:7]}  {v['serie']}")
        return

    url = (args[args.index("--url") + 1] if "--url" in args else None) \
        or str(get_setting("app_url", "http://127.0.0.1:8756") or "")
    token = str(get_setting("ingest_token", "") or "")
    if not token:
        print("Sem token: configure MITHRANDIR_INGEST_TOKEN.")
        return
    res = request_json("POST", url.rstrip("/") + "/api/case-sales/ingest",
                       headers={"Authorization": f"Bearer {token}"},
                       json_body={"sales": raw}, timeout=180)
    ing = (res or {}).get("ingested") or {}
    print(f"Enviado para {url}: {ing.get('recebidos')} registros -> "
          f"{ing.get('modelos')} modelos com curva de largada.")
    for t in ing.get("top", []):
        print(f"  {t['modelo']:24} {t['total6']:>6} un nos 6 primeiros meses")


COMMANDS = {"run": cmd_run, "top": cmd_top, "info": cmd_info,
            "serve": cmd_serve, "agent": cmd_agent, "ingest": cmd_ingest,
            "ingest-catalog": cmd_ingest_catalog,
            "ingest-case-sales": cmd_ingest_case_sales}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "run"
    handler = COMMANDS.get(cmd)
    if not handler:
        print(f"Comando desconhecido: {cmd}\nDisponiveis: {', '.join(COMMANDS)}")
        return 1
    handler(argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
