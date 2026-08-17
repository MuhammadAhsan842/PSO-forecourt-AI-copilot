import type { EventRecord } from "../types";

export function LiveAlertToast({ event }: { event: EventRecord | null }) {
  if (!event) return null;
  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-50 max-w-sm rounded-xl border border-amber-500 bg-amber-950/90 px-4 py-3 text-sm shadow-2xl">
      <div className="text-xs uppercase tracking-wider text-amber-300">New alert</div>
      <div className="mt-1 font-medium">{event.kind.replaceAll("_", " ")}</div>
      <div className="text-xs text-slate-300">
        camera {event.camera_id}
        {event.zone_id ? ` · zone ${event.zone_id}` : ""}
      </div>
    </div>
  );
}
