// Formatting helpers.

export function parseTime(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

// Compact UTC clock, e.g. "19:30Z"
export function fmtClock(iso: string | null | undefined): string {
  const t = parseTime(iso);
  if (t == null) return '—';
  const d = new Date(t);
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${hh}:${mm}Z`;
}

export function fmtClockFromMs(ms: number): string {
  const d = new Date(ms);
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${hh}:${mm}Z`;
}

// Date + time, e.g. "20 Aug 19:30Z"
export function fmtDateTime(iso: string | null | undefined): string {
  const t = parseTime(iso);
  if (t == null) return '—';
  const d = new Date(t);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${d.getUTCDate()} ${months[d.getUTCMonth()]} ${fmtClock(iso)}`;
}

export function fmtPct(x: number | null | undefined, digits = 0): string {
  if (x == null || Number.isNaN(x)) return '—';
  return `${(x * 100).toFixed(digits)}%`;
}

export function fmtMinutes(m: number | null | undefined): string {
  if (m == null || Number.isNaN(m)) return '—';
  const r = Math.round(m);
  return `${r >= 0 ? '' : ''}${r} min`;
}

// Lead-time band, e.g. "44 min (3–114)". Negative = fire already past that point.
export function fmtLeadBand(d: {
  lead_time_min: number | null;
  lead_time_low_min: number | null;
  lead_time_high_min: number | null;
}): string {
  if (d.lead_time_min == null) return 'no ETA';
  const mid = Math.round(d.lead_time_min);
  const lo = d.lead_time_low_min == null ? null : Math.round(d.lead_time_low_min);
  const hi = d.lead_time_high_min == null ? null : Math.round(d.lead_time_high_min);
  const base = mid < 0 ? `${mid} min (past)` : `${mid} min`;
  if (lo == null || hi == null) return base;
  return `${base}  ·  80% band ${lo}–${hi}`;
}

export function fmtNumber(x: number | null | undefined, digits = 0): string {
  if (x == null || Number.isNaN(x)) return '—';
  return x.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function fmtArea(km2: number | null | undefined): string {
  if (km2 == null || Number.isNaN(km2)) return '—';
  return `${km2.toFixed(2)} km²`;
}

// Compass label from a bearing (degrees, 0 = N, clockwise).
export function bearingToCompass(deg: number): string {
  const dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  const idx = Math.round(((deg % 360) + 360) % 360 / 22.5) % 16;
  return dirs[idx];
}

// m/s -> km/h and mph, formatted.
export function fmtWindSpeed(ms: number): string {
  const kmh = ms * 3.6;
  return `${ms.toFixed(1)} m/s · ${kmh.toFixed(0)} km/h`;
}
