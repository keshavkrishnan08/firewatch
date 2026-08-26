"""Build the FIREWATCH instrument — a self-contained scientific fire-analysis app.

Reads outputs/historical.json (from `firewatch.historical.run_all`), embeds the real tracking /
response videos and evolution frames, and renders a dark, dense, research-tool SPA: an events
browser plus per-event tabs (Overview · Video · Images · Forecast · Analysis · Data) with a shared
time scrubber. Every number/asset traces to a real GOES-18 tracking run.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "docs" / "assets"
KM2_PER_ACRE = 0.00404686
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

META = {
    "park": {"region": "Tehama & Butte Counties, California", "challenge": "Rapidly spreading · mountainous terrain",
             "blurb": "Ignited near Chico on 24 Jul 2024 and ran up the Sierra foothills, growing into one "
                      "of the largest wildfires in California history (~429,000 acres eventual)."},
    "palisades": {"region": "Pacific Palisades, Los Angeles, California", "challenge": "Wind-driven · urban interface",
                  "blurb": "Erupted 7 Jan 2025 and was driven by extreme Santa Ana winds toward the coast — "
                           "one of the most destructive urban-interface firestorms in California history."},
    "eaton": {"region": "Altadena / Eaton Canyon, California", "challenge": "Nighttime · steep San Gabriel front",
              "blurb": "Broke out the night of 7 Jan 2025 at the foot of the San Gabriels and swept into "
                       "Altadena under hurricane-force downslope winds."},
}


def b64(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def build(out_path: Path) -> Path:
    raw = json.loads((REPO / "outputs" / "historical.json").read_text())
    raw = [d for d in raw if (ASSETS / (d.get("video_asset") or "x")).exists()]
    if not raw:
        sys.exit("no historical results — run firewatch.historical.run_all first")

    events = []
    for d in raw:
        m = META.get(d["key"], {"region": "", "challenge": "", "blurb": ""})
        area_km2 = d["peak_area_km2"]
        heading = COMPASS[int(((d["heading_deg"] % 360) + 11.25) // 22.5) % 16]
        evo = [e for e in d.get("evolution", []) if (ASSETS / e["asset"]).exists()]
        ev = {
            "key": d["key"], "name": d["name"].split(" (")[0].upper(), "full_name": d["name"],
            "region": m["region"], "challenge": m["challenge"], "blurb": m["blurb"],
            "started_utc": d.get("start_utc", "")[:16].replace("T", " ") + " UTC",
            "center": d.get("center", [None, None]),
            "area_km2": round(area_km2, 1), "area_acres": round(area_km2 / KM2_PER_ACRE),
            "detections": d["goes_detections"], "passes": d["n_frames"],
            "heading": heading, "heading_deg": round(d["heading_deg"]),
            "ros_kmh": d["mean_ros_kmh"], "growth": d.get("growth_km2_per_h", 0),
            "window_min": d.get("window_min", 360), "assim_min": d.get("assim_min", 180),
            "feeds": d.get("feeds", []),
            "iou_on": d["iou_on"], "iou_off": d["iou_off"], "delta": d["ablation_delta_iou"],
            "skill": d.get("skill_by_horizon", []),
            "observations": d.get("observations", []),
            "exposure": {"communities": d.get("n_flagged", 0), "residents": d.get("residents_at_risk", 0),
                         "list": d.get("responses", [])},
            "video": {
                "tracking": b64(ASSETS / d["video_asset"], "video/mp4") if d.get("video_asset") else None,
                "tracking_poster": b64(ASSETS / f"poster_{d['key']}.png", "image/png") if (ASSETS / f"poster_{d['key']}.png").exists() else None,
                "response": b64(ASSETS / d["response_asset"], "video/mp4") if d.get("response_asset") and (ASSETS / d["response_asset"]).exists() else None,
                "response_poster": b64(ASSETS / f"response_poster_{d['key']}.png", "image/png") if (ASSETS / f"response_poster_{d['key']}.png").exists() else None,
            },
            "evolution": [{"img": b64(ASSETS / e["asset"], "image/png"), "t_min": e["t_min"],
                           "phase": e["phase"], "area_km2": e["area_km2"], "caption": e["caption"]} for e in evo],
        }
        events.append(ev)

    payload = json.dumps(events, separators=(",", ":"))
    html = TEMPLATE.replace("/*__DATA__*/", payload)
    out_path.write_text(html)
    print(f"wrote {out_path} ({out_path.stat().st_size // 1024} KB, {len(events)} events)")
    return out_path


TEMPLATE = r"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FIREWATCH</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --bg:#0B0D0F; --surface:#11151A; --surface-2:#0e1216; --border:#242A31; --border-2:#2f3740;
  --text:#E7EAED; --text-2:#8A939E; --text-3:#5c656f;
  --blue:#4C9AFF; --blue-dim:#27405e; --fire:#FF6848; --fire-2:#F2B84B;
  --mono:"IBM Plex Mono",ui-monospace,monospace;
}
*{box-sizing:border-box}
[hidden]{display:none!important}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--text);font-family:"Inter",system-ui,sans-serif;font-size:14px;
  line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:var(--blue);text-decoration:none}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
button{font-family:inherit;cursor:pointer}
::selection{background:var(--blue-dim)}

/* ── top nav ── */
.nav{display:flex;align-items:center;gap:26px;height:48px;padding:0 20px;border-bottom:1px solid var(--border);
  position:sticky;top:0;background:var(--bg);z-index:40}
.brand{font-weight:700;letter-spacing:.14em;font-size:13px}
.brand b{color:var(--fire)}
.nav .links{display:flex;gap:20px}
.nav .links a{color:var(--text-2);font-size:12.5px;letter-spacing:.06em;text-transform:uppercase;padding:2px 0;border-bottom:1px solid transparent}
.nav .links a.on{color:var(--text);border-color:var(--blue)}
.sys{margin-left:auto;display:flex;align-items:center;gap:16px;font-family:var(--mono);font-size:11px;color:var(--text-2)}
.sys .dot{width:6px;height:6px;border-radius:50%;background:var(--blue);box-shadow:0 0 6px var(--blue)}
.sys .clock{color:var(--text-3)}

.page{max-width:1360px;margin:0 auto;padding:22px 20px 60px}
.crumb{font-family:var(--mono);font-size:11px;color:var(--text-3);letter-spacing:.08em;text-transform:uppercase;margin-bottom:16px}
.crumb a{color:var(--text-2)}
.h-sec{font-family:var(--mono);font-size:11px;letter-spacing:.16em;color:var(--text-3);text-transform:uppercase;
  margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid var(--border)}

/* ── events list ── */
.evrow{display:grid;grid-template-columns:150px 1fr auto;gap:22px;align-items:center;padding:18px 20px;
  border:1px solid var(--border);border-top:none;background:var(--surface);cursor:pointer}
.evlist .evrow:first-child{border-top:1px solid var(--border)}
.evrow:hover{background:#131820}
.evrow .thumb{width:150px;height:96px;border:1px solid var(--border);object-fit:cover;background:#05070d;border-radius:2px}
.evrow h3{margin:0 0 3px;font-size:16px;font-weight:600;letter-spacing:.02em}
.evrow .sub{font-family:var(--mono);font-size:11.5px;color:var(--text-2)}
.evrow .tags{margin-top:9px;display:flex;gap:8px;flex-wrap:wrap}
.pill{font-family:var(--mono);font-size:10.5px;letter-spacing:.05em;padding:3px 8px;border:1px solid var(--border-2);
  color:var(--text-2);border-radius:100px}
.pill.active{color:var(--fire);border-color:#5a2f28}
.pill.done{color:var(--text-3)}
.evrow .stat{text-align:right;font-family:var(--mono)}
.evrow .stat .big{font-size:20px;color:var(--text);font-weight:500}
.evrow .stat .lbl{font-size:10.5px;color:var(--text-3);letter-spacing:.06em;text-transform:uppercase}
.evrow .go{color:var(--blue);font-family:var(--mono);font-size:12px;margin-top:10px}

/* ── event header + tabs ── */
.ehead{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;flex-wrap:wrap;margin-bottom:2px}
.ehead h1{margin:0;font-size:27px;font-weight:700;letter-spacing:.02em}
.ehead .loc{font-family:var(--mono);font-size:12.5px;color:var(--text-2);margin-top:4px}
.ehead .meta{display:flex;gap:26px;font-family:var(--mono);font-size:11.5px}
.ehead .meta .k{color:var(--text-3);text-transform:uppercase;letter-spacing:.06em;font-size:10px}
.ehead .meta .v{color:var(--text);margin-top:2px}
.tabs{display:flex;gap:0;border-bottom:1px solid var(--border);margin:16px 0 20px}
.tab{background:none;border:0;border-bottom:1px solid transparent;color:var(--text-2);font-size:12px;
  letter-spacing:.08em;text-transform:uppercase;padding:10px 15px;margin-bottom:-1px}
.tab.on{color:var(--text);border-color:var(--blue)}

/* ── generic panels/tables ── */
.grid{display:grid;gap:16px}
.panel{border:1px solid var(--border);background:var(--surface);border-radius:4px}
.panel > .ph{font-family:var(--mono);font-size:11px;letter-spacing:.1em;color:var(--text-3);text-transform:uppercase;
  padding:11px 14px;border-bottom:1px solid var(--border)}
.panel > .pb{padding:14px}
.kv{display:grid;grid-template-columns:1fr auto;gap:9px 14px;font-family:var(--mono);font-size:12.5px}
.kv .k{color:var(--text-3);text-transform:uppercase;letter-spacing:.05em;font-size:10.5px;align-self:center}
.kv .v{color:var(--text);text-align:right}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px}
th{text-align:left;color:var(--text-3);font-weight:500;text-transform:uppercase;letter-spacing:.06em;font-size:10px;
  padding:9px 12px;border-bottom:1px solid var(--border)}
td{padding:9px 12px;border-bottom:1px solid var(--surface-2);color:var(--text-2)}
tr:hover td{background:#0f141a;color:var(--text)}
td.num{text-align:right;color:var(--text)}
.hi{color:var(--blue)} .fire{color:var(--fire)} .warn{color:var(--fire-2)}

/* ── media ── */
.scope{width:100%;display:block;border:1px solid var(--border);border-radius:3px;background:#05070d;object-fit:cover}
.vwrap{position:relative}
.vlbl{position:absolute;left:10px;top:10px;font-family:var(--mono);font-size:10px;color:#dfe8f2;
  background:rgba(5,7,13,.66);border:1px solid var(--border-2);padding:3px 8px;border-radius:3px}
.prov{font-family:var(--mono);font-size:11px;color:var(--text-2);display:grid;grid-template-columns:auto 1fr;gap:5px 12px}
.prov .k{color:var(--text-3)}
.mini{width:100%;height:120px;object-fit:cover;border:1px solid var(--border);border-radius:2px;cursor:pointer;background:#05070d}

/* ── forecast horizon ── */
.hz{display:flex;gap:6px;flex-wrap:wrap}
.hz button{font-family:var(--mono);font-size:12px;color:var(--text-2);background:var(--surface);
  border:1px solid var(--border);padding:7px 13px;border-radius:3px}
.hz button.on{color:var(--text);border-color:var(--blue);background:#0f1723}
.bar{height:6px;background:var(--surface-2);border:1px solid var(--border);border-radius:3px;overflow:hidden}
.bar i{display:block;height:100%}
.bar.on i{background:var(--blue)} .bar.off i{background:var(--text-3)}

/* ── scrubber ── */
.scrub{position:sticky;bottom:0;background:var(--surface);border-top:1px solid var(--border);padding:10px 20px;
  display:flex;align-items:center;gap:16px;z-index:30}
.scrub .t{font-family:var(--mono);font-size:12px;color:var(--text);min-width:110px}
.scrub input[type=range]{flex:1;accent-color:var(--blue)}
.scrub .phase{font-family:var(--mono);font-size:11px;padding:3px 9px;border:1px solid var(--border-2);border-radius:100px;color:var(--text-2)}
.scrub .phase.fc{color:var(--fire);border-color:#5a2f28}
.scrub button.pl{background:none;border:1px solid var(--border-2);color:var(--text);width:30px;height:30px;border-radius:4px}

.cols-2{grid-template-columns:340px 1fr}
.cols-3{grid-template-columns:1fr 1fr 1fr}
.cols-4{grid-template-columns:repeat(4,1fr)}
.muted{color:var(--text-2)} .note{color:var(--text-2);font-size:12.5px;margin:10px 0 0}
@media (max-width:900px){.cols-2{grid-template-columns:1fr}.cols-3,.cols-4{grid-template-columns:1fr 1fr}
  .evrow{grid-template-columns:1fr}.nav .links{display:none}}
</style>

<div class="nav">
  <span class="brand">FIRE<b>WATCH</b></span>
  <div class="links" id="nav-links"></div>
  <div class="sys"><span class="clock" id="clock"></span><span class="dot"></span>SYSTEM OPERATIONAL</div>
</div>
<div id="app"></div>
<div class="scrub" id="scrub" hidden>
  <button class="pl" id="play">▶</button>
  <span class="t mono" id="scrub-t"></span>
  <input type="range" id="scrub-r" min="0" max="5" value="0" step="1">
  <span class="phase" id="scrub-ph"></span>
</div>

<script>
const FW = /*__DATA__*/;
const app = document.getElementById('app');
const $ = (h)=>{const t=document.createElement('template');t.innerHTML=h.trim();return t.content.firstChild;};
const esc = (s)=> (s==null?'':(''+s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])));
const fmt = (n)=> n==null?'—':(''+n).replace(/\B(?=(\d{3})+(?!\d))/g,',');
const km2acre = 0.00404686;

function clock(){const d=new Date();const M=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
  const p=x=>(''+x).padStart(2,'0');
  document.getElementById('clock').textContent=`${p(d.getUTCDate())} ${M[d.getUTCMonth()]} ${d.getUTCFullYear()} · ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;}
clock();setInterval(clock,30000);

let state={view:'events',key:null,tab:'overview',hz:null,frame:0,playing:false,timer:null};

function route(){
  const h=location.hash.slice(2).split('/');            // #/event/park/overview
  if(h[0]==='event'&&FW.find(e=>e.key===h[1])){state.view='event';state.key=h[1];state.tab=h[2]||'overview';}
  else {state.view='events';state.key=null;}
  render();
}
window.addEventListener('hashchange',route);

function navLinks(){
  const cur=state.view;
  document.getElementById('nav-links').innerHTML =
    `<a href="#/events" class="${cur==='events'?'on':''}">Events</a>`+
    (state.key?`<a href="#/event/${state.key}/overview" class="on">Event</a>`:'');
}

function render(){
  navLinks();
  const sc=document.getElementById('scrub');
  if(state.view==='events'){sc.hidden=true;renderEvents();}
  else {renderEvent();}
}

/* ── EVENTS ── */
function renderEvents(){
  const rows = FW.map(e=>{
    const poster = e.video.tracking_poster || (e.evolution[0]&&e.evolution[0].img);
    return `<div class="evrow" onclick="location.hash='#/event/${e.key}/overview'">
      <img class="thumb" src="${poster}" alt="">
      <div>
        <h3>${esc(e.full_name)}</h3>
        <div class="sub">${esc(e.region)} · ${e.center[0]}°N ${Math.abs(e.center[1])}°W</div>
        <div class="tags"><span class="pill done">HISTORICAL</span>
          <span class="pill">${esc(e.challenge)}</span>
          <span class="pill">${e.feeds.length} data source${e.feeds.length!==1?'s':''}</span></div>
      </div>
      <div class="stat">
        <div class="big">${fmt(e.area_acres)}</div><div class="lbl">acres tracked</div>
        <div class="go">OPEN EVENT →</div>
      </div>
    </div>`;}).join('');
  app.innerHTML =
    `<div class="page">
      <div class="crumb">FIREWATCH / EVENTS</div>
      <div class="h-sec">Historical events · ${FW.length} incidents</div>
      <div class="evlist">${rows}</div>
      <p class="note">Each incident is replayed from real GOES-18 active-fire detections over its first
      ${Math.round((FW[0].window_min)/60)} hours. Terrain from AWS Terrain Tiles, fuels from ESA WorldCover,
      wind from NOAA HRRR, assets from OpenStreetMap. Open an event to inspect the observations, tracking,
      forecast, and model performance.</p>
    </div>`;
}

/* ── EVENT ── */
function ev(){return FW.find(e=>e.key===state.key);}
function renderEvent(){
  const e=ev();
  if(!state.hz && e.skill.length) state.hz = e.skill[0].horizon_min;
  const tabs=['overview','video','images','forecast','analysis','data'];
  app.innerHTML =
    `<div class="page">
      <div class="crumb"><a href="#/events">Events</a> / ${esc(e.name)}</div>
      <div class="ehead">
        <div><h1>${esc(e.full_name)}</h1><div class="loc">${esc(e.region)} · ${e.center[0]}°N ${Math.abs(e.center[1])}°W</div></div>
        <div class="meta">
          <div><div class="k">Started</div><div class="v">${esc(e.started_utc)}</div></div>
          <div><div class="k">Window</div><div class="v">${Math.round(e.window_min/60)} h replay</div></div>
          <div><div class="k">Observations</div><div class="v">${e.detections} px · ${e.passes} passes</div></div>
        </div>
      </div>
      <div class="tabs">${tabs.map(t=>`<button class="tab ${state.tab===t?'on':''}" onclick="location.hash='#/event/${e.key}/${t}'">${t}</button>`).join('')}</div>
      <div id="tab"></div>
    </div>`;
  renderTab();
}

function renderTab(){
  const e=ev(), t=document.getElementById('tab');
  const sc=document.getElementById('scrub');
  sc.hidden = !(['overview','images','forecast'].includes(state.tab) && e.evolution.length);
  if(!sc.hidden) setupScrub();
  ({overview:tabOverview,video:tabVideo,images:tabImages,forecast:tabForecast,analysis:tabAnalysis,data:tabData}[state.tab]||tabOverview)(e,t);
  playVisible();
}

function tabOverview(e,el){
  const acres=fmt(e.area_acres);
  el.innerHTML=`<div class="grid cols-2">
    <div class="panel"><div class="ph">Event information</div><div class="pb">
      <div class="kv">
        <div class="k">Event</div><div class="v">${esc(e.name)}</div>
        <div class="k">Location</div><div class="v">${esc(e.region.split(',')[0])}</div>
        <div class="k">Started</div><div class="v">${esc(e.started_utc)}</div>
        <div class="k">Coordinates</div><div class="v">${e.center[0]}, ${e.center[1]}</div>
        <div class="k">Peak area</div><div class="v">${acres} ac · ${e.area_km2} km²</div>
        <div class="k">Spread rate</div><div class="v">${e.ros_kmh} km/h</div>
        <div class="k">Heading</div><div class="v">${e.heading} (${e.heading_deg}°)</div>
        <div class="k">Detections</div><div class="v">${e.detections} px</div>
        <div class="k">Satellite passes</div><div class="v">${e.passes}</div>
      </div>
      <div class="h-sec" style="margin:18px 0 10px">Data sources</div>
      <div class="prov">${e.feeds.map(f=>`<span class="k">•</span><span>${esc(f)}</span>`).join('')}
        <span class="k">•</span><span>AWS Terrain Tiles · ESA WorldCover · NOAA HRRR · OpenStreetMap</span></div>
    </div></div>
    <div class="panel"><div class="ph">Fire state · <span id="ov-time" class="hi"></span></div><div class="pb vwrap">
      <img class="scope" id="ov-img" src="${e.evolution[state.frame]?e.evolution[state.frame].img:''}">
      <p class="note" id="ov-cap"></p>
    </div></div>
  </div>`;
  syncFrame();
}

function tabVideo(e,el){
  const src=(v)=> v?`<video class="scope" muted loop autoplay playsinline preload="auto" poster="${v.poster||''}"><source src="${v.src}" type="video/mp4"></video>`:'<div class="scope" style="padding:40px;text-align:center;color:var(--text-3)">no video</div>';
  const provTrack=`<div class="prov">
    <span class="k">Source</span><span>GOES-18 · ABI Fire Detection &amp; Characterization</span>
    <span class="k">Window</span><span>first ${Math.round(e.window_min/60)} h from first detection</span>
    <span class="k">Cadence</span><span>~5 min (geostationary)</span>
    <span class="k">Detections</span><span>${e.detections} fire pixels · ${e.passes} timesteps</span></div>`;
  const provResp=`<div class="prov">
    <span class="k">Forecast</span><span>Rothermel + MTT ensemble, issued at +${Math.round(e.assim_min/60)} h</span>
    <span class="k">Assets</span><span>OpenStreetMap populated places within threat radius</span>
    <span class="k">Exposure</span><span>${e.exposure.communities} communities · ~${fmt(e.exposure.residents)} residents (OSM)</span></div>`;
  el.innerHTML=`<div class="grid cols-2" style="grid-template-columns:1fr 1fr;align-items:start">
    <div class="panel"><div class="ph">Satellite tracking · time-lapse</div><div class="pb">
      <div class="vwrap"><span class="vlbl">GOES-18 · tracking</span>${src(e.video.tracking&&{src:e.video.tracking,poster:e.video.tracking_poster})}</div>
      <div style="margin-top:12px">${provTrack}</div></div></div>
    <div class="panel"><div class="ph">Forecast &amp; exposure · time-lapse</div><div class="pb">
      <div class="vwrap"><span class="vlbl warn">forecast projection</span>${src(e.video.response&&{src:e.video.response,poster:e.video.response_poster})}</div>
      <div style="margin-top:12px">${provResp}</div></div></div>
  </div>
  <p class="note">Time-lapses play the real detection sequence sped up. The tracking view clusters GOES
  fire pixels into a tracked object; the forecast view projects the fire forward from its observed
  perimeter and shades burn probability. Population figures come from OpenStreetMap and are shown as
  exposure analysis, not an operational evacuation order.</p>`;
}

function tabImages(e,el){
  const cells=e.evolution.map((f,i)=>`<figure style="margin:0">
    <img class="mini" src="${f.img}" onclick="state.frame=${i};syncFrame();document.getElementById('scrub-r').value=${i};updScrub();">
    <figcaption class="mono" style="margin-top:6px;font-size:11px;color:var(--text-2)">
      <span class="hi">T+${f.t_min} min</span> · ${f.area_km2} km² · ${esc(f.phase)}</figcaption></figure>`).join('');
  el.innerHTML=`<div class="grid" style="grid-template-columns:repeat(3,1fr)">${cells}</div>
    <div class="panel" style="margin-top:16px"><div class="ph">Selected frame · <span id="ov-time" class="hi"></span></div>
    <div class="pb"><img class="scope" id="ov-img" src="${e.evolution[state.frame].img}"><p class="note" id="ov-cap"></p></div></div>`;
  syncFrame();
}

function tabForecast(e,el){
  const rows=e.skill.map(s=>`<tr>
    <td>+${s.horizon_min>=60?(s.horizon_min/60)+' h':s.horizon_min+' min'}</td>
    <td class="num">${s.iou_off.toFixed(3)}</td>
    <td class="num hi">${s.iou_on.toFixed(3)}</td>
    <td class="num">${s.dice_on.toFixed(3)}</td>
    <td class="num">${s.brier_on.toFixed(4)}</td>
    <td class="num">${s.coverage90.toFixed(2)}</td></tr>`).join('');
  el.innerHTML=`<div class="grid cols-2">
    <div class="panel"><div class="ph">Forecast · fire state at <span id="ov-time" class="hi"></span></div>
      <div class="pb vwrap"><img class="scope" id="ov-img" src="${e.evolution[state.frame].img}"><p class="note" id="ov-cap"></p></div></div>
    <div class="panel"><div class="ph">Model performance vs GOES-observed perimeter</div><div class="pb">
      <table><thead><tr><th>Horizon</th><th>IoU baseline</th><th>IoU assimilation</th><th>Dice</th><th>Brier</th><th>Cov. 90%</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="h-sec" style="margin:18px 0 10px">Ablation · assimilation vs baseline (mean IoU)</div>
      <div class="kv" style="grid-template-columns:110px 1fr 50px">
        <div class="k">Baseline</div><div class="bar off"><i style="width:${Math.min(100,e.iou_off/0.4*100)}%"></i></div><div class="v">${e.iou_off.toFixed(3)}</div>
        <div class="k">Assimilation</div><div class="bar on"><i style="width:${Math.min(100,e.iou_on/0.4*100)}%"></i></div><div class="v hi">${e.iou_on.toFixed(3)}</div>
      </div>
      <p class="note">Ground truth is the GOES-18 active-fire progression. Assimilation of satellite
      detections lifts mean perimeter IoU by <span class="hi">${e.delta>=0?'+':''}${e.delta.toFixed(3)}</span>.
      Modest and honest — GOES pixels are coarse (~2 km) and few land in the early window.</p>
    </div></div>
  </div>`;
  syncFrame();
}

function tabAnalysis(e,el){
  // tracked fire-area curve from the evolution frames (real extents)
  const pts=e.evolution.map(f=>[f.t_min,f.area_km2]);
  const W=560,H=200,pl=42,pb=26;
  const xmax=Math.max(...pts.map(p=>p[0]))||1, ymax=Math.max(...pts.map(p=>p[1]))||1;
  const X=x=>pl+(W-pl-8)*x/xmax, Y=y=>H-pb-(H-pb-10)*y/ymax;
  const line=pts.map((p,i)=>(i?'L':'M')+X(p[0]).toFixed(1)+' '+Y(p[1]).toFixed(1)).join(' ');
  const issueX=X(e.assim_min);
  const dots=pts.map(p=>`<circle cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="3" fill="var(--fire)"/>`).join('');
  const yt=[0,ymax/2,ymax].map(v=>`<text x="6" y="${Y(v)+3}" fill="#5c656f" font-size="10" font-family="monospace">${v.toFixed(0)}</text>`).join('');
  const xt=[0,xmax/2,xmax].map(v=>`<text x="${X(v)}" y="${H-8}" fill="#5c656f" font-size="10" font-family="monospace" text-anchor="middle">${v.toFixed(0)}</text>`).join('');
  const exp=e.exposure.list.slice(0,6).map(r=>`<tr><td>${esc(r.zone)}</td>
    <td class="num">${fmt(r.residents||0)}</td><td class="num">${(r.confidence*100).toFixed(0)}%</td></tr>`).join('');
  el.innerHTML=`<div class="grid cols-2">
    <div class="panel"><div class="ph">Tracked fire extent over time</div><div class="pb">
      <svg viewBox="0 0 ${W} ${H}" style="width:100%">
        <line x1="${issueX}" y1="10" x2="${issueX}" y2="${H-pb}" stroke="var(--blue-dim)" stroke-dasharray="3 3"/>
        <text x="${issueX+4}" y="20" fill="var(--blue)" font-size="10" font-family="monospace">forecast issued</text>
        <path d="${line}" fill="none" stroke="var(--fire)" stroke-width="1.6"/>${dots}${yt}${xt}
        <text x="${W/2}" y="${H-1}" fill="#5c656f" font-size="10" font-family="monospace" text-anchor="middle">minutes since first detection</text>
      </svg>
      <div class="kv" style="margin-top:6px"><div class="k">Peak extent</div><div class="v">${e.area_km2} km²</div>
        <div class="k">Mean spread rate</div><div class="v">${e.ros_kmh} km/h</div>
        <div class="k">Net heading</div><div class="v">${e.heading} (${e.heading_deg}°)</div></div>
    </div></div>
    <div class="panel"><div class="ph">Exposure · OpenStreetMap populations within forecast</div><div class="pb">
      ${exp?`<table><thead><tr><th>Community</th><th>Residents</th><th>P(threat)</th></tr></thead><tbody>${exp}</tbody></table>`:'<p class="muted">No populated places within the forecast footprint.</p>'}
      <p class="note">Communities whose surroundings the forecast projects fire into, with OSM resident
      counts and the ensemble threat probability. Analysis only — not an operational recommendation.</p>
    </div></div>
  </div>`;
}

function tabData(e,el){
  const rows=e.observations.map((o,i)=>`<tr onclick="this.classList.toggle('open')">
    <td>${esc(o.t_utc)}</td><td>${esc(o.source)}</td><td>${esc(o.kind)}</td>
    <td>${esc(o.product)}</td><td class="num">${o.n_pixels}</td>
    <td class="num">${o.lat!=null?o.lat+', '+o.lon:'—'}</td>
    <td class="num">${o.resolution_m?o.resolution_m+' m':'—'}</td></tr>`).join('');
  el.innerHTML=`<div class="panel"><div class="ph">Observations · ${e.observations.length} records</div>
    <div class="pb" style="padding:0"><table>
      <thead><tr><th>Time (UTC)</th><th>Source</th><th>Kind</th><th>Product</th><th>Pixels</th><th>Centroid</th><th>Native res.</th></tr></thead>
      <tbody>${rows}</tbody></table></div></div>
    <p class="note">Every observation ingested for this event, with its source and native resolution.
    GOES-18 provides ~5-minute geostationary coverage; NIFC perimeters and (where available) VIIRS
    refine it. This is the provenance behind every number on the other tabs.</p>`;
}

/* ── scrubber (shared time) ── */
function setupScrub(){
  const e=ev(), r=document.getElementById('scrub-r');
  r.max=e.evolution.length-1; r.value=state.frame;
  r.oninput=()=>{state.frame=+r.value;syncFrame();updScrub();};
  document.getElementById('play').onclick=togglePlay;
  updScrub();
}
function updScrub(){
  const e=ev(), f=e.evolution[state.frame];
  document.getElementById('scrub-t').textContent=`T+${f.t_min} min`;
  const ph=document.getElementById('scrub-ph'); ph.textContent=f.phase.toUpperCase();
  ph.className='phase'+(f.phase==='Forecast'?' fc':'');
}
function syncFrame(){
  const e=ev(), f=e.evolution[state.frame];
  const img=document.getElementById('ov-img'); if(img) img.src=f.img;
  const tt=document.getElementById('ov-time'); if(tt) tt.textContent='T+'+f.t_min+' min';
  const cap=document.getElementById('ov-cap'); if(cap) cap.textContent=f.caption;
}
function togglePlay(){
  state.playing=!state.playing;
  document.getElementById('play').textContent=state.playing?'❚❚':'▶';
  if(state.playing){state.timer=setInterval(()=>{const e=ev();state.frame=(state.frame+1)%e.evolution.length;
    document.getElementById('scrub-r').value=state.frame;syncFrame();updScrub();},1100);}
  else clearInterval(state.timer);
}
function playVisible(){document.querySelectorAll('video').forEach(v=>{v.muted=true;const p=v.play();if(p&&p.catch)p.catch(()=>{});});}

route();
</script>
"""


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "outputs" / "history.html"
    build(dest)
