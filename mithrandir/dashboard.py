"""Gera o dashboard (RF-06) como um HTML auto-contido.

Os dados sao embutidos como JSON e a interatividade (filtro, ordenacao,
drill-down) roda 100% no navegador em JavaScript puro. Nao precisa de servidor:
basta abrir o arquivo. Consistente com o modo "rodar 1 comando por dia".
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import OUTPUT_DIR
from .models import Candidate


def _payload(candidates: list[Candidate], mock_mode: bool) -> dict:
    return {
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "mock_mode": mock_mode,
        "count": len(candidates),
        "candidates": [c.to_dict() for c in candidates],
    }


def generate(candidates: list[Candidate], mock_mode: bool,
             out_path: Path | None = None) -> Path:
    out_path = out_path or (OUTPUT_DIR / "dashboard.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = _payload(candidates, mock_mode)
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = _TEMPLATE.replace("__DATA__", data_json)
    out_path.write_text(html, encoding="utf-8")
    return out_path


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mithrandir — Candidatos</title>
<style>
  :root{--indigo:#4338ca;--indigo-d:#312e81;--indigo-l:#eef2ff;--ink:#1e293b;
    --muted:#64748b;--line:#e2e8f0;--bg:#f8fafc;--card:#fff;--green:#059669;--amber:#d97706}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    color:var(--ink);background:var(--bg);line-height:1.5;padding:28px 20px}
  .wrap{max-width:1120px;margin:0 auto}
  header{background:linear-gradient(135deg,var(--indigo-d),var(--indigo));color:#fff;
    border-radius:14px;padding:24px 28px}
  header h1{font-size:26px;font-weight:800;letter-spacing:-.02em}
  header .sub{opacity:.9;font-size:14px;margin-top:3px}
  .badges{margin-top:14px;display:flex;gap:10px;flex-wrap:wrap}
  .badge{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.25);
    border-radius:8px;padding:6px 12px;font-size:13px}
  .badge.mock{background:var(--amber);border-color:var(--amber);font-weight:700}
  .controls{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0 14px}
  .controls input,.controls select{padding:9px 12px;border:1px solid var(--line);
    border-radius:9px;font-size:14px;background:#fff}
  .controls input{flex:1;min-width:200px}
  table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
    border-radius:12px;overflow:hidden}
  th{background:var(--indigo-d);color:#fff;text-align:left;padding:11px 13px;font-size:12px;
    text-transform:uppercase;letter-spacing:.04em;cursor:pointer;user-select:none}
  th:hover{background:var(--indigo)}
  td{padding:11px 13px;border-top:1px solid var(--line);font-size:13.5px;vertical-align:middle}
  tbody tr{cursor:pointer}
  tbody tr:hover{background:var(--indigo-l)}
  .rankn{font-weight:800;color:var(--muted);width:34px}
  .model{font-weight:700}
  .model small{display:block;font-weight:400;color:var(--muted);font-size:11.5px}
  .pill{display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:20px}
  .pre{background:#e0e7ff;color:#3730a3}.post{background:#d1fae5;color:#047857}
  .scorebar{display:flex;align-items:center;gap:8px}
  .scorebar .bar{flex:1;height:8px;background:var(--line);border-radius:6px;overflow:hidden;min-width:60px}
  .scorebar .fill{height:100%;background:linear-gradient(90deg,var(--indigo),#818cf8)}
  .scorebar b{font-variant-numeric:tabular-nums;width:44px;text-align:right}
  .flag{font-size:11px;color:var(--amber);font-weight:600}
  /* Drawer */
  .backdrop{position:fixed;inset:0;background:rgba(15,23,42,.4);display:none;z-index:10}
  .drawer{position:fixed;top:0;right:0;height:100%;width:min(460px,92vw);background:#fff;
    box-shadow:-8px 0 30px rgba(0,0,0,.15);transform:translateX(100%);transition:.25s;
    z-index:11;overflow-y:auto;padding:24px}
  .drawer.open{transform:translateX(0)}
  .backdrop.open{display:block}
  .drawer h2{font-size:20px;margin-bottom:2px}
  .drawer .close{position:absolute;top:16px;right:18px;font-size:22px;border:none;background:none;
    cursor:pointer;color:var(--muted)}
  .sec{margin-top:18px}
  .sec h3{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
    margin-bottom:8px;border-bottom:1px solid var(--line);padding-bottom:5px}
  .kv{display:flex;justify-content:space-between;font-size:13.5px;padding:3px 0}
  .kv span:first-child{color:var(--muted)}
  .comp{margin:6px 0}
  .comp .lbl{display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:3px}
  .comp .track{height:7px;background:var(--line);border-radius:5px;overflow:hidden}
  .comp .val{height:100%;background:var(--indigo)}
  .srclist{font-size:12.5px;color:var(--ink)}
  .srclist li{padding:4px 0 4px 16px;position:relative;list-style:none}
  .srclist li::before{content:"•";position:absolute;left:2px;color:var(--indigo)}
  .empty{text-align:center;color:var(--muted);padding:30px}
  footer{text-align:center;color:var(--muted);font-size:12px;margin-top:22px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🧙 Mithrandir — Candidatos a capinha</h1>
    <div class="sub">Ranking priorizado de modelos de celular</div>
    <div class="badges" id="badges"></div>
  </header>

  <div class="controls">
    <input id="q" type="text" placeholder="Buscar modelo ou marca...">
    <select id="fbrand"><option value="">Todas as marcas</option></select>
    <select id="fphase">
      <option value="">Todas as fases</option>
      <option value="pre_launch">Pré-lançamento</option>
      <option value="post_launch">Pós-lançamento</option>
    </select>
  </div>

  <table>
    <thead><tr>
      <th data-k="rank">#</th>
      <th data-k="canonical_model">Modelo</th>
      <th data-k="brand">Marca</th>
      <th data-k="phase">Fase</th>
      <th data-k="score">Score</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none">Nenhum candidato com esses filtros.</div>

  <footer id="foot"></footer>
</div>

<div class="backdrop" id="backdrop"></div>
<div class="drawer" id="drawer"><button class="close" id="close">×</button><div id="detail"></div></div>

<script>
const DATA = __DATA__;
let sortKey = "score", sortDir = -1;

const phaseLabel = p => p === "pre_launch" ? "Pré-lançamento" : "Pós-lançamento";
const fmt = n => n === null || n === undefined ? "—" : n;
const money = n => n ? "R$ " + Number(n).toLocaleString("pt-BR",{minimumFractionDigits:0}) : "—";

function initBadges(){
  const b = document.getElementById("badges");
  const parts = [
    `<div class="badge">Gerado em ${DATA.generated_at}</div>`,
    `<div class="badge">${DATA.count} candidatos</div>`,
  ];
  if(DATA.mock_mode) parts.push(`<div class="badge mock">MODO MOCK — dados de exemplo</div>`);
  else parts.push(`<div class="badge">dados reais</div>`);
  b.innerHTML = parts.join("");
  const brands = [...new Set(DATA.candidates.map(c=>c.brand).filter(Boolean))].sort();
  const sel = document.getElementById("fbrand");
  brands.forEach(br=>{const o=document.createElement("option");o.value=br;o.textContent=br;sel.appendChild(o);});
}

function filtered(){
  const q = document.getElementById("q").value.toLowerCase();
  const fb = document.getElementById("fbrand").value;
  const fp = document.getElementById("fphase").value;
  let list = DATA.candidates.filter(c=>{
    if(fb && c.brand!==fb) return false;
    if(fp && c.phase!==fp) return false;
    if(q && !(c.canonical_model.toLowerCase().includes(q) || (c.brand||"").toLowerCase().includes(q))) return false;
    return true;
  });
  list.sort((a,b)=>{
    let va=a[sortKey], vb=b[sortKey];
    if(sortKey==="rank"){va=a.score;vb=b.score;return (vb-va);}
    if(typeof va==="string"){return sortDir*va.localeCompare(vb);}
    return sortDir*((va||0)-(vb||0));
  });
  return list;
}

function render(){
  const list = filtered();
  const tb = document.getElementById("rows");
  tb.innerHTML = "";
  list.forEach((c,i)=>{
    const tr = document.createElement("tr");
    const flags = [];
    if(c.already_have_case) flags.push("já temos capinha");
    if(c.similar_sold_poorly) flags.push("similar vendeu mal");
    tr.innerHTML = `
      <td class="rankn">${i+1}</td>
      <td class="model">${c.canonical_model}
        ${flags.length?`<small class="flag">⚠ ${flags.join(" · ")}</small>`:
          (c.predicted_launch?`<small>previsto: ${c.predicted_launch}</small>`:"")}</td>
      <td>${c.brand||"—"}</td>
      <td><span class="pill ${c.phase==='pre_launch'?'pre':'post'}">${phaseLabel(c.phase)}</span></td>
      <td><div class="scorebar"><div class="bar"><div class="fill" style="width:${c.score}%"></div></div><b>${c.score.toFixed(1)}</b></div></td>`;
    tr.onclick = ()=>openDrawer(c);
    tb.appendChild(tr);
  });
  document.getElementById("empty").style.display = list.length?"none":"block";
  document.getElementById("foot").textContent =
    `Mithrandir v0.1 · ${list.length} de ${DATA.count} candidatos exibidos`;
}

function comp(label, val){
  return `<div class="comp"><div class="lbl"><span>${label}</span><span>${val.toFixed(1)}</span></div>
    <div class="track"><div class="val" style="width:${val}%"></div></div></div>`;
}

function openDrawer(c){
  const b = c.score_breakdown || {};
  const comps = b.components_0_100 || {};
  const m = c.marketplace, inte = c.internal;
  let html = `<h2>${c.canonical_model}</h2>
    <div style="color:var(--muted);font-size:13px">${c.brand||""} · ${phaseLabel(c.phase)} · score <b>${c.score.toFixed(1)}</b></div>`;

  html += `<div class="sec"><h3>Componentes do score</h3>
    ${comp("Sinal de lançamento", comps.launch||0)}
    ${comp("Desempenho similar (BI)", comps.internal||0)}
    ${comp("Tração no marketplace", comps.traction||0)}
    ${comp("Momentum", comps.momentum||0)}</div>`;

  if(b.penalties && b.penalties.total){
    html += `<div class="sec"><h3>Penalidades</h3>`;
    if(b.penalties.already_have_case) html+=`<div class="kv"><span>Já temos capinha</span><span>-${b.penalties.already_have_case}</span></div>`;
    if(b.penalties.similar_sold_poorly) html+=`<div class="kv"><span>Similar vendeu mal</span><span>-${b.penalties.similar_sold_poorly}</span></div>`;
    html += `</div>`;
  }

  if(c.phase==="pre_launch"){
    html += `<div class="sec"><h3>Previsão de lançamento</h3>
      <div class="kv"><span>Janela prevista</span><span>${c.predicted_launch||"—"}</span></div>
      <div class="kv"><span>Confiança</span><span>${(c.launch_confidence*100).toFixed(0)}%</span></div></div>`;
  }

  if(m){
    html += `<div class="sec"><h3>Marketplace (${m.source})</h3>
      <div class="kv"><span>Posição no ranking</span><span>${fmt(m.rank)}</span></div>
      <div class="kv"><span>Avaliações</span><span>${fmt(m.review_count)}</span></div>
      <div class="kv"><span>Nota média</span><span>${fmt(m.rating)}</span></div>
      <div class="kv"><span>Preço</span><span>${money(m.price)}</span></div></div>`;
  }

  if(inte){
    html += `<div class="sec"><h3>Base interna (similar)</h3>
      <div class="kv"><span>Modelo similar</span><span>${inte.similar_model}</span></div>
      <div class="kv"><span>Unidades vendidas</span><span>${fmt(inte.units)}</span></div>
      <div class="kv"><span>Sell-through</span><span>${inte.sell_through_pct}%</span></div>
      <div class="kv"><span>Margem</span><span>${inte.margin_pct}%</span></div>
      <div class="kv"><span>Desempenho (0-100)</span><span>${inte.perf_score}</span></div></div>`;
  }

  if(c.sources && c.sources.length){
    html += `<div class="sec"><h3>Fontes</h3><ul class="srclist">
      ${c.sources.map(s=>`<li>${s}</li>`).join("")}</ul></div>`;
  }

  document.getElementById("detail").innerHTML = html;
  document.getElementById("drawer").classList.add("open");
  document.getElementById("backdrop").classList.add("open");
}
function closeDrawer(){
  document.getElementById("drawer").classList.remove("open");
  document.getElementById("backdrop").classList.remove("open");
}

document.querySelectorAll("th").forEach(th=>th.onclick=()=>{
  const k=th.dataset.k;
  if(k===sortKey) sortDir*=-1; else {sortKey=k; sortDir = (k==="canonical_model"||k==="brand")?1:-1;}
  render();
});
["q","fbrand","fphase"].forEach(id=>document.getElementById(id).addEventListener("input",render));
document.getElementById("close").onclick=closeDrawer;
document.getElementById("backdrop").onclick=closeDrawer;
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeDrawer();});

initBadges();
render();
</script>
</body>
</html>
"""
