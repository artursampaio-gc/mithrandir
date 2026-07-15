"""Servidor local do Mithrandir (biblioteca padrao, sem dependencias).

Serve um app de 3 abas (Candidatos, Calendario, Intel) e uma API JSON para
inserir intel manual que sobrepoe o scouting. Rode com:  python -m mithrandir serve
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import store
from .ai.proxy import AIClient
from .config import ROOT, load_config
from .intel_parser import parse_intel
from .launch_estimator import apply_overrides_to, build_calendar, clear_ai_cache
from .overrides import add_override, delete_override, load_overrides
from .pipeline import run_pipeline
from .settings import load_settings, save_settings

_cfg = load_config()


# Compute (grava no store). Pesado (IA) = calendario; leve = candidatos e intel.

def _rebuild_candidates() -> None:
    store.set_cached("candidates", [c.to_dict() for c in run_pipeline(_cfg)])


def _rebuild_calendar() -> None:
    """Recalcula o calendario base (IA) e aplica a intel. Pesado — usar no cron/refresh."""
    base = build_calendar(_cfg, with_overrides=False)
    store.set_cached("calendar_base", base)
    store.set_cached("calendar", apply_overrides_to(base))


def _apply_intel() -> None:
    """Reaplica a intel sobre o calendario base (barato, sem IA)."""
    base = store.get_cached("calendar_base")
    if base is None:
        _rebuild_calendar()
    else:
        store.set_cached("calendar", apply_overrides_to(base))


def _rebuild_all() -> None:
    _rebuild_candidates()
    _rebuild_calendar()


def _state() -> dict:
    cands = store.get_cached("candidates")
    # Local: enquanto o bootstrap roda, sinaliza "carregando" (a UI tenta de novo).
    if cands is None and not store.is_supabase():
        return {"loading": True}
    return {
        "mock_mode": _cfg.mock_mode,
        "ai_available": _cfg.ai.is_configured,
        "candidates": cands or [],
        "calendar": store.get_cached("calendar") or [],
        "overrides": load_overrides(),
        "settings": load_settings(),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencia o log padrao
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, APP_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json(_state())
        elif self.path == "/api/settings":
            self._json(load_settings())
        elif self.path in ("/favicon.svg", "/assets/favicon.svg"):
            self._serve_asset("favicon.svg")
        elif self.path == "/assets/logo.svg":
            self._serve_asset("logo.svg")
        elif self.path.split("?")[0] in ("/api/cron", "/api/cron/scout"):
            self._run_cron()  # Vercel Cron chama via GET
        else:
            self._send(404, b"not found", "text/plain")

    def _serve_asset(self, name: str) -> None:
        p = ROOT / "assets" / name
        if not p.exists():
            self._send(404, b"not found", "text/plain")
            return
        self._send(200, p.read_bytes(), "image/svg+xml; charset=utf-8")

    def do_POST(self):
        body = self._read_body()
        if self.path == "/api/intel":
            self._handle_intel(body)
        elif self.path == "/api/intel/delete":
            delete_override(int(body.get("id", -1)))
            _apply_intel()  # barato: reaplica intel sobre a base
            self._json({"ok": True, "state": _state()})
        elif self.path == "/api/refresh":
            clear_ai_cache()  # busca estimativas frescas da IA
            _rebuild_all()
            self._json({"ok": True, "state": _state()})
        elif self.path == "/api/settings":
            saved = save_settings(body)
            _rebuild_candidates()  # custos afetam a viabilidade (rapido, sem IA)
            self._json({"ok": True, "settings": saved, "state": _state()})
        elif self.path == "/api/agent":
            from .news_agent import refresh_news_cache
            try:
                updated = refresh_news_cache(ai=AIClient(_cfg.ai))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
                return
            clear_ai_cache()
            _rebuild_calendar()
            self._json({"ok": True, "updated": updated, "state": _state()})
        elif self.path in ("/api/cron", "/api/cron/scout"):
            self._run_cron()
        else:
            self._send(404, b"not found", "text/plain")

    def _run_cron(self) -> None:
        """Job diario: atualiza noticias (best-effort) + recalcula tudo."""
        from .news_agent import refresh_news_cache
        updated = []
        try:
            updated = refresh_news_cache(ai=AIClient(_cfg.ai))
        except Exception as e:
            print(f"[cron] agente falhou: {e}")
        clear_ai_cache()
        _rebuild_all()
        self._json({"ok": True, "updated": updated})

    def _handle_intel(self, body: dict):
        device = (body.get("device") or "").strip()
        date = body.get("date") or None
        note = (body.get("note") or body.get("text") or "").strip()
        confidence = float(body.get("confidence", 0.85))
        text = (body.get("text") or "").strip()

        # Caminho manual: device explicito -> grava direto
        if device:
            entry = add_override(device, date, confidence, note or text)
            _apply_intel()
            self._json({"ok": True, "entry": entry, "state": _state()})
            return

        # Caminho chat: interpreta o texto livre
        if not text:
            self._json({"ok": False, "error": "Informe um texto ou um device."}, 400)
            return
        parsed = parse_intel(text, AIClient(_cfg.ai))
        if parsed["needs_device"]:
            self._json({"ok": False, "needs_device": True, "parsed": parsed})
            return
        # respeita a data/confianca informadas na UI, se houver
        entry = add_override(parsed["device"], date or parsed["date"],
                             confidence, parsed["note"])
        _apply_intel()
        self._json({"ok": True, "entry": entry, "parsed": parsed, "state": _state()})


def serve(host: str = "127.0.0.1", port: int = 8756) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    # Constroi os dados em background para a porta responder imediatamente
    threading.Thread(target=_rebuild_all, daemon=True).start()
    print(f"Mithrandir no ar em http://{host}:{port}  (Ctrl+C para parar)")
    print(f"  scouting: {'MOCK' if _cfg.mock_mode else 'REAL'} | IA: {_cfg.ai.is_configured} "
          f"({_cfg.ai.model if _cfg.ai.is_configured else '-'})")
    print("  (preparando dados... a primeira carga leva alguns segundos)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
        httpd.shutdown()


APP_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mithrandir</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
:root{--gold:#CAB04A;--gold-b:#FFDF60;--gold-d:#c9a83f;--gold-ink:#d9bb57;--gold-l:#2b2612;--dark:#1e1e1e;
--indigo:#CAB04A;--indigo-d:#d9bb57;--indigo-l:#2b2612;--ink:#ededed;--muted:#9a9a9a;
--line:#2f2f2f;--bg:#141414;--card:#1f1f1f;--green:#34c759;--green-l:#16321f;--amber:#f0a020;
--amber-l:#3a2a08;--red:#ff5a52;--violet:#a78bfa;--violet-l:#2a2340}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--ink);
background:var(--bg);line-height:1.5;padding:24px 18px}
.wrap{max-width:1080px;margin:0 auto}
header{background:var(--dark);color:#fff;border-radius:14px;padding:22px 26px;border:1px solid #2e2a1a}
header h1{font-size:24px;font-weight:800}
header .logo{height:42px;width:auto;display:block}
header .sub{opacity:.9;font-size:13.5px;margin-top:2px}
.badges{margin-top:12px;display:flex;gap:8px;flex-wrap:wrap}
.badge{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.25);border-radius:8px;padding:5px 11px;font-size:12.5px}
.badge.mock{background:var(--amber);border-color:var(--amber);font-weight:700}
.refreshbtn{margin-top:12px;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.3);color:#fff;
border-radius:9px;padding:7px 14px;font-size:13px;font-weight:600;cursor:pointer}
.refreshbtn:hover{background:rgba(255,255,255,.26)}.refreshbtn:disabled{opacity:.6;cursor:default}
.tabs{display:flex;gap:6px;margin:18px 0 16px;border-bottom:2px solid var(--line)}
.tab{padding:10px 18px;font-size:14px;font-weight:650;color:var(--muted);cursor:pointer;border:none;
background:none;border-bottom:3px solid transparent;margin-bottom:-2px}
.tab.active{color:var(--gold-ink);border-bottom-color:var(--gold)}
.panel{display:none}.panel.active{display:block}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th{background:#262626;color:var(--gold);text-align:left;padding:10px 12px;font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;cursor:pointer}
td{padding:10px 12px;border-top:1px solid var(--line);font-size:13.5px}
tbody tr{cursor:pointer}tbody tr:hover{background:var(--indigo-l)}
.pill{display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:20px}
.pre{background:var(--violet-l);color:var(--violet)}.post{background:var(--green-l);color:var(--green)}
.scorebar{display:flex;align-items:center;gap:8px}.scorebar .bar{flex:1;height:8px;background:var(--line);border-radius:6px;overflow:hidden;min-width:50px}
.scorebar .fill{height:100%;background:linear-gradient(90deg,var(--gold-d),var(--gold-b))}.scorebar b{width:42px;text-align:right;font-variant-numeric:tabular-nums}
.flag{font-size:11px;color:var(--amber);font-weight:600}
/* calendario */
.monthgroup{margin-bottom:18px}
.monthlabel{font-size:13px;font-weight:750;color:var(--indigo-d);text-transform:capitalize;margin:6px 0 10px;
padding-bottom:5px;border-bottom:1px solid var(--line)}
.evt{background:var(--card);border:1px solid var(--line);border-left-width:5px;border-radius:10px;padding:14px 16px;margin-bottom:10px}
.evt.previsto{border-left-color:var(--indigo)}.evt.lancado{border-left-color:var(--green)}.evt.incerto{border-left-color:var(--muted)}
.evt .top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.evt .dev{font-weight:750;font-size:15px}
.evt .date{font-size:14px;font-weight:700;white-space:nowrap}
.evt .date small{display:block;font-weight:500;color:var(--muted);font-size:11px;text-align:right}
.tags{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.tag{font-size:11px;font-weight:600;padding:2px 8px;border-radius:6px}
.t-intel{background:var(--violet-l);color:var(--violet)}.t-ia{background:var(--indigo-l);color:var(--indigo)}
.t-noticias{background:#e0f2fe;color:#0369a1}.t-sazonal{background:var(--amber-l);color:var(--amber)}
.t-incerto{background:var(--line);color:var(--muted)}
.st-previsto{background:var(--indigo-l);color:#3730a3}.st-lancado{background:var(--green-l);color:#047857}.st-incerto{background:var(--line);color:var(--muted)}
.confbar{height:6px;background:var(--line);border-radius:5px;overflow:hidden;margin:8px 0;max-width:180px}
.confbar .v{height:100%;background:var(--indigo)}
.rationale{font-size:13px;color:var(--ink);margin:6px 0}
.evi{font-size:12px;color:var(--muted);margin-top:6px}
.evi a{color:var(--indigo);text-decoration:none}.evi a:hover{text-decoration:underline}
.evtbtn{margin-top:8px;font-size:12px;font-weight:600;color:var(--indigo);background:none;border:1px solid var(--indigo);
border-radius:7px;padding:5px 10px;cursor:pointer}.evtbtn:hover{background:var(--indigo-l)}
/* filtros + grade de calendario */
.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
.filters input[type=text],.filters select{padding:8px 11px;border:1px solid var(--line);border-radius:9px;font-size:13.5px;background:var(--card)}
.filters input[type=text]{flex:1;min-width:150px}
.fmini{font-size:12.5px;color:var(--muted);display:flex;align-items:center;gap:6px}
.pager{display:flex;align-items:center;gap:8px;margin:2px 0 16px}
.pgbtn{width:36px;height:36px;border:1px solid var(--line);background:var(--card);border-radius:9px;cursor:pointer;
font-size:14px;color:var(--ink);font-weight:700}
.pgbtn:hover:not(:disabled){background:var(--indigo-l)}
.pgbtn:disabled{opacity:.35;cursor:default}
.pgyears{display:flex;gap:6px}
.pgyear{border:1px solid var(--line);background:var(--card);border-radius:9px;padding:8px 18px;cursor:pointer;
font-size:14px;font-weight:700;color:var(--muted)}
.pgyear.on{background:var(--dark);color:var(--gold-b);border-color:var(--dark)}
.pgyear:hover:not(.on){background:var(--indigo-l)}
.sech{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700;margin:22px 0 11px}
.sech:first-child{margin-top:2px}
.calgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:14px}
.mcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;
min-height:118px;display:flex;flex-direction:column;box-shadow:0 1px 2px rgba(15,23,42,.04)}
.mcard.cur{border-color:var(--indigo);box-shadow:0 0 0 3px var(--indigo-l)}
.mcard.empty{background:#191919;border-style:dashed;border-color:var(--line);min-height:0;
box-shadow:none;justify-content:center;align-self:start}
.mhead{display:flex;justify-content:space-between;align-items:baseline;
border-bottom:1px solid var(--line);padding-bottom:9px;margin-bottom:11px}
.mcard.empty .mhead{border-bottom:none;padding-bottom:0;margin-bottom:0}
.mname{font-size:15px;font-weight:800;color:var(--indigo-d);text-transform:capitalize}
.mcard.empty .mname{color:var(--muted);font-weight:700;font-size:13.5px}
.myear{font-size:13px;color:var(--muted);font-weight:600;display:flex;align-items:center;gap:6px}
.cur-tag{font-size:9px;background:var(--dark);color:var(--gold-b);padding:2px 7px;border-radius:10px;
text-transform:uppercase;letter-spacing:.05em;font-weight:700}
.mini{display:flex;gap:9px;align-items:flex-start;padding:8px 9px;border-radius:9px;cursor:pointer;
margin-bottom:6px;background:var(--bg);transition:background .12s}
.mini:last-child{margin-bottom:0}
.mini:hover{background:var(--indigo-l)}
.mini .dot{flex:none;width:9px;height:9px;border-radius:50%;margin-top:5px}
.dot-previsto{background:var(--indigo)}.dot-lancado{background:var(--green)}.dot-incerto{background:var(--muted)}
.mini .mn{font-weight:650;font-size:13px;line-height:1.25}
.mini .mmeta{font-size:11px;color:var(--muted);margin-top:2px}
.mempty{color:#555;font-size:12px;text-align:center}
.pastwrap{display:flex;flex-wrap:wrap;gap:10px}
.pchip{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--green);
border-radius:10px;padding:9px 13px;cursor:pointer;min-width:180px;transition:background .12s}
.pchip:hover{background:var(--green-l)}
.pchip.unk{border-left-color:var(--muted)}.pchip.unk:hover{background:var(--line)}
.pchip .pn{font-weight:650;font-size:13px}
.pchip .pm{font-size:11px;color:var(--muted);margin-top:2px}
/* intel */
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-bottom:16px}
.card h3{font-size:15px;margin-bottom:4px}.card .hint{font-size:13px;color:var(--muted);margin-bottom:14px}
label{font-size:12.5px;font-weight:600;color:var(--muted);display:block;margin-bottom:4px;margin-top:10px}
textarea,input[type=text],input[type=date],input[type=number],select{width:100%;padding:9px 12px;border:1px solid var(--line);
border-radius:9px;font-size:14px;font-family:inherit;background:#262626;color:var(--ink)}
textarea{min-height:70px;resize:vertical}
.row{display:flex;gap:12px;flex-wrap:wrap}.row>div{flex:1;min-width:150px}
.btn{margin-top:14px;background:var(--gold);color:#1e1e1e;border:none;border-radius:9px;padding:10px 20px;
font-size:14px;font-weight:700;cursor:pointer}.btn:hover{background:var(--gold-b)}
.msg{margin-top:12px;font-size:13px;padding:10px 14px;border-radius:9px;display:none}
.msg.ok{background:var(--green-l);color:var(--green);display:block}.msg.err{background:#3a1512;color:var(--red);display:block}
.ovitem{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:11px 0;border-top:1px solid var(--line);font-size:13.5px}
.ovitem:first-child{border-top:none}
.ovitem .del{background:none;border:none;color:var(--red);cursor:pointer;font-size:18px}
.empty{color:var(--muted);font-size:13px;padding:8px 0}
/* relatorio de viabilidade (one-pager) */
.reportback{position:fixed;inset:0;background:rgba(15,23,42,.5);display:none;z-index:20}
.reportback.open{display:block}
.report{position:fixed;top:2.5vh;left:50%;transform:translateX(-50%);width:min(1400px,97vw);
max-height:95vh;overflow-y:auto;background:var(--card);border-radius:16px;z-index:21;display:none;
box-shadow:0 24px 70px rgba(0,0,0,.35);padding:22px 30px 28px}
.report.open{display:block}
.report .close{position:absolute;top:14px;right:18px;font-size:24px;border:none;background:none;cursor:pointer;color:var(--muted)}
.rhead{display:flex;gap:18px;align-items:flex-start;border:2px solid var(--gold-d);border-radius:12px;
padding:14px 18px;margin-bottom:18px}
.rbrand{font-size:26px;font-weight:900;letter-spacing:-.03em;color:var(--ink)}
.rtitle{flex:1;text-align:center}
.rtitle h2{font-size:19px;font-weight:800}
.rtitle div{font-size:13.5px;margin-top:3px}
.rmeta{text-align:right;font-size:13px;color:var(--muted);min-width:120px}
.rmeta .rscore{font-weight:800;color:var(--gold-ink);font-size:16px;margin:3px 0}
.rbody{display:grid;grid-template-columns:0.95fr 1.25fr 1.25fr;gap:26px}
.rsec{font-size:13px;font-weight:750;color:var(--indigo-d);margin:4px 0 9px;
border-bottom:1px solid var(--line);padding-bottom:5px}
.rsub{font-size:12px;color:var(--muted);margin:-5px 0 9px}
.vtab,.ftab,.rktab{width:100%;border-collapse:collapse;font-size:13px}
.vtab td,.ftab td{padding:5px 4px;border-bottom:1px solid var(--line)}
.vtab td.num,.ftab td.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
.vtab td.mom{text-align:right;font-size:11px;width:64px}
.mom.up{color:var(--green)}.mom.down{color:var(--red)}.mom.err{color:var(--amber)}
.vtab tr.ttl td{border-top:2px solid var(--gold-d);border-bottom:none;font-weight:800;padding-top:7px}
.vtab tr.ttl td.num{background:var(--gold-l)}
.ftab{margin-top:14px}
.ftab tr.hl td{background:var(--gold-l);font-weight:800}
.ftab tr.sp td{padding-top:12px}
.chart{width:100%;height:auto;display:block;margin-bottom:6px}
.grid{stroke:#2a2a2a;stroke-width:1}
.linev{fill:none;stroke:var(--gold-d);stroke-width:2}
.linec{fill:none;stroke:#94a3b8;stroke-width:2;stroke-dasharray:0}
.dotp{fill:var(--gold-d)}
.ptlbl{font-size:9px;fill:var(--muted);text-anchor:middle}
.axlbl{font-size:9px;fill:var(--muted);text-anchor:middle}
.ylbl{font-size:8px;fill:var(--muted);text-anchor:end}
.bex{fill:var(--ink);font-size:9px;font-weight:700;text-anchor:middle}
.bedot{fill:#fff;stroke:var(--ink);stroke-width:2}
.legend2{display:flex;gap:14px;font-size:12px;color:var(--muted);margin-bottom:4px}
.legend2 i{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:5px;vertical-align:middle}
.rktab th{font-size:10px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);text-align:left;padding:5px 6px;border-bottom:1px solid var(--line)}
.rktab td{font-size:12.5px;padding:6px;border-bottom:1px solid var(--line)}
.rktab td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rktab td:nth-child(2){white-space:nowrap}
.rktab .store{font-weight:700;text-transform:capitalize}
.rktab tr.tot td{font-weight:800;border-top:2px solid var(--gold-d);border-bottom:none}
@media(max-width:900px){.rbody{grid-template-columns:1fr}}
/* drawer */
.backdrop{position:fixed;inset:0;background:rgba(15,23,42,.4);display:none;z-index:10}
.backdrop.open{display:block}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(440px,92vw);background:var(--card);box-shadow:-8px 0 30px rgba(0,0,0,.15);
transform:translateX(100%);transition:.25s;z-index:11;overflow-y:auto;padding:22px}
.drawer.open{transform:translateX(0)}.drawer .close{position:absolute;top:14px;right:16px;font-size:22px;border:none;background:none;cursor:pointer;color:var(--muted)}
.sec{margin-top:16px}.sec h4{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:7px;border-bottom:1px solid var(--line);padding-bottom:4px}
.kv{display:flex;justify-content:space-between;font-size:13.5px;padding:3px 0}.kv span:first-child{color:var(--muted)}
.comp{margin:6px 0}.comp .lbl{display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:3px}
.comp .track{height:7px;background:var(--line);border-radius:5px;overflow:hidden}.comp .val{height:100%;background:var(--indigo)}
</style></head>
<body><div class="wrap">
<header>
  <img src="/assets/logo.svg" alt="Mithrandir" class="logo">
  <div class="sub">Scouting de celulares — candidatos, calendário de lançamentos e intel</div>
  <div class="badges" id="badges"></div>
  <button class="refreshbtn" id="agent">🔎 Buscar notícias (IA)</button>
  <button class="refreshbtn" id="refresh">🔄 Recalcular</button>
</header>

<div class="tabs">
  <button class="tab active" data-p="cal">📅 Calendário</button>
  <button class="tab" data-p="cand">🏆 Candidatos</button>
  <button class="tab" data-p="intel">🗒️ Intel</button>
  <button class="tab" data-p="config">⚙️ Config</button>
</div>

<div class="panel active" id="p-cal">
  <div class="filters">
    <input type="text" id="f-q" placeholder="Buscar device...">
    <select id="f-brand"><option value="">Todas as marcas</option></select>
    <select id="f-status"><option value="">Todos os status</option><option value="previsto">Previsto</option><option value="lancado">Lançado</option><option value="incerto">Incerto</option></select>
    <select id="f-source"><option value="">Todas as fontes</option><option value="intel">Intel</option><option value="ia">IA</option><option value="noticias">Notícias</option><option value="sazonal">Sazonal</option></select>
    <label class="fmini">Confiança ≥ <b id="f-cval">0</b>%<input type="range" id="f-conf" min="0" max="100" value="0"></label>
    <label class="fmini"><input type="checkbox" id="f-hidelaunched"> Ocultar lançados</label>
  </div>
  <div id="calendar"></div>
</div>

<div class="panel" id="p-cand">
  <table><thead><tr><th>#</th><th>Modelo</th><th>Marca</th><th>Fase</th><th>Score</th></tr></thead>
  <tbody id="candrows"></tbody></table>
</div>

<div class="panel" id="p-intel">
  <div class="card">
    <h3>Adicionar intel</h3>
    <div class="hint">O que você sabe (ex.: contato em fábrica) <b>sobrepõe</b> a estimativa online. Escreva livremente ou preencha os campos.</div>
    <label>Nota (texto livre)</label>
    <textarea id="i-text" placeholder="Ex.: Contato na fábrica confirmou que o Galaxy S26 FE chega ao Brasil em 25 de setembro de 2026."></textarea>
    <div class="row">
      <div><label>Device (opcional se a nota já cita)</label><input type="text" id="i-device" placeholder="Ex.: Samsung Galaxy S26 FE"></div>
      <div><label>Data (opcional)</label><input type="date" id="i-date"></div>
      <div><label>Confiança: <span id="i-cval">85</span>%</label><input type="range" id="i-conf" min="0" max="100" value="85"></div>
    </div>
    <button class="btn" id="i-submit">Salvar intel</button>
    <div class="msg" id="i-msg"></div>
  </div>
  <div class="card">
    <h3>Intel ativa</h3>
    <div class="hint">Estes registros sobrepõem o scouting no calendário.</div>
    <div id="ovlist"></div>
  </div>
</div>

<div class="panel" id="p-config">
  <div class="card">
    <h3>Financeiro (viabilidade)</h3>
    <div class="hint">Usados no cálculo de receita e breakeven da análise de cada candidato.</div>
    <div class="row">
      <div><label>Valor da capinha (R$)</label><input type="number" step="0.01" id="s-case"></div>
      <div><label>Custo do molde (R$)</label><input type="number" step="1" id="s-mold"></div>
      <div><label>Custo por unidade (R$)</label><input type="number" step="0.01" id="s-unit"></div>
    </div>
  </div>
  <div class="card">
    <h3>Scouting</h3>
    <div class="hint">Com que frequência o agente busca novidades. O agendamento é aplicado no sistema (ver docs).</div>
    <div class="row">
      <div><label>Frequência</label><select id="s-freq">
        <option value="diaria">Diária</option><option value="semanal">Semanal</option><option value="manual">Manual</option>
      </select></div>
      <div><label>Horário</label><input type="time" id="s-time"></div>
      <div><label>Meses de histórico (viabilidade)</label><input type="number" step="1" min="1" max="12" id="s-hist"></div>
    </div>
  </div>
  <button class="btn" id="s-save">Salvar configurações</button>
  <div class="msg" id="s-msg"></div>
</div>

</div>
<div class="backdrop" id="backdrop"></div>
<div class="drawer" id="drawer"><button class="close" id="close">×</button><div id="detail"></div></div>
<div class="reportback" id="reportback"></div>
<div class="report" id="report"><button class="close" id="rclose">×</button><div id="rcontent"></div></div>

<script>
let STATE=null;
let calYear=null;  // ano exibido no calendario (paginacao)
const MONTHS_PT=["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"];
const $=id=>document.getElementById(id);
const phaseLabel=p=>p==='pre_launch'?'pré-lançamento':'pós-lançamento';

async function load(){
  const s=await (await fetch('/api/state')).json();
  if(s.loading){
    $('calendar').innerHTML='<div class="empty">⏳ Preparando dados e consultando a IA… aguarde.</div>';
    setTimeout(load,1500); return;
  }
  STATE=s; renderAll();
}
async function post(url,body){ return await (await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})).json(); }

function renderAll(){ renderBadges(); renderCalendar(); renderCandidates(); renderOverrides(); renderSettings(); }
function renderSettings(){
  const s=STATE.settings||{};
  $('s-case').value=s.case_price; $('s-mold').value=s.mold_cost; $('s-unit').value=s.unit_cost;
  $('s-freq').value=s.scouting_frequency||'diaria'; $('s-time').value=s.scouting_time||'08:00';
  $('s-hist').value=s.history_months||6;
}

function renderBadges(){
  const p=[`<div class="badge">${STATE.candidates.length} candidatos</div>`,
    `<div class="badge">${STATE.calendar.length} no calendário</div>`];
  p.push(STATE.mock_mode?`<div class="badge mock">MODO MOCK</div>`:`<div class="badge">dados reais</div>`);
  p.push(`<div class="badge">IA: ${STATE.ai_available?'proxy ligado':'heurística'}</div>`);
  $('badges').innerHTML=p.join('');
}

function fmtDate(iso,prec){
  if(!iso) return {big:"Sem data",small:"a confirmar"};
  const [y,m,d]=iso.split('-').map(Number);
  if(prec==='day') return {big:`${String(d).padStart(2,'0')}/${String(m).padStart(2,'0')}/${y}`,small:MONTHS_PT[m-1]};
  return {big:`${MONTHS_PT[m-1]}/${y}`,small:"mês estimado"};
}
function monthKey(iso){ if(!iso) return "Sem data confirmada"; const[y,m]=iso.split('-').map(Number); return `${MONTHS_PT[m-1]} de ${y}`; }

function srcLabel(s){return {intel:"✋ intel",ia:"🤖 IA",noticias:"📰 notícias",sazonal:"📈 sazonal",incerto:"❓ incerto"}[s]||s;}
function ymToIdx(ym){const[y,m]=ym.split('-').map(Number);return y*12+(m-1);}
function idxToYm(i){return `${Math.floor(i/12)}-${String(i%12+1).padStart(2,'0')}`;}
function curYm(){const n=new Date();return `${n.getFullYear()}-${String(n.getMonth()+1).padStart(2,'0')}`;}

function populateBrands(){
  const sel=$('f-brand'), cur=sel.value;
  const brands=[...new Set(STATE.calendar.map(e=>e.brand).filter(Boolean))].sort();
  sel.innerHTML='<option value="">Todas as marcas</option>'+brands.map(b=>`<option>${b}</option>`).join('');
  sel.value=cur;
}
function filteredCal(){
  const q=$('f-q').value.toLowerCase(),fb=$('f-brand').value,fs=$('f-status').value,
    fsrc=$('f-source').value,fc=(+$('f-conf').value)/100,hide=$('f-hidelaunched').checked;
  return STATE.calendar.filter(e=>{
    if(fb&&e.brand!==fb)return false;
    if(fs&&e.status!==fs)return false;
    if(fsrc&&e.source!==fsrc)return false;
    if((e.confidence||0)<fc)return false;
    if(hide&&e.status==='lancado')return false;
    if(q&&!e.device.toLowerCase().includes(q))return false;
    return true;
  });
}
function evCount(e){const n=(e.evidence||[]).length;return (n&&e.source!=='noticias')?` · ${n} notícia${n>1?'s':''}`:'';}
function miniMeta(e){return `${srcLabel(e.source)}${evCount(e)} · ${(e.confidence*100).toFixed(0)}%`;}
function miniCard(e){
  return `<div class="mini" onclick="openEstimate('${e.canonical}')">
    <span class="dot dot-${e.status}"></span>
    <div><div class="mn">${e.device}</div><div class="mmeta">${miniMeta(e)}</div></div></div>`;
}
function calYears(){
  // Anos disponiveis: atual e proximo, mais qualquer ano com evento datado
  const cyY=+curYm().split('-')[0]; let maxY=cyY+1;
  STATE.calendar.forEach(e=>{if(e.estimated_date){const y=+e.estimated_date.slice(0,4); if(y>maxY)maxY=y;}});
  const ys=[]; for(let y=cyY;y<=maxY;y++) ys.push(y); return ys;
}
function renderCalendar(){
  populateBrands();
  const years=calYears();
  if(calYear==null||!years.includes(calYear)) calYear=years[0];
  const idx=years.indexOf(calYear);
  const list=filteredCal();
  const undated=list.filter(e=>!e.estimated_date);
  const byMonth={};
  list.filter(e=>e.estimated_date).forEach(e=>{const k=e.estimated_date.slice(0,7);(byMonth[k]=byMonth[k]||[]).push(e);});
  const cy=curYm();

  // Paginacao por ano
  let html=`<div class="pager">
    <button class="pgbtn" id="py-prev" ${idx<=0?'disabled':''} title="Ano anterior">◀</button>
    <div class="pgyears">${years.map(y=>`<button class="pgyear ${y===calYear?'on':''}" data-y="${y}">${y}${y===+cy.split('-')[0]?' •':''}</button>`).join('')}</div>
    <button class="pgbtn" id="py-next" ${idx>=years.length-1?'disabled':''} title="Proximo ano">▶</button>
  </div>`;

  html+='<div class="calgrid">';
  for(let m=1;m<=12;m++){
    const ym=`${calYear}-${String(m).padStart(2,'0')}`, evs=byMonth[ym]||[], cur=(ym===cy);
    html+=`<div class="mcard ${evs.length?'':'empty'} ${cur?'cur':''}">
      <div class="mhead"><span class="mname">${MONTHS_PT[m-1]}</span>
        <span class="myear">${cur?'<span class="cur-tag">atual</span>':''}${calYear}</span></div>
      ${evs.length?evs.map(miniCard).join(''):'<div class="mempty">—</div>'}</div>`;
  }
  html+='</div>';

  // Sem data confirmada (independe do ano)
  if(undated.length){
    html+='<div class="sech">❓ Sem data confirmada</div><div class="pastwrap">';
    undated.forEach(e=>{html+=`<div class="pchip unk" onclick="openEstimate('${e.canonical}')">
      <div class="pn">${e.device}</div><div class="pm">${miniMeta(e)}</div></div>`;});
    html+='</div>';
  }
  $('calendar').innerHTML=html;

  // liga os controles de paginacao
  const prev=$('py-prev'), next=$('py-next');
  if(prev) prev.onclick=()=>{calYear=years[Math.max(0,idx-1)]; renderCalendar();};
  if(next) next.onclick=()=>{calYear=years[Math.min(years.length-1,idx+1)]; renderCalendar();};
  document.querySelectorAll('.pgyear').forEach(b=>b.onclick=()=>{calYear=+b.dataset.y; renderCalendar();});
}
function openEstimate(canon){
  const e=STATE.calendar.find(x=>x.canonical===canon); if(!e)return;
  const dt=fmtDate(e.estimated_date,e.date_precision);
  const evi=(e.evidence||[]).map(s=>`<div style="font-size:12.5px;padding:4px 0;color:var(--muted)">• <a href="${s.url}" target="_blank" rel="noopener" style="color:var(--indigo);text-decoration:none">${s.source}</a> — ${s.text||''}</div>`).join('');
  let h=`<h2>${e.device}</h2><div style="color:var(--muted);font-size:13px">${e.brand||''}</div>
    <div class="sec"><h4>Estimativa</h4>
      <div class="kv"><span>Data</span><span>${dt.big} <span style="color:var(--muted)">(${dt.small})</span></span></div>
      <div class="kv"><span>Status</span><span>${e.status}</span></div>
      <div class="kv"><span>Fonte</span><span>${srcLabel(e.source)}</span></div>
      <div class="kv"><span>Confiança</span><span>${(e.confidence*100).toFixed(0)}%</span></div></div>
    <div class="sec"><h4>Justificativa</h4><div style="font-size:13.5px">${e.rationale||'—'}</div></div>`;
  if(evi)h+=`<div class="sec"><h4>Evidências</h4>${evi}</div>`;
  h+=`<div class="sec"><button class="btn" onclick='prefillIntel(${JSON.stringify(e.device)})'>✋ Tenho info melhor</button></div>`;
  $('detail').innerHTML=h; $('drawer').classList.add('open'); $('backdrop').classList.add('open');
}

function renderCandidates(){
  const tb=$('candrows'); tb.innerHTML="";
  STATE.candidates.forEach((c,i)=>{
    const flags=[]; if(c.already_have_case)flags.push("já temos capinha"); if(c.similar_sold_poorly)flags.push("similar vendeu mal");
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><b style="color:var(--muted)">${i+1}</b></td>
      <td><b>${c.canonical_model}</b>${flags.length?`<br><small class="flag">⚠ ${flags.join(" · ")}</small>`:""}</td>
      <td>${c.brand||"—"}</td>
      <td><span class="pill ${c.phase==='pre_launch'?'pre':'post'}">${c.phase==='pre_launch'?'pré':'pós'}-lançamento</span></td>
      <td><div class="scorebar"><div class="bar"><div class="fill" style="width:${c.score}%"></div></div><b>${c.score.toFixed(1)}</b></div></td>`;
    tr.onclick=()=>openReport(c); tb.appendChild(tr);
  });
}

function comp(l,v){return `<div class="comp"><div class="lbl"><span>${l}</span><span>${v.toFixed(1)}</span></div><div class="track"><div class="val" style="width:${v}%"></div></div></div>`;}
function openDrawer(c){
  const b=c.score_breakdown||{},k=b.components_0_100||{},m=c.marketplace,inte=c.internal;
  let h=`<h2>${c.canonical_model}</h2><div style="color:var(--muted);font-size:13px">${c.brand||""} · score ${c.score.toFixed(1)}</div>`;
  h+=`<div class="sec"><h4>Componentes do score</h4>${comp("Sinal de lançamento",k.launch||0)}${comp("Desempenho similar (BI)",k.internal||0)}${comp("Tração marketplace",k.traction||0)}${comp("Momentum",k.momentum||0)}</div>`;
  if(b.penalties&&b.penalties.total){h+=`<div class="sec"><h4>Penalidades</h4>`;
    if(b.penalties.already_have_case)h+=`<div class="kv"><span>Já temos capinha</span><span>-${b.penalties.already_have_case}</span></div>`;
    if(b.penalties.similar_sold_poorly)h+=`<div class="kv"><span>Similar vendeu mal</span><span>-${b.penalties.similar_sold_poorly}</span></div>`;h+=`</div>`;}
  if(m){h+=`<div class="sec"><h4>Marketplace</h4><div class="kv"><span>Ranking</span><span>${m.rank??"—"}</span></div><div class="kv"><span>Avaliações</span><span>${m.review_count??"—"}</span></div><div class="kv"><span>Nota</span><span>${m.rating??"—"}</span></div></div>`;}
  if(inte){h+=`<div class="sec"><h4>Base interna (similar)</h4><div class="kv"><span>Similar</span><span>${inte.similar_model}</span></div><div class="kv"><span>Unidades</span><span>${inte.units}</span></div><div class="kv"><span>Sell-through</span><span>${inte.sell_through_pct}%</span></div></div>`;}
  if(c.sources&&c.sources.length){h+=`<div class="sec"><h4>Fontes</h4>${c.sources.map(s=>`<div style="font-size:12.5px;padding:2px 0">• ${s}</div>`).join("")}</div>`;}
  $('detail').innerHTML=h; $('drawer').classList.add('open'); $('backdrop').classList.add('open');
}
function closeDrawer(){$('drawer').classList.remove('open');$('backdrop').classList.remove('open');}

/* ---- Relatorio de viabilidade (one-pager) ---- */
const money2=n=>(n||n===0)?'R$ '+Number(n).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
function momStr(m){if(m===null||m===undefined)return '';if(m==='div0')return '#DIV/0!';return (m>0?'▲ +':(m<0?'▼ ':''))+m+'%';}
function momCls(m){if(m==='div0')return 'err';if(m>0)return 'up';if(m<0)return 'down';return '';}

function salesChart(months){
  const W=340,H=168,pl=30,pr=14,pt=18,pb=24,n=months.length;
  const maxU=Math.max(...months.map(m=>m.units),1);
  const X=i=>pl+(n<=1?0:i*(W-pl-pr)/(n-1));
  const Y=u=>pt+(H-pt-pb)*(1-u/(maxU*1.15));
  let grid='';for(let k=0;k<=2;k++){const gy=(pt+(H-pt-pb)*k/2).toFixed(1);grid+=`<line class="grid" x1="${pl}" y1="${gy}" x2="${W-pr}" y2="${gy}"/>`;}
  const pts=months.map((m,i)=>`${X(i).toFixed(1)},${Y(m.units).toFixed(1)}`).join(' ');
  const dots=months.map((m,i)=>`<circle class="dotp" cx="${X(i).toFixed(1)}" cy="${Y(m.units).toFixed(1)}" r="3.5"/><text class="ptlbl" x="${X(i).toFixed(1)}" y="${(Y(m.units)-7).toFixed(1)}">${m.units}</text>`).join('');
  const lbls=months.map((m,i)=>`<text class="axlbl" x="${X(i).toFixed(1)}" y="${H-7}">${m.label.slice(0,3)}</text>`).join('');
  return `<svg viewBox="0 0 ${W} ${H}" class="chart">${grid}<polyline class="linev" points="${pts}"/>${dots}${lbls}</svg>`;
}
function breakevenChart(v){
  const W=340,H=185,pl=48,pr=14,pt=14,pb=24;
  const be=v.breakeven_weeks||7, Wk=Math.max(10,Math.ceil(be*1.5));
  const qWeek=v.avg_week;                 // capinhas por semana
  const custo=w=>v.mold_cost + v.unit_cost*qWeek*w;   // molde + custo das unidades
  const receita=w=>v.case_price*qWeek*w;              // receita das vendas
  const maxY=Math.max(receita(Wk),custo(Wk))*1.08;
  const X=w=>pl+w*(W-pl-pr)/Wk;           // eixo x de 0..Wk (semanas)
  const Y=val=>pt+(H-pt-pb)*(1-val/maxY);
  let grid='',ylab='';
  for(let k=0;k<=2;k++){const val=maxY*k/2,gy=Y(val).toFixed(1);
    grid+=`<line class="grid" x1="${pl}" y1="${gy}" x2="${W-pr}" y2="${gy}"/>`;
    ylab+=`<text class="ylbl" x="${pl-5}" y="${(+gy+3).toFixed(1)}">R$ ${Math.round(val/1000)}k</text>`;}
  let cp=[],rp=[];
  for(let w=0;w<=Wk;w++){cp.push(`${X(w).toFixed(1)},${Y(custo(w)).toFixed(1)}`);rp.push(`${X(w).toFixed(1)},${Y(receita(w)).toFixed(1)}`);}
  let xlab='';for(let w=0;w<=Wk;w+=2)xlab+=`<text class="axlbl" x="${X(w).toFixed(1)}" y="${H-7}">${w}</text>`;
  const cx=X(Math.min(be,Wk)).toFixed(1),cy=Y(custo(Math.min(be,Wk))).toFixed(1);
  const cross=`<circle class="bedot" cx="${cx}" cy="${cy}" r="4.5"/><text class="bex" x="${cx}" y="${(+cy-9).toFixed(1)}">${v.breakeven_weeks} sem</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" class="chart">${grid}${ylab}<polyline class="linec" points="${cp.join(' ')}"/><polyline class="linev" points="${rp.join(' ')}"/>${cross}${xlab}</svg>`;
}
function rankingsTable(rk){
  const totVal=rk.reduce((a,r)=>a+(r.value||0),0)/rk.length;
  const totRev=rk.reduce((a,r)=>a+(r.reviews||0),0);
  return `<table class="rktab"><thead><tr><th>Loja</th><th>Posição</th><th>Critério</th><th class="num">Valor</th><th class="num">Reviews</th></tr></thead><tbody>
    ${rk.map(r=>`<tr><td class="store">${r.store}</td><td>${r.position}</td><td>${r.criterio}</td><td class="num">${money2(r.value)}</td><td class="num">${(r.reviews||0).toLocaleString('pt-BR')}</td></tr>`).join('')}
    <tr class="tot"><td colspan="3">Média / Total</td><td class="num">${money2(totVal)}</td><td class="num">${totRev.toLocaleString('pt-BR')}</td></tr>
  </tbody></table>`;
}
function openReport(c){
  const v=c.viability, hasV=v&&v.months&&v.months.length;
  const today=new Date().toLocaleDateString('pt-BR');
  let col1='',col2='';
  if(hasV){
    col1=`<div class="rcol"><div class="rsec">Vendas últimos 6 meses</div>
      <table class="vtab"><tbody>
        ${v.months.map(m=>`<tr><td>${m.label}</td><td class="num">${m.units}</td><td class="mom ${momCls(m.mom)}">${momStr(m.mom)}</td></tr>`).join('')}
        <tr class="ttl"><td>Total</td><td class="num">${v.total}</td><td class="mom">${v.per_day}/dia</td></tr>
      </tbody></table>
      <table class="ftab"><tbody>
        <tr><td>Valor Case</td><td class="num">${money2(v.case_price)}</td></tr>
        <tr class="hl"><td>Receita</td><td class="num">${money2(v.receita_mes)} /mês</td></tr>
        <tr class="sp"><td>Custo Molde</td><td class="num">${money2(v.mold_cost)}</td></tr>
        <tr><td>Custo p/ Und.</td><td class="num">${money2(v.unit_cost)}</td></tr>
        <tr><td>Méd. Vendas</td><td class="num">${v.avg_month} un/mês</td></tr>
        <tr><td></td><td class="num">${v.avg_week} un/sem</td></tr>
        <tr class="sp hl"><td>Breakeven</td><td class="num">${v.breakeven_weeks} sem.</td></tr>
        <tr><td>Qtd p/ Breakeven</td><td class="num">${v.qtd_breakeven} cases</td></tr>
      </tbody></table></div>`;
    col2=`<div class="rcol"><div class="rsec">Vendas (6 meses)</div>${salesChart(v.months)}
      <div class="rsec">Custo × Vendas (breakeven)</div>
      <div class="legend2"><span><i style="background:#94a3b8"></i>Custo total (molde + capinhas)</span><span><i style="background:var(--gold-d)"></i>Receita (vendas)</span></div>
      ${breakevenChart(v)}</div>`;
  } else {
    col1=`<div class="rcol"><div class="rsec">Viabilidade</div><div class="empty">Sem base interna de vendas para este device.</div></div>`;
  }
  const col3=`<div class="rcol"><div class="rsec">Rankings 🏆</div><div class="rsub">Tração nos marketplaces</div>
    ${c.rankings&&c.rankings.length?rankingsTable(c.rankings):'<div class="empty">Sem dados de marketplace ainda (device pré-lançamento).</div>'}</div>`;
  $('rcontent').innerHTML=`
    <div class="rhead"><div class="rbrand">gocase</div>
      <div class="rtitle"><h2>Análise de Viabilidade de Novo Device</h2>
        <div>Device proposto: <b>${c.canonical_model}</b></div>
        <div>Device de estudo: <b>${c.internal?c.internal.similar_model:'—'}</b></div></div>
      <div class="rmeta"><div>${today}</div><div class="rscore">score ${c.score.toFixed(1)}</div>
        <span class="pill ${c.phase==='pre_launch'?'pre':'post'}">${phaseLabel(c.phase)}</span></div></div>
    <div class="rbody">${col1}${col2}${col3}</div>`;
  $('report').classList.add('open');$('reportback').classList.add('open');
}
function closeReport(){$('report').classList.remove('open');$('reportback').classList.remove('open');}

function renderOverrides(){
  const el=$('ovlist');
  if(!STATE.overrides.length){el.innerHTML=`<div class="empty">Nenhuma intel cadastrada ainda.</div>`;return;}
  el.innerHTML=STATE.overrides.map(o=>`<div class="ovitem"><div>
    <b>${o.device}</b> — ${o.date||"sem data"} <span style="color:var(--muted)">(${(o.confidence*100).toFixed(0)}%)</span>
    ${o.note?`<br><small style="color:var(--muted)">${o.note}</small>`:""}</div>
    <button class="del" title="Remover" onclick="delOverride(${o.id})">🗑</button></div>`).join("");
}

function prefillIntel(dev){ closeDrawer(); switchTab('intel'); $('i-device').value=dev; $('i-text').focus(); }
async function delOverride(id){ const r=await post('/api/intel/delete',{id}); if(r.ok){STATE=r.state;renderAll();} }

async function submitIntel(){
  const text=$('i-text').value.trim(), device=$('i-device').value.trim();
  const date=$('i-date').value||null, conf=(+$('i-conf').value)/100;
  const msg=$('i-msg'); msg.className='msg';
  if(!text&&!device){msg.className='msg err';msg.textContent='Escreva uma nota ou informe o device.';return;}
  const r=await post('/api/intel',{text,device,date,confidence:conf,note:text});
  if(r.ok){ STATE=r.state; renderAll();
    msg.className='msg ok'; msg.textContent=`Intel salva para "${r.entry.device}" (${r.entry.date||'sem data'}). Aplicada no calendário.`;
    $('i-text').value='';$('i-device').value='';$('i-date').value='';
  } else if(r.needs_device){
    msg.className='msg err'; msg.textContent='Não identifiquei o device na nota. Preencha o campo "Device" e salve de novo.';
  } else { msg.className='msg err'; msg.textContent=r.error||'Erro ao salvar.'; }
}

function switchTab(p){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.p===p));
  document.querySelectorAll('.panel').forEach(pl=>pl.classList.toggle('active',pl.id==='p-'+p));
}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>switchTab(t.dataset.p));
['f-q','f-brand','f-status','f-source','f-conf','f-hidelaunched'].forEach(id=>{
  $(id).addEventListener('input',renderCalendar); $(id).addEventListener('change',renderCalendar);
});
$('f-conf').addEventListener('input',e=>$('f-cval').textContent=e.target.value);
$('i-conf').oninput=e=>$('i-cval').textContent=e.target.value;
$('i-submit').onclick=submitIntel;
$('refresh').onclick=async()=>{const b=$('refresh');b.disabled=true;b.textContent='Recalculando…';
  const r=await post('/api/refresh');if(r.ok&&!r.state.loading){STATE=r.state;renderAll();}
  b.disabled=false;b.textContent='🔄 Recalcular';};
$('agent').onclick=async()=>{const b=$('agent');b.disabled=true;b.textContent='Buscando notícias…';
  const r=await post('/api/agent');
  if(r.ok&&r.state&&!r.state.loading){STATE=r.state;renderAll();
    switchTab('cal');alert('Agente atualizou: '+(r.updated&&r.updated.length?r.updated.join(', '):'nenhum device'));}
  else{alert('Falha no agente: '+(r.error||'erro'));}
  b.disabled=false;b.textContent='🔎 Buscar notícias (IA)';};
$('close').onclick=closeDrawer; $('backdrop').onclick=closeDrawer;
$('rclose').onclick=closeReport; $('reportback').onclick=closeReport;
$('s-save').onclick=async()=>{
  const b=$('s-save'),msg=$('s-msg'); b.disabled=true; b.textContent='Salvando…'; msg.className='msg';
  const patch={case_price:+$('s-case').value,mold_cost:+$('s-mold').value,unit_cost:+$('s-unit').value,
    scouting_frequency:$('s-freq').value,scouting_time:$('s-time').value,history_months:+$('s-hist').value};
  const r=await post('/api/settings',patch);
  if(r.ok&&r.state&&!r.state.loading){STATE=r.state;renderAll();switchTab('config');
    msg.className='msg ok';msg.textContent='Configurações salvas. Viabilidade recalculada com os novos custos.';}
  else{msg.className='msg err';msg.textContent='Erro ao salvar.';}
  b.disabled=false; b.textContent='Salvar configurações';};
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeDrawer();closeReport();}});
load();
</script>
</body></html>
"""
