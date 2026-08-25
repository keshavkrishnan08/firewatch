// Geometry helpers: bbox fitting, geometry bounds, camera view cones.

import { WebMercatorViewport } from '@deck.gl/core';
import type { Geometry, Position } from 'geojson';

export interface ViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch: number;
  bearing: number;
}

export type Bounds = [[number, number], [number, number]]; // [[minLng,minLat],[maxLng,maxLat]]

export function viewStateForBounds(
  bounds: Bounds,
  width: number,
  height: number,
  padding = 60,
): ViewState {
  const safeW = Math.max(1, width);
  const safeH = Math.max(1, height);
  try {
    const vp = new WebMercatorViewport({ width: safeW, height: safeH });
    const { longitude, latitude, zoom } = vp.fitBounds(bounds, { padding });
    return { longitude, latitude, zoom: Math.min(zoom, 15), pitch: 0, bearing: 0 };
  } catch {
    const longitude = (bounds[0][0] + bounds[1][0]) / 2;
    const latitude = (bounds[0][1] + bounds[1][1]) / 2;
    return { longitude, latitude, zoom: 11, pitch: 0, bearing: 0 };
  }
}

export function bboxToBounds(bbox: [number, number, number, number]): Bounds {
  return [
    [bbox[0], bbox[1]],
    [bbox[2], bbox[3]],
  ];
}

// Walk any GeoJSON geometry and accumulate lng/lat bounds.
export function geometryBounds(geom: Geometry | null | undefined): Bounds | null {
  if (!geom) return null;
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;

  const visit = (pos: Position) => {
    const [lng, lat] = pos;
    if (typeof lng !== 'number' || typeof lat !== 'number') return;
    if (lng < minLng) minLng = lng;
    if (lat < minLat) minLat = lat;
    if (lng > maxLng) maxLng = lng;
    if (lat > maxLat) maxLat = lat;
  };

  const walk = (coords: unknown) => {
    if (!Array.isArray(coords)) return;
    if (typeof coords[0] === 'number') {
      visit(coords as Position);
    } else {
      for (const c of coords) walk(c);
    }
  };

  if (geom.type === 'GeometryCollection') {
    for (const g of geom.geometries) {
      const b = geometryBounds(g);
      if (b) {
        minLng = Math.min(minLng, b[0][0]);
        minLat = Math.min(minLat, b[0][1]);
        maxLng = Math.max(maxLng, b[1][0]);
        maxLat = Math.max(maxLat, b[1][1]);
      }
    }
  } else {
    walk((geom as { coordinates: unknown }).coordinates);
  }

  if (!Number.isFinite(minLng) || !Number.isFinite(minLat)) return null;
  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ];
}

// Pad bounds by a fraction so a flown-to feature isn't edge-to-edge.
export function padBounds(bounds: Bounds, frac = 0.35): Bounds {
  const dLng = (bounds[1][0] - bounds[0][0]) * frac || 0.005;
  const dLat = (bounds[1][1] - bounds[0][1]) * frac || 0.005;
  return [
    [bounds[0][0] - dLng, bounds[0][1] - dLat],
    [bounds[1][0] + dLng, bounds[1][1] + dLat],
  ];
}

// Build a wedge polygon (ring of [lng,lat]) representing a camera's field of view.
// pan is a compass bearing (0 = N, clockwise), fov the angular width in degrees.
export function viewConePolygon(
  center: [number, number],
  panDeg: number,
  fovDeg: number,
  rangeKm = 2.2,
  steps = 18,
): Position[] {
  const [lng, lat] = center;
  const latRad = (lat * Math.PI) / 180;
  const kmPerDegLat = 110.574;
  const kmPerDegLng = 111.32 * Math.cos(latRad);

  const ring: Position[] = [[lng, lat]];
  const half = fovDeg / 2;
  for (let i = 0; i <= steps; i++) {
    const bearing = panDeg - half + (fovDeg * i) / steps;
    const rad = (bearing * Math.PI) / 180;
    const dEast = (Math.sin(rad) * rangeKm) / kmPerDegLng;
    const dNorth = (Math.cos(rad) * rangeKm) / kmPerDegLat;
    ring.push([lng + dEast, lat + dNorth]);
  }
  ring.push([lng, lat]);
  return ring;
}

// Endpoint of a short direction indicator (for the camera pan tick).
export function bearingEndpoint(
  center: [number, number],
  bearingDeg: number,
  rangeKm: number,
): [number, number] {
  const [lng, lat] = center;
  const latRad = (lat * Math.PI) / 180;
  const kmPerDegLat = 110.574;
  const kmPerDegLng = 111.32 * Math.cos(latRad);
  const rad = (bearingDeg * Math.PI) / 180;
  return [lng + (Math.sin(rad) * rangeKm) / kmPerDegLng, lat + (Math.cos(rad) * rangeKm) / kmPerDegLat];
}
