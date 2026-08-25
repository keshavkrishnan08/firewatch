# FIREWATCH — Common Operating Picture (web)

An operational, dark-themed **common operating picture** for the FIREWATCH wildfire
forecasting system. It renders a single COP JSON document into a three-pane
emergency-ops console: **Observe** (cameras + observation feed), a MapLibre + deck.gl
**map** (burn-probability bands, perimeters, zones, roads, structures, hotspots,
camera view-cones, ignition, wind), and **Decide** (ranked evacuation / egress /
staging recommendations, exposure summary, and a natural-language query box).
A bottom **time scrubber** replays the assimilation window and steps through
forecast horizons.

## Stack

- Vite + React + TypeScript
- MapLibre GL JS via `react-map-gl/maplibre`
- deck.gl (`@deck.gl/core`, `@deck.gl/layers`, `@deck.gl/react`) as a `DeckGL` overlay
- Basemap: CARTO **dark-matter** GL style (no API key required)

## Data contract

The app fetches exactly one document:

```
GET ${API}/api/event/${eventId}/cop
```

`API` is empty (same-origin) by default; the default `eventId` is `demo`
(override with `?event=<id>` in the URL). Camera frames are loaded from
`${API}/outputs/${eventId}/${camera.frame}`. The optional NL query box calls
`GET ${API}/api/event/${eventId}/query?q=...` and shows the returned `answer`
plus any cited ids.

Everything on screen is driven by the fetched JSON — there is no hardcoded fire
data. Null geometry fields (common at early horizons) and a missing `evaluation`
block are handled gracefully.

See the live example document shape at `outputs/demo/cop.json` in the repo root.

## Develop

```bash
npm install
npm run dev        # http://localhost:5173
```

The dev server proxies `/api` and `/outputs` to the FIREWATCH backend at
`http://localhost:8000`, so run that backend alongside for live data. Point at a
different backend by setting `VITE_API_BASE` (e.g. `VITE_API_BASE=http://host:8000`).

## Build

```bash
npm run build      # type-checks (tsc) then emits dist/
npm run preview    # serve the production build locally
```

## Layout notes

- **Header** — fire name + status, wind (arrow / speed / RH / temp), issued time,
  an `ASSIMILATION ON` badge, and the `+ΔIoU` ablation stat at +60 min when
  `evaluation.ablation` is present. A synthetic-data banner appears when
  `meta.note` mentions "synthetic".
- **Map controls** — horizon selector (+15/+30/+60/+180), assimilation ON/OFF arm
  toggle, per-layer visibility switches, a probability-ramp legend, and a wind rose.
- **Interactions** — hover any feature for a tooltip; click a camera (map or card)
  to expand its frame + pose and fly to it; click any Decide recommendation to fly
  to and highlight its geometry; drag or play the timeline to filter observations by
  time and move through forecast horizons.
