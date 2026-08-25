import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Point } from 'geojson';

import type { Cop, Decision, Arm, CameraProps, ObsProps } from './api/types';
import { fetchCop, DEFAULT_EVENT_ID } from './api/client';
import { parseTime } from './lib/format';
import { geometryBounds, padBounds } from './lib/geo';

import Header from './components/Header';
import ObservePane from './components/ObservePane';
import DecidePane from './components/DecidePane';
import TimeScrubber from './components/TimeScrubber';
import MapView, { type MapHandle } from './components/MapView';
import type { LayerVisibility } from './components/mapLayers';

const DEFAULT_VISIBLE: LayerVisibility = {
  bands: true,
  perimeters: true,
  zones: true,
  roads: true,
  structures: true,
  observations: true,
  cameras: true,
  staging: false,
};

function pickDefaultHorizon(horizons: number[]): number {
  if (!horizons.length) return 60;
  if (horizons.includes(60)) return 60;
  return horizons[Math.min(horizons.length - 1, Math.floor(horizons.length / 2))];
}

function getEventId(): string {
  try {
    const q = new URLSearchParams(window.location.search).get('event');
    return q && q.trim() ? q.trim() : DEFAULT_EVENT_ID;
  } catch {
    return DEFAULT_EVENT_ID;
  }
}

export default function App() {
  const [eventId] = useState(getEventId);
  const [cop, setCop] = useState<Cop | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [arm, setArm] = useState<Arm>('on');
  const [horizon, setHorizon] = useState<number>(60);
  const [scrubMs, setScrubMs] = useState<number>(0);
  const [visible, setVisible] = useState<LayerVisibility>(DEFAULT_VISIBLE);
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);

  const mapRef = useRef<MapHandle>(null);
  const userCamInteract = useRef(false);

  // ---- fetch ----
  useEffect(() => {
    const ac = new AbortController();
    setLoading(true);
    setError(null);
    fetchCop(eventId, ac.signal)
      .then((doc) => {
        setCop(doc);
        const issued = parseTime(doc.meta.issued_at) ?? Date.now();
        setHorizon(pickDefaultHorizon(doc.meta.horizons ?? []));
        setScrubMs(issued);
        setSelectedDecision(null);
        userCamInteract.current = false;
        const firstCam = doc.layers.cameras?.features?.[0];
        setSelectedCameraId(firstCam ? (firstCam.properties as CameraProps).id : null);
      })
      .catch((e) => {
        if (ac.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [eventId]);

  const ignitionMs = useMemo(() => (cop ? parseTime(cop.meta.ignition_time) ?? 0 : 0), [cop]);
  const issuedMs = useMemo(() => (cop ? parseTime(cop.meta.issued_at) ?? 0 : 0), [cop]);
  const obsCutoffMs = Math.min(scrubMs || issuedMs, issuedMs);

  const obsCount = useMemo(() => {
    if (!cop) return 0;
    let n = 0;
    for (const f of cop.layers.observations?.features ?? []) {
      const t = parseTime((f.properties as ObsProps).t);
      if (t == null || t <= obsCutoffMs) n++;
    }
    return n;
  }, [cop, obsCutoffMs]);

  // ---- handlers ----
  const onHorizonControl = useCallback(
    (h: number) => {
      setHorizon(h);
      if (issuedMs) setScrubMs(issuedMs + h * 60000);
    },
    [issuedMs],
  );

  const onScrub = useCallback(
    (ms: number) => {
      setScrubMs(ms);
      if (cop && issuedMs && ms > issuedMs + 1) {
        const offMin = (ms - issuedMs) / 60000;
        const hs = cop.meta.horizons ?? [15, 30, 60, 180];
        let chosen = hs[0];
        for (const h of hs) if (h <= offMin + 1e-6) chosen = h;
        setHorizon(chosen);
      }
    },
    [cop, issuedMs],
  );

  const onSelectCamera = useCallback((id: string) => {
    userCamInteract.current = true;
    setSelectedCameraId(id);
  }, []);

  const onSelectDecision = useCallback((d: Decision) => {
    setSelectedDecision((prev) => (prev?.id === d.id ? null : d));
  }, []);

  const onToggle = useCallback((key: keyof LayerVisibility) => {
    setVisible((v) => ({ ...v, [key]: !v[key] }));
  }, []);

  // ---- fly-to effects ----
  useEffect(() => {
    if (!cop || !selectedCameraId || !userCamInteract.current) return;
    const cam = cop.layers.cameras?.features?.find((f) => (f.properties as CameraProps).id === selectedCameraId);
    if (!cam) return;
    const [lng, lat] = (cam.geometry as Point).coordinates as [number, number];
    mapRef.current?.flyToBounds([
      [lng - 0.012, lat - 0.009],
      [lng + 0.012, lat + 0.009],
    ]);
  }, [selectedCameraId, cop]);

  useEffect(() => {
    if (!selectedDecision) return;
    const b = geometryBounds(selectedDecision.geometry);
    if (b) mapRef.current?.flyToBounds(padBounds(b, 0.6));
  }, [selectedDecision]);

  // ---- render ----
  if (loading || error || !cop) {
    return (
      <div className="app">
        <div style={{ position: 'relative', height: '100vh' }}>
          <div className="center-state">
            <div className="cs-inner">
              {loading && (
                <>
                  <div className="spinner" />
                  <h2>Loading operating picture…</h2>
                  <p>
                    Fetching <code>/api/event/{eventId}/cop</code>
                  </p>
                </>
              )}
              {error && !loading && (
                <>
                  <h2 style={{ color: 'var(--red-soft)' }}>Could not load event</h2>
                  <p>{error}</p>
                  <p style={{ marginTop: 14 }}>
                    Confirm the FIREWATCH backend is serving <code>/api/event/{eventId}/cop</code> (dev proxy → localhost:8000),
                    or open with <code>?event=&lt;id&gt;</code>.
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  const synthetic = (cop.meta.note ?? '').toLowerCase().includes('synthetic');

  return (
    <div className="app">
      <Header meta={cop.meta} evaluation={cop.evaluation} />
      {synthetic && (
        <div className="synthetic-banner">
          <span className="tag">Synthetic</span>
          <span>{cop.meta.note}</span>
        </div>
      )}

      <div className="workspace">
        <ObservePane
          cop={cop}
          eventId={eventId}
          selectedCameraId={selectedCameraId}
          onSelectCamera={onSelectCamera}
        />

        <MapView
          ref={mapRef}
          cop={cop}
          arm={arm}
          horizon={horizon}
          onArm={setArm}
          onHorizon={onHorizonControl}
          visible={visible}
          onToggle={onToggle}
          obsCutoffMs={obsCutoffMs}
          selectedCameraId={selectedCameraId}
          onSelectCamera={onSelectCamera}
          highlight={selectedDecision}
        />

        <DecidePane
          cop={cop}
          eventId={eventId}
          horizon={horizon}
          selectedDecisionId={selectedDecision?.id ?? null}
          onSelectDecision={onSelectDecision}
        />
      </div>

      <TimeScrubber
        ignitionMs={ignitionMs}
        issuedMs={issuedMs}
        horizons={cop.meta.horizons ?? [15, 30, 60, 180]}
        value={scrubMs}
        onChange={onScrub}
        obsCount={obsCount}
      />
    </div>
  );
}
