import type { EventKind } from "../types";

const KINDS: EventKind[] = [
  "after_hours_presence",
  "queue_dwell",
  "restricted_entry",
  "loitering",
  "vehicle_settled_at_pump",
  "drive_off",
  "sale_recorded",
  "camera_offline",
  "camera_online",
  "meter_optics_fail",
  "meter_fill_start",
  "meter_fill_t0",
  "meter_fill_stop",
  "meter_fill_final",
  "meter_needs_review",
  "meter_health",
  "meter_pos_mismatch",
  "meter_unbilled",
  "meter_no_vehicle",
];

interface Props {
  cameraIds: string[];
  camera: string;
  kind: EventKind | "all";
  onCamera: (v: string) => void;
  onKind: (v: EventKind | "all") => void;
}

export function EventFilters({ cameraIds, camera, kind, onCamera, onKind }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3">
      <label className="text-xs uppercase tracking-wider text-slate-400">Filter</label>
      <select
        value={camera}
        onChange={(e) => onCamera(e.target.value)}
        className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
      >
        <option value="all">all cameras</option>
        {cameraIds.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      <select
        value={kind}
        onChange={(e) => onKind(e.target.value as EventKind | "all")}
        className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
      >
        <option value="all">all kinds</option>
        {KINDS.map((k) => (
          <option key={k} value={k}>
            {k.replaceAll("_", " ")}
          </option>
        ))}
      </select>
    </div>
  );
}
