import type {
  CameraStatus,
  EventKind,
  EventRecord,
  MeterHealth,
  MeterReading,
  MeterTick,
  Summary,
  WsMessage,
} from "./types";

function defaultApiBase(): string {
  const fromEnv = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  // Match the page hostname so 127.0.0.1:5173 talks to 127.0.0.1:8080, not
  // localhost (which often resolves to IPv6 ::1 while uvicorn is IPv4-only).
  if (typeof window !== "undefined") {
    return `http://${window.location.hostname}:8080`;
  }
  return "http://127.0.0.1:8080";
}

export const API_BASE = defaultApiBase();
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

export interface NvrChannel {
  channel: number;
  live: boolean;
  resolution: string | null;
  still: string | null;
  label: string | null;
}

export interface NvrManifest {
  host: string;
  scanned_at: string;
  subtype: number;
  channels: NvrChannel[];
}

export async function fetchNvrChannels(): Promise<NvrManifest> {
  const r = await fetch(`${API_BASE}/api/v1/nvr/channels`);
  if (!r.ok) throw new Error(`GET /nvr/channels ${r.status}`);
  return r.json();
}

export function nvrStillUrl(fileName: string): string {
  return `${API_BASE}/nvr-stills/${fileName}`;
}

export async function fetchMeterHealth(): Promise<MeterHealth> {
  const r = await fetch(`${API_BASE}/api/v1/meter/health`);
  if (!r.ok) throw new Error(`GET /meter/health ${r.status}`);
  return r.json();
}

export async function fetchMeterLive(): Promise<{ pumps: MeterTick[] } | MeterTick> {
  const r = await fetch(`${API_BASE}/api/v1/meter/live`);
  if (!r.ok) throw new Error(`GET /meter/live ${r.status}`);
  return r.json();
}

export async function fetchMeterReadings(limit = 20): Promise<MeterReading[]> {
  const r = await fetch(`${API_BASE}/api/v1/meter/readings?limit=${limit}`);
  if (!r.ok) throw new Error(`GET /meter/readings ${r.status}`);
  return r.json();
}

export async function fetchMeterReview(limit = 40): Promise<EventRecord[]> {
  const r = await fetch(`${API_BASE}/api/v1/meter/review?limit=${limit}`);
  if (!r.ok) throw new Error(`GET /meter/review ${r.status}`);
  return r.json();
}

export async function simulateMeterFill(): Promise<{ ticks: MeterTick[]; events: EventRecord[] }> {
  const r = await fetch(`${API_BASE}/api/v1/meter/simulate-fill`, { method: "POST" });
  if (!r.ok) throw new Error(`POST /meter/simulate-fill ${r.status}`);
  return r.json();
}

export async function saveMeterRoi(
  pumpId: string,
  box: { x: number; y: number; w: number; h: number }
): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/meter/roi/${pumpId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(box),
  });
  if (!r.ok) throw new Error(`PUT /meter/roi ${r.status}`);
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
