"use client";

import { useCallback, useEffect, useState } from "react";
import {
  compareEvaluations,
  getEvaluation,
  stopEvaluation,
  type Comparison,
  type Evaluation,
  type EvaluationDetail,
} from "@/lib/api";
import { budgetText, failedChecks, rateText } from "@/lib/evaluation";
import { modelLabel } from "@/lib/models";
import { EvaluationCompare } from "./EvaluationCompare";

const POLL_MS = 2000;

function average(value: number | null, unit: string): string | null {
  return value == null ? null : `${Math.round(value).toLocaleString("en")} ${unit}`;
}

/** One evaluation's results; polled while it runs. Mount with key={evalId}. */
export function EvaluationResults({
  evalId,
  earlier,
  onOpenRun,
  onChanged,
}: {
  evalId: string;
  earlier: Evaluation[]; // what it can be compared with
  onOpenRun: (runId: string) => void;
  onChanged: () => void;
}) {
  const [detail, setDetail] = useState<EvaluationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);

  const load = useCallback(() => {
    getEvaluation(evalId).then(
      (next) => {
        setDetail(next);
        setError(null);
      },
      () => setError("The results are unavailable until the backend is running."),
    );
  }, [evalId]);

  useEffect(load, [load]);
  const state = detail?.evaluation.state;
  useEffect(() => {
    if (state !== "running") return;
    const timer = window.setInterval(load, POLL_MS);
    return () => {
      window.clearInterval(timer);
      onChanged(); // it ended, or the page moved on: the list may have changed
    };
  }, [state, load, onChanged]);

  if (error && !detail) return <p className="text-sm text-muted">{error}</p>;
  if (!detail) return <p className="text-sm text-muted">Loading the results…</p>;
  const { evaluation, summary, attempts } = detail;
  const { overall } = summary;
  const averages = [
    average(overall.avg_llm_calls, "model calls"),
    average(overall.avg_tokens, "tokens"),
    average(overall.avg_wall_ms, "ms"),
  ].filter(Boolean);

  return (
    <section aria-label="Evaluation results" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h3 className="text-base font-semibold text-ink">
          {attempts.length ? rateText(overall) : "No attempts yet"}
        </h3>
        <span className="text-sm text-muted">{evaluation.state}</span>
        {evaluation.state === "running" && (
          <button
            type="button"
            className="ml-auto rounded-md border border-rule px-2.5 py-1 text-sm font-semibold text-ink hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm"
            onClick={() => void stopEvaluation(evalId).then(load, load)}
          >
            Stop
          </button>
        )}
      </div>
      <p className="text-sm break-words text-muted">
        Config {evaluation.config_version}, {modelLabel(evaluation.model)}, {evaluation.repeats} per case.
        {averages.length > 0 && ` On average ${averages.join(", ")} per attempt.`}
      </p>
      <p className="text-sm break-words text-muted">Budget per attempt: {budgetText(evaluation.harness)}</p>
      <ul className="flex flex-col gap-2">
        {evaluation.cases.map((c) => {
          const rates = summary.cases[c.case_id];
          const troubled = attempts.filter((a) => a.case_id === c.case_id && a.outcome !== "pass");
          return (
            <li key={c.case_id} className="rounded-md border border-rule p-3 text-sm">
              <div className="flex flex-wrap justify-between gap-x-4">
                <span className="font-medium text-ink">{c.name}</span>
                <span className="text-ink">{rates ? rateText(rates) : "not run"}</span>
              </div>
              {troubled.length > 0 && (
                <ul className="mt-2 flex flex-col gap-2">
                  {troubled.map((a) => (
                    <li key={a.number} className="text-muted">
                      <span className={a.outcome === "fail" ? "text-fault" : "text-signal-ink"}>
                        Attempt {a.number}: {a.outcome}
                      </span>
                      {a.run_id && (
                        <button
                          type="button"
                          className="ml-2 font-semibold text-llm hover:underline focus-visible:outline-2 focus-visible:outline-llm"
                          onClick={() => onOpenRun(a.run_id as string)}
                        >
                          Open its run
                        </button>
                      )}
                      {failedChecks(a).length === 0 && a.reason && <p className="break-words">{a.reason}</p>}
                      {failedChecks(a).map((check) => (
                        <p key={check.expected} className="break-words">
                          Expected {check.expected}: {check.reason ?? check.result}
                        </p>
                      ))}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      {earlier.length > 0 && (
        <label className="flex flex-col gap-1 text-sm font-medium text-ink">
          Compare with
          <select
            defaultValue=""
            className="rounded-md border border-rule bg-panel px-2.5 py-1.5 text-sm text-ink"
            onChange={(e) => {
              if (!e.target.value) return setComparison(null);
              compareEvaluations(e.target.value, evalId).then(setComparison, () => setComparison(null));
            }}
          >
            <option value="">No comparison</option>
            {earlier.map((other) => (
              <option key={other.eval_id} value={other.eval_id}>
                {new Date(other.started_at * 1000).toLocaleString()} ({other.config_version})
              </option>
            ))}
          </select>
        </label>
      )}
      {comparison && <EvaluationCompare comparison={comparison} />}
    </section>
  );
}
