// Color system for the COP map + panels.
// deck.gl expects RGBA arrays [0-255].

export type RGBA = [number, number, number, number];

// Burn-probability ramp: low = translucent yellow -> high = deep red/orange.
// Anchored at the band levels present in the data (0.1 .. 0.9).
const RAMP_STOPS: { p: number; rgb: [number, number, number] }[] = [
  { p: 0.0, rgb: [255, 245, 158] }, // pale yellow
  { p: 0.1, rgb: [255, 224, 102] },
  { p: 0.3, rgb: [255, 179, 51] }, // amber
  { p: 0.5, rgb: [247, 138, 31] }, // orange
  { p: 0.7, rgb: [232, 80, 31] }, // deep orange
  { p: 0.9, rgb: [186, 24, 27] }, // deep red
  { p: 1.0, rgb: [140, 10, 20] },
];

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function rampRGB(p: number): [number, number, number] {
  const x = Math.max(0, Math.min(1, p));
  for (let i = 1; i < RAMP_STOPS.length; i++) {
    const lo = RAMP_STOPS[i - 1];
    const hi = RAMP_STOPS[i];
    if (x <= hi.p) {
      const t = (x - lo.p) / (hi.p - lo.p || 1);
      return [
        Math.round(lerp(lo.rgb[0], hi.rgb[0], t)),
        Math.round(lerp(lo.rgb[1], hi.rgb[1], t)),
        Math.round(lerp(lo.rgb[2], hi.rgb[2], t)),
      ];
    }
  }
  return RAMP_STOPS[RAMP_STOPS.length - 1].rgb;
}

// Fill color for a probability band: hue from ramp, alpha rising with level.
export function bandFill(level: number): RGBA {
  const [r, g, b] = rampRGB(level);
  const alpha = Math.round(lerp(55, 205, Math.max(0, Math.min(1, level))));
  return [r, g, b, alpha];
}

// CSS string for the ramp (legend swatches).
export function rampCss(p: number, alpha = 1): string {
  const [r, g, b] = rampRGB(p);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Urgency -> semantic color (evac zones, road threat, decision bars).
export function urgencyRGB(urgency: number): [number, number, number] {
  if (urgency >= 0.66) return [229, 72, 77]; // red
  if (urgency >= 0.33) return [245, 166, 35]; // amber
  return [48, 164, 108]; // green
}

export function urgencyCss(urgency: number): string {
  const [r, g, b] = urgencyRGB(urgency);
  return `rgb(${r}, ${g}, ${b})`;
}

export function urgencyLabel(urgency: number): string {
  if (urgency >= 0.66) return 'HIGH';
  if (urgency >= 0.33) return 'MODERATE';
  return 'LOW';
}

// Observation kind -> color.
export const OBS_COLORS: Record<string, RGBA> = {
  goes: [255, 122, 89, 235], // GOES hotspots — warm red
  viirs: [255, 196, 61, 235], // VIIRS — amber-yellow
  modis: [255, 150, 120, 235], // MODIS
  camera_front: [77, 214, 232, 255], // cyan
  official_perimeter: [190, 130, 246, 255], // violet
};

export function obsColor(kind: string): RGBA {
  return OBS_COLORS[kind] ?? [150, 165, 185, 220];
}

export function obsLabel(kind: string): string {
  switch (kind) {
    case 'goes':
      return 'GOES hotspot';
    case 'viirs':
      return 'VIIRS hotspot';
    case 'modis':
      return 'MODIS hotspot';
    case 'camera_front':
      return 'Camera-derived front';
    case 'official_perimeter':
      return 'Official perimeter';
    default:
      return kind;
  }
}
