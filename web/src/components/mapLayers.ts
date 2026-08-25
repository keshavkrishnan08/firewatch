// Builds the deck.gl layer stack for the COP map from the fetched document.

import { GeoJsonLayer, ScatterplotLayer, PolygonLayer, TextLayer } from '@deck.gl/layers';
import type { Feature, FeatureCollection, Point, MultiPoint, Position } from 'geojson';
import type { Cop, Decision, CameraProps, ObsProps, ZoneProps, RoadProps, Arm } from '../api/types';
import { bandFill, urgencyRGB, obsColor, type RGBA } from '../lib/colors';
import { viewConePolygon } from '../lib/geo';

export interface LayerVisibility {
  bands: boolean;
  perimeters: boolean; // expected + region90
  zones: boolean;
  roads: boolean;
  structures: boolean;
  observations: boolean;
  cameras: boolean;
  staging: boolean;
}

export interface BuildOpts {
  arm: Arm;
  horizon: number;
  visible: LayerVisibility;
  obsCutoffMs: number;
  selectedCameraId: string | null;
  highlight: Decision | null;
}

const SAT_KINDS = new Set(['goes', 'viirs', 'modis']);

interface HotspotPt {
  position: [number, number];
  kind: string;
  id: string;
  t: string;
}

function featureOf(geometry: unknown): Feature {
  return { type: 'Feature', geometry: geometry as Feature['geometry'], properties: {} };
}

export function buildLayers(cop: Cop, opts: BuildOpts): unknown[] {
  const { arm, horizon, visible, obsCutoffMs, selectedCameraId, highlight } = opts;
  const layers: unknown[] = [];

  const zones = cop.layers.zones ?? emptyFC();
  const roads = cop.layers.roads ?? emptyFC();
  const structures = cop.layers.structures ?? emptyFC();
  const cameras = cop.layers.cameras ?? emptyFC();
  const observations = cop.layers.observations ?? emptyFC();

  // ---- evac / egress lookups (target id -> urgency) ----
  const evacUrgency = new Map<string, number>();
  for (const d of cop.decisions?.evacuations ?? []) evacUrgency.set(d.target, d.urgency);
  const egressUrgency = new Map<string, number>();
  for (const d of cop.decisions?.egress ?? []) egressUrgency.set(d.target, d.urgency);

  // ---- 1. zones ----
  if (visible.zones) {
    layers.push(
      new GeoJsonLayer({
        id: 'zones',
        data: zones as FeatureCollection,
        pickable: true,
        stroked: true,
        filled: true,
        getFillColor: (f: Feature): RGBA => {
          const p = f.properties as ZoneProps;
          const u = evacUrgency.get(p.id);
          if (u == null) return [120, 140, 165, 16];
          const [r, g, b] = urgencyRGB(u);
          return [r, g, b, 42];
        },
        getLineColor: (f: Feature): RGBA => {
          const p = f.properties as ZoneProps;
          const u = evacUrgency.get(p.id);
          if (u == null) return [150, 170, 195, 120];
          const [r, g, b] = urgencyRGB(u);
          return [r, g, b, 210];
        },
        lineWidthUnits: 'pixels',
        getLineWidth: 1.4,
        lineWidthMinPixels: 1.2,
        updateTriggers: { getFillColor: [arm], getLineColor: [arm] },
      }),
    );
  }

  // ---- 2. roads ----
  if (visible.roads) {
    layers.push(
      new GeoJsonLayer({
        id: 'roads',
        data: roads as FeatureCollection,
        pickable: true,
        stroked: true,
        filled: false,
        getLineColor: (f: Feature): RGBA => {
          const p = f.properties as RoadProps;
          const u = egressUrgency.get(p.id);
          if (u == null || u < 0.33) return [150, 170, 195, 150];
          const [r, g, b] = urgencyRGB(u);
          return [r, g, b, 235];
        },
        lineWidthUnits: 'pixels',
        getLineWidth: (f: Feature): number => {
          const p = f.properties as RoadProps;
          const u = egressUrgency.get(p.id) ?? 0;
          return u >= 0.66 ? 4 : u >= 0.33 ? 3 : 2.2;
        },
        lineWidthMinPixels: 2,
        capRounded: true,
        jointRounded: true,
      }),
    );
  }

  // ---- 3. probability bands (selected arm + horizon) ----
  const hf = cop.forecast?.[arm]?.[String(horizon)];
  if (visible.bands && hf?.bands?.length) {
    const sorted = [...hf.bands].sort((a, b) => a.level - b.level);
    sorted.forEach((band, i) => {
      layers.push(
        new GeoJsonLayer({
          id: `band-${arm}-${horizon}-${i}`,
          data: featureOf(band.geometry),
          stroked: false,
          filled: true,
          getFillColor: bandFill(band.level),
          pickable: false,
        }),
      );
    });
  }

  // ---- 4. region90 + expected perimeter ----
  if (visible.perimeters && hf?.region90) {
    layers.push(
      new GeoJsonLayer({
        id: 'region90',
        data: featureOf(hf.region90),
        stroked: true,
        filled: false,
        getLineColor: [214, 226, 240, 150],
        lineWidthUnits: 'pixels',
        getLineWidth: 1.2,
        lineWidthMinPixels: 1,
        pickable: false,
      }),
    );
  }
  if (visible.perimeters && hf?.expected) {
    layers.push(
      new GeoJsonLayer({
        id: 'expected',
        data: featureOf(hf.expected),
        stroked: true,
        filled: false,
        getLineColor: [255, 255, 255, 235],
        lineWidthUnits: 'pixels',
        getLineWidth: 2.4,
        lineWidthMinPixels: 2,
        pickable: false,
      }),
    );
  }

  // ---- 5. structures ----
  if (visible.structures) {
    layers.push(
      new ScatterplotLayer({
        id: 'structures',
        data: (structures.features ?? []) as Feature<Point>[],
        pickable: true,
        getPosition: (f: Feature<Point>) => f.geometry.coordinates as [number, number],
        getFillColor: [150, 170, 195, 165],
        getRadius: 2,
        radiusUnits: 'pixels',
        radiusMinPixels: 1.6,
        radiusMaxPixels: 3.2,
        stroked: false,
      }),
    );
  }

  // ---- 6. camera view cones ----
  if (visible.cameras) {
    const coneData = (cameras.features ?? []).map((f) => {
      const p = f.properties as CameraProps;
      const c = (f.geometry as Point).coordinates as [number, number];
      return { polygon: viewConePolygon(c, p.pan, p.fov), id: p.id };
    });
    layers.push(
      new PolygonLayer({
        id: 'cam-cones',
        data: coneData,
        getPolygon: (d: { polygon: Position[] }) => d.polygon,
        filled: true,
        stroked: true,
        getFillColor: (d: { id: string }): RGBA =>
          d.id === selectedCameraId ? [76, 157, 255, 55] : [76, 157, 255, 24],
        getLineColor: [76, 157, 255, 95],
        lineWidthUnits: 'pixels',
        getLineWidth: 1,
        lineWidthMinPixels: 1,
        pickable: false,
        updateTriggers: { getFillColor: [selectedCameraId] },
      }),
    );
  }

  // ---- 7. observation outlines (official perimeter, camera front) ----
  if (visible.observations) {
    const outlineFeats = (observations.features ?? []).filter((f) => {
      const p = f.properties as ObsProps;
      if (!(p.kind === 'official_perimeter' || p.kind === 'camera_front')) return false;
      const t = Date.parse(p.t);
      return Number.isNaN(t) || t <= obsCutoffMs;
    });
    if (outlineFeats.length) {
      layers.push(
        new GeoJsonLayer({
          id: 'obs-outlines',
          data: { type: 'FeatureCollection', features: outlineFeats } as FeatureCollection,
          pickable: true,
          stroked: true,
          filled: false,
          getLineColor: (f: Feature): RGBA => obsColor((f.properties as ObsProps).kind),
          lineWidthUnits: 'pixels',
          getLineWidth: 2,
          lineWidthMinPixels: 1.6,
          updateTriggers: { getLineColor: [obsCutoffMs] },
        }),
      );
    }

    // ---- 8. satellite hotspots (flattened points) ----
    const hotspots: HotspotPt[] = [];
    for (const f of observations.features ?? []) {
      const p = f.properties as ObsProps;
      if (!SAT_KINDS.has(p.kind)) continue;
      const t = Date.parse(p.t);
      if (!Number.isNaN(t) && t > obsCutoffMs) continue;
      const g = f.geometry;
      if (!g) continue;
      if (g.type === 'Point') {
        hotspots.push({ position: (g as Point).coordinates as [number, number], kind: p.kind, id: p.id, t: p.t });
      } else if (g.type === 'MultiPoint') {
        for (const c of (g as MultiPoint).coordinates) {
          hotspots.push({ position: c as [number, number], kind: p.kind, id: p.id, t: p.t });
        }
      }
    }
    if (hotspots.length) {
      layers.push(
        new ScatterplotLayer({
          id: 'hotspots',
          data: hotspots,
          pickable: true,
          getPosition: (d: HotspotPt) => d.position,
          getFillColor: (d: HotspotPt): RGBA => obsColor(d.kind),
          getRadius: 3,
          radiusUnits: 'pixels',
          radiusMinPixels: 2.6,
          radiusMaxPixels: 5,
          stroked: true,
          getLineColor: [8, 11, 16, 200],
          lineWidthUnits: 'pixels',
          getLineWidth: 0.6,
          updateTriggers: { getFillColor: [obsCutoffMs], data: [obsCutoffMs] },
        }),
      );
    }
  }

  // ---- 9. staging candidates ----
  if (visible.staging) {
    const stagePts = (cop.decisions?.staging ?? []).filter((d) => d.geometry?.type === 'Point');
    if (stagePts.length) {
      layers.push(
        new ScatterplotLayer({
          id: 'staging',
          data: stagePts,
          pickable: true,
          getPosition: (d: Decision) => (d.geometry as Point).coordinates as [number, number],
          getFillColor: [48, 164, 108, 210],
          getRadius: 5,
          radiusUnits: 'pixels',
          radiusMinPixels: 4,
          radiusMaxPixels: 7,
          stroked: true,
          getLineColor: [230, 245, 238, 220],
          lineWidthUnits: 'pixels',
          getLineWidth: 1,
        }),
      );
    }
  }

  // ---- 10. cameras (markers + labels) ----
  if (visible.cameras) {
    layers.push(
      new ScatterplotLayer({
        id: 'cameras',
        data: (cameras.features ?? []) as Feature<Point>[],
        pickable: true,
        getPosition: (f: Feature<Point>) => f.geometry.coordinates as [number, number],
        getFillColor: (f: Feature<Point>): RGBA =>
          (f.properties as CameraProps).id === selectedCameraId ? [255, 255, 255, 255] : [76, 157, 255, 255],
        getRadius: (f: Feature<Point>) => ((f.properties as CameraProps).id === selectedCameraId ? 7 : 5),
        radiusUnits: 'pixels',
        radiusMinPixels: 4,
        radiusMaxPixels: 8,
        stroked: true,
        getLineColor: [10, 15, 22, 230],
        lineWidthUnits: 'pixels',
        getLineWidth: 1.5,
        updateTriggers: { getFillColor: [selectedCameraId], getRadius: [selectedCameraId] },
      }),
    );
    layers.push(
      new TextLayer({
        id: 'cam-labels',
        data: (cameras.features ?? []) as Feature<Point>[],
        getPosition: (f: Feature<Point>) => f.geometry.coordinates as [number, number],
        getText: (f: Feature<Point>) => (f.properties as CameraProps).name,
        getColor: [200, 216, 232, 225],
        getSize: 11,
        sizeUnits: 'pixels',
        getPixelOffset: [0, -14],
        fontFamily: 'ui-monospace, Menlo, monospace',
        fontWeight: 600,
        getTextAnchor: 'middle',
        getAlignmentBaseline: 'bottom',
        outlineWidth: 2,
        outlineColor: [6, 9, 14, 255],
        fontSettings: { sdf: true },
      }),
    );
  }

  // ---- 11. ignition star ----
  const ign = cop.meta?.fire?.ignition;
  if (ign) {
    layers.push(
      new TextLayer({
        id: 'ignition',
        data: [{ position: ign as [number, number] }],
        getPosition: (d: { position: [number, number] }) => d.position,
        getText: () => '★',
        characterSet: ['★'],
        getColor: [255, 196, 87, 255],
        getSize: 26,
        sizeUnits: 'pixels',
        fontFamily: 'sans-serif',
        getTextAnchor: 'middle',
        getAlignmentBaseline: 'center',
        outlineWidth: 3,
        outlineColor: [120, 40, 0, 255],
        fontSettings: { sdf: true },
        billboard: true,
      }),
    );
  }

  // ---- 12. highlighted decision geometry (top) ----
  if (highlight?.geometry) {
    layers.push(
      new GeoJsonLayer({
        id: 'highlight',
        data: featureOf(highlight.geometry),
        stroked: true,
        filled: true,
        getFillColor: [76, 157, 255, 45],
        getLineColor: [140, 200, 255, 255],
        lineWidthUnits: 'pixels',
        getLineWidth: 3,
        lineWidthMinPixels: 2.5,
        pointType: 'circle',
        getPointRadius: 9,
        pointRadiusUnits: 'pixels',
        pointRadiusMinPixels: 8,
        pickable: false,
      }),
    );
  }

  return layers;
}

function emptyFC(): FeatureCollection {
  return { type: 'FeatureCollection', features: [] };
}
