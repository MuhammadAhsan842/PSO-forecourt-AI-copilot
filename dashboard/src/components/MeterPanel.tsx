import { useEffect, useState } from "react";
import {
  fetchMeterHealth,
  fetchMeterLive,
  fetchMeterReadings,
  saveMeterRoi,
  simulateMeterFill,
} from "../api";
import type { MeterHealth, MeterReading, MeterTick } from "../types";

function badge(provenance: string, tier: string) {
  if (provenance === "pos-confirmed") return "bg-emerald-700/80 text-emerald-50";
  if (provenance === "optics-blocked" || tier === "review") return "bg-amber-800/80 text-amber-50";
  return "bg-sky-800/80 text-sky-50";
}

export function MeterPanel() {
  const [health, setHealth] = useState<MeterHealth | null>(null);
  const [tick, setTick] = useState<MeterTick | null>(null);
  const [readings, setReadings] = useState<MeterReading[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [roi, setRoi] = useState({ x: 1800, y: 700, w: 220, h: 110 });

  const refresh = async () => {
    try {
      const [h, live, rs] = await Promise.all([
        fetchMeterHealth(),
        fetchMeterLive().catch(() => ({ pumps: [] as MeterTick[] })),
        fetchMeterReadings(12),
      ]);
      setHealth(h);
      const pumps = "pumps" in live ? live.pumps : [live];
      setTick((prev) => pumps[0] ?? prev);
      setReadings(rs);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "meter API unreachable");
    }
  };

  useEffect(() => {
    void refresh();
    const iv = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(iv);
  }, []);

  const runSim = async () => {
    setBusy(true);
    try {
      const out = await simulateMeterFill();
      const last = out.ticks[out.ticks.length - 1] ?? null;
      await refresh();
      if (last) setTick(last);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "simulate failed");
    } finally {
      setBusy(false);
    }
  };

  const saveRoi = async () => {
    setBusy(true);
    try {
      await saveMeterRoi("m1", roi);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ROI save failed");
    } finally {
      setBusy(false);
    }
  };

  const pump = health?.pumps[0];
  const litres =
    tick?.fill_phase === "final" && tick.T_final != null
      ? tick.T_final.toFixed(2)
      : tick?.litres_est != null
        ? tick.litres_est.toFixed(2)
        : tick?.litres_raw || "—";

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-amber-400/90">Meter pipeline</div>
          <div className="text-lg font-semibold text-white">
            {pump?.label || "M1 / Pump 1"} · camera-observed
          </div>
        </div>
        <button
          type="button"
          onClick={() => void runSim()}
          disabled={busy}
          className="rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-900 hover:bg-white disabled:opacity-50"
        >
          {busy ? "Running…" : "Simulate fill"}
        </button>
      </div>

      {err && <div className="mb-3 text-sm text-amber-300">{err}</div>}

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
          <div className="text-xs uppercase tracking-wider text-slate-500">Litres</div>
          <div className="mt-1 font-mono text-4xl text-white">{litres}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className={`rounded-md px-2 py-0.5 text-xs ${badge(tick?.provenance || "optics-blocked", tick?.confidence_tier || "review")}`}>
              {tick?.provenance || "no live tick"}
            </span>
            <span className="rounded-md border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
              {tick?.confidence_tier || "review"} · {(tick?.confidence ?? 0).toFixed(2)}
            </span>
            <span className="rounded-md border border-red-900/60 px-2 py-0.5 text-xs text-red-300">
              not billed
            </span>
          </div>
          <div className="mt-3 text-xs text-slate-500">
            raw {tick?.litres_raw || "—"} · T0 {tick?.T0 ?? "—"} · T_final {tick?.T_final ?? "—"} ·
            amount {tick?.amount ?? "—"} (T_final − T0) · {tick?.fill_phase || "idle"}
            {tick?.flags && tick.flags.length > 0 ? ` · flags ${tick.flags.join(", ")}` : ""}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-300">
          <div className="text-xs uppercase tracking-wider text-slate-500">Optics / health</div>
          <div className="mt-2">
            pixel gate:{" "}
            <span className={tick?.optics_pass || pump?.optics_pass ? "text-emerald-400" : "text-amber-400"}>
              {tick?.optics_pass || pump?.optics_pass ? "PASS" : "FAIL / unknown"}
            </span>
          </div>
          <div>max L/min: {pump?.max_lpm ?? "unset (not invented)"}</div>
          <div>needs review: {String(tick?.needs_review ?? pump?.needs_review ?? true)}</div>
          <div className="mt-2 text-xs text-slate-500">
            Ch9 idle crop is ~220×110. A FAIL gate never becomes a billed number.
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
          <div className="text-xs uppercase tracking-wider text-slate-500">ROI calibration (M1)</div>
          <div className="mt-2 grid grid-cols-4 gap-1 text-xs">
            {(["x", "y", "w", "h"] as const).map((k) => (
              <label key={k} className="text-slate-400">
                {k}
                <input
                  type="number"
                  value={roi[k]}
                  onChange={(e) => setRoi({ ...roi, [k]: Number(e.target.value) })}
                  className="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1 py-1 text-slate-100"
                />
              </label>
            ))}
          </div>
          <button
            type="button"
            onClick={() => void saveRoi()}
            disabled={busy}
            className="mt-2 w-full rounded-md border border-slate-600 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            Save ROI vN
          </button>
        </div>
      </div>

      {readings.length > 0 && (
        <div className="mt-4 overflow-x-auto text-xs text-slate-400">
          <div className="mb-1 uppercase tracking-wider text-slate-500">Stored readings</div>
          <table className="w-full text-left">
            <thead>
              <tr className="text-slate-500">
                <th className="py-1 pr-3">time</th>
                <th className="py-1 pr-3">value</th>
                <th className="py-1 pr-3">conf</th>
                <th className="py-1">provenance</th>
              </tr>
            </thead>
            <tbody>
              {readings.map((r) => (
                <tr key={r.id} className="border-t border-slate-800">
                  <td className="py-1 pr-3">{new Date(r.ts).toLocaleTimeString()}</td>
                  <td className="py-1 pr-3 font-mono text-slate-200">{r.value || "—"}</td>
                  <td className="py-1 pr-3">{r.confidence.toFixed(2)}</td>
                  <td className="py-1">{String(r.payload.provenance ?? "camera-observed")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
