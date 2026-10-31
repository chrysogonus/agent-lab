import type { AgentInfo, Run } from "@/lib/api";
import { agentName, formatTotals } from "@/lib/run-state";

const STATUS_DOT: Record<Run["status"], string> = {
  running: "bg-signal",
  completed: "bg-tool",
  max_iterations: "bg-fault",
  error: "bg-fault",
};

function when(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function RunList({
  runs,
  agents,
  current,
  onOpen,
}: {
  runs: Run[];
  agents: AgentInfo[];
  current: string | null;
  onOpen: (run: Run) => void;
}) {
  if (runs.length === 0) {
    return <p className="p-3 text-sm text-muted">No runs yet.</p>;
  }
  return (
    <ul className="divide-y divide-rule/60">
      {runs.map((run) => (
        <li key={run.run_id}>
          <button
            type="button"
            onClick={() => onOpen(run)}
            aria-current={run.run_id === current}
            className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm ${
              run.run_id === current ? "bg-paper" : ""
            }`}
          >
            <span className="text-xs font-semibold text-muted">
              {run.agent_name ?? agentName(agents, run.agent_id)}
            </span>
            <span className="line-clamp-2 text-sm text-ink">{run.prompt}</span>
            <span className="flex items-center gap-2 text-xs text-muted">
              <span className={`size-2 rounded-full ${STATUS_DOT[run.status]}`} aria-hidden />
              {run.status.replace("_", " ")}, {when(run.started_at)}
            </span>
            {run.totals && <span className="text-xs text-muted">{formatTotals(run.totals)}</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}
