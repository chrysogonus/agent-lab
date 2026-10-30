"use client";

import { useCallback, useEffect, useState } from "react";
import { PromptForm } from "@/components/PromptForm";
import { RunList } from "@/components/RunList";
import { RunViewer } from "@/components/RunViewer";
import { listRuns, type Run } from "@/lib/api";

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [current, setCurrent] = useState<Run | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listRuns()
      .then((r) => {
        setRuns(r);
        setListError(null);
      })
      .catch(() => setListError("Past runs are unavailable until the backend is running."));
  }, []);

  useEffect(refresh, [refresh]);

  const started = (run: Run) => {
    setCurrent(run);
    setRuns((r) => [run, ...r]);
  };

  return (
    <div className="flex min-h-dvh flex-col gap-4 p-4 lg:h-dvh">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:gap-6">
        <h1 className="pt-2 text-xl font-semibold tracking-tight text-ink">Agent Lab</h1>
        <PromptForm onStarted={started} />
      </header>
      <div className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row">
        <nav
          className="max-h-60 shrink-0 overflow-auto rounded-lg border border-rule bg-panel lg:max-h-none lg:w-64"
          aria-label="Past runs"
        >
          <h2 className="border-b border-rule px-3 py-2 text-sm font-semibold text-ink">Past runs</h2>
          {listError ? (
            <p className="p-3 text-sm text-muted">{listError}</p>
          ) : (
            <RunList runs={runs} current={current?.run_id ?? null} onOpen={setCurrent} />
          )}
        </nav>
        <main className="flex min-h-0 min-w-0 flex-1">
          {current ? (
            <RunViewer key={current.run_id} initial={current} onEnded={refresh} />
          ) : (
            <p className="text-sm text-muted">
              Run the agent, or open a past run to replay it.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
