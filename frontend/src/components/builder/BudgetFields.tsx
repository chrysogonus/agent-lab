"use client";

import { useEffect, useState } from "react";
import { budgetLimits, type Budget } from "@/lib/api";
import { NumberField, type Form } from "./fields";

const FIELDS: [keyof Budget, string][] = [
  ["model_calls", "Model calls"],
  ["tokens", "Tokens"],
  ["tool_calls", "Tool calls"],
  ["seconds", "Seconds"],
];

/** The most a run may use. The limits come from the server, which has the last word. */
export function BudgetFields({ form }: { form: Form }) {
  const [limits, setLimits] = useState<{ default: Budget; max: Budget } | null>(null);
  useEffect(() => {
    budgetLimits().then(setLimits, () => {});
  }, []);
  const { budget } = form.draft;
  const shown = budget === undefined ? limits?.default : budget; // unset: what a save will give it

  if (form.readOnly && !shown) {
    return <p className="text-sm text-muted">Budget: none. Templates run without one.</p>;
  }
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-medium text-ink">Budget per run</legend>
      {shown && budget !== undefined ? (
        FIELDS.map(([key, label]) => (
          <NumberField
            key={key}
            form={form}
            path={["budget", key]}
            label={limits ? `${label} (at most ${limits.max[key].toLocaleString("en")})` : label}
          />
        ))
      ) : shown ? (
        <p className="text-sm text-muted">
          The default: {shown.model_calls} model calls, {shown.tokens.toLocaleString("en")} tokens,{" "}
          {shown.tool_calls} tool calls, {shown.seconds} seconds.
        </p>
      ) : (
        <p className="text-sm text-muted">None: nothing limits this agent&apos;s runs.</p>
      )}
      {!form.readOnly && limits && (
        <button
          type="button"
          className="self-start rounded-md border border-rule px-2.5 py-1 text-sm font-semibold text-ink hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm"
          onClick={() => form.set(["budget"], shown ? null : limits.default)}
        >
          {shown ? "Remove the budget" : "Add a budget"}
        </button>
      )}
    </fieldset>
  );
}
