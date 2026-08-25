// Type definitions for the FIREWATCH Common Operating Picture (COP) document.
// Mirrors the JSON returned by GET /api/event/:id/cop.

import type {
  FeatureCollection,
  Feature,
  Geometry,
  Polygon,
  MultiPolygon,
  Point,
  LineString,
} from 'geojson';

export type PolyGeom = Polygon | MultiPolygon;

export interface Wind {
  speed_ms: number;
  dir_to_deg: number;
  rh_pct: number;
  temp_c: number;
  source: string;
}

export interface FireMeta {
  id: string;
  name: string;
  status: string;
  ignition: [number, number]; // [lon, lat]
  discovered_at: string;
}

export interface Meta {
  event_id: string;
  fire: FireMeta;
  issued_at: string;
  ignition_time: string;
  horizons: number[];
  assimilation: boolean;
  wind: Wind;
  bbox: [number, number, number, number]; // [minlon, minlat, maxlon, maxlat]
  note: string;
}

export interface Band {
  level: number;
  geometry: PolyGeom;
}

export interface HorizonForecast {
  expected: PolyGeom | null;
  region90: PolyGeom | null;
  bands: Band[];
  region90_area_km2: number | null;
}

export type Arm = 'on' | 'off';

// Keyed by horizon-as-string, e.g. "15", "30", "60", "180".
export type ForecastArm = Record<string, HorizonForecast>;

export interface Forecast {
  on: ForecastArm;
  off: ForecastArm;
}

export interface Decision {
  id: string;
  kind: string; // evacuate | close_road | stage
  target: string;
  target_name: string;
  lead_time_min: number | null;
  lead_time_low_min: number | null;
  lead_time_high_min: number | null;
  confidence: number;
  urgency: number;
  rationale: string;
  evidence: string[];
  geometry: Geometry;
}

export interface RiskZone {
  zone_id: string;
  name: string;
  population: number;
  prob_burned: Record<string, number>;
  expected_people_exposed: Record<string, number>;
}

export interface Risk {
  issued_at: string;
  assimilation: boolean;
  aggregate_expected_people: Record<string, number>;
  zones: RiskZone[];
}

export interface StructureStat {
  expected: number;
  high_conf: number;
  n_total: number;
}

export interface Decisions {
  evacuations: Decision[];
  egress: Decision[];
  staging: Decision[];
  risk: Risk;
  structures: Record<string, StructureStat>;
}

export interface SkillMetrics {
  iou: number;
  dice: number;
  brier: number;
  coverage_90: number;
  region90_area_km2: number;
}

export interface Ablation {
  iou_on: number;
  iou_off: number;
  dice_on: number;
  dice_off: number;
}

export interface Evaluation {
  skill_on?: Record<string, SkillMetrics>;
  skill_off?: Record<string, SkillMetrics>;
  ablation?: Record<string, Ablation>;
}

export interface Layers {
  cameras: FeatureCollection;
  zones: FeatureCollection;
  roads: FeatureCollection;
  structures: FeatureCollection;
  observations: FeatureCollection;
}

export interface Cop {
  meta: Meta;
  layers: Layers;
  forecast: Forecast;
  decisions: Decisions;
  evaluation?: Evaluation;
}

// Per-feature property shapes (properties are `any` in GeoJSON typings).
export interface CameraProps {
  id: string;
  name: string;
  pan: number;
  tilt: number;
  fov: number;
  network: string;
  frame: string;
}

export interface ZoneProps {
  id: string;
  name: string;
  population: number;
  evac_status: string;
}

export interface RoadProps {
  id: string;
  name: string;
  highway: string;
}

export interface StructureProps {
  id: string;
  type: string;
  pop: number;
}

export interface ObsProps {
  id: string;
  kind: string; // goes | viirs | modis | camera_front | official_perimeter
  t: string;
  source: string;
}

export type CameraFeature = Feature<Point, CameraProps>;
export type ObsFeature = Feature<Geometry, ObsProps>;
export type RoadFeature = Feature<LineString, RoadProps>;

export interface NLQueryResponse {
  answer?: string;
  cited?: string[];
  citations?: string[];
  ids?: string[];
  [k: string]: unknown;
}
