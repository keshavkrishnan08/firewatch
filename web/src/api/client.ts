// API client for the FIREWATCH COP backend.
// API base defaults to same-origin (''); dev server proxies /api and /outputs to :8000.

import type { Cop, NLQueryResponse } from './types';

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? '';
export const DEFAULT_EVENT_ID: string = import.meta.env.VITE_EVENT_ID ?? 'demo';

export async function fetchCop(eventId: string, signal?: AbortSignal): Promise<Cop> {
  const res = await fetch(`${API_BASE}/api/event/${encodeURIComponent(eventId)}/cop`, { signal });
  if (!res.ok) {
    throw new Error(`Failed to load COP for "${eventId}" (HTTP ${res.status})`);
  }
  return (await res.json()) as Cop;
}

export async function queryNL(eventId: string, q: string, signal?: AbortSignal): Promise<NLQueryResponse> {
  const url = `${API_BASE}/api/event/${encodeURIComponent(eventId)}/query?q=${encodeURIComponent(q)}`;
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`Query failed (HTTP ${res.status})`);
  }
  return (await res.json()) as NLQueryResponse;
}

// Camera frame images live at ${API}/outputs/${eventId}/${frame}
export function frameUrl(eventId: string, frame: string): string {
  return `${API_BASE}/outputs/${encodeURIComponent(eventId)}/${frame}`;
}
