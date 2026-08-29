import { LiveZoom } from "./LiveZoom";

/** Full-bleed 4K cinema stage for M1 (channel 9) — the world-class display. */
export function CinemaStage() {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-800 bg-black shadow-[0_20px_80px_rgba(0,0,0,0.55)]">
      <div className="flex items-center justify-between border-b border-white/10 bg-gradient-to-r from-slate-950 to-slate-900 px-5 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-amber-400/90">PSO 295-A · Forecourt</div>
          <div className="text-lg font-semibold tracking-tight text-white">M1 · Pump 1 · Hi-Cetane Diesel</div>
        </div>
        <div className="text-right text-xs text-slate-400">
          <div>Dahua 4K · channel 9 · NVR I-frame</div>
          <div className="text-slate-500">2560 display from 3840×2160 source</div>
        </div>
      </div>
      <div className="relative aspect-video w-full bg-black">
        <LiveZoom channel={9} cinema className="absolute inset-0" />
        <div className="absolute bottom-4 right-4 w-[28%] min-w-[240px] max-w-md overflow-hidden rounded-xl border border-white/25 bg-black/80 shadow-2xl">
          <div className="bg-amber-500/90 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-black">
            Meter loupe ×5
          </div>
          <LiveZoom channel={9} meter className="aspect-[2/1]" />
        </div>
      </div>
    </section>
  );
}
