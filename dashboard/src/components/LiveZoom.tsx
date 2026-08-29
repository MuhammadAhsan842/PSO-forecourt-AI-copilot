import { useEffect, useState } from "react";
import { API_BASE } from "../api";

function snapshotUrl(ch: number, extra: string) {
  const sep = extra.startsWith("?") ? extra : `?${extra}`;
  return `${API_BASE}/api/v1/nvr/snapshot/${ch}.jpg${sep}`;
}

type LiveZoomProps = {
  channel: number;
  meter?: boolean;
  cinema?: boolean;
  className?: string;
};

/** Live frames via blob URLs so the browser scales 4K with high-quality filtering. */
export function LiveZoom({ channel, meter = false, cinema = false, className }: LiveZoomProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [fps, setFps] = useState(0);

  useEffect(() => {
    let alive = true;
    let current: string | null = null;
    let frames = 0;
    const fpsTimer = window.setInterval(() => {
      setFps(frames);
      frames = 0;
    }, 1000);

    const qs = () => {
      const t = Date.now();
      if (meter) return `?roi=meter&scale=5&q=95&hq=1&t=${t}`;
      if (cinema || channel === 9 || channel === 10) {
        const w = cinema ? 2560 : 1920;
        return `?hq=1&width=${w}&q=92&t=${t}`;
      }
      return `?subtype=1&q=70&t=${t}`;
    };

    const loop = async () => {
      while (alive) {
        try {
          const r = await fetch(snapshotUrl(channel, qs()), { cache: "no-store" });
          if (!r.ok) {
            await new Promise((res) => setTimeout(res, 400));
            continue;
          }
          const blob = await r.blob();
          const next = URL.createObjectURL(blob);
          if (!alive) {
            URL.revokeObjectURL(next);
            break;
          }
          setUrl(next);
          frames += 1;
          if (current) URL.revokeObjectURL(current);
          current = next;
        } catch {
          await new Promise((res) => setTimeout(res, 500));
        }
      }
    };
    void loop();
    return () => {
      alive = false;
      window.clearInterval(fpsTimer);
      if (current) URL.revokeObjectURL(current);
    };
  }, [channel, meter, cinema]);

  return (
    <div className={`relative overflow-hidden bg-black ${className ?? ""}`}>
      {url ? (
        <img
          src={url}
          alt=""
          className="h-full w-full object-contain"
          style={{ imageRendering: "auto" }}
        />
      ) : (
        <div className="flex h-full min-h-[12rem] items-center justify-center text-sm text-slate-500">
          Tuning 4K feed…
        </div>
      )}
      <span className="absolute left-3 top-3 inline-flex items-center gap-1.5 rounded bg-red-600 px-2 py-1 text-[11px] font-semibold tracking-wide text-white shadow-lg">
        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-white" />
        LIVE {fps} fps · 4K
      </span>
    </div>
  );
}
