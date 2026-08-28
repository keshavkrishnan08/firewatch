"""FastAPI backend for the COP board (FR-API-1).

Serves the precomputed COP JSON plus live ontology time-travel endpoints (state/forecast/decisions
as of any instant, the scrubber is a query over object versions), static frames/figures, and the
read-only NL query. Run: `make api` (uvicorn firewatch.api.server:app --port 8000).
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from firewatch.api.query import answer_query
from firewatch.config import EventPaths, outputs_dir
from firewatch.ontology.store import Store

app = FastAPI(title="FIREWATCH", description="Real-time wildfire common operating picture", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_OUT = outputs_dir()
_OUT.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(_OUT)), name="outputs")


def _parse_t(t: str | None) -> datetime | None:
    if not t:
        return None
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        raise HTTPException(400, f"bad timestamp: {t}") from None


def _store(event_id: str) -> Store:
    db = EventPaths(event_id).ontology_db
    if not db.exists():
        raise HTTPException(404, f"no ontology store for event '{event_id}', run `make replay FIRE={event_id}`")
    return Store(db)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "firewatch"}


@app.get("/api/events")
def events():
    ids = [p.name for p in _OUT.iterdir() if p.is_dir() and (p / "cop.json").exists()] if _OUT.exists() else []
    return {"events": sorted(ids)}


@app.get("/api/event/{event_id}/cop")
def cop(event_id: str):
    path = EventPaths(event_id).outputs / "cop.json"
    if not path.exists():
        raise HTTPException(404, f"no COP for '{event_id}', run `make replay FIRE={event_id}`")
    return JSONResponse(json.loads(path.read_text()))


@app.get("/api/event/{event_id}/metrics")
def metrics(event_id: str):
    path = EventPaths(event_id).outputs / "metrics.json"
    if not path.exists():
        raise HTTPException(404, "no metrics")
    return JSONResponse(json.loads(path.read_text()))


@app.get("/api/event/{event_id}/state")
def state(event_id: str, t: str | None = Query(None), kind: str | None = Query(None)):
    """Ontology state as of time `t` (the scrubber). Optionally filter by object kind."""
    store = _store(event_id)
    at = _parse_t(t)
    kinds = [kind] if kind else store.kinds()
    out = {k: [json.loads(o.model_dump_json()) for o in store.state_at(k, at)] for k in kinds}
    store.close()
    return {"event_id": event_id, "t": t, "objects": out}


@app.get("/api/event/{event_id}/forecast")
def forecast(event_id: str, h: int | None = Query(None), t: str | None = Query(None)):
    store = _store(event_id)
    fcs = store.state_at("Forecast", _parse_t(t))
    if h is not None:
        fcs = [f for f in fcs if f.horizon_min == h]
    out = [json.loads(f.model_dump_json()) for f in fcs]
    store.close()
    return {"event_id": event_id, "forecasts": out}


@app.get("/api/event/{event_id}/decisions")
def decisions(event_id: str, t: str | None = Query(None)):
    store = _store(event_id)
    recs = store.state_at("Recommendation", _parse_t(t))
    recs.sort(key=lambda r: r.urgency, reverse=True)
    out = [json.loads(r.model_dump_json()) for r in recs]
    store.close()
    return {"event_id": event_id, "recommendations": out}


@app.get("/api/event/{event_id}/observe/{camera_id}")
def observe(event_id: str, camera_id: str):
    store = _store(event_id)
    cams = [c for c in store.state_at("Camera") if c.id == camera_id]
    store.close()
    if not cams:
        raise HTTPException(404, "camera not found")
    c = cams[0]
    return {"camera": json.loads(c.model_dump_json()),
            "frame_url": f"/outputs/{event_id}/{c.last_frame}" if c.last_frame else None}


@app.get("/api/event/{event_id}/query")
def query(event_id: str, q: str = Query(...), t: str | None = Query(None)):
    store = _store(event_id)
    ans = answer_query(store, q, _parse_t(t))
    store.close()
    return ans


# serve the built frontend if present (web/dist)
from pathlib import Path  # noqa: E402

_WEB = Path(__file__).resolve().parents[3] / "web" / "dist"
if _WEB.exists():
    app.mount("/", StaticFiles(directory=str(_WEB), html=True), name="web")
