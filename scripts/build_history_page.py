"""Generate the self-contained 'Fires From Orbit' page from real run artifacts.

Reads outputs/historical.json (from `firewatch.historical.run_all`) plus the per-fire tracking
videos/figures, base64-embeds them, and writes a self-contained, light-mode editorial HTML page with
the sped-up tracking videos playing. Every number, image, and video comes from a real GOES-18
tracking run — nothing synthetic.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FIRE_META = {
    "park": {"loc": "Butte & Tehama Counties, CA", "when": "24 Jul 2024",
             "blurb": "Ignited near Chico and ran up the Sierra foothills, growing into one of the "
                      "largest wildfires in California history (~429,000 acres eventual)."},
    "palisades": {"loc": "Pacific Palisades, Los Angeles", "when": "07 Jan 2025",
                  "blurb": "Driven by extreme Santa Ana winds toward the coast — one of the most "
                           "destructive urban-interface firestorms in California history."},
    "eaton": {"loc": "Altadena / Eaton Canyon, CA", "when": "07 Jan 2025",
              "blurb": "Erupted at the foot of the San Gabriels the same night as the Palisades Fire "
                       "and swept into Altadena under hurricane-force downslope winds."},
}
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _b64(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def _bar(iou: float) -> int:
    return max(4, min(100, round(iou / 0.25 * 100)))


def build(out_path: Path) -> Path:
    data = json.loads((REPO / "outputs" / "historical.json").read_text())
    data = [d for d in data if (REPO / "docs" / "assets" / d["asset"]).exists()]
    if not data:
        sys.exit("no historical results with figures found — run firewatch.historical.run_all first")

    tot_det = sum(d["goes_detections"] for d in data)
    tot_frames = sum(d["n_frames"] for d in data)
    mean_ros = sum(d["mean_ros_kmh"] for d in data) / len(data)

    modules = []
    for i, d in enumerate(data, 1):
        m = FIRE_META.get(d["key"], {"loc": "", "when": d["start_utc"][:10], "blurb": ""})
        asset_dir = REPO / "docs" / "assets"
        vid_file = asset_dir / (d.get("video_asset") or "")
        poster_file = asset_dir / f"poster_{d['key']}.png"
        if d.get("video_asset") and vid_file.exists():
            poster = f' poster="{_b64(poster_file, "image/png")}"' if poster_file.exists() else ""
            media = (f'<video class="scope" autoplay loop muted playsinline preload="auto"{poster} '
                     f'aria-label="Time-lapse fire tracking — {d["name"]}">'
                     f'<source src="{_b64(vid_file, "video/mp4")}" type="video/mp4"></video>'
                     f'<span class="replay">▶ time-lapse · GOES-18</span>')
        else:
            media = f'<img class="scope" loading="lazy" src="{_b64(asset_dir / d["asset"], "image/png")}" alt="{d["name"]}">'
        heading = COMPASS[int(((d["heading_deg"] % 360) + 11.25) // 22.5) % 16]
        delta = d["ablation_delta_iou"]
        badge = f'<span class="badge up">assimilation +{delta:.3f} IoU</span>' if delta > 0 else f'<span class="badge">assimilation {delta:+.3f} IoU</span>'
        modules.append(f"""
      <article class="module reveal">
        <div class="scope-wrap">{media}</div>
        <div class="panel">
          <header class="mod-head">
            <span class="idx">{i:02d}</span>
            <div><h2>{d['name']}</h2><p class="loc">{m['when']} · {m['loc']}</p></div>
          </header>
          {badge}
          <p class="blurb">{m['blurb']}</p>
          <dl class="readout">
            <div><dt>Frames</dt><dd>{d['n_frames']}</dd></div>
            <div><dt>Detections</dt><dd>{d['goes_detections']}<span>px</span></dd></div>
            <div><dt>Peak extent</dt><dd>{d['peak_area_km2']:.0f}<span>km²</span></dd></div>
            <div><dt>Spread rate</dt><dd>{d['mean_ros_kmh']:.1f}<span>km/h</span></dd></div>
            <div><dt>Growth</dt><dd>{d['growth_km2_per_h']:.0f}<span>km²/h</span></dd></div>
            <div><dt>Heading</dt><dd>{heading}<span>{d['heading_deg']:.0f}°</span></dd></div>
          </dl>
          <div class="skill">
            <span class="skill-label">Forecast skill vs GOES truth — mean perimeter IoU</span>
            <div class="bar"><span>baseline</span><span class="track"><i style="width:{_bar(d['iou_off'])}%"></i></span><b>{d['iou_off']:.3f}</b></div>
            <div class="bar on"><span>assimilation</span><span class="track"><i style="width:{_bar(d['iou_on'])}%"></i></span><b>{d['iou_on']:.3f}</b></div>
          </div>
        </div>
      </article>""")

    html = f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fires From Orbit</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400..700;1,9..144,400..600&family=Hanken+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{
  --bg:#f3f5fb; --bg-2:#eaeef7; --card:#ffffff; --edge:#e2e7f1; --edge-2:#d3dae8;
  --ink:#141c30; --muted:#586074; --faint:#8992a6;
  --ember:#e0522a; --ember-2:#ee8a3a; --teal:#0d9488; --teal-deep:#0b7c72; --good:#0ea371;
  --scope-shadow:0 18px 46px -22px rgba(20,28,48,.5);
}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --bg:#0a0e18; --bg-2:#0e1424; --card:#111828; --edge:#1f2940; --edge-2:#2c395c;
  --ink:#e7ecf7; --muted:#96a0ba; --faint:#69748f;
  --ember:#ff7a4a; --ember-2:#ffb060; --teal:#3fd8c8; --teal-deep:#2fb7a8; --good:#41d69a;
  --scope-shadow:0 18px 50px -20px rgba(0,0,0,.7);
}}}}
:root[data-theme="dark"]{{
  --bg:#0a0e18; --bg-2:#0e1424; --card:#111828; --edge:#1f2940; --edge-2:#2c395c;
  --ink:#e7ecf7; --muted:#96a0ba; --faint:#69748f;
  --ember:#ff7a4a; --ember-2:#ffb060; --teal:#3fd8c8; --teal-deep:#2fb7a8; --good:#41d69a;
  --scope-shadow:0 18px 50px -20px rgba(0,0,0,.7);
}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Hanken Grotesk",system-ui,sans-serif;line-height:1.6;-webkit-font-smoothing:antialiased;
  background-image:
    radial-gradient(900px 520px at 88% -6%, color-mix(in srgb, var(--ember) 12%, transparent), transparent 60%),
    radial-gradient(760px 480px at 4% 2%, color-mix(in srgb, var(--teal) 10%, transparent), transparent 62%);}}
.wrap{{max-width:1120px;margin:0 auto;padding:0 26px}}
a{{color:var(--teal-deep)}}

.topbar{{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 86%, transparent);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--edge)}}
.topbar .wrap{{display:flex;align-items:center;gap:12px;height:58px}}
.mark{{display:flex;align-items:center;gap:10px;font-weight:700;letter-spacing:.02em;font-size:16px}}
.glyph{{width:19px;height:19px;position:relative}}
.glyph::before{{content:"";position:absolute;inset:0;clip-path:polygon(50% 0,100% 100%,0 100%);
  background:linear-gradient(160deg,var(--ember-2),var(--ember))}}
.mark small{{color:var(--muted);font-weight:500;letter-spacing:.12em;font-size:10.5px;
  font-family:"IBM Plex Mono";text-transform:uppercase}}
.chip{{margin-left:auto;font-family:"IBM Plex Mono";font-size:11px;color:var(--muted);
  letter-spacing:.08em;border:1px solid var(--edge);padding:5px 11px;border-radius:100px;background:var(--card)}}
.chip .dot{{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--teal);
  margin-right:6px;box-shadow:0 0 8px var(--teal);vertical-align:middle}}

.hero{{padding:74px 0 22px}}
.kicker{{font-family:"IBM Plex Mono";font-size:12px;letter-spacing:.22em;color:var(--teal-deep);text-transform:uppercase}}
h1{{font-family:"Fraunces",Georgia,serif;font-weight:600;font-size:clamp(42px,6.6vw,80px);line-height:1.02;
  letter-spacing:-.015em;margin:.26em 0 .34em;text-wrap:balance}}
h1 em{{font-style:italic;color:var(--ember);font-weight:500}}
.lede{{max-width:60ch;color:var(--muted);font-size:19px;margin:0}}
.lede b{{color:var(--ink);font-weight:600}} .lede .ns{{color:var(--ember);font-weight:600}}

.ribbon{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:36px 0 6px}}
.stat{{background:var(--card);border:1px solid var(--edge);border-radius:16px;padding:16px 18px;
  box-shadow:0 1px 0 rgba(20,28,48,.03)}}
.stat .k{{font-family:"IBM Plex Mono";font-size:10.5px;letter-spacing:.12em;color:var(--faint);text-transform:uppercase}}
.stat .v{{font-family:"Fraunces",serif;font-weight:600;font-size:32px;margin-top:5px;font-variant-numeric:tabular-nums;letter-spacing:-.01em}}
.stat .v span{{font-family:"IBM Plex Mono";font-size:13px;color:var(--muted);margin-left:5px;font-weight:400}}

main{{padding:24px 0 10px;display:flex;flex-direction:column;gap:26px}}
.module{{background:var(--card);border:1px solid var(--edge);border-radius:20px;overflow:hidden;
  display:grid;grid-template-columns:1fr .92fr;gap:0}}
.scope-wrap{{position:relative;padding:16px;background:var(--bg-2);border-right:1px solid var(--edge);
  display:flex;align-items:center;justify-content:center}}
.scope{{width:100%;max-width:520px;aspect-ratio:1/1;border-radius:14px;display:block;object-fit:cover;
  background:#05070d;box-shadow:var(--scope-shadow)}}
.replay{{position:absolute;left:26px;bottom:26px;font-family:"IBM Plex Mono";font-size:10.5px;
  letter-spacing:.08em;color:#cfe;background:rgba(5,7,13,.62);border:1px solid rgba(120,200,190,.3);
  padding:4px 9px;border-radius:100px;backdrop-filter:blur(4px)}}
.panel{{padding:26px 28px;display:flex;flex-direction:column;gap:16px}}
.mod-head{{display:flex;align-items:center;gap:14px}}
.idx{{font-family:"Fraunces",serif;font-weight:600;font-size:22px;color:var(--teal-deep);
  border:1px solid var(--edge-2);border-radius:10px;padding:3px 11px}}
.mod-head h2{{font-family:"Fraunces",serif;font-weight:600;font-size:26px;margin:0;letter-spacing:-.01em}}
.mod-head .loc{{margin:1px 0 0;color:var(--muted);font-size:13px;font-family:"IBM Plex Mono";letter-spacing:.02em}}
.badge{{align-self:flex-start;font-family:"IBM Plex Mono";font-size:12px;letter-spacing:.03em;
  padding:6px 12px;border-radius:100px;border:1px solid var(--edge-2);color:var(--muted);background:var(--bg-2)}}
.badge.up{{color:var(--good);border-color:color-mix(in srgb,var(--good) 45%,transparent);
  background:color-mix(in srgb,var(--good) 10%,transparent)}}
.blurb{{margin:0;color:var(--muted);font-size:15px}}
.readout{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px 16px;margin:2px 0}}
.readout div{{border-left:2px solid var(--edge-2);padding-left:10px}}
.readout dt{{font-family:"IBM Plex Mono";font-size:10px;letter-spacing:.1em;color:var(--faint);text-transform:uppercase}}
.readout dd{{margin:2px 0 0;font-family:"Fraunces",serif;font-weight:600;font-size:22px;font-variant-numeric:tabular-nums}}
.readout dd span{{font-family:"IBM Plex Mono";font-size:11px;color:var(--muted);margin-left:4px;font-weight:400}}
.skill{{border-top:1px solid var(--edge);padding-top:15px;margin-top:auto;display:flex;flex-direction:column;gap:9px}}
.skill-label{{font-family:"IBM Plex Mono";font-size:10.5px;letter-spacing:.06em;color:var(--faint);text-transform:uppercase}}
.bar{{display:grid;grid-template-columns:82px 1fr 46px;align-items:center;gap:11px;font-family:"IBM Plex Mono";font-size:12px;color:var(--muted)}}
.bar.on{{color:var(--teal-deep)}}
.bar .track{{height:8px;border-radius:6px;background:var(--bg-2);border:1px solid var(--edge);overflow:hidden}}
.bar .track i{{display:block;height:100%;background:var(--faint);border-radius:6px}}
.bar.on .track i{{background:linear-gradient(90deg,var(--teal-deep),var(--teal))}}
.bar b{{text-align:right;color:var(--ink);font-weight:500;font-variant-numeric:tabular-nums}}

footer{{border-top:1px solid var(--edge);margin-top:26px;padding:32px 0 64px;color:var(--faint);font-size:13px}}
footer .wrap{{display:flex;flex-wrap:wrap;gap:12px 24px;align-items:baseline}}
footer .prov{{font-family:"IBM Plex Mono";font-size:11.5px}}
footer .rule{{color:var(--ember);font-weight:500}}
footer code{{font-family:"IBM Plex Mono";color:var(--muted)}}

.reveal{{opacity:0;transform:translateY(15px);animation:rise .7s cubic-bezier(.2,.7,.2,1) forwards}}
.reveal:nth-child(2){{animation-delay:.09s}} .reveal:nth-child(3){{animation-delay:.18s}}
@keyframes rise{{to{{opacity:1;transform:none}}}}
@media (prefers-reduced-motion:reduce){{.reveal{{animation:none;opacity:1;transform:none}}.scope{{}}}}
@media (max-width:820px){{.ribbon{{grid-template-columns:1fr 1fr}}.module{{grid-template-columns:1fr}}
  .scope-wrap{{border-right:none;border-bottom:1px solid var(--edge)}}.readout{{grid-template-columns:1fr 1fr}}}}
</style>

<div class="topbar"><div class="wrap">
  <span class="mark"><span class="glyph"></span>FIREWATCH<small>Fires From Orbit</small></span>
  <span class="chip"><span class="dot"></span>ARCHIVE · GOES-18 ABI · FDC</span>
</div></div>

<header class="hero"><div class="wrap">
  <span class="kicker">Satellite fire-object tracking</span>
  <h1>Tracking wildfires <em>from orbit.</em></h1>
  <p class="lede">Real <b>GOES-18</b> active-fire detections, clustered into fire objects and
  <b>tracked over time</b>, then fused with a physics + data-assimilation spread forecast over real
  terrain and fuels. Three named fires, played back from the first satellite detection.
  <span class="ns">Nothing synthetic.</span></p>
  <div class="ribbon">
    <div class="stat"><div class="k">Fires tracked</div><div class="v">{len(data)}</div></div>
    <div class="stat"><div class="k">GOES detections</div><div class="v">{tot_det}<span>px</span></div></div>
    <div class="stat"><div class="k">Frames processed</div><div class="v">{tot_frames}</div></div>
    <div class="stat"><div class="k">Mean spread rate</div><div class="v">{mean_ros:.1f}<span>km/h</span></div></div>
  </div>
</div></header>

<main class="wrap">{''.join(modules)}
</main>

<footer><div class="wrap">
  <span class="prov">SOURCES · GOES-18 ABI FDC · USGS/AWS Terrain Tiles · ESA WorldCover 10 m · NOAA HRRR</span>
  <span class="rule">FIREWATCH recommends; a human decides.</span>
  <span>Reproducible: <code>make history</code></span>
</div></footer>
"""
    out_path.write_text(html)
    print(f"wrote {out_path} ({out_path.stat().st_size // 1024} KB, {len(data)} fires)")
    return out_path


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "outputs" / "history.html"
    build(dest)
