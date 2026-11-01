"use client";

import { useState } from "react";
import { getRun, type ChronicleEntry, type Run } from "@/lib/api";
import { calendarText, newEntries } from "@/lib/village";

const WEATHER_WORDS: Record<ChronicleEntry["weather"], string> = {
  sun: "sunny",
  clouds: "cloudy",
  rain: "rain",
  storm: "storm",
  fog: "fog",
  snow: "snow",
};

/** The village chronicle, newest first; entries written since `seen` are marked new. */
export function ChroniclePanel({
  chronicle,
  seen,
  onClose,
  onOpenTurn,
}: {
  chronicle: ChronicleEntry[];
  seen: string | null; // the newest run id the owner had seen when opening the chronicle
  onClose: () => void;
  onOpenTurn: (run: Run) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const fresh = newEntries(chronicle, seen);
  const open = (runId: string) => {
    setError(null);
    getRun(runId).then(onOpenTurn, () => setError("That run is no longer stored."));
  };

  return (
    <section className="flex flex-col gap-4" aria-label="Chronicle">
      <div className="flex items-center gap-3">
        <h2 className="flex-1 text-xl leading-tight">The village chronicle</h2>
        <button type="button" onClick={onClose} className="village-button village-button--small">
          Back
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-fault">
          {error}
        </p>
      )}
      {chronicle.length === 0 ? (
        <p className="text-sm text-dusk-muted">Nothing written yet. Each night, once everyone is asleep, the chronicler writes about the day.</p>
      ) : (
        <ol className="flex flex-col gap-4">
          {chronicle.map((entry, i) => (
            <li key={entry.run_id} className="border-b-2 border-dashed border-dusk-rule pb-3 last:border-b-0">
              <p className="text-sm text-dusk-muted">
                {calendarText({ calendar: { ...entry, festival_in: null } })}, {WEATHER_WORDS[entry.weather]}
                {i < fresh && <span className="ml-2 rounded-sm bg-[#ffd75e] px-1.5 text-dusk">New</span>}
              </p>
              <h3 className="text-lg leading-snug">{entry.title}</h3>
              <p className="mt-1 font-sans text-sm leading-relaxed text-dusk">{entry.text}</p>
              <button type="button" onClick={() => open(entry.run_id)} className="village-button village-button--small mt-2">
                Open the run
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
