import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { FlyToInterpolator } from '@deck.gl/core';
import { Map } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';

import type { Cop, Decision, Arm, ZoneProps, RoadProps, StructureProps, ObsProps, CameraProps } from '../api/types';
import { buildLayers, type LayerVisibility } from './mapLayers';
import Legend from './Legend';
import { viewStateForBounds, bboxToBounds, type Bounds, type ViewState } from '../lib/geo';
import { obsColor, obsLabel } from '../lib/colors';
import { fmtClock, bearingToCompass } from '../lib/format';

const BASEMAP = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

export interface MapHandle {
  flyToBounds: (b: Bounds) => void;
  fit: () => void;
}

interface Props {
  cop: Cop;
  arm: Arm;
  horizon: number;
  onArm: (a: Arm) => void;
  onHorizon: (h: number) => void;
  visible: LayerVisibility;
  onToggle: (key: keyof LayerVisibility) => void;
  obsCutoffMs: number;
  selectedCameraId: string | null;
  onSelectCamera: (id: string) => void;
  highlight: Decision | null;
}

interface HoverState {
  x: number;
  y: number;
  layerId: string;
  object: unknown;
}

const TOGGLE_ITEMS: { key: keyof LayerVisibility; label: string; color: string }[] = [
  { key: 'bands', label: 'Burn probability', color: 'linear-gradient(90deg,#ffe066,#ba181b)' },
  { key: 'perimeters', label: 'Perimeters', color: '#ffffff' },
  { key: 'observations', label: 'Observations', color: '#ff7a59' },
  { key: 'zones', label: 'Zones', color: '#f5a623' },
  { key: 'roads', label: 'Roads', color: '#9fb0c5' },
  { key: 'structures', label: 'Structures', color: '#7a8aa0' },
  { key: 'cameras', label: 'Cameras', color: '#4c9dff' },
  { key: 'staging', label: 'Staging', color: '#30a46c' },
];

function WindWidget({ cop }: { cop: Cop }) {
  const w = cop.meta.wind;
  return (
    <div className="map-overlay wind-widget">
      <div className="ctrl-card" style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
        <div className="rose">
          <span className="n">N</span>
          <svg width="34" height="34" viewBox="0 0 24 24" style={{ transform: `rotate(${w.dir_to_deg}deg)` }}>
            <path d="M12 3 L12 21 M12 3 L7.5 9.5 M12 3 L16.5 9.5" fill="none" stroke="#ff8a5c" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div className="wx">
          <div className="big">{w.speed_ms.toFixed(1)} m/s</div>
          <div className="sm">→ {bearingToCompass(w.dir_to_deg)} ({Math.round(w.dir_to_deg)}°)</div>
          <div className="sm">{Math.round(w.rh_pct)}% RH · {Math.round(w.temp_c)}°C</div>
        </div>
      </div>
    </div>
  );
}

function Tooltip({ hover }: { hover: HoverState }) {
  const o = hover.object as Record<string, unknown> & { properties?: Record<string, unknown> };
  const props = (o?.properties ?? o) as Record<string, unknown>;
  let title = '';
  let kindColor = '#4c9dff';
  const rows: [string, string][] = [];

  switch (hover.layerId) {
    case 'zones': {
      const p = props as unknown as ZoneProps;
      title = p.name;
      kindColor = '#f5a623';
      rows.push(['Population', String(p.population)]);
      rows.push(['Evac status', p.evac_status]);
      break;
    }
    case 'roads': {
      const p = props as unknown as RoadProps;
      title = p.name;
      kindColor = '#9fb0c5';
      rows.push(['Class', p.highway]);
      break;
    }
    case 'structures': {
      const p = props as unknown as StructureProps;
      title = p.type ? `Structure · ${p.type}` : 'Structure';
      kindColor = '#7a8aa0';
      if (p.pop != null) rows.push(['Occupants', Number(p.pop).toFixed(1)]);
      break;
    }
    case 'cameras': {
      const p = props as unknown as CameraProps;
      title = p.name;
      kindColor = '#4c9dff';
      rows.push(['Network', p.network]);
      rows.push(['Pan / FOV', `${p.pan.toFixed(0)}° / ${p.fov.toFixed(0)}°`]);
      break;
    }
    case 'hotspots':
    case 'obs-outlines': {
      const kind = String((o as { kind?: string }).kind ?? (props as unknown as ObsProps).kind ?? '');
      const t = String((o as { t?: string }).t ?? (props as unknown as ObsProps).t ?? '');
      title = obsLabel(kind);
      kindColor = `rgb(${obsColor(kind)[0]},${obsColor(kind)[1]},${obsColor(kind)[2]})`;
      if (t) rows.push(['Observed', fmtClock(t)]);
      break;
    }
    case 'staging': {
      const d = o as unknown as Decision;
      title = d.target_name;
      kindColor = '#30a46c';
      rows.push(['Type', 'Staging area']);
      break;
    }
    default:
      title = hover.layerId;
  }

  return (
    <div className="map-tip" style={{ left: hover.x, top: hover.y }}>
      <div className="tt-title">
        <span className="tt-kind" style={{ background: kindColor }} />
        {title}
      </div>
      {rows.map(([k, v]) => (
        <div className="tt-row" key={k}>
          <span>{k}</span>
          <span className="v">{v}</span>
        </div>
      ))}
    </div>
  );
}

const MapView = forwardRef<MapHandle, Props>(function MapView(props, ref) {
  const { cop, arm, horizon, onArm, onHorizon, visible, onToggle, obsCutoffMs, selectedCameraId, onSelectCamera, highlight } = props;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const sizeRef = useRef({ w: 1000, h: 700 });
  const [size, setSize] = useState({ w: 1000, h: 700 });
  const fittedFor = useRef<string | null>(null);

  const [viewState, setViewState] = useState<ViewState>({
    longitude: (cop.meta.bbox[0] + cop.meta.bbox[2]) / 2,
    latitude: (cop.meta.bbox[1] + cop.meta.bbox[3]) / 2,
    zoom: 11,
    pitch: 0,
    bearing: 0,
  });
  const [hover, setHover] = useState<HoverState | null>(null);

  // Track container size for fit/fly math.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      const next = { w: Math.round(r.width), h: Math.round(r.height) };
      sizeRef.current = next;
      setSize(next);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Fit to bbox once per event.
  useEffect(() => {
    if (size.w < 2 || size.h < 2) return;
    if (fittedFor.current === cop.meta.event_id) return;
    fittedFor.current = cop.meta.event_id;
    setViewState(viewStateForBounds(bboxToBounds(cop.meta.bbox), size.w, size.h, 72));
  }, [cop, size.w, size.h]);

  const flyToBounds = useCallback((b: Bounds) => {
    const vs = viewStateForBounds(b, sizeRef.current.w, sizeRef.current.h, 110);
    setViewState({
      ...vs,
      transitionDuration: 1100,
      transitionInterpolator: new FlyToInterpolator({ speed: 1.6 }),
    } as unknown as ViewState);
  }, []);

  useImperativeHandle(ref, () => ({
    flyToBounds,
    fit: () => setViewState(viewStateForBounds(bboxToBounds(cop.meta.bbox), sizeRef.current.w, sizeRef.current.h, 72)),
  }), [flyToBounds, cop]);

  const layers = useMemo(
    () => buildLayers(cop, { arm, horizon, visible, obsCutoffMs, selectedCameraId, highlight }),
    [cop, arm, horizon, visible, obsCutoffMs, selectedCameraId, highlight],
  );

  const horizons = cop.meta.horizons ?? [15, 30, 60, 180];

  return (
    <div className="map-wrap" ref={containerRef}>
      <DeckGL
        style={{ position: 'absolute', top: '0', left: '0', width: '100%', height: '100%' }}
        viewState={viewState as unknown as Record<string, number>}
        controller={{ dragRotate: false }}
        onViewStateChange={(e: any) => setViewState(e.viewState)}
        layers={layers as never}
        getCursor={({ isDragging, isHovering }: { isDragging: boolean; isHovering: boolean }) =>
          isDragging ? 'grabbing' : isHovering ? 'pointer' : 'grab'
        }
        onHover={(info: any) => {
          if (info?.object && info.layer) {
            setHover({ x: info.x, y: info.y, layerId: info.layer.id, object: info.object });
          } else {
            setHover(null);
          }
        }}
        onClick={(info: any) => {
          if (info?.layer?.id === 'cameras' && info.object?.properties?.id) {
            onSelectCamera(info.object.properties.id as string);
          }
        }}
      >
        <Map mapStyle={BASEMAP} reuseMaps />
      </DeckGL>

      {/* Controls */}
      <div className="map-overlay map-controls">
        <div className="ctrl-card">
          <div className="ctrl-title">Forecast horizon</div>
          <div className="seg">
            {horizons.map((h) => (
              <button key={h} className={h === horizon ? 'on' : ''} onClick={() => onHorizon(h)}>
                +{h}
              </button>
            ))}
          </div>
        </div>

        <div className="ctrl-card">
          <div className="ctrl-title">Assimilation arm</div>
          <div className="seg arm">
            <button className={arm === 'on' ? 'on' : ''} onClick={() => onArm('on')}>
              ON
            </button>
            <button className={arm === 'off' ? 'on off-arm' : ''} onClick={() => onArm('off')}>
              OFF (baseline)
            </button>
          </div>
        </div>

        <div className="ctrl-card">
          <div className="ctrl-title">Layers</div>
          <div className="toggles">
            {TOGGLE_ITEMS.map((it) => (
              <div
                key={it.key}
                className={`toggle${visible[it.key] ? ' on' : ''}`}
                onClick={() => onToggle(it.key)}
              >
                <span className="swatch" style={{ background: it.color }} />
                <span style={{ flex: 1 }}>{it.label}</span>
                <span className="sw" />
              </div>
            ))}
          </div>
        </div>
      </div>

      <WindWidget cop={cop} />
      <Legend arm={arm} horizon={horizon} />

      {hover && <Tooltip hover={hover} />}
    </div>
  );
});

export default MapView;
