import { useEffect, useState } from "react";
import { fetchMeterReview } from "../api";
import type { EventRecord } from "../types";
import { EventLog } from "./EventLog";

export function FlagQueue() {
  const [items, setItems] = useState<EventRecord[]>([]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const rows = await fetchMeterReview(24);
        if (alive) setItems(rows);
      } catch {
        // API down
      }
    };
    void load();
    const iv = window.setInterval(() => void load(), 8000);
    return () => {
      alive = false;
      window.clearInterval(iv);
    };
  }, []);

  return (
    <section className="rounded-2xl border border-amber-900/40 bg-slate-900/60 p-4">
      <div className="mb-3">
        <div className="text-[11px] uppercase tracking-[0.2em] text-amber-400/90">Flag review</div>
        <div className="text-sm text-slate-300">
          Low-confidence, mismatch, unbilled, and health flags — confirm or reject. Never billed.
        </div>
      </div>
      {items.length === 0 ? (
        <div className="text-sm text-slate-500">No flagged meter events in the queue.</div>
      ) : (
        <EventLog events={items} onFeedbackDone={(id) => setItems((p) => p.filter((e) => e.id !== id))} />
      )}
    </section>
  );
}
