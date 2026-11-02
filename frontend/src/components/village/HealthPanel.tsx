"use client";

import { useEffect, useState } from "react";
import { getRun, healthTurns, villageHealth, type DayHealth, type Run } from "@/lib/api";
import { healthDetail, healthRow, healthTitle, refusalLines } from "@/lib/health";
import { turnLabel } from "@/lib/village";

/** Village health (M13): numbers for the recent days, a day's detail, and the turns behind a
 * refusal reason, each opening its run. */
export function HealthPanel({ onClose, onOpenTurn }: { onClose: () => void; onOpenTurn: (run: Run) => void }) {
  const [days, setDays] = useState<DayHealth[] | null>(null);
  const [open, setOpen] = useState<DayHealth | null>(null);
  const [turns, setTurns] = useState<{ reason: string; runs: Run[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    villageHealth(14).then(
      (h) => setDays(h.days),
      () => setError("Village health is unavailable until the backend is running."),
    );
  }, []);

  const showTurns = (day: DayHealth, reason: string) => {
    setError(null);
    healthTurns(day.day, reason).then(
      (runs) => setTurns({ reason, runs }),
      () => setError("Could not load those turns."),
    );
  };
  const openRun = (runId: string) => getRun(runId).then(onOpenTurn, () => setError("That run is no longer stored."));

  return (
    <section className="flex flex-col gap-4" aria-label="Village health">
      <div className="flex items-center gap-3">
        <h2 className="flex-1 text-xl leading-tight">{open ? healthTitle(open) : "Village health"}</h2>
        <button
          type="button"
          onClick={() => (turns ? setTurns(null) : open ? setOpen(null) : onClose())}
          className="village-button village-button--small"
        >
          Back
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-fault">
          {error}
        </p>
      )}
      {!days && !error && <p className="text-sm text-dusk-muted">Counting…</p>}
      {days && !open && (
        <>
          {days.length === 0 && <p className="text-sm text-dusk-muted">No village days with decisions yet.</p>}
          <ul className="flex flex-col gap-3">
            {days.map((d) => (
              <li key={d.day}>
                <button type="button" onClick={() => setOpen(d)} className="village-menu-item w-full rounded-md p-2 text-left">
                  <span className="block text-base">{healthTitle(d)}</span>
                  <span className="mt-1 grid grid-cols-3 gap-x-3 gap-y-0.5 font-sans text-xs text-dusk">
                    {healthRow(d).map((c) => (
                      <span key={c.label} title={c.why}>
                        <span className="text-dusk-muted">{c.label}</span> {c.value}
                      </span>
                    ))}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {open && !turns && (
        <div className="flex flex-col gap-3 font-sans text-sm text-dusk">
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
            {healthDetail(open).map((c) => (
              <div key={c.label} title={c.why} className="contents">
                <dt className="text-dusk-muted">{c.label}</dt>
                <dd>{c.value}</dd>
              </div>
            ))}
          </dl>
          <h3 className="font-pixel text-lg">Refusals</h3>
          {open.refusals.length === 0 ? (
            <p className="text-dusk-muted">None.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {open.refusals.map((r, i) => (
                <li key={r.reason}>
                  <button type="button" onClick={() => showTurns(open, r.reason)} className="text-left underline decoration-dotted">
                    {refusalLines(open)[i]}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {open && turns && (
        <div className="flex flex-col gap-2 font-sans text-sm text-dusk">
          <p className="text-dusk-muted">{turns.reason.replaceAll("<villager>", "someone").replaceAll("<goods>", "goods")}</p>
          <ul className="flex flex-col gap-1">
            {turns.runs.map((run) => (
              <li key={run.run_id}>
                <button type="button" onClick={() => openRun(run.run_id)} className="text-left underline decoration-dotted">
                  {run.villager}: {turnLabel(run)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
