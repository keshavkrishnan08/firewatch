"""Build a dead-simple FIREWATCH page: three real historical wildfires, each as an autoplaying
time-lapse video with a one-line caption. Reads outputs/historical.json; embeds the videos."""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "docs" / "assets"

META = {
    "park": "Tehama & Butte Counties, CA · 24 Jul 2024",
    "palisades": "Pacific Palisades, Los Angeles · 07 Jan 2025",
    "eaton": "Altadena / Eaton Canyon, CA · 07 Jan 2025",
}


def b64(p: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def build(out_path: Path) -> Path:
    data = json.loads((REPO / "outputs" / "historical.json").read_text())
    data = [d for d in data if (ASSETS / (d.get("video_asset") or "x")).exists()]
    if not data:
        sys.exit("no historical results — run firewatch.historical.run_all first")

    cards = ""
    for d in data:
        v = ASSETS / d["video_asset"]
        poster = ASSETS / f"poster_{d['key']}.png"
        pa = f' poster="{b64(poster, "image/png")}"' if poster.exists() else ""
        cards += f"""
      <figure class="fire">
        <video muted loop autoplay playsinline preload="auto"{pa}>
          <source src="{b64(v, "video/mp4")}" type="video/mp4"></video>
        <figcaption><b>{d['name']}</b><span>{META.get(d['key'], '')} · peak {d['peak_area_km2']:.0f} km²</span></figcaption>
      </figure>"""

    html = f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FIREWATCH</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700&family=IBM+Plex+Mono:wght@400&display=swap">
<style>
:root{{--bg:#0b0d0f;--card:#11151a;--border:#242a31;--text:#e7eaed;--muted:#8a939e;--fire:#ff6848}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:"Inter",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased}}
header{{padding:44px 24px 10px;max-width:1000px;margin:0 auto}}
header h1{{margin:0;font-size:24px;font-weight:700;letter-spacing:.14em}}
header h1 b{{color:var(--fire)}}
header p{{margin:8px 0 0;color:var(--muted);font-size:14px;max-width:60ch}}
main{{max-width:1000px;margin:0 auto;padding:20px 24px 60px;display:grid;gap:24px}}
.fire{{margin:0}}
.fire video{{width:100%;display:block;aspect-ratio:1/1;object-fit:cover;background:#05070d;
  border:1px solid var(--border);border-radius:6px}}
.fire figcaption{{margin-top:10px;display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 12px}}
.fire figcaption b{{font-size:17px;font-weight:600}}
.fire figcaption span{{font-family:"IBM Plex Mono",monospace;font-size:12.5px;color:var(--muted)}}
@media(min-width:720px){{main{{grid-template-columns:1fr 1fr}}.fire:first-child{{grid-column:1/-1}}}}
footer{{max-width:1000px;margin:0 auto;padding:0 24px 50px;color:#5c656f;font-size:12px;
  font-family:"IBM Plex Mono",monospace}}
</style>

<header>
  <h1>FIRE<b>WATCH</b></h1>
  <p>Three real California wildfires, tracked from GOES-18 satellite detections and played back as
  time-lapse. The fire grows, the tracked path follows it, and the forecast projects ahead.</p>
</header>
<main>{cards}
</main>
<footer>GOES-18 ABI · Terrain Tiles · ESA WorldCover · NOAA HRRR</footer>

<script>
document.querySelectorAll('video').forEach(v=>{{v.muted=true;var p=v.play();if(p&&p.catch)p.catch(()=>{{}});}});
</script>
"""
    out_path.write_text(html)
    print(f"wrote {out_path} ({out_path.stat().st_size // 1024} KB, {len(data)} fires)")
    return out_path


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "outputs" / "history.html"
    build(dest)
