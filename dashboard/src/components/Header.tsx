import clsx from "clsx";

export function Header({ live }: { live: boolean }) {
  return (
    <header className="flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/70 px-6 py-4">
      <div>
        <div className="text-lg font-semibold tracking-tight">PSO Forecourt AI Surveillance</div>
        <div className="text-xs text-slate-400">Pilot dashboard · 295-A Airlines Society, Lahore</div>
      </div>
      <div className="flex items-center gap-2 text-sm">
        <span
          className={clsx(
            "inline-block h-2.5 w-2.5 rounded-full",
            live ? "bg-emerald-500 shadow-[0_0_10px_rgba(52,211,153,0.7)]" : "bg-slate-500"
          )}
        />
        <span className={clsx("font-medium", live ? "text-emerald-400" : "text-slate-400")}>
          {live ? "Live" : "Reconnecting…"}
        </span>
      </div>
    </header>
  );
}
