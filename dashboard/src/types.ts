export type EventKind =
  | "after_hours_presence"
  | "queue_dwell"
  | "restricted_entry"
  | "loitering"
  | "vehicle_settled_at_pump"
  | "drive_off"
  | "sale_recorded"
  | "camera_offline"
  | "camera_online"
  | "meter_optics_fail"
  | "meter_fill_start"
  | "meter_fill_t0"
  | "meter_fill_stop"
  | "meter_fill_final"
  | "meter_needs_review"
  | "meter_health"
  | "meter_pos_mismatch"
  | "meter_unbilled"
  | "meter_no_vehicle";

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

export interface MeterTick {
  ts: string;
  pump_id: string;
  camera_id: string;
  optics_pass: boolean;
  litres_raw: string;
  amount_raw: string;
  rate_raw: string;
  litres_est: number | null;
  rate_lps: number | null;
  confidence: number;
  confidence_tier: "high" | "medium" | "review" | string;
  provenance: "camera-observed" | "pos-confirmed" | "optics-blocked" | string;
  needs_review: boolean;
  source: string;
  state: string;
  fill_phase: string;
  flags?: string[];
  T0?: number | null;
  T_final?: number | null;
  amount?: number | null;
  camera_observed: boolean;
  billed: boolean;
}

export interface MeterHealth {
  schema_version: number;
  running: boolean;
  n_pumps: number;
  pumps: Array<{
    pump_id: string;
    label: string;
    nvr_channel: number;
    optics_pass: boolean | null;
    fill_phase: string;
    provenance: string | null;
    needs_review: boolean | null;
    supervisor_running: boolean;
    max_lpm: number | null;
  }>;
}

export interface MeterReading {
  id: string;
  camera_id: string;
  kind: string;
  value: string;
  confidence: number;
  ts: string;
  payload: Record<string, unknown>;
}
