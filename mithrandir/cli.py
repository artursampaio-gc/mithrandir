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
    cfg = load_config()
    mode = "MOCK (dados de exemplo)" if cfg.mock_mode else "REAL"
    print(f"Mithrandir · modo {mode}")
    candidates = run_pipeline(cfg)
    out = generate(candidates, cfg.mock_mode)
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


COMMANDS = {"run": cmd_run, "top": cmd_top, "info": cmd_info,
            "serve": cmd_serve, "agent": cmd_agent}


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
