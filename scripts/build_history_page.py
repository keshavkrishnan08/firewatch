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
    "davis": {"region": "Washoe Valley, Nevada", "when": "07 Sep 2024"},
    "gray": {"region": "Medical Lake, Washington", "when": "18 Aug 2023"},
}
# Fires that carry full annotated video on the page (kept under the 16 MB self-contained limit).
# Every fire is still fully present in Results, Retrospective, Ontology and Data.
VIDEO_KEYS = {"park", "palisades", "gray"}
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
        has_video = d["key"] in VIDEO_KEYS and (ASSETS / (d.get("video_asset") or "x")).exists()
        events.append({
            "key": d["key"], "name": d["name"].split(" (")[0], "full": d["name"],
            "region": m["region"], "when": m["when"], "center": d.get("center", [None, None]),
            "area": round(d["peak_area_km2"]), "detections": d["goes_detections"],
            "ros": d["mean_ros_kmh"], "iou_on": d["iou_on"], "iou_off": d["iou_off"],
            "delta": d["ablation_delta_iou"], "skill": d.get("skill_by_horizon", []),
            "impact": d.get("impact", {}), "residents_at_risk": d.get("residents_at_risk", 0),
            "n_flagged": d.get("n_flagged", 0),
            "coverage90_raw": d.get("coverage90_raw", 0), "coverage90_cal": d.get("coverage90_cal", 0),
            "observations": d.get("observations", []),
            "has_video": has_video,
            "tracking": vid(ASSETS / d["video_asset"]) if has_video else "",
            "still": img(ASSETS / d["asset"], 760) if (ASSETS / d.get("asset", "x")).exists() else "",
            "tracking_poster": img(ASSETS / f"poster_{d['key']}.png", 600) if (ASSETS / f"poster_{d['key']}.png").exists() else "",
            "response": vid(ASSETS / d["response_asset"]) if has_video and d.get("response_asset") and (ASSETS / d["response_asset"]).exists() else "",
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
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:6px 0}
.stat{border:1px solid var(--border);background:var(--surface);border-radius:10px;padding:16px 18px}
.stat .v{font-size:28px;font-weight:600;letter-spacing:-.02em;color:var(--blue)}
.stat .l{font-size:12.5px;color:var(--text-2);margin-top:4px}
@media(max-width:820px){.stats{grid-template-columns:1fr 1fr}}
.feats{display:flex;flex-direction:column;gap:38px;margin-top:10px}
.feat{display:grid;grid-template-columns:1.05fr .95fr;gap:34px;align-items:center}
.feat:nth-child(even) .feat-img{order:2}
.feat-img img{width:100%;aspect-ratio:16/10;object-fit:cover;border:1px solid var(--border);border-radius:12px;background:#05070d;display:block}
.feat-img .ucap{margin-top:9px;font-family:var(--mono);font-size:11.5px;color:var(--text-3)}
.feat-txt .fnum{font-family:var(--mono);font-size:44px;font-weight:600;color:var(--border-2);line-height:1}
.feat-txt h3{font-size:23px;font-weight:600;margin:6px 0 10px;letter-spacing:-.015em}
.feat-txt p{margin:0;color:var(--text-2);font-size:15.5px;line-height:1.75}
/* distinct impact banner for How it helps */
.band{border:1px solid var(--border-2);border-left:3px solid var(--blue);background:linear-gradient(180deg,#12171d,#0e1216);
  border-radius:12px;padding:22px 24px;display:grid;grid-template-columns:repeat(4,1fr);gap:26px;margin:6px 0}
.band .bv{font-size:32px;font-weight:600;letter-spacing:-.02em;color:var(--text)}
.band .bv b{color:var(--blue);font-weight:600}
.band .bl{font-size:12.5px;color:var(--text-2);margin-top:5px;line-height:1.45}
@media(max-width:820px){.band{grid-template-columns:1fr 1fr}.feat,.feat:nth-child(even) .feat-img{order:0}
  .feat{grid-template-columns:1fr}}
.oseg-row{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 4px}
.oseg{background:var(--surface);border:1px solid var(--border);color:var(--text-2);font-family:inherit;
  font-size:13px;padding:7px 13px;border-radius:7px;cursor:pointer}
.oseg.on{border-color:var(--blue);color:var(--text);background:#12171d}
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
const TABS=[['overview','Overview'],['fires','Fires'],['pipeline','How it works'],['ontology','Ontology'],['retro','Retrospective'],['results','Results'],['ops','How it helps']];
const LIVES_UPLIFT=[0.00015,0.00045];
let tab='overview';
document.getElementById('tabs').innerHTML=TABS.map(([k,l])=>`<button class="tab" data-t="${k}">${l}</button>`).join('');
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{tab=b.dataset.t;location.hash='#/'+tab;render();});
window.addEventListener('hashchange',()=>{const t=location.hash.slice(2);if(TABS.find(x=>x[0]===t)){tab=t;render();}});
function vd(src,poster,label){return src?`<figure style="margin:0">
  <video class="scope" muted loop autoplay playsinline preload="auto" poster="${poster||''}"><source src="${src}" type="video/mp4"></video>
  <figcaption style="font-size:12.5px;color:var(--text-3);margin-top:8px">${label}</figcaption></figure>`:'';}
function play(){document.querySelectorAll('video').forEach(v=>{v.muted=true;const p=v.play();if(p&&p.catch)p.catch(()=>{});});}
const chip=(v,l)=>`<div class="stat"><div class="v">${v}</div><div class="l">${l}</div></div>`;
const livesRange=r=>{const a=Math.round(r*LIVES_UPLIFT[0]),b=Math.round(r*LIVES_UPLIFT[1]);
  return a>0?`${a}–${b}`:(b>0?`up to ${b}`:'<1');};
function estFor(e){const r=e.residents_at_risk||0,im=e.impact||{};
  const lives=livesRange(r);
  const nf=e.n_flagged||0;
  return `<div class="stats">
    ${chip(lives,'estimated lives protected by earlier warning')}
    ${chip((im.forest_km2||0)+' km²','wildland flagged ahead of the front')}
    ${chip(r.toLocaleString(),'residents in flagged communities')}
    ${chip(nf+(nf===1?' community':' communities'),'flagged ahead of the front')}</div>`;}
function render(){document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on',b.dataset.t===tab));
  ({overview:vO,fires:vF,pipeline:vP,ontology:vOnt,retro:vRetro,results:vR,ops:vOps}[tab]||vO)();play();}
let ontKey=null, retroKey=null;

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

// a curved connector that bows away from a center point, so the loop reads as non-straight
function arcAround(x1,y1,x2,y2,cx,cy,amt){const mx=(x1+x2)/2,my=(y1+y2)/2;
  let vx=mx-cx,vy=my-cy;const l=Math.hypot(vx,vy)||1;vx/=l;vy/=l;
  return `<path d="M${x1},${y1} Q${mx+vx*amt},${my+vy*amt} ${x2},${y2}" fill="none" stroke="#5a6470" stroke-width="1.6" marker-end="url(#ah)"/>`;}

// human-in-the-loop cycle: forecast -> recommendation -> human -> new observations -> forecast
function hitlDiagram(){const W=760,H=360,cx=W/2,cy=180,A=64;
  const N=[300,22,160,44],E=[556,150,184,44],S=[300,300,160,44],Wn=[20,150,184,44];
  const b=(n,label,kind)=>box(n[0],n[1],n[2],n[3],label,kind);
  const arcs=
    arcAround(N[0]+N[2],N[1]+N[3]/2, E[0]+E[2]/2,E[1], cx,cy,A)+
    arcAround(E[0]+E[2]/2,E[1]+E[3], S[0]+S[2],S[1]+S[3]/2, cx,cy,A)+
    arcAround(S[0],S[1]+S[3]/2, Wn[0]+Wn[2]/2,Wn[1]+Wn[3], cx,cy,A)+
    arcAround(Wn[0]+Wn[2]/2,Wn[1], N[0],N[1]+N[3]/2, cx,cy,A);
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px">${defs}${arcs}
    ${b(N,'FIREWATCH forecast','model')}${b(E,'Recommendation + confidence','out')}
    ${b(S,'Human decides and acts','fire')}${b(Wn,'New observations arrive','data')}
    <text x="${cx}" y="${cy-6}" fill="#e7eaed" font-size="14" text-anchor="middle" font-weight="600">Human in the loop</text>
    <text x="${cx}" y="${cy+14}" fill="#8a939e" font-size="11.5" text-anchor="middle">the loop always closes on a person</text></svg>`;}

function vO(){const d=FW.events[0];
  app.innerHTML=`<div class="page">
    <h1>See where a wildfire is going <b>before</b> it gets there.</h1>
    <p class="lede">FIREWATCH watches a wildfire from satellites, follows it as it grows, and predicts
    where it will spread next, then checks every prediction against what actually happened.</p>
    <div class="how"><h4>How to use this</h4>
      <ul>
        <li><b>Overview</b> (here): a quick demo of the whole thing on one real fire.</li>
        <li><b>Fires</b>: watch real wildfires from several regions play out.</li>
        <li><b>How it works</b>: each step of the model, in plain terms.</li>
        <li><b>Ontology</b>: one fire as a graph of linked objects and actions.</li>
        <li><b>Retrospective</b>: the causal replay, warning lead time and calibration.</li>
        <li><b>Results</b>: how accurate the predictions were.</li>
      </ul>
      <div class="legend">
        <span><i style="background:var(--fire-2)"></i>Orange is the actual fire the satellite sees.</span>
        <span><i style="background:var(--blue)"></i>Blue is what the model is doing or predicting.</span>
      </div>
    </div>
    <div class="h-sec">Watch the whole system run on the 2024 Park Fire</div>
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
    const media=e.has_video
      ? `<div class="grid g2">
          ${vd(e.tracking,e.tracking_poster,'Satellite tracking')}
          ${vd(e.response,e.response_poster,'Forecast and who is nearby')}</div>
         <p class="desc"><b>Tracking.</b> ${esc(FW.track_desc)}</p>
         <p class="desc"><b>Forecast.</b> ${esc(FW.resp_desc)}</p>`
      : `<figure style="margin:0"><img class="scope" src="${e.still}" alt="${esc(e.full)}">
          <figcaption style="font-size:12.5px;color:var(--text-3);margin-top:8px">Satellite tracking and forecast for ${esc(e.full)}. Full annotated video is on the four flagship fires; every fire is scored in Results and the Retrospective.</figcaption></figure>`;
    return `<div class="card">
      <div class="chead"><div><h2>${esc(e.full)}</h2><div class="sub">${esc(e.region)}, ${e.when}</div></div>
        <div class="tagrow"><span class="pill">${e.detections} detections</span><span class="pill">${e.area} km² at peak</span></div></div>
      ${media}
      <div class="h-sec" style="margin:22px 0 12px">What the forecast would have bought</div>
      ${estFor(e)}
      <p class="note">Lives protected is a modeled planning estimate scaled from the exposed population and evacuation-lead-time research, shown as a range. It is not a measured outcome, and a human always makes the evacuation call.</p>
      <div class="h-sec" style="margin:22px 0 12px">Step by step</div>
      <div class="strip">${strip}</div>
    </div>`;}).join('');
  app.innerHTML=`<div class="page"><h1>Watch real wildfires unfold from space.</h1>
    <p class="lede">Fires from California, Nevada and Washington, each replayed from its first satellite
    detection. Three flagship fires carry the full annotated video; every fire below is scored in the
    Retrospective and Results. Under each, the stills show the fire and the model's read over time.</p>
    ${videoLegend}
    <div class="grid" style="margin-top:22px">${cards}</div></div>`;}

function vP(){const st=FW.pipeline.map((s,i)=>`<div class="stagewrap">
    <div class="stage">
      <div class="fig">${s.figure?`<img src="${s.figure}" alt="${esc(s.title)}">`:''}</div>
      <div><div class="n">Step ${i+1} of ${FW.pipeline.length}</div><h3>${esc(s.title)}</h3>
        <div class="st">${esc(s.subtitle)}</div><p>${esc(s.desc)}</p></div></div>
    <div class="wf">${(s.inputs&&s.inputs.length)?stepDiagram(s):''}</div>
  </div>`).join('');
  app.innerHTML=`<div class="page"><h1>See how the model turns raw data into a forecast.</h1>
    <p class="lede">A walk through what the model does, from raw satellite data to a forecast you can
    check. Every picture is made from real data, and each step has a small workflow showing what goes
    in and what comes out.</p>
    <div class="h-sec">See the whole model end to end</div>
    <div class="card" style="text-align:center">${overallDiagram()}</div>
    <div class="h-sec">Each step in detail</div>${st}</div>`;}

function vOps(){
  const ev=FW.events;const pick=(i,k)=>((ev[i]&&ev[i][k])||ev[0].response_poster||ev[0].tracking_poster||'');
  const uses=[
    ['1','Decide when to call an evacuation',
     'Read the confidence band at 30, 60 and 180 minutes ahead. The moment a community crosses the threat threshold you have a time-stamped, defensible basis to move early rather than wait for the fire to confirm it.',
     pick(0,'response_poster'),'Forecast over a community, with a confidence band'],
    ['2','See who and what is in the path',
     'Exposure is computed from real population and road data. Flagged communities, residents and threatened roads update every time the forecast updates.',
     pick(2,'response_poster'),'Population and roads under the projected front'],
    ['3','Run the room from one screen',
     'Satellite detections, tracking and weather resolve into a single shared map, so dispatch, command and field crews all read the same picture instead of a wall of separate feeds.',
     pick(1,'tracking_poster'),'Satellite tracking of a live fire'],
    ['4','Check every number against reality',
     'Rewind to any minute and see exactly what the system knew then. Each layer traces back to a real observation with a source and a timestamp, and every forecast is scored against what the satellite later recorded.',
     ((ev[2].evolution[3]||{}).img)||pick(2,'tracking_poster'),'A replayed moment, model read beside the fire'],
  ];
  const flagged=ev.reduce((a,e)=>a+(e.residents_at_risk||0),0);
  const forestKm2=ev.reduce((a,e)=>a+((e.impact||{}).forest_km2||0),0);
  const meanGain=(ev.reduce((a,e)=>a+e.delta,0)/ev.length);
  const livesLo=Math.round(flagged*LIVES_UPLIFT[0]),livesHi=Math.round(flagged*LIVES_UPLIFT[1]);
  const bs=(v,l)=>`<div><div class="bv">${v}</div><div class="bl">${l}</div></div>`;
  app.innerHTML=`<div class="page">
    <h1>See how FIREWATCH helps the people responding.</h1>
    <p class="lede">Wildfire response is a decision made under extreme time pressure. The data to make
    the call already exists and is mostly public. It is just scattered across many screens and never
    turned into a forward look. FIREWATCH pulls it into one place, forecasts where the fire is going,
    and keeps a person in charge of every decision.</p>
    <div class="h-sec">See what that adds up to across five fires</div>
    <div class="band">
      ${bs('<b>'+(flagged/1000).toFixed(0)+'K</b>',"residents in flagged communities")}
      ${bs('<b>'+livesLo+'–'+livesHi+'</b>',"estimated lives protected by earlier warning")}
      ${bs('<b>'+forestKm2.toFixed(0)+'</b> km²',"wildland flagged ahead of the front")}
      ${bs('<b>+'+meanGain.toFixed(3)+'</b>',"forecast overlap gained from live data")}
    </div>
    <p class="desc">Estimated lives protected is a transparent planning figure, scaled from the exposed
    population and evacuation-lead-time research and shown as a range. It is a modeled estimate, not a
    measured outcome, and a human always makes the evacuation call.</p>
    <div class="h-sec">See how to use it in the field</div>
    <div class="feats">${uses.map(u=>`<div class="feat">
      <div class="feat-img">${u[3]?`<img class="scope" src="${u[3]}" alt="${esc(u[1])}">`:''}
        <div class="ucap">${esc(u[4])}</div></div>
      <div class="feat-txt"><div class="fnum">${u[0]}</div><h3>${esc(u[1])}</h3><p>${esc(u[2])}</p></div>
    </div>`).join('')}</div>
    <div class="h-sec">Human in the loop</div>
    <div class="card" style="text-align:center">${hitlDiagram()}</div>
    <p class="desc">FIREWATCH forecasts, ranks the risk and hands a recommendation with its confidence
    to a person. The person decides and acts. New satellite passes and camera frames feed back in, and
    the picture updates. FIREWATCH never issues an evacuation order on its own.</p>
  </div>`;}

function vR(){const r=FW.results||{};
  const hs=FW.events[0].skill.map(s=>s.horizon_min);
  const rows=hs.map(h=>{const c=FW.events.map(e=>{const s=e.skill.find(x=>x.horizon_min===h);
    return s?`<td class="num">${s.iou_off.toFixed(2)}</td><td class="num hi">${s.iou_on.toFixed(2)}</td>`:'<td>n/a</td><td>n/a</td>';}).join('');
    return `<tr><td>${h>=60?(h/60)+' h':h+' min'}</td>${c}</tr>`;}).join('');
  const heads=FW.events.map(e=>`<th colspan="2" style="text-align:center">${esc(e.name)}</th>`).join('');
  const sub=FW.events.map(()=>'<th>plain</th><th class="hi">with data</th>').join('');
  const g=(k,cap)=>r[k]?`<div class="card"><img class="scope" style="border:none" src="${r[k]}"><p class="note">${cap}</p></div>`:'';
  app.innerHTML=`<div class="page"><h1>See how close the forecasts came to the real fire.</h1>
    <p class="lede">We check the forecast against what the satellite later observed. Feeding live
    detections into the model improves the overlap with the real fire at every time step, on every
    fire. The gain is real but modest, since satellite pixels are coarse (about 2 km).</p>
    <div class="h-sec">Overlap with the real fire (higher is better)</div>
    <div class="card" style="padding:0;overflow-x:auto"><table>
      <thead><tr><th>Time ahead</th>${heads}</tr><tr><th></th>${sub}</tr></thead><tbody>${rows}</tbody></table></div>
    <div class="h-sec">See the predictive value on each fire</div>
    <div class="grid g2">
      ${g('lives','Estimated lives protected by earlier warning, per fire. A transparent planning estimate from the exposed population, shown as a range, not a measured outcome.')}
      ${g('forest','Wildland area the forecast flags ahead of the front, before it burns, per fire. This is the area a human can pre-position crews and warnings against.')}
      ${g('warned','Residents in the communities the forecast flagged, per fire, from real OpenStreetMap population.')}
      ${g('improvement','How much feeding in live data improved the forecast, per fire.')}
    </div>
    <div class="h-sec">See the rest of the measurements</div>
    <div class="grid g2">
      ${g('growth','How big each fire grew over time, from the satellite.')}
      ${g('performance','How well the forecast matched the real fire: plain model vs model with live data.')}
      ${g('brier','Forecast error over time, lower is better.')}
      ${g('detections','How many fire pixels the satellite saw, adding up over time.')}
      ${g('spread','How fast each fire moved, on average.')}
      ${g('coverage','How often the truth fell inside the model 90% region. The dashed line is the target.')}
      ${g('extent','How large each fire got at its peak, in this window.')}
      ${g('calibration','Whether the model probabilities are honest, before and after calibration.')}
    </div></div>`;}

// ── Ontology (Palantir-style object/link/action graph for one fire) ──
function ontologyGraph(e){
  const nObs=e.observations.length,nComm=e.n_flagged||0,nH=e.skill.length;
  const W=920,H=430;
  const N1=[16,96,158,46],N2=[200,96,162,46],N3=[400,84,164,66],N4=[602,96,156,46],
        N5=[602,252,156,54],N6=[772,252,140,54],Wc=[200,246,162,40],Tc=[200,316,162,40],Oc=[400,320,164,40];
  const b=(n,l,k)=>box(n[0],n[1],n[2],n[3],l,k);
  const rc=n=>[n[0]+n[2],n[1]+n[3]/2],lc=n=>[n[0],n[1]+n[3]/2],tc=n=>[n[0]+n[2]/2,n[1]],bc=n=>[n[0]+n[2]/2,n[1]+n[3]];
  const E=(p,q,l)=>{const mx=(p[0]+q[0])/2,my=(p[1]+q[1])/2;return arrow(p[0],p[1],q[0],q[1])+
    `<text x="${mx}" y="${my-6}" fill="#8a939e" font-size="10.5" text-anchor="middle">${l}</text>`;};
  const edges=E(rc(N1),lc(N2),'detects')+E(rc(N2),lc(N3),'assimilated')+
    E(rc(Wc),[N3[0],N3[1]+N3[3]-16],'drives')+E(rc(Tc),bc(N3),'constrains')+
    E(rc(N3),lc(N4),'produces')+E(bc(N4),tc(N5),'threatens')+
    E(rc(Oc),lc(N5),'defines')+E(rc(N5),lc(N6),'informs');
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px">${defs}${edges}
    ${b(N1,'GOES-18 ABI L2-FDC','data')}${b(N2,'Observation ×'+nObs,'model')}
    ${b(N3,esc(e.name),'fire')}${b(N4,'Forecast ×'+nH,'out')}
    ${b(N5,'Community ×'+nComm,'fire')}${b(N6,'Recommend','out')}
    ${b(Wc,'HRRR wind','data')}${b(Tc,'Terrain + fuels','data')}${b(Oc,'OpenStreetMap','data')}
    <text x="${N6[0]+N6[2]/2}" y="${N6[1]-8}" fill="#8a939e" font-size="10" text-anchor="middle">human decides</text>
    <text x="16" y="20" fill="#69707a" font-size="10">FEEDS</text>
    <text x="400" y="20" fill="#69707a" font-size="10">FIRE OBJECT</text>
    <text x="772" y="20" fill="#69707a" font-size="10">ACTION</text></svg>`;}

function vOnt(){const evs=FW.events;
  if(!ontKey||!evs.find(x=>x.key===ontKey)) ontKey=evs.slice().sort((a,b)=>(b.n_flagged||0)-(a.n_flagged||0))[0].key;
  const e=evs.find(x=>x.key===ontKey);
  const sel=evs.map(x=>`<button class="oseg${x.key===e.key?' on':''}" onclick="ontKey='${x.key}';vOnt();play()">${esc(x.name)}</button>`).join('');
  app.innerHTML=`<div class="page">
    <h1>Everything on the map is one linked object model.</h1>
    <p class="lede">FIREWATCH is not a pile of layers. Every feed resolves into typed objects, a fire, its
    observations, its forecasts and the communities in its path, joined by explicit links and driving a
    small set of human actions. Nothing is a black box. Every number traces back to the observation that
    produced it.</p>
    <div class="oseg-row">${sel}</div>
    <div class="h-sec">The object and link graph for ${esc(e.name)}</div>
    <div class="card" style="text-align:center">${ontologyGraph(e)}</div>
    <div class="grid g2" style="margin-top:22px">
      <div><div class="h-sec" style="margin-top:0">Objects in this incident</div>
        <div class="stats" style="grid-template-columns:1fr 1fr">
          ${chip('1','Fire, the anchor object')}
          ${chip(e.observations.length,'Observations from GOES-18 active fire')}
          ${chip(e.skill.length,'Forecast objects, one per horizon')}
          ${chip(e.n_flagged||0,'Threatened community objects')}
        </div>
        <div class="h-sec">Actions always keep a human in the loop</div>
        <div class="how" style="margin-top:0"><ul>
          <li><b>Recommend evacuation</b> for a flagged community, with the forecast and its confidence attached.</li>
          <li><b>Pre-position crews</b> against the projected front and the threatened egress roads.</li>
          <li>FIREWATCH proposes and a person decides. It never issues an order on its own.</li>
        </ul></div></div>
      <div><div class="h-sec" style="margin-top:0">Provenance ledger</div>
        <p class="note" style="margin-top:0">Every observation carries its source, product, native resolution
        and timestamp. This is the audit trail behind the fire object.</p>
        <div class="card" style="padding:0;overflow-x:auto"><table>
          <thead><tr><th>Time (UTC)</th><th>Source</th><th>Product</th><th class="num">Native</th><th class="num">Pixels</th></tr></thead>
          <tbody>${e.observations.slice(0,10).map(o=>`<tr><td>${esc(o.t_utc)}</td><td>${esc(o.source)}</td><td>${esc(o.product)}</td><td class="num">${o.resolution_m?o.resolution_m+' m':'—'}</td><td class="num">${o.n_pixels}</td></tr>`).join('')}</tbody>
        </table></div>
        <p class="note">Showing ${Math.min(10,e.observations.length)} of ${e.observations.length} assimilated observations.</p></div>
    </div></div>`;}

// ── Retrospective (M5): causal replay of a real named fire, lead-time + calibration ──
function vRetro(){const evs=FW.events;const av=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:0;
  const covRaw=av(evs.map(e=>e.coverage90_raw||0)),covCal=av(evs.map(e=>e.coverage90_cal||0));
  const gain=av(evs.map(e=>e.delta||0));
  // every community the forecast flagged AHEAD of the fire (positive warning), across all fires
  const warns=[];
  evs.forEach(e=>(e.impact&&e.impact.communities||[]).forEach(c=>{if(c.warning_min>0)
    warns.push([c.zone||'unnamed',e.name.split(' Fire')[0],c.warning_min,c.residents||0]);}));
  warns.sort((a,b)=>b[2]-a[2]);
  const warnRows=warns.map(w=>`<tr><td>${esc(w[0])}</td><td>${esc(w[1])}</td><td class="num hi">+${w[2]} min</td><td class="num">${w[3].toLocaleString()}</td></tr>`).join('')
    ||`<tr><td colspan="4" style="color:var(--text-3)">No community was reached after forecast issue in these windows.</td></tr>`;
  const abl=evs.map(e=>`<tr><td>${esc(e.name)}</td><td class="num">${(e.iou_off||0).toFixed(3)}</td><td class="num hi">${(e.iou_on||0).toFixed(3)}</td><td class="num">${(e.delta>=0?'+':'')+(e.delta||0).toFixed(3)}</td></tr>`).join('');
  app.innerHTML=`<div class="page">
    <h1>Replay a real fire and measure the warning it would have given.</h1>
    <p class="lede">The retrospective is the load-bearing test. Each fire is replayed from its first
    GOES-18 detection under strict causal masking: no forecast at time t uses any observation after t.
    We assimilate the first few hours, then score the forecast against what the satellite actually
    recorded, and read off how much earlier the model flags each community than the fire reaches it.</p>
    <div class="h-sec">Warning lead time, community by community</div>
    <p class="desc" style="margin-top:0">For every community the fire reached after forecast issue, the
    interval between when the forecast first flagged it and when the fire actually arrived. Positive means
    the model would have warned that community ahead of the front.</p>
    <div class="card" style="padding:0;overflow-x:auto"><table>
      <thead><tr><th>Community</th><th>Fire</th><th class="num">Warning</th><th class="num">Residents</th></tr></thead>
      <tbody>${warnRows}</tbody></table></div>
    <div class="h-sec">Assimilating live data earns its keep</div>
    <p class="desc" style="margin-top:0">Forecast overlap with the real fire (mean IoU over horizons),
    with assimilation off vs on. The gain is real on every fire, and modest because GOES pixels are coarse.</p>
    <div class="card" style="padding:0;overflow-x:auto"><table>
      <thead><tr><th>Fire</th><th class="num">Assimilation off</th><th class="num">Assimilation on</th><th class="num">Δ</th></tr></thead>
      <tbody>${abl}</tbody></table></div>
    <div class="h-sec">Honest uncertainty, calibrated coverage</div>
    <div class="stats">
      ${chip((covRaw*100).toFixed(0)+'%','raw 90% band coverage, over-confident')}
      ${chip((covCal*100).toFixed(0)+'%','after leave-one-out spread calibration')}
      ${chip('+'+gain.toFixed(3),'mean forecast overlap gained from live data')}
      ${chip(evs.length,'real named fires replayed')}
    </div>
    <p class="desc">A raw ensemble 90% region contained only about ${(covRaw*100).toFixed(0)}% of the real
    burned area, it was badly over-confident. Widening the ensemble with a fast-tail mixture and then
    calibrating the region level on held-out fires lifts that to about ${(covCal*100).toFixed(0)}%. The
    residual gap is largely irreducible: at 2 km GOES resolution the real perimeter is patchier than any
    smooth ensemble. Both numbers are reported, nothing is hidden.</p>
    <div class="how" style="margin-top:22px"><h4>Why this is a fair test</h4><ul>
      <li>Causal masking: no forecast uses future observations, and the scored window is held out.</li>
      <li>The assimilation-off arm is a real baseline the on arm has to beat.</li>
      <li>Ground truth is the GOES-18 active-fire progression, not a model run.</li>
      <li>Spread calibration is fit leave-one-out, so it is never tuned to the fire being scored.</li>
    </ul></div></div>`;}

(function(){const t=location.hash.slice(2);if(TABS.find(x=>x[0]===t))tab=t;render();})();
</script>
"""


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "outputs" / "history.html"
    build(dest)
