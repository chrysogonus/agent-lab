// Pure view logic for test cases, results and comparisons (M17).
import type { Attempt, CaseFields, Check, CheckResult, ComparisonRow, EvaluationHarness, Rates, TestCase } from "./api";

export const CHECK_KINDS: { kind: Check["kind"]; label: string }[] = [
  { kind: "contains", label: "The answer contains" },
  { kind: "not_contains", label: "The answer does not contain" },
  { kind: "matches", label: "The answer matches the pattern" },
  { kind: "tool_called", label: "This tool was called" },
  { kind: "tool_not_called", label: "This tool was not called" },
  { kind: "end_state", label: "The run ended as" },
  { kind: "max_model_calls", label: "At most this many model calls" },
  { kind: "max_tokens", label: "At most this many tokens" },
  { kind: "judge", label: "A judge model answers yes to" },
];

export const END_STATES = ["completed", "max_iterations", "over_budget", "stopped", "error"] as const;

export function blankCheck(kind: Check["kind"]): Check {
  switch (kind) {
    case "contains":
    case "not_contains":
      return { kind, text: "" };
    case "matches":
      return { kind, pattern: "" };
    case "tool_called":
    case "tool_not_called":
      return { kind, tool: "" };
    case "end_state":
      return { kind, state: "completed" };
    case "max_model_calls":
    case "max_tokens":
      return { kind, limit: 0 };
    case "judge":
      return { kind, question: "" };
  }
}

export function checkLabel(check: Check): string {
  switch (check.kind) {
    case "contains":
      return `contains "${check.text}"`;
    case "not_contains":
      return `does not contain "${check.text}"`;
    case "matches":
      return `matches "${check.pattern}"`;
    case "tool_called":
      return `calls ${check.tool}`;
    case "tool_not_called":
      return `does not call ${check.tool}`;
    case "end_state":
      return `ends ${check.state.replace("_", " ")}`;
    case "max_model_calls":
      return `at most ${check.limit.toLocaleString("en")} model calls`;
    case "max_tokens":
      return `at most ${check.limit.toLocaleString("en")} tokens`;
    case "judge":
      return `judge: "${check.question}"`;
  }
}

function isBlank(check: Check): boolean {
  switch (check.kind) {
    case "contains":
    case "not_contains":
      return !check.text;
    case "matches":
      return !check.pattern;
    case "tool_called":
    case "tool_not_called":
      return !check.tool.trim();
    case "end_state":
      return false;
    case "max_model_calls":
    case "max_tokens":
      return check.limit < 1;
    case "judge":
      return !check.question.trim();
  }
}

/** What a client may send back: the server refuses the fields it adds itself. */
export function caseFields({ name, prompt, checks, approvals }: TestCase): CaseFields {
  return { name, prompt, checks, approvals };
}

/** What to fix before sending; the server still has the last word, on patterns for one. */
export function caseProblems(fields: CaseFields): string[] {
  const problems: string[] = [];
  if (!fields.name.trim()) problems.push("Give the case a name.");
  if (!fields.prompt.trim()) problems.push("Give the case a prompt.");
  if (fields.checks.length === 0) problems.push("Add at least one check.");
  fields.checks.forEach((check, i) => {
    if (isBlank(check)) problems.push(`Check ${i + 1} is not filled in.`);
  });
  return problems;
}

function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

function optional(rate: number | null): string {
  return rate == null ? "no pass rate" : percent(rate);
}

export function rateText(rates: Rates): string {
  const errors = rates.errors === 1 ? "1 error" : `${rates.errors} errors`;
  if (rates.pass_rate == null) return `no pass rate, ${errors}`;
  return rates.errors ? `${percent(rates.pass_rate)}, ${errors}` : percent(rates.pass_rate);
}

export function changeText({ change, earlier_rate: was, later_rate: now }: ComparisonRow): string {
  switch (change) {
    case "up":
      return `better: ${optional(was)} → ${optional(now)}`;
    case "down":
      return `worse: ${optional(was)} → ${optional(now)}`;
    case "same":
      return `the same: ${optional(now)}`;
    case "changed":
      return `the case changed: ${optional(was)}, then ${optional(now)}`;
    case "new":
      return `new: ${optional(now)}`;
    case "removed":
      return `removed: was ${optional(was)}`;
    case "no_rate":
      return `no comparison: ${optional(was)}, then ${optional(now)}`;
  }
}

export function failedChecks(attempt: Attempt): CheckResult[] {
  return attempt.checks.filter((c) => c.result !== "pass");
}

export function budgetText({ budget, default_budget }: EvaluationHarness): string {
  if (!budget) return "no budget";
  const limits = [
    `${budget.model_calls.toLocaleString("en")} model calls`,
    `${budget.tokens.toLocaleString("en")} tokens`,
    `${budget.tool_calls.toLocaleString("en")} tool calls`,
    `${budget.seconds.toLocaleString("en")} s`,
  ].join(", ");
  return default_budget ? `${limits} (the default: this agent has no budget)` : limits;
}
