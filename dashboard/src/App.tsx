import { useEffect, useMemo, useState } from "react";
import { fetchCameraStatus, fetchEvents, fetchSummary, openEventStream } from "./api";
import type { CameraStatus, EventKind, EventRecord, Summary } from "./types";
import { StatCards } from "./components/StatCards";
import { CameraHealthBar } from "./components/CameraHealthBar";
import { LiveAlertToast } from "./components/LiveAlertToast";
import { EventLog } from "./components/EventLog";
import { EventFilters } from "./components/EventFilters";
import { Header } from "./components/Header";
import { NvrGrid } from "./components/NvrGrid";
import { CinemaStage } from "./components/CinemaStage";
import { MeterPanel } from "./components/MeterPanel";
import { FlagQueue } from "./components/FlagQueue";

const REFRESH_MS = 15000;

export default function App() {
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cameras, setCameras] = useState<CameraStatus[]>([]);
  const [live, setLive] = useState(false);
  const [toast, setToast] = useState<EventRecord | null>(null);
  const [filterCamera, setFilterCamera] = useState<string>("all");
  const [filterKind, setFilterKind] = useState<EventKind | "all">("all");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [e, s, c] = await Promise.all([fetchEvents({ limit: 200 }), fetchSummary(1), fetchCameraStatus()]);
        if (!alive) return;
        setEvents(e);
        setSummary(s);
        setCameras(c);
      } catch {
        // API might be down; UI stays with previous data
      }
    };
    load();
    const iv = window.setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      window.clearInterval(iv);
    };
  }, []);

  useEffect(() => {
    const close = openEventStream(
      (msg) => {
        if (msg.type === "event") {
          const ev = msg.data as EventRecord;
          setEvents((prev) => [ev, ...prev].slice(0, 500));
          setToast(ev);
          window.setTimeout(() => setToast(null), 6000);
        }
      },
      (open) => setLive(open)
    );
    return close;
  }, []);

  const visible = useMemo(() => {
    return events.filter((e) => {
      if (filterCamera !== "all" && e.camera_id !== filterCamera) return false;
      if (filterKind !== "all" && e.kind !== filterKind) return false;
      return true;
    });
  }, [events, filterCamera, filterKind]);

  const cameraIds = useMemo(() => Array.from(new Set(events.map((e) => e.camera_id))), [events]);

  const handleFeedback = (evId: string) => {
    setEvents((prev) => prev.filter((e) => e.id !== evId));
  };

  return (
    <div className="mx-auto flex min-h-full max-w-[1760px] flex-col gap-6 px-4 py-5 lg:px-6">
      <Header live={live} />
      <CinemaStage />
      <MeterPanel />
      <FlagQueue />
      <StatCards summary={summary} />
      <CameraHealthBar cameras={cameras} />
      <NvrGrid />
      <EventFilters
        cameraIds={cameraIds}
        camera={filterCamera}
        kind={filterKind}
        onCamera={setFilterCamera}
        onKind={setFilterKind}
      />
      <EventLog events={visible} onFeedbackDone={handleFeedback} />
      <LiveAlertToast event={toast} />
    </div>
  );
}
