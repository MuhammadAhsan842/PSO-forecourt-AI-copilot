import type { Summary } from "../types";

const Card = ({ label, value, hint }: { label: string; value: string; hint?: string }) => (
  <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
    <div className="text-xs uppercase tracking-wider text-slate-400">{label}</div>
    <div className="mt-1 text-2xl font-semibold text-slate-100">{value}</div>
    {hint && <div className="text-xs text-slate-500">{hint}</div>}
  </div>
);

export function StatCards({ summary }: { summary: Summary | null }) {
  if (!summary) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-2xl bg-slate-900/40" />
        ))}
      </div>
    );
  }
  const totalEvents = Object.values(summary.event_counts).reduce((a, b) => a + b, 0);
  const precision = summary.feedback.precision;
  const drive = summary.event_counts["drive_off"] ?? 0;
  const settled = summary.event_counts["vehicle_settled_at_pump"] ?? 0;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Card label="Events (last 24h)" value={String(totalEvents)} hint="all cameras" />
      <Card
        label="Precision"
        value={precision === null ? "—" : `${Math.round(precision * 100)}%`}
        hint={`${summary.feedback.true} true / ${summary.feedback.false} false`}
      />
      <Card label="Drive-off events" value={String(drive)} hint="unpaid amounts flagged" />
      <Card label="Vehicles at pumps" value={String(settled)} hint="capture triggers" />
    </div>
  );
}
