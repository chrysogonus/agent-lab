"use client";

import { useEffect, useState } from "react";
import type { Run } from "@/lib/api";
import { runModel } from "@/lib/models";
import { activeNodes, formatTotals, isLive, runTotals, takenEdges } from "@/lib/run-state";
import { useNow } from "@/lib/use-now";
import { useRunStream } from "@/lib/use-run-stream";
import { GraphView } from "./GraphView";
import { SpanDetail } from "./SpanDetail";
import { Waterfall } from "./Waterfall";

const STATUS_TEXT: Record<Run["status"], string> = {
  running: "Running",
  waiting_approval: "Waiting for approval",
  completed: "Completed",
  max_iterations: "Stopped at the iteration or round cap",
  over_budget: "Over budget",
  stopped: "Stopped",
  interrupted: "Interrupted: the lab stopped during this run",
  error: "Failed",
};

/** Live view and replay of one run; both render the same stream. Mount with key={run_id}. */
export function RunViewer({
  initial,
  onEnded,
  onEdit,
}: {
  initial: Run;
  onEnded: (run: Run) => void;
  onEdit?: () => void; // set while the run's custom agent still exists
}) {
  const view = useRunStream(initial.run_id);
  const run = view.run ?? initial;
  const [selected, setSelected] = useState<string | null>(null);
  const status = view.run?.status ?? view.status ?? initial.status;
  const now = useNow(isLive(status));

  useEffect(() => {
    if (view.run) onEnded(view.run);
  }, [view.run, onEnded]);

  const visited = new Set(Object.values(view.spans).map((s) => s.node_id));
  const span = selected ? (view.spans[selected] ?? null) : null;

  return (
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_24rem]">
      <div className="flex min-h-0 flex-col gap-4">
        <section className="rounded-lg border border-rule bg-panel" aria-label="Run summary">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-rule px-4 py-3">
            {/* long prompts (a villager's observation) stay readable in the span detail */}
            <h2 className="line-clamp-3 text-base font-semibold text-ink" title={run.prompt}>
              {run.prompt}
            </h2>
            <span className={`text-sm ${isLive(status) ? "text-signal-ink" : status === "completed" ? "text-tool" : "text-fault"}`}>
              {STATUS_TEXT[status]}
            </span>
            {runModel(run) && <span className="text-sm text-ink">{runModel(run)}</span>}
            <span className="text-sm text-muted">{formatTotals(runTotals(view.spans, run, now))}</span>
            {onEdit && (
              <button
                type="button"
                onClick={onEdit}
                className="ml-auto text-sm font-semibold text-llm hover:underline focus-visible:outline-2 focus-visible:outline-llm"
              >
                {run.eval_id ? "Back to the results" : "Back to editing"}
              </button>
            )}
          </div>
          {run.stop_reason && <p className="px-4 pt-3 text-sm text-fault">{run.stop_reason}</p>}
          {run.answer && <p className="px-4 py-3 text-sm text-ink">{run.answer}</p>}
          {view.error && <p role="alert" className="px-4 py-3 text-sm text-fault">{view.error}</p>}
        </section>
        <section className="h-72 rounded-lg border border-rule bg-panel" aria-label="Agent graph">
          <GraphView
            graph={run.graph}
            active={activeNodes(view.spans)}
            visited={visited}
            taken={takenEdges(run.graph, view.spans)}
          />
        </section>
        <section className="min-h-0 overflow-auto rounded-lg border border-rule bg-panel" aria-label="Spans">
          <Waterfall spans={view.spans} selected={selected} onSelect={setSelected} />
        </section>
      </div>
      <aside className="overflow-auto rounded-lg border border-rule bg-panel p-4" aria-label="Span detail">
        <SpanDetail span={span} />
      </aside>
    </div>
  );
}
