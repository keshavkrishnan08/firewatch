"""Build the FIREWATCH site — a self-contained, dark research instrument with four tabs:
Overview (demo video + what it does), Fires (annotated time-lapses + descriptions), Pipeline
(a figure + academic description per stage), Results (custom research graphs).

Reads outputs/historical.json + outputs/showcase.json; embeds all media as data URIs (each video
embedded once and referenced by key to keep the file small)."""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "docs" / "assets"

META = {
    "park": {"region": "Tehama & Butte Counties, CA", "when": "24 Jul 2024"},
    "palisades": {"region": "Pacific Palisades, Los Angeles", "when": "07 Jan 2025"},
    "eaton": {"region": "Altadena / Eaton Canyon, CA", "when": "07 Jan 2025"},
}
TRACK_DESC = ("Real GOES-18 active-fire pixels are clustered into a fire object and tracked over time. "
              "The cyan path is the tracked centroid; the orange outline is the observed burn footprint; "
              "the blue MODEL line names the pipeline stage running at each moment. After the forecast is "
              "issued, the dashed outline is the projected perimeter.")
RESP_DESC = ("The forecast is projected forward from the fire's observed perimeter; the shaded field is the "
             "ensemble burn probability (yellow → red). Communities light up as the forecast crosses a "
             "threat threshold near them, annotated with the OpenStreetMap resident count and the ensemble "
             "threat probability. This is exposure analysis — not an operational evacuation order.")


def b64(p: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def build(out_path: Path) -> Path:
    data = json.loads((REPO / "outputs" / "historical.json").read_text())
    data = [d for d in data if (ASSETS / (d.get("video_asset") or "x")).exists()]
    if not data:
        sys.exit("no historical results — run firewatch.historical.run_all first")
    show = {}
    sp = REPO / "outputs" / "showcase.json"
    if sp.exists():
        show = json.loads(sp.read_text())

    events = []
    for d in data:
        m = META.get(d["key"], {"region": "", "when": ""})
        events.append({
            "key": d["key"], "name": d["name"].split(" (")[0], "full": d["name"],
            "region": m["region"], "when": m["when"], "center": d.get("center", [None, None]),
            "area": round(d["peak_area_km2"]), "detections": d["goes_detections"], "passes": d["n_frames"],
            "heading_deg": round(d["heading_deg"]), "ros": d["mean_ros_kmh"],
            "iou_on": d["iou_on"], "iou_off": d["iou_off"], "delta": d["ablation_delta_iou"],
            "skill": d.get("skill_by_horizon", []),
            "exposure": {"n": d.get("n_flagged", 0), "residents": d.get("residents_at_risk", 0)},
            "tracking": b64(ASSETS / d["video_asset"], "video/mp4"),
            "tracking_poster": b64(ASSETS / f"poster_{d['key']}.png", "image/png") if (ASSETS / f"poster_{d['key']}.png").exists() else "",
            "response": b64(ASSETS / d["response_asset"], "video/mp4") if d.get("response_asset") and (ASSETS / d["response_asset"]).exists() else "",
            "response_poster": b64(ASSETS / f"response_poster_{d['key']}.png", "image/png") if (ASSETS / f"response_poster_{d['key']}.png").exists() else "",
        })

    pipeline = []
    for s in show.get("pipeline", []):
        fig = s.get("figure")
        pipeline.append({"title": s["title"], "subtitle": s["subtitle"], "desc": s["desc"],
                         "figure": b64(ASSETS / fig, "image/png") if fig and (ASSETS / fig).exists() else ""})
    results = {}
    for k, fn in (show.get("results") or {}).items():
        if fn and (ASSETS / fn).exists():
            results[k] = b64(ASSETS / fn, "image/png")

    model = {"events": events, "pipeline": pipeline, "results": results,
             "track_desc": TRACK_DESC, "resp_desc": RESP_DESC}
    html = TEMPLATE.replace("/*__DATA__*/", json.dumps(model, separators=(",", ":")))
    out_path.write_text(html)
    print(f"wrote {out_path} ({out_path.stat().st_size // 1024} KB, {len(events)} fires, {len(pipeline)} stages)")
    return out_path


TEMPLATE = r"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FIREWATCH</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#0b0d0f;--surface:#11151a;--surface-2:#0e1216;--border:#242a31;--border-2:#2f3740;
  --text:#e7eaed;--text-2:#8a939e;--text-3:#5c656f;--blue:#4c9aff;--fire:#ff6848;--fire-2:#f2b84b;
  --mono:"IBM Plex Mono",ui-monospace,monospace}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--text);font-family:"Inter",system-ui,sans-serif;font-size:14px;
  line-height:1.6;-webkit-font-smoothing:antialiased}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.nav{display:flex;align-items:center;gap:26px;height:50px;padding:0 24px;border-bottom:1px solid var(--border);
  position:sticky;top:0;background:var(--bg);z-index:40}
.brand{font-weight:700;letter-spacing:.14em;font-size:14px}.brand b{color:var(--fire)}
.tabs{display:flex;gap:2px}
.tab{background:none;border:0;border-bottom:1px solid transparent;color:var(--text-2);font-family:inherit;
  font-size:12.5px;letter-spacing:.06em;text-transform:uppercase;padding:16px 14px;margin-bottom:-1px;cursor:pointer}
.tab.on{color:var(--text);border-color:var(--blue)}
.sys{margin-left:auto;display:flex;align-items:center;gap:14px;font-family:var(--mono);font-size:11px;color:var(--text-2)}
.sys .dot{width:6px;height:6px;border-radius:50%;background:var(--blue);box-shadow:0 0 6px var(--blue)}
.page{max-width:1140px;margin:0 auto;padding:30px 24px 80px}
h1{font-size:30px;font-weight:700;letter-spacing:.01em;margin:0 0 10px}
h1 b{color:var(--fire)}
.lede{color:var(--text-2);font-size:16px;max-width:70ch;margin:0}
.h-sec{font-family:var(--mono);font-size:11px;letter-spacing:.16em;color:var(--text-3);text-transform:uppercase;
  margin:34px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.scope{width:100%;display:block;border:1px solid var(--border);border-radius:4px;background:#05070d;object-fit:cover}
.vwrap{position:relative}
.vlbl{position:absolute;left:12px;top:12px;font-family:var(--mono);font-size:10px;color:#dfe8f2;
  background:rgba(5,7,13,.62);border:1px solid var(--border-2);padding:3px 8px;border-radius:3px}
.desc{color:var(--text-2);font-size:14px;margin:12px 0 0;max-width:78ch}
.grid{display:grid;gap:22px}.g2{grid-template-columns:1fr 1fr}
.card{border:1px solid var(--border);background:var(--surface);border-radius:4px;padding:18px}
.chead{display:flex;align-items:baseline;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:14px}
.chead h2{font-size:19px;font-weight:600;margin:0}
.chead .sub{font-family:var(--mono);font-size:11.5px;color:var(--text-2)}
.tagrow{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}
.pill{font-family:var(--mono);font-size:10.5px;padding:3px 9px;border:1px solid var(--border-2);color:var(--text-2);border-radius:100px}
.stage{display:grid;grid-template-columns:1fr 1.1fr;gap:26px;align-items:center;padding:26px 0;border-bottom:1px solid var(--border)}
.stage:nth-child(even){grid-template-columns:1.1fr 1fr}
.stage:nth-child(even) .fig{order:2}
.stage img{width:100%;border:1px solid var(--border);border-radius:4px;background:#05070d}
.stage .n{font-family:var(--mono);font-size:12px;color:var(--blue);letter-spacing:.1em}
.stage h3{font-size:21px;font-weight:600;margin:6px 0 3px}
.stage .st{color:var(--fire-2);font-size:13px;font-family:var(--mono);margin-bottom:12px}
.stage p{color:var(--text-2);font-size:14px;margin:0;line-height:1.7}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px}
th{text-align:left;color:var(--text-3);font-weight:500;text-transform:uppercase;letter-spacing:.06em;font-size:10px;
  padding:9px 12px;border-bottom:1px solid var(--border)}
td{padding:9px 12px;border-bottom:1px solid var(--surface-2);color:var(--text-2)}
td.num{text-align:right;color:var(--text)}.hi{color:var(--blue)}
.legend{display:flex;gap:18px;margin:8px 0 0;font-family:var(--mono);font-size:11.5px;color:var(--text-2);flex-wrap:wrap}
.legend i{display:inline-block;width:22px;height:3px;vertical-align:middle;margin-right:6px}
.note{color:var(--text-3);font-size:12.5px;margin-top:14px}
@media(max-width:820px){.g2{grid-template-columns:1fr}.stage,.stage:nth-child(even){grid-template-columns:1fr}
  .stage:nth-child(even) .fig{order:0}.nav{gap:12px}.tab{padding:16px 9px}}
</style>

<div class="nav">
  <span class="brand">FIRE<b>WATCH</b></span>
  <div class="tabs" id="tabs"></div>
  <div class="sys"><span class="dot"></span>SYSTEM OPERATIONAL</div>
</div>
<div id="app"></div>

<script>
const FW = /*__DATA__*/;
const app=document.getElementById('app');
const esc=s=>(s==null?'':(''+s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])));
const fmt=n=>n==null?'—':(''+n).replace(/\B(?=(\d{3})+(?!\d))/g,',');
const TABS=[['overview','Overview'],['fires','Fires'],['pipeline','Pipeline'],['results','Results']];
let tab='overview';

document.getElementById('tabs').innerHTML=TABS.map(([k,l])=>`<button class="tab" data-t="${k}">${l}</button>`).join('');
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{tab=b.dataset.t;location.hash=k2h();render();});
function k2h(){return '#/'+tab;}
window.addEventListener('hashchange',()=>{const t=location.hash.slice(2);if(TABS.find(x=>x[0]===t)){tab=t;render();}});

function video(src,poster,label){
  return src?`<div class="vwrap"><span class="vlbl">${label}</span>
    <video class="scope" muted loop autoplay playsinline preload="auto" poster="${poster||''}">
    <source src="${src}" type="video/mp4"></video></div>`:'';
}
function playVisible(){document.querySelectorAll('video').forEach(v=>{v.muted=true;const p=v.play();if(p&&p.catch)p.catch(()=>{});});}

function render(){
  document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on',b.dataset.t===tab));
  ({overview:vOverview,fires:vFires,pipeline:vPipeline,results:vResults}[tab]||vOverview)();
  playVisible();
}

function vOverview(){
  const demo=FW.events[0];
  app.innerHTML=`<div class="page">
    <h1>Watching wildfires from <b>orbit</b> — and forecasting where they go.</h1>
    <p class="lede">FIREWATCH ingests real satellite, weather, terrain and fuel data, detects and
    <b>tracks</b> the fire over time, <b>forecasts</b> its probabilistic spread with data assimilation,
    and <b>estimates exposure</b> — then validates every prediction against what actually happened.
    The demo below runs the full pipeline on the 2024 Park Fire; the blue <span class="hi">MODEL</span>
    line names the stage executing at each moment.</p>
    <div class="h-sec">Demo · the whole system on one real fire</div>
    <div class="grid g2">
      ${video(demo.tracking,demo.tracking_poster,'1 · tracking · GOES-18')}
      ${video(demo.response,demo.response_poster,'2 · forecast &amp; exposure')}
    </div>
    <p class="desc">Left: the satellite tracking. Right: the forecast projected forward with population
    exposure. Explore the <b>Fires</b>, walk the <b>Pipeline</b> stage by stage, or read the measured
    <b>Results</b> using the tabs above.</p>
    <div class="h-sec">Pipeline</div>
    <p class="lede mono" style="font-size:13px;color:var(--text-2)">
      ${FW.pipeline.map(s=>s.title).join('  →  ')}</p>
  </div>`;
}

function vFires(){
  const cards=FW.events.map(e=>`<div class="card">
    <div class="chead"><div><h2>${esc(e.full)}</h2><div class="sub">${esc(e.region)} · ${e.center[0]}°N ${Math.abs(e.center[1])}°W</div></div>
      <div class="tagrow"><span class="pill">${e.detections} detections</span><span class="pill">${e.area} km² peak</span>
      <span class="pill">assimilation ${e.delta>=0?'+':''}${e.delta.toFixed(3)} IoU</span></div></div>
    <div class="grid g2">
      ${video(e.tracking,e.tracking_poster,'satellite tracking')}
      ${video(e.response,e.response_poster,'forecast &amp; exposure')}
    </div>
    <p class="desc"><b>Tracking.</b> ${esc(FW.track_desc)}</p>
    <p class="desc"><b>Forecast &amp; exposure.</b> ${esc(FW.resp_desc)}</p>
  </div>`).join('');
  app.innerHTML=`<div class="page"><h1>Historical fires</h1>
    <p class="lede">Three real California wildfires, each replayed from the first GOES-18 detection over
    its first six hours. Videos play slowly so each pipeline stage is legible.</p>
    <div class="grid" style="margin-top:22px">${cards}</div></div>`;
}

function vPipeline(){
  const stages=FW.pipeline.map((s,i)=>`<div class="stage">
    <div class="fig">${s.figure?`<img src="${s.figure}" alt="${esc(s.title)}">`:'<div class="scope" style="height:220px"></div>'}</div>
    <div><div class="n">STAGE ${String(i+1).padStart(2,'0')}</div><h3>${esc(s.title)}</h3>
      <div class="st">${esc(s.subtitle)}</div><p>${esc(s.desc)}</p></div>
  </div>`).join('');
  app.innerHTML=`<div class="page"><h1>How it works</h1>
    <p class="lede">The site is a visual walk through the actual pipeline — raw feeds become detections,
    detections become a tracked fire object, physics + assimilation become a calibrated probabilistic
    forecast, and the forecast becomes exposure analysis. Each figure is generated from real data.</p>
    <div style="margin-top:10px">${stages}</div></div>`;
}

function vResults(){
  const r=FW.results||{};
  const hs=FW.events[0].skill.map(s=>s.horizon_min);
  const rows=hs.map(h=>{
    const cells=FW.events.map(e=>{const s=e.skill.find(x=>x.horizon_min===h);return s?`<td class="num">${s.iou_off.toFixed(3)}</td><td class="num hi">${s.iou_on.toFixed(3)}</td>`:'<td>—</td><td>—</td>';}).join('');
    return `<tr><td>+${h>=60?(h/60)+' h':h+' min'}</td>${cells}</tr>`;
  }).join('');
  const heads=FW.events.map(e=>`<th colspan="2" style="text-align:center">${esc(e.name)}</th>`).join('');
  const sub=FW.events.map(()=>'<th>base</th><th class="hi">assim</th>').join('');
  const g=(k,cap)=>r[k]?`<div class="card"><img class="scope" src="${r[k]}" style="border:none"><p class="note">${cap}</p></div>`:'';
  app.innerHTML=`<div class="page"><h1>Results</h1>
    <p class="lede">Ground truth is the GOES-18 active-fire progression. Assimilating satellite detections
    into the physical prior lifts perimeter agreement at every horizon on all three fires — a modest,
    honest gain, since geostationary pixels are coarse (~2 km).</p>
    <div class="h-sec">Perimeter IoU vs GOES-observed truth · baseline vs assimilation</div>
    <div class="card" style="padding:0"><table>
      <thead><tr><th>Horizon</th>${heads}</tr><tr><th></th>${sub}</tr></thead><tbody>${rows}</tbody></table></div>
    <div class="h-sec">Custom analysis</div>
    <div class="grid g2">${g('growth','Tracked fire extent (convex hull of GOES detections) versus time, for all three fires.')}
      ${g('performance','Mean perimeter IoU across the three fires, baseline versus assimilation, per horizon.')}</div>
    <div class="grid g2" style="margin-top:22px">${g('detections','Cumulative GOES fire-pixel detections over the replay window.')}
      ${r.calibration?`<div class="card"><img class="scope" src="${r.calibration}" style="border:none"><p class="note">Reliability of the burn-probability field, raw vs temperature-scaled.</p></div>`:''}</div>
  </div>`;
}

(function(){const t=location.hash.slice(2);if(TABS.find(x=>x[0]===t))tab=t;render();})();
</script>
"""


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "outputs" / "history.html"
    build(dest)
