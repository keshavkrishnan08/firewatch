"""Build the FIREWATCH site: a self-contained dark research tool with four tabs (Overview, Fires,
Pipeline, Results). Reads outputs/historical.json + outputs/showcase.json. Videos are embedded as
MP4; still images are downscaled to compact JPEG so the page can carry many of them.
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "docs" / "assets"

META = {
    "park": {"region": "Tehama & Butte Counties, California", "when": "24 Jul 2024"},
    "palisades": {"region": "Pacific Palisades, Los Angeles", "when": "07 Jan 2025"},
    "eaton": {"region": "Altadena / Eaton Canyon, California", "when": "07 Jan 2025"},
}
TRACK_DESC = ("The satellite watches the fire. Orange is the fire the satellite actually sees; cyan is "
              "the path the model tracks as it follows the fire; the blue line at the bottom says which "
              "step the model is running. Once the model issues a forecast, the dashed outline is where "
              "it thinks the fire will go.")
RESP_DESC = ("The model projects the fire forward. The shaded area is how likely each place is to burn "
             "(yellow is lower, red is higher). Towns turn red when the forecast reaches them, with the "
             "number of residents nearby. This is an estimate of who is exposed, not an evacuation order.")


def vid(p: Path) -> str:
    return "data:video/mp4;base64," + base64.b64encode(p.read_bytes()).decode()


def img(p: Path, maxw: int = 720, q: int = 82) -> str:
    """Downscale to a compact JPEG data URI so the page can carry many images."""
    try:
        from PIL import Image
        im = Image.open(p).convert("RGB")
        if im.width > maxw:
            im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def build(out_path: Path) -> Path:
    data = json.loads((REPO / "outputs" / "historical.json").read_text())
    data = [d for d in data if (ASSETS / (d.get("video_asset") or "x")).exists()]
    if not data:
        sys.exit("no historical results")
    sp = REPO / "outputs" / "showcase.json"
    show = json.loads(sp.read_text()) if sp.exists() else {}

    events = []
    for d in data:
        m = META.get(d["key"], {"region": "", "when": ""})
        evo = [{"img": img(ASSETS / e["asset"], 460), "t": e["t_min"], "cap": e["caption"]}
               for e in d.get("evolution", []) if (ASSETS / e["asset"]).exists()]
        events.append({
            "key": d["key"], "name": d["name"].split(" (")[0], "full": d["name"],
            "region": m["region"], "when": m["when"], "center": d.get("center", [None, None]),
            "area": round(d["peak_area_km2"]), "detections": d["goes_detections"],
            "ros": d["mean_ros_kmh"], "iou_on": d["iou_on"], "iou_off": d["iou_off"],
            "delta": d["ablation_delta_iou"], "skill": d.get("skill_by_horizon", []),
            "tracking": vid(ASSETS / d["video_asset"]),
            "tracking_poster": img(ASSETS / f"poster_{d['key']}.png", 600) if (ASSETS / f"poster_{d['key']}.png").exists() else "",
            "response": vid(ASSETS / d["response_asset"]) if d.get("response_asset") and (ASSETS / d["response_asset"]).exists() else "",
            "response_poster": img(ASSETS / f"response_poster_{d['key']}.png", 600) if (ASSETS / f"response_poster_{d['key']}.png").exists() else "",
            "evolution": evo,
        })

    pipeline = [{"title": s["title"], "subtitle": s["subtitle"], "desc": s["desc"],
                 "inputs": s.get("inputs", []), "process": s.get("process", []), "outputs": s.get("outputs", []),
                 "figure": img(ASSETS / s["figure"], 760) if s.get("figure") and (ASSETS / s["figure"]).exists() else ""}
                for s in show.get("pipeline", [])]
    results = {k: img(ASSETS / fn, 900) for k, fn in (show.get("results") or {}).items() if fn and (ASSETS / fn).exists()}

    model = {"events": events, "pipeline": pipeline, "results": results,
             "track_desc": TRACK_DESC, "resp_desc": RESP_DESC}
    html = TEMPLATE.replace("/*__DATA__*/", json.dumps(model, separators=(",", ":")))
    out_path.write_text(html)
    # also write index.html next to it so a static server serves the page at the root URL
    (out_path.parent / "index.html").write_text(html)
    print(f"wrote {out_path} + index.html ({out_path.stat().st_size // 1024} KB, {len(events)} fires, {len(pipeline)} stages)")
    return out_path


TEMPLATE = r"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FIREWATCH</title>
<style>
:root{--bg:#0b0d0f;--surface:#12161b;--surface-2:#0e1216;--border:#242a31;--border-2:#2f3740;
  --text:#e7eaed;--text-2:#9aa3ad;--text-3:#69707a;--blue:#4c9aff;--fire:#ff6848;--fire-2:#f2b84b;
  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",system-ui,sans-serif;
  --mono:ui-monospace,"SF Mono","SFMono-Regular",Menlo,monospace}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;
  line-height:1.6;-webkit-font-smoothing:antialiased;letter-spacing:-.01em}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.nav{display:flex;align-items:center;gap:22px;height:52px;padding:0 24px;border-bottom:1px solid var(--border);
  position:sticky;top:0;background:rgba(11,13,15,.9);backdrop-filter:blur(8px);z-index:40}
.brand{font-weight:600;letter-spacing:.02em;font-size:16px}.brand b{color:var(--fire)}
.tabs{display:flex;gap:2px}
.tab{background:none;border:0;border-bottom:2px solid transparent;color:var(--text-2);font-family:inherit;
  font-size:14px;padding:16px 12px;margin-bottom:-1px;cursor:pointer;font-weight:500}
.tab.on{color:var(--text);border-color:var(--blue)}
.sys{margin-left:auto;display:flex;align-items:center;gap:9px;font-family:var(--mono);font-size:11px;color:var(--text-3)}
.sys .dot{width:6px;height:6px;border-radius:50%;background:var(--blue)}
.page{max-width:1080px;margin:0 auto;padding:34px 24px 90px}
h1{font-size:32px;font-weight:600;letter-spacing:-.02em;margin:0 0 12px;line-height:1.15}
h1 b{color:var(--fire);font-weight:600}
.lede{color:var(--text-2);font-size:17px;max-width:64ch;margin:0}.lede b{color:var(--text);font-weight:600}
.how{border:1px solid var(--border);background:var(--surface);border-radius:10px;padding:18px 20px;margin:22px 0}
.how h4{margin:0 0 10px;font-size:12px;color:var(--text-3);font-weight:600;letter-spacing:.03em;text-transform:uppercase}
.how ul{margin:0;padding-left:18px;color:var(--text-2)}.how li{margin:5px 0}.how b{color:var(--text)}
.legend{display:flex;gap:18px;flex-wrap:wrap;margin-top:12px;font-size:13.5px;color:var(--text-2)}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;vertical-align:-1px;margin-right:6px}
.h-sec{font-size:12px;color:var(--text-3);font-weight:600;text-transform:uppercase;letter-spacing:.05em;
  margin:36px 0 16px;padding-bottom:9px;border-bottom:1px solid var(--border)}
.scope{width:100%;display:block;border:1px solid var(--border);border-radius:8px;background:#05070d;object-fit:cover}
.grid{display:grid;gap:22px}.g2{grid-template-columns:1fr 1fr}
.card{border:1px solid var(--border);background:var(--surface);border-radius:12px;padding:20px}
.chead{display:flex;align-items:baseline;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:16px}
.chead h2{font-size:21px;font-weight:600;margin:0;letter-spacing:-.01em}.chead .sub{font-size:13px;color:var(--text-2)}
.tagrow{display:flex;gap:8px;flex-wrap:wrap}
.pill{font-family:var(--mono);font-size:11px;padding:4px 10px;border:1px solid var(--border-2);color:var(--text-2);border-radius:6px}
.desc{color:var(--text-2);font-size:15px;margin:14px 0 0;max-width:82ch}.desc b{color:var(--text)}
.strip{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-top:8px}
.frame img{width:100%;border:1px solid var(--border);border-radius:7px;background:#05070d;display:block}
.frame figcaption{margin-top:7px;font-size:12px;color:var(--text-2);line-height:1.4}
.frame .ft{font-family:var(--mono);font-size:10.5px;color:var(--blue);display:block}
.stage{display:grid;grid-template-columns:1fr 1.05fr;gap:28px;align-items:center;padding:28px 0;border-bottom:1px solid var(--border)}
.stage:nth-child(even) .fig{order:2}
.stage img{width:100%;border:1px solid var(--border);border-radius:8px;background:#05070d}
.stage .n{font-family:var(--mono);font-size:12px;color:var(--blue)}
.stage h3{font-size:22px;font-weight:600;margin:6px 0 3px;letter-spacing:-.01em}
.stage .st{color:var(--fire-2);font-size:14px;margin-bottom:12px}
.stage p{color:var(--text-2);font-size:15px;margin:0;line-height:1.7}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12.5px}
th{text-align:left;color:var(--text-3);font-weight:500;font-size:11px;padding:10px 12px;border-bottom:1px solid var(--border)}
td{padding:10px 12px;border-bottom:1px solid var(--surface-2);color:var(--text-2)}
td.num{text-align:right;color:var(--text)}.hi{color:var(--blue)}
.note{color:var(--text-3);font-size:13px;margin-top:12px}
.vleg{display:flex;gap:16px;flex-wrap:wrap;margin-top:14px;padding:12px 16px;border:1px solid var(--border);
  border-radius:8px;background:var(--surface);font-size:12.5px;color:var(--text-2)}
.vleg span{display:inline-flex;align-items:center}
.vleg i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:7px}
.stagewrap{border-bottom:1px solid var(--border);padding-bottom:20px}
.stagewrap .stage{border-bottom:none;padding-bottom:8px}
.wf{background:var(--surface-2);border:1px solid var(--border);border-radius:8px;padding:14px;overflow-x:auto}
svg text{font-family:var(--sans)}
@media(max-width:820px){.g2{grid-template-columns:1fr}.stage,.stage:nth-child(even){grid-template-columns:1fr}
  .stage:nth-child(even) .fig{order:0}.strip{grid-template-columns:repeat(3,1fr)}.nav{gap:10px}.tab{padding:16px 8px}}
</style>

<div class="nav">
  <span class="brand">FIRE<b>WATCH</b></span>
  <div class="tabs" id="tabs"></div>
  <div class="sys"><span class="dot"></span>operational</div>
</div>
<div id="app"></div>

<script>
const FW=/*__DATA__*/;
const app=document.getElementById('app');
const esc=s=>(s==null?'':(''+s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])));
const TABS=[['overview','Overview'],['fires','Fires'],['pipeline','How it works'],['results','Results'],['ops','Who it helps']];
let tab='overview';
document.getElementById('tabs').innerHTML=TABS.map(([k,l])=>`<button class="tab" data-t="${k}">${l}</button>`).join('');
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{tab=b.dataset.t;location.hash='#/'+tab;render();});
window.addEventListener('hashchange',()=>{const t=location.hash.slice(2);if(TABS.find(x=>x[0]===t)){tab=t;render();}});
function vd(src,poster,label){return src?`<figure style="margin:0">
  <video class="scope" muted loop autoplay playsinline preload="auto" poster="${poster||''}"><source src="${src}" type="video/mp4"></video>
  <figcaption style="font-size:12.5px;color:var(--text-3);margin-top:8px">${label}</figcaption></figure>`:'';}
function play(){document.querySelectorAll('video').forEach(v=>{v.muted=true;const p=v.play();if(p&&p.catch)p.catch(()=>{});});}
function render(){document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on',b.dataset.t===tab));
  ({overview:vO,fires:vF,pipeline:vP,results:vR,ops:vOps}[tab]||vO)();play();}

const videoLegend=`<div class="vleg">
  <span><i style="background:var(--fire-2)"></i>Fire the satellite sees</span>
  <span><i style="background:#4ff0d0"></i>Path the model tracks</span>
  <span><i style="background:var(--fire);border-radius:0;height:0;border-top:2px dashed var(--fire);width:14px"></i>Model forecast (dashed)</span>
  <span><i style="background:var(--fire);opacity:.55"></i>Burn probability (yellow to red)</span>
  <span><i style="background:#7bd88f"></i>Town safe</span>
  <span><i style="background:#ff3b30"></i>Town flagged</span>
  <span><i style="background:var(--blue)"></i>What the model is doing</span></div>`;

// Lucidchart-style boxes/arrows
function box(x,y,w,h,label,kind){const c={data:'#2a3038',model:'#1e3a5f',fire:'#5a2f28',out:'#1f3b30'}[kind]||'#20262e';
  const s={data:'#3a434e',model:'var(--blue)',fire:'var(--fire)',out:'#3aa06f'}[kind]||'#3a434e';
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="7" fill="${c}" stroke="${s}" stroke-width="1"/>
    <text x="${x+w/2}" y="${y+h/2+4}" fill="#e7eaed" font-size="12" text-anchor="middle" font-family="var(--sans)">${label}</text>`;}
function arrow(x1,y1,x2,y2){return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#5a6470" stroke-width="1.4" marker-end="url(#ah)"/>`;}
const defs=`<defs><marker id="ah" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
  <path d="M0,0 L6,3 L0,6 Z" fill="#5a6470"/></marker></defs>`;

function stepDiagram(s){
  const iw=150,pw=200,ow=170,h=34,gap=12,pad=16;
  const rows=Math.max(s.inputs.length,s.process.length,s.outputs.length);
  const H=pad*2+rows*(h+gap)-gap, W=760;
  const col=(items,x,w,kind)=>items.map((it,i)=>box(x,pad+i*(h+gap)+(rows-items.length)*(h+gap)/2,w,h,esc(it),kind)).join('');
  const ix=pad, px=(W-pw)/2, ox=W-ow-pad;
  const aI=s.inputs.map((_,i)=>arrow(ix+iw,pad+i*(h+gap)+(rows-s.inputs.length)*(h+gap)/2+h/2,px, H/2)).join('');
  const aO=arrow(px+pw,H/2,ox,H/2);
  const pArr=s.process.slice(0,-1).map((_,i)=>{const y=pad+i*(h+gap)+(rows-s.process.length)*(h+gap)/2+h; return arrow(px+pw/2,y,px+pw/2,y+gap);}).join('');
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px">${defs}
    ${aI}${aO}${pArr}
    ${col(s.inputs,ix,iw,'data')}${col(s.process,px,pw,'model')}${col(s.outputs,ox,ow,'out')}
    <text x="${ix}" y="12" fill="#69707a" font-size="10">INPUT</text>
    <text x="${px}" y="12" fill="#69707a" font-size="10">PROCESS</text>
    <text x="${ox}" y="12" fill="#69707a" font-size="10">OUTPUT</text></svg>`;}

function overallDiagram(){
  const W=760,bw=150,bh=32;
  const rows=[
    [['Satellite','data'],['Cameras','data'],['Weather','data'],['Terrain / fuels','data']],
    [['Ingest into ontology','model']],
    [['Detect + track fire','model'],['Estimate fire state','model']],
    [['Forecast spread (ensemble)','model']],
    [['Assimilate live data','model']],
    [['Calibrate probabilities','model']],
    [['Estimate exposure','fire']],
    [['Validate vs actual fire','out']],
  ];
  const rh=64; let y=8, svg='';
  const centers=[];
  rows.forEach((row,ri)=>{
    const tw=row.length*bw+(row.length-1)*24, x0=(W-tw)/2, cy=y+bh/2;
    row.forEach((b,ci)=>{const x=x0+ci*(bw+24);svg+=box(x,y,bw,bh,b[0],b[1]);});
    centers.push([W/2,cy]); y+=rh;
  });
  let arr='';
  for(let i=0;i<centers.length-1;i++) arr+=arrow(centers[i][0],centers[i][1]+bh/2,centers[i+1][0],centers[i+1][1]-bh/2);
  return `<svg viewBox="0 0 ${W} ${y}" style="width:100%;max-width:${W}px">${defs}${arr}${svg}</svg>`;}

function vO(){const d=FW.events[0];
  app.innerHTML=`<div class="page">
    <h1>See where a wildfire is going, <b>before</b> it gets there.</h1>
    <p class="lede">FIREWATCH watches a wildfire from satellites, follows it as it grows, and predicts
    where it will spread next, then checks every prediction against what actually happened.</p>
    <div class="how"><h4>How to use this</h4>
      <ul>
        <li><b>Overview</b> (here): a quick demo of the whole thing on one real fire.</li>
        <li><b>Fires</b>: watch three real California wildfires play out.</li>
        <li><b>How it works</b>: each step of the model, in plain terms.</li>
        <li><b>Results</b>: how accurate the predictions were.</li>
      </ul>
      <div class="legend">
        <span><i style="background:var(--fire-2)"></i>Orange is the actual fire the satellite sees.</span>
        <span><i style="background:var(--blue)"></i>Blue is what the model is doing or predicting.</span>
      </div>
    </div>
    <div class="h-sec">Demo, the whole system on the 2024 Park Fire</div>
    <div class="grid g2">
      ${vd(d.tracking,d.tracking_poster,'The satellite tracks the fire.')}
      ${vd(d.response,d.response_poster,'The model forecasts where it spreads and who is nearby.')}
    </div>
    ${videoLegend}
    <p class="desc">The videos play slowly so you can read each step. The blue line at the bottom of each
    video names what the model is doing at that moment.</p>
  </div>`;}

function vF(){
  const cards=FW.events.map(e=>{
    const strip=e.evolution.map(f=>`<figure class="frame" style="margin:0">
      <img loading="lazy" src="${f.img}"><figcaption><span class="ft">${f.t} min</span>${esc(f.cap)}</figcaption></figure>`).join('');
    return `<div class="card">
      <div class="chead"><div><h2>${esc(e.full)}</h2><div class="sub">${esc(e.region)}, ${e.when}</div></div>
        <div class="tagrow"><span class="pill">${e.detections} detections</span><span class="pill">${e.area} km² at peak</span></div></div>
      <div class="grid g2">
        ${vd(e.tracking,e.tracking_poster,'Satellite tracking')}
        ${vd(e.response,e.response_poster,'Forecast and who is nearby')}</div>
      <p class="desc"><b>Tracking.</b> ${esc(FW.track_desc)}</p>
      <p class="desc"><b>Forecast.</b> ${esc(FW.resp_desc)}</p>
      <div class="h-sec" style="margin:22px 0 12px">Step by step</div>
      <div class="strip">${strip}</div>
    </div>`;}).join('');
  app.innerHTML=`<div class="page"><h1>Three real fires</h1>
    <p class="lede">Each is replayed from the first satellite detection over its first six hours. Under
    each pair of videos, the six stills show the fire and the model's read at that moment.</p>
    ${videoLegend}
    <div class="grid" style="margin-top:22px">${cards}</div></div>`;}

function vP(){const st=FW.pipeline.map((s,i)=>`<div class="stagewrap">
    <div class="stage">
      <div class="fig">${s.figure?`<img src="${s.figure}" alt="${esc(s.title)}">`:''}</div>
      <div><div class="n">Step ${i+1} of ${FW.pipeline.length}</div><h3>${esc(s.title)}</h3>
        <div class="st">${esc(s.subtitle)}</div><p>${esc(s.desc)}</p></div></div>
    <div class="wf">${(s.inputs&&s.inputs.length)?stepDiagram(s):''}</div>
  </div>`).join('');
  app.innerHTML=`<div class="page"><h1>How it works</h1>
    <p class="lede">A walk through what the model does, from raw satellite data to a forecast you can
    check. Every picture is made from real data, and each step has a small workflow showing what goes
    in and what comes out.</p>
    <div class="h-sec">The model, end to end</div>
    <div class="card" style="text-align:center">${overallDiagram()}</div>
    <div class="h-sec">Each step in detail</div>${st}</div>`;}

function vOps(){
  const roles=[
    ['Incident commanders','Decide evacuation timing and where to move crews under uncertainty. FIREWATCH gives a probabilistic view of where the fire will be in 30, 60 and 180 minutes, with a confidence band, instead of a single guess.'],
    ['Emergency managers','See which communities and roads are in the fire\'s path and roughly when. Exposure is computed from real population and road data, so the picture matches the ground.'],
    ['Dispatch and 911 centers','Turn scattered satellite alerts, camera feeds and weather into one shared, time-stamped picture that everyone is looking at, instead of a wall of separate screens.'],
    ['GIS and intel analysts','Trace every number back to the observation that produced it. Nothing on the map is a black box; each layer is a real datum with a source and a timestamp.'],
  ];
  app.innerHTML=`<div class="page">
    <h1>An operating picture for wildfire response.</h1>
    <p class="lede">Wildfire response is a decision made under extreme time pressure with fragmented
    information. The data to make the call, satellite hotspots, camera feeds, weather, terrain, fuels,
    already exists and is mostly public, but it is scattered and not turned into a forward look.
    FIREWATCH pulls it into one place, forecasts where the fire is going, and keeps a person in the loop.</p>
    <div class="h-sec">Who it helps</div>
    <div class="grid g2">${roles.map(r=>`<div class="card"><h3 style="margin:0 0 8px;font-size:18px">${r[0]}</h3>
      <p style="margin:0;color:var(--text-2)">${r[1]}</p></div>`).join('')}</div>
    <div class="h-sec">How it fits together, like an operating system</div>
    <div class="card" style="text-align:center">${overallDiagram()}</div>
    <p class="desc">Feeds come in at the bottom, become one shared model of the fire, and drive a
    forecast and an exposure estimate at the top. Because every stage reads and writes the same shared
    objects, you can rewind to any moment, see exactly what the system knew then, and check its forecast
    against what actually happened.</p>
    <div class="how" style="margin-top:26px"><h4>The one rule</h4>
      <p style="margin:0;color:var(--text-2)">FIREWATCH recommends and informs. It never issues an
      evacuation order on its own. A human always makes the decision.</p></div>
  </div>`;}

function vR(){const r=FW.results||{};
  const hs=FW.events[0].skill.map(s=>s.horizon_min);
  const rows=hs.map(h=>{const c=FW.events.map(e=>{const s=e.skill.find(x=>x.horizon_min===h);
    return s?`<td class="num">${s.iou_off.toFixed(2)}</td><td class="num hi">${s.iou_on.toFixed(2)}</td>`:'<td>n/a</td><td>n/a</td>';}).join('');
    return `<tr><td>${h>=60?(h/60)+' h':h+' min'}</td>${c}</tr>`;}).join('');
  const heads=FW.events.map(e=>`<th colspan="2" style="text-align:center">${esc(e.name)}</th>`).join('');
  const sub=FW.events.map(()=>'<th>plain</th><th class="hi">with data</th>').join('');
  const g=(k,cap)=>r[k]?`<div class="card"><img class="scope" style="border:none" src="${r[k]}"><p class="note">${cap}</p></div>`:'';
  app.innerHTML=`<div class="page"><h1>Results</h1>
    <p class="lede">We check the forecast against what the satellite later observed. Feeding live
    detections into the model improves the overlap with the real fire at every time step, on all three
    fires. The gain is real but modest, since satellite pixels are coarse (about 2 km).</p>
    <div class="h-sec">Overlap with the real fire (higher is better)</div>
    <div class="card" style="padding:0;overflow-x:auto"><table>
      <thead><tr><th>Time ahead</th>${heads}</tr><tr><th></th>${sub}</tr></thead><tbody>${rows}</tbody></table></div>
    <div class="h-sec">Graphs</div>
    <div class="grid g2">
      ${g('growth','How big each fire grew over time, from the satellite.')}
      ${g('performance','How well the forecast matched the real fire: plain model vs model with live data.')}
      ${g('improvement','How much feeding in live data improved the forecast, per fire.')}
      ${g('brier','Forecast error over time, lower is better.')}
      ${g('detections','How many fire pixels the satellite saw, adding up over time.')}
      ${g('spread','How fast each fire moved, on average.')}
      ${g('coverage','How often the truth fell inside the model 90% region. The dashed line is the target.')}
      ${g('extent','How large each fire got at its peak, in this window.')}
      ${g('calibration','Whether the model probabilities are honest, before and after calibration.')}
    </div></div>`;}

(function(){const t=location.hash.slice(2);if(TABS.find(x=>x[0]===t))tab=t;render();})();
</script>
"""


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "outputs" / "history.html"
    build(dest)
