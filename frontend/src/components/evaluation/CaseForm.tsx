"use client";

import { useState } from "react";
import { ValidationError, type CaseFields, type Check, type ToolInfo } from "@/lib/api";
import { blankCheck, caseProblems, CHECK_KINDS, END_STATES } from "@/lib/evaluation";
import { FIELD } from "../builder/fields";

const SMALL_BUTTON =
  "rounded-md border border-rule px-2.5 py-1 text-sm font-semibold text-ink hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm disabled:opacity-40";

function CheckValue({
  check,
  label,
  onChange,
}: {
  check: Check;
  label: string;
  onChange: (check: Check) => void;
}) {
  switch (check.kind) {
    case "contains":
    case "not_contains":
      return (
        <input
          aria-label={label}
          value={check.text}
          onChange={(e) => onChange({ ...check, text: e.target.value })}
          className={FIELD}
        />
      );
    case "matches":
      return (
        <input
          aria-label={label}
          value={check.pattern}
          onChange={(e) => onChange({ ...check, pattern: e.target.value })}
          className={`${FIELD} font-mono`}
        />
      );
    case "tool_called":
    case "tool_not_called":
      return (
        <input
          aria-label={label}
          list="case-form-tools"
          value={check.tool}
          onChange={(e) => onChange({ ...check, tool: e.target.value })}
          className={FIELD}
        />
      );
    case "end_state":
      return (
        <select
          aria-label={label}
          value={check.state}
          onChange={(e) => onChange({ ...check, state: e.target.value as typeof check.state })}
          className={FIELD}
        >
          {END_STATES.map((state) => (
            <option key={state} value={state}>
              {state.replace("_", " ")}
            </option>
          ))}
        </select>
      );
    case "max_model_calls":
    case "max_tokens":
      return (
        <input
          aria-label={label}
          type="number"
          min={1}
          value={check.limit || ""}
          onChange={(e) => onChange({ ...check, limit: Number(e.target.value) })}
          className={FIELD}
        />
      );
    case "judge":
      return (
        <input
          aria-label={label}
          value={check.question}
          placeholder="Does the answer give a temperature for Berlin?"
          onChange={(e) => onChange({ ...check, question: e.target.value })}
          className={FIELD}
        />
      );
  }
}

/** Writes or edits one test case; the server has the last word on what it accepts. */
export function CaseForm({
  initial,
  tools,
  onSave,
  onCancel,
}: {
  initial: CaseFields | null;
  tools: ToolInfo[];
  onSave: (fields: CaseFields) => Promise<void>;
  onCancel: () => void;
}) {
  const [fields, setFields] = useState<CaseFields>(
    initial ?? { name: "", prompt: "", checks: [blankCheck("contains")], approvals: "deny" },
  );
  const [problems, setProblems] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const setCheck = (index: number, check: Check) =>
    setFields({ ...fields, checks: fields.checks.map((c, i) => (i === index ? check : c)) });

  const save = async () => {
    const found = caseProblems(fields);
    setProblems(found);
    if (found.length) return;
    setSaving(true);
    try {
      await onSave(fields);
    } catch (e) {
      setProblems([e instanceof ValidationError || e instanceof Error ? e.message : "Saving failed."]);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="flex flex-col gap-3 rounded-md border border-rule p-3"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <label className="flex flex-col gap-1 text-sm font-medium text-ink">
        Name
        <input
          value={fields.name}
          maxLength={80}
          onChange={(e) => setFields({ ...fields, name: e.target.value })}
          className={FIELD}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium text-ink">
        Prompt
        <textarea
          value={fields.prompt}
          rows={2}
          maxLength={4000}
          onChange={(e) => setFields({ ...fields, prompt: e.target.value })}
          className={FIELD}
        />
      </label>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-ink">Checks</legend>
        <datalist id="case-form-tools">
          {tools.map((tool) => (
            <option key={tool.name} value={tool.name} />
          ))}
        </datalist>
        {fields.checks.map((check, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_auto]">
            <select
              aria-label={`Check ${i + 1}: kind`}
              value={check.kind}
              onChange={(e) => setCheck(i, blankCheck(e.target.value as Check["kind"]))}
              className={FIELD}
            >
              {CHECK_KINDS.map(({ kind, label }) => (
                <option key={kind} value={kind}>
                  {label}
                </option>
              ))}
            </select>
            <CheckValue check={check} label={`Check ${i + 1}: value`} onChange={(c) => setCheck(i, c)} />
            <button
              type="button"
              className={SMALL_BUTTON}
              onClick={() => setFields({ ...fields, checks: fields.checks.filter((_, j) => j !== i) })}
            >
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          disabled={fields.checks.length >= 10}
          className={`${SMALL_BUTTON} self-start`}
          onClick={() => setFields({ ...fields, checks: [...fields.checks, blankCheck("contains")] })}
        >
          Add a check
        </button>
      </fieldset>
      <label className="flex flex-col gap-1 text-sm font-medium text-ink">
        When a tool marked ask first is called
        <select
          value={fields.approvals}
          onChange={(e) => setFields({ ...fields, approvals: e.target.value as CaseFields["approvals"] })}
          className={FIELD}
        >
          <option value="deny">Deny it</option>
          <option value="approve">Approve it</option>
        </select>
      </label>
      {problems.map((problem) => (
        <p key={problem} role="alert" className="text-sm text-fault">
          {problem}
        </p>
      ))}
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className={SMALL_BUTTON}>
          Save case
        </button>
        <button type="button" className={SMALL_BUTTON} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
