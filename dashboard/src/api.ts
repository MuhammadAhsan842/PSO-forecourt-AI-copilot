import type { CameraStatus, EventKind, EventRecord, Summary, WsMessage } from "./types";

const RAW_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8080";
export const API_BASE = RAW_BASE.replace(/\/$/, "");
export const WS_BASE = API_BASE.replace(/^http/i, "ws");

export async function fetchEvents(params: {
  camera_id?: string;
  kind?: EventKind;
  limit?: number;
} = {}): Promise<EventRecord[]> {
  const q = new URLSearchParams();
  if (params.camera_id) q.set("camera_id", params.camera_id);
  if (params.kind) q.set("kind", params.kind);
  q.set("limit", String(params.limit ?? 100));
  const r = await fetch(`${API_BASE}/api/v1/events?${q.toString()}`);
  if (!r.ok) throw new Error(`GET /events ${r.status}`);
  return r.json();
}

export async function fetchSummary(days = 1): Promise<Summary> {
  const r = await fetch(`${API_BASE}/api/v1/stats/summary?days=${days}`);
  if (!r.ok) throw new Error(`GET /stats/summary ${r.status}`);
  return r.json();
}

export async function fetchCameraStatus(): Promise<CameraStatus[]> {
  const r = await fetch(`${API_BASE}/api/v1/stats/cameras`);
  if (!r.ok) throw new Error(`GET /stats/cameras ${r.status}`);
  return r.json();
}

export async function submitFeedback(eventId: string, verdict: "true" | "false", reviewer = "staff"): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: eventId, verdict, reviewer }),
  });
  if (!r.ok) throw new Error(`POST /feedback ${r.status}`);
}

export function snapshotUrl(rel: string | null): string | null {
  if (!rel) return null;
  return `${API_BASE}/snapshots/${rel}`;
}

export function openEventStream(onMessage: (msg: WsMessage) => void, onStatus: (open: boolean) => void): () => void {
  const url = `${WS_BASE}/ws/events`;
  let ws: WebSocket | null = null;
  let attempt = 0;
  let closed = false;

  const connect = () => {
    ws = new WebSocket(url);
    ws.onopen = () => {
      attempt = 0;
      onStatus(true);
    };
    ws.onmessage = (ev) => {
      try {
        onMessage(JSON.parse(ev.data) as WsMessage);
      } catch {
        // ignore malformed frame
      }
    };
    ws.onclose = () => {
      onStatus(false);
      if (!closed) setTimeout(connect, Math.min(1000 * 2 ** attempt++, 15000));
    };
    ws.onerror = () => ws?.close();
  };
  connect();
  return () => {
    closed = true;
    ws?.close();
  };
}
