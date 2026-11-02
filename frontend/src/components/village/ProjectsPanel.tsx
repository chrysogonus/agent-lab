"use client";

import { useState } from "react";
import { getRun, type Run, type VillageState } from "@/lib/api";
import { meetingLines } from "@/lib/village";

/** What the village builds: the latest town hall meeting, the current project and what stands. */
export function ProjectsPanel({
  state,
  onClose,
  onOpenTurn,
}: {
  state: Pick<VillageState, "meeting" | "next_meeting" | "day">;
  onClose: () => void;
  onOpenTurn: (run: Run) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const open = (runId: string) => {
    setError(null);
    getRun(runId).then(onOpenTurn, () => setError("That run is no longer stored."));
  };
  const { meeting } = state;

  return (
    <section className="flex flex-col gap-4" aria-label="Village projects">
      <div className="flex items-center gap-3">
        <h2 className="flex-1 text-xl leading-tight">Village projects</h2>
        <button type="button" onClick={onClose} className="village-button village-button--small">
          Back
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-fault">
          {error}
        </p>
      )}
      <div>
        <h3 className="text-lg leading-snug">{meeting ? `Town hall meeting, day ${meeting.day}` : "Town hall meeting"}</h3>
        <p className="text-sm text-dusk-muted">
          {state.next_meeting === state.day && meeting?.day !== state.day ? "Today at 17:00." : `The next one is on day ${state.next_meeting} at 17:00.`}
        </p>
        {meeting ? (
          <ul className="mt-2 flex flex-col gap-1.5">
            {meetingLines(meeting).map((line, i) => (
              <li key={i} className="font-sans text-sm leading-relaxed text-dusk">
                {line.text}
                {line.runId && (
                  <button type="button" onClick={() => open(line.runId!)} className="village-button village-button--small ml-2">
                    Open the run
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-dusk-muted">No meeting yet. Every third day Hilde proposes what to build, the others vote and she decides.</p>
        )}
      </div>
    </section>
  );
}
