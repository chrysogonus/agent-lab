"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createCase,
  deleteCase,
  evaluationNotice,
  listCases,
  listEvaluations,
  startEvaluation,
  updateCase,
  type AgentInfo,
  type CaseFields,
  type EvaluationSummary,
  type ModelInfo,
  type TestCase,
  type ToolInfo,
} from "@/lib/api";
import { caseFields, checkLabel, rateText } from "@/lib/evaluation";
import { modelLabel, modelOptions, refFromValue } from "@/lib/models";
import { FIELD } from "../builder/fields";
import { CaseForm } from "./CaseForm";
import { EvaluationResults } from "./EvaluationResults";

const BUTTON =
  "rounded-md border border-rule px-2.5 py-1 text-sm font-semibold text-ink hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm disabled:opacity-40";

/** An agent's test cases and evaluations. Mount with key={agent id}. */
export function EvaluationPanel({
  agent,
  models,
  tools,
  openEval,
  onOpenEval,
  onOpenRun,
}: {
  agent: AgentInfo;
  models: ModelInfo[];
  tools: ToolInfo[];
  openEval: string | null;
  onOpenEval: (evalId: string) => void;
  onOpenRun: (runId: string) => void;
}) {
  const [cases, setCases] = useState<TestCase[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationSummary[]>([]);
  const [editing, setEditing] = useState<TestCase | "new" | null>(null);
  const [left, setLeft] = useState<Set<string>>(new Set()); // cases not chosen for the next run
  const [repeats, setRepeats] = useState(3);
  const [model, setModel] = useState(""); // "": the agent's own
  const [sharesProvider, setSharesProvider] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    Promise.all([listCases(agent.id), listEvaluations(agent.id)]).then(
      ([nextCases, nextEvaluations]) => {
        setCases(nextCases);
        setEvaluations(nextEvaluations);
        setError(null);
      },
      () => setError("Cases and results are unavailable until the backend is running."),
    );
  }, [agent.id]);
  useEffect(refresh, [refresh]);

  const chosenModel = refFromValue(model);
  const provider =
    chosenModel?.provider ?? agent.model?.provider ?? models.find((m) => m.default)?.provider;
  useEffect(() => {
    if (!provider) return;
    evaluationNotice(provider).then(
      (notice) => setSharesProvider(notice.village_shares_provider),
      () => setSharesProvider(false),
    );
  }, [provider]);

  const saveCase = async (fields: CaseFields) => {
    if (editing && editing !== "new") await updateCase(editing.case_id, fields);
    else await createCase(agent.id, fields);
    setEditing(null);
    refresh();
  };

  const removeCase = async (testCase: TestCase) => {
    if (!window.confirm(`Delete the case "${testCase.name}"? Past results keep their copy.`)) return;
    try {
      await deleteCase(testCase.case_id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Deleting failed.");
    }
  };

  const start = async () => {
    try {
      const chosen = cases.filter((c) => !left.has(c.case_id)).map((c) => c.case_id);
      const evaluation = await startEvaluation(agent.id, {
        repeats,
        case_ids: chosen,
        model: chosenModel,
      });
      onOpenEval(evaluation.eval_id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The evaluation did not start.");
    }
  };

  const options = modelOptions(models, chosenModel);
  const chosenCount = cases.filter((c) => !left.has(c.case_id)).length;
  const opened = evaluations.find((e) => e.evaluation.eval_id === openEval);
  const earlier = evaluations
    .map((e) => e.evaluation)
    .filter((e) => opened && e.started_at < opened.evaluation.started_at);

  return (
    <section
      aria-label="Test cases and evaluations"
      className="flex min-w-0 flex-1 flex-col gap-4 overflow-auto rounded-lg border border-rule bg-panel p-4"
    >
      {error && (
        <p role="alert" className="text-sm text-fault">
          {error}
        </p>
      )}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-ink">Test cases of {agent.name}</h2>
          <button type="button" className={BUTTON} onClick={() => setEditing("new")}>
            New case
          </button>
        </div>
        {editing && (
          <CaseForm
            key={editing === "new" ? "new" : editing.case_id}
            initial={editing === "new" ? null : caseFields(editing)}
            tools={tools}
            models={models}
            onSave={saveCase}
            onCancel={() => setEditing(null)}
          />
        )}
        {cases.length === 0 && <p className="text-sm text-muted">No cases yet. Write one to measure this agent.</p>}
        <ul className="flex flex-col gap-2">
          {cases.map((testCase) => (
            <li key={testCase.case_id} className="flex items-start gap-3 rounded-md border border-rule p-3 text-sm">
              <input
                type="checkbox"
                aria-label={`Run "${testCase.name}"`}
                className="mt-1"
                checked={!left.has(testCase.case_id)}
                onChange={(e) => {
                  const next = new Set(left);
                  if (e.target.checked) next.delete(testCase.case_id);
                  else next.add(testCase.case_id);
                  setLeft(next);
                }}
              />
              <div className="min-w-0 flex-1">
                <p className="font-medium text-ink">
                  {testCase.name}
                  {testCase.read_only && <span className="ml-2 font-normal text-muted">example</span>}
                </p>
                <p className="line-clamp-2 break-words text-muted">{testCase.prompt}</p>
                <p className="break-words text-muted">{testCase.checks.map(checkLabel).join("; ")}</p>
              </div>
              {!testCase.read_only && (
                <div className="flex shrink-0 gap-2">
                  <button type="button" className={BUTTON} onClick={() => setEditing(testCase)}>
                    Edit
                  </button>
                  <button type="button" className={BUTTON} onClick={() => void removeCase(testCase)}>
                    Delete
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-col gap-2 rounded-md border border-rule p-3">
        <h3 className="text-sm font-semibold text-ink">Run an evaluation</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm font-medium text-ink">
            Times per case
            <input
              type="number"
              min={1}
              max={10}
              value={repeats}
              onChange={(e) => setRepeats(Number(e.target.value))}
              className={FIELD}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-ink">
            Model
            <select value={model} onChange={(e) => setModel(e.target.value)} className={FIELD}>
              <option value="">The agent&apos;s own</option>
              {options.groups.map((group) => (
                <optgroup key={group.label} label={group.label}>
                  {group.options.map((o) => (
                    <option key={o.value} value={o.value} disabled={o.disabled}>
                      {o.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
        </div>
        {sharesProvider && (
          <p role="status" className="rounded-md border border-signal/40 p-2 text-sm text-signal-ink">
            The village is running on this provider, so they share its rate limits, and the village
            could lose turns or pause itself. You can pause it first.
          </p>
        )}
        <button
          type="button"
          className={`${BUTTON} self-start`}
          disabled={chosenCount === 0 || repeats < 1 || repeats > 10}
          onClick={() => void start()}
        >
          Run {chosenCount} {chosenCount === 1 ? "case" : "cases"}
        </button>
      </div>
      {openEval && (
        <EvaluationResults
          key={openEval}
          evalId={openEval}
          earlier={earlier}
          onOpenRun={onOpenRun}
          onChanged={refresh}
        />
      )}
      {evaluations.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-ink">Evaluations</h3>
          <ul className="divide-y divide-rule/60 rounded-md border border-rule">
            {evaluations.map(({ evaluation, summary }) => (
              <li key={evaluation.eval_id}>
                <button
                  type="button"
                  aria-current={evaluation.eval_id === openEval}
                  onClick={() => onOpenEval(evaluation.eval_id)}
                  className={`flex w-full flex-wrap justify-between gap-x-4 px-3 py-2 text-left text-sm hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm ${evaluation.eval_id === openEval ? "bg-paper" : ""}`}
                >
                  <span className="text-ink">
                    {new Date(evaluation.started_at * 1000).toLocaleString()}, {modelLabel(evaluation.model)}
                  </span>
                  <span className="text-muted">
                    {evaluation.state}, {rateText(summary.overall)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
