export type EventKind =
  | "after_hours_presence"
  | "queue_dwell"
  | "restricted_entry"
  | "loitering"
  | "vehicle_settled_at_pump"
  | "drive_off"
  | "sale_recorded"
  | "camera_offline"
  | "camera_online";

export interface EventRecord {
  id: string;
  kind: EventKind;
  camera_id: string;
  track_id: number | null;
  zone_id: string | null;
  confidence: number;
  snapshot_path: string | null;
  ts: string;
  payload: Record<string, string | number | boolean | null>;
}

export interface Summary {
  since: string;
  event_counts: Record<string, number>;
  feedback: { true: number; false: number; precision: number | null };
}

export interface CameraStatus {
  camera_id: string;
  online: boolean;
  last_seen: string;
  last_error: string | null;
}

export interface WsMessage {
  type: "event" | "hello";
  data: EventRecord | { clients: number };
}
