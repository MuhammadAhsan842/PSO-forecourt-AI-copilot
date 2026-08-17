import { snapshotUrl, submitFeedback } from "../api";
import type { EventRecord } from "../types";

interface Props {
  events: EventRecord[];
  onFeedbackDone: (id: string) => void;
}

const KIND_COLORS: Record<string, string> = {
  drive_off: "bg-red-950/50 border-red-800 text-red-200",
  restricted_entry: "bg-amber-950/50 border-amber-800 text-amber-200",
  after_hours_presence: "bg-purple-950/50 border-purple-800 text-purple-200",
  queue_dwell: "bg-sky-950/50 border-sky-800 text-sky-200",
  loitering: "bg-orange-950/50 border-orange-800 text-orange-200",
  vehicle_settled_at_pump: "bg-emerald-950/50 border-emerald-800 text-emerald-200",
  sale_recorded: "bg-emerald-950/50 border-emerald-800 text-emerald-200",
  camera_offline: "bg-slate-800/60 border-slate-600 text-slate-200",
  camera_online: "bg-slate-800/60 border-slate-600 text-slate-300",
};

function tag(kind: string) {
  return KIND_COLORS[kind] ?? "bg-slate-800/50 border-slate-700 text-slate-200";
}

export function EventLog({ events, onFeedbackDone }: Props) {
  if (events.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-12 text-center text-slate-500">
        No events yet. When alerts fire they will appear here in real time.
      </div>
    );
  }
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {events.map((e) => (
        <EventCard key={e.id} ev={e} onFeedback={onFeedbackDone} />
      ))}
    </div>
  );
}

function EventCard({ ev, onFeedback }: { ev: EventRecord; onFeedback: (id: string) => void }) {
  const snap = snapshotUrl(ev.snapshot_path);
  const kindTag = tag(ev.kind);
  const send = async (verdict: "true" | "false") => {
    try {
      await submitFeedback(ev.id, verdict);
      onFeedback(ev.id);
    } catch {
      // Fail silently in the UI; the card stays so the reviewer can retry.
    }
  };
  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">
      <div className="aspect-video w-full bg-slate-950">
        {snap ? (
          <img src={snap} alt={ev.kind} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-xs text-slate-500">
            no snapshot
          </div>
        )}
      </div>
      <div className="flex flex-col gap-2 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-block rounded-md border px-2 py-0.5 text-xs ${kindTag}`}>
            {ev.kind.replaceAll("_", " ")}
          </span>
          <span className="text-xs text-slate-400">{ev.camera_id}</span>
          {ev.zone_id && <span className="text-xs text-slate-500">· {ev.zone_id}</span>}
          <span className="ml-auto text-xs text-slate-500">
            {new Date(ev.ts).toLocaleTimeString()}
          </span>
        </div>
        {Object.keys(ev.payload || {}).length > 0 && (
          <div className="text-xs text-slate-400">
            {Object.entries(ev.payload).map(([k, v]) => (
              <span key={k} className="mr-2">
                <span className="text-slate-500">{k}:</span> {String(v)}
              </span>
            ))}
          </div>
        )}
        <div className="mt-1 flex gap-2">
          <button
            onClick={() => send("true")}
            className="flex-1 rounded-md bg-emerald-700/70 py-1.5 text-sm hover:bg-emerald-600"
          >
            True
          </button>
          <button
            onClick={() => send("false")}
            className="flex-1 rounded-md bg-red-700/70 py-1.5 text-sm hover:bg-red-600"
          >
            False
          </button>
        </div>
      </div>
    </div>
  );
}
