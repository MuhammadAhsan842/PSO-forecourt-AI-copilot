import { useEffect, useState } from "react";
import clsx from "clsx";
import { API_BASE, fetchNvrChannels, nvrStillUrl, type NvrChannel, type NvrManifest } from "../api";
import { LiveZoom } from "./LiveZoom";

const METER_CHANNELS = new Set([9]);

function snapshotUrl(ch: number, extra = "") {
  const sep = extra.includes("?") ? extra : extra ? `?${extra}` : "";
  return `${API_BASE}/api/v1/nvr/snapshot/${ch}.jpg${sep}`;
}

export function NvrGrid() {
  const [manifest, setManifest] = useState<NvrManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<NvrChannel | null>(null);
  const [liveMode, setLiveMode] = useState(false);
  const [liveChannels, setLiveChannels] = useState<Set<number>>(new Set());
  const [meterOpen, setMeterOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchNvrChannels()
      .then((m) => alive && setManifest(m))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  if (error) {
    return (
      <section className="rounded-2xl border border-amber-800/40 bg-amber-950/20 p-4 text-sm text-amber-200">
        <div className="font-semibold">No NVR scan available</div>
        <div className="mt-1 text-amber-300/80">
          Run <code className="rounded bg-black/40 px-1.5 py-0.5">python -m scripts.nvr_scan</code> then refresh.
        </div>
      </section>
    );
  }

  if (!manifest) {
    return (
      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-500">
        Loading NVR scan…
      </section>
    );
  }

  const live = manifest.channels.filter((c) => c.live);
  const scannedAt = new Date(manifest.scanned_at).toLocaleString();

  const toggleLive = (ch: number) => {
    setLiveChannels((prev) => {
      const next = new Set(prev);
      if (next.has(ch)) next.delete(ch);
      else next.add(ch);
      return next;
    });
  };

  const toggleAll = () => {
    const next = !liveMode;
    setLiveMode(next);
    setLiveChannels(next ? new Set(live.map((c) => c.channel)) : new Set());
  };

  const openMeter = (c: NvrChannel) => {
    setSelected(c);
    setMeterOpen(true);
    setLiveChannels((prev) => new Set(prev).add(c.channel));
  };

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <header className="mb-3 flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">NVR Cameras</h2>
          <div className="text-xs text-slate-500">
            {manifest.host} · {live.length}/{manifest.channels.length} channels live · scanned {scannedAt}
          </div>
        </div>
        <button
          onClick={toggleAll}
          className={clsx(
            "rounded-md border px-3 py-1.5 text-xs font-medium transition",
            liveMode
              ? "border-red-500/60 bg-red-600/20 text-red-200 hover:bg-red-600/30"
              : "border-emerald-600/60 bg-emerald-600/20 text-emerald-200 hover:bg-emerald-600/30"
          )}
        >
          {liveMode ? "◼ Stop all live" : "▶ Live all"}
        </button>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {live.map((c) => {
          const isLive = liveChannels.has(c.channel);
          const hasMeter = METER_CHANNELS.has(c.channel);
          return (
            <div
              key={c.channel}
              className={clsx(
                "group relative overflow-hidden rounded-lg border border-slate-800 bg-black text-left transition hover:border-sky-600/70",
                hasMeter && "ring-1 ring-emerald-600/50"
              )}
            >
              <button type="button" onClick={() => setSelected(c)} className="block w-full">
                {isLive ? (
                  <LiveZoom channel={c.channel} className="aspect-video w-full object-cover" />
                ) : c.still ? (
                  <img
                    src={nvrStillUrl(c.still)}
                    alt={`Channel ${c.channel}`}
                    className="aspect-video w-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="flex aspect-video w-full items-center justify-center text-xs text-slate-500">no still</div>
                )}
              </button>
              <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/85 to-transparent px-2 py-1.5 text-xs">
                <span className="font-mono text-slate-200">ch {String(c.channel).padStart(2, "0")}</span>
                <span className="text-slate-400">{c.resolution ?? "-"}</span>
              </div>
              {c.label && (
                <div className="pointer-events-none absolute left-1 top-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
                  {c.label}
                </div>
              )}
              <div className="absolute right-1 top-1 flex flex-col items-end gap-1">
                {hasMeter && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      openMeter(c);
                    }}
                    className="rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold text-black hover:bg-amber-400"
                  >
                    🔍 Meter
                  </button>
                )}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleLive(c.channel);
                  }}
                  className={clsx(
                    "rounded px-1.5 py-0.5 text-[10px] font-semibold transition",
                    isLive
                      ? "bg-red-600/80 text-white hover:bg-red-500"
                      : "bg-emerald-600/80 text-white hover:bg-emerald-500"
                  )}
                >
                  {isLive ? "● LIVE" : "▶ Live"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {selected && (
        <div
          onClick={() => {
            setSelected(null);
            setMeterOpen(false);
          }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
        >
          <div className="max-h-full w-full max-w-6xl" onClick={(e) => e.stopPropagation()}>
            {meterOpen && METER_CHANNELS.has(selected.channel) ? (
              <div className="flex flex-col gap-3">
                <div>
                  <div className="mb-1 flex items-center justify-between text-xs uppercase tracking-wide">
                    <span className="text-amber-300">M1 HQ live — 4K NVR still + Lanczos zoom + denoise</span>
                    <span className="text-slate-500">fixed camera · digital zoom of 4K stream</span>
                  </div>
                  <LiveZoom
                    channel={selected.channel}
                    meter
                    className="max-h-[70vh] w-full rounded-lg"
                  />
                </div>
                <div className="max-w-sm">
                  <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">Context (full island)</div>
                  <LiveZoom channel={selected.channel} className="w-full rounded-lg" />
                </div>
              </div>
            ) : liveChannels.has(selected.channel) ? (
              <LiveZoom
                channel={selected.channel}
                className="max-h-[85vh] w-auto rounded-lg"
              />
            ) : (
              <img
                src={
                  liveChannels.has(selected.channel)
                    ? `${snapshotUrl(selected.channel, "?subtype=1")}&t=${Date.now()}`
                    : selected.still
                    ? nvrStillUrl(selected.still)
                    : ""
                }
                alt={`Channel ${selected.channel}`}
                className="max-h-[85vh] w-auto rounded-lg"
              />
            )}
            <div className="mt-2 flex items-center justify-between text-sm text-slate-200">
              <div>
                <span className="font-mono">ch {String(selected.channel).padStart(2, "0")}</span>
                {selected.label && <span className="ml-2 text-emerald-300">{selected.label}</span>}
              </div>
              <div className="flex items-center gap-3 text-slate-400">
                {METER_CHANNELS.has(selected.channel) && (
                  <button
                    onClick={() => setMeterOpen((v) => !v)}
                    className="rounded bg-amber-500 px-2 py-1 text-xs font-semibold text-black hover:bg-amber-400"
                  >
                    {meterOpen ? "Hide meter zoom" : "🔍 Meter zoom"}
                  </button>
                )}
                <button
                  onClick={() => toggleLive(selected.channel)}
                  className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700"
                >
                  {liveChannels.has(selected.channel) ? "Stop live" : "Go live"}
                </button>
                <span>{selected.resolution} · click background to close</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
