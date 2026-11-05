import type { OpenApproval } from "@/lib/api";

/** Shows on every page that a run is waiting for the owner, and goes to it. */
export function ApprovalsBanner({
  approvals,
  current,
  onOpen,
}: {
  approvals: OpenApproval[];
  current: string | null; // the run on screen shows its own request
  onOpen: (runId: string) => void;
}) {
  const elsewhere = approvals.filter((a) => a.run_id !== current);
  if (elsewhere.length === 0) return null;
  return (
    <section
      role="status"
      aria-label="Runs waiting for approval"
      className="flex flex-col gap-1 rounded-lg border border-signal/40 bg-panel px-3 py-2 text-sm"
    >
      {elsewhere.map((a) => (
        <p key={a.approval_id} className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-ink">
            {a.agent_name} wants to call <code className="font-semibold">{a.tool}</code>.
          </span>
          <button
            type="button"
            onClick={() => onOpen(a.run_id)}
            className="font-semibold text-llm hover:underline focus-visible:outline-2 focus-visible:outline-llm"
          >
            Go to the run
          </button>
        </p>
      ))}
    </section>
  );
}
