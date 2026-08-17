import clsx from "clsx";
import type { CameraStatus } from "../types";

export function CameraHealthBar({ cameras }: { cameras: CameraStatus[] }) {
  if (!cameras.length) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-sm text-slate-500">
        No camera health reports yet.
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-slate-800 bg-slate-900/60 p-3">
      {cameras.map((c) => (
        <div
          key={c.camera_id}
          className={clsx(
            "flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs",
            c.online
              ? "border-emerald-700/50 bg-emerald-950/40 text-emerald-300"
              : "border-red-700/50 bg-red-950/40 text-red-300"
          )}
          title={c.last_error ?? c.last_seen}
        >
          <span
            className={clsx(
              "inline-block h-2 w-2 rounded-full",
              c.online ? "bg-emerald-400" : "bg-red-400"
            )}
          />
          <span className="font-medium">{c.camera_id}</span>
          <span className="text-slate-500">·</span>
          <span>{c.online ? "online" : "offline"}</span>
        </div>
      ))}
    </div>
  );
}
