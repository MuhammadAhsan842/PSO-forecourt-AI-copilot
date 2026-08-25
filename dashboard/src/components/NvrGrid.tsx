import { useEffect, useState } from "react";
import clsx from "clsx";
import { fetchNvrChannels, nvrStillUrl, type NvrChannel, type NvrManifest } from "../api";

export function NvrGrid() {
  const [manifest, setManifest] = useState<NvrManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<NvrChannel | null>(null);

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

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <header className="mb-3 flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">NVR Cameras</h2>
          <div className="text-xs text-slate-500">
            {manifest.host} · {live.length}/{manifest.channels.length} channels live · scanned {scannedAt}
          </div>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {live.map((c) => (
          <button
            key={c.channel}
            onClick={() => setSelected(c)}
            className={clsx(
              "group relative overflow-hidden rounded-lg border border-slate-800 bg-black text-left transition hover:border-sky-600/70",
              c.channel === 10 && "ring-1 ring-amber-600/40"
            )}
          >
            {c.still ? (
              <img
                src={nvrStillUrl(c.still)}
                alt={`Channel ${c.channel}`}
                className="aspect-video w-full object-cover"
                loading="lazy"
              />
            ) : (
              <div className="flex aspect-video w-full items-center justify-center text-xs text-slate-500">no still</div>
            )}
            <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/85 to-transparent px-2 py-1.5 text-xs">
              <span className="font-mono text-slate-200">ch {String(c.channel).padStart(2, "0")}</span>
              <span className="text-slate-400">{c.resolution ?? "-"}</span>
            </div>
            {c.label && (
              <div className="pointer-events-none absolute left-1 top-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
                {c.label}
              </div>
            )}
          </button>
        ))}
      </div>

      {selected && (
        <div
          onClick={() => setSelected(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
        >
          <div className="max-h-full max-w-6xl">
            <img
              src={selected.still ? nvrStillUrl(selected.still) : ""}
              alt={`Channel ${selected.channel}`}
              className="max-h-[85vh] w-auto rounded-lg"
            />
            <div className="mt-2 flex items-center justify-between text-sm text-slate-200">
              <div>
                <span className="font-mono">ch {String(selected.channel).padStart(2, "0")}</span>
                {selected.label && <span className="ml-2 text-emerald-300">{selected.label}</span>}
              </div>
              <div className="text-slate-400">{selected.resolution} · click anywhere to close</div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
