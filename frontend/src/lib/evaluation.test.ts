import { describe, expect, it } from "vitest";
import type { Attempt, Check, Rates } from "./api";
import { blankCheck, budgetText, caseFields, caseProblems, changeText, checkLabel, failedChecks, rateText, CHECK_KINDS } from "./evaluation";

const rates = (changes: Partial<Rates>): Rates => ({
  passed: 0,
  failed: 0,
  errors: 0,
  pass_rate: null,
  avg_llm_calls: null,
  avg_tokens: null,
  avg_wall_ms: null,
  ...changes,
});

describe("rateText", () => {
  it("shows a whole percentage", () => {
    expect(rateText(rates({ passed: 2, failed: 1, pass_rate: 2 / 3 }))).toBe("67%");
    expect(rateText(rates({ passed: 1, pass_rate: 1 }))).toBe("100%");
    expect(rateText(rates({ failed: 1, pass_rate: 0 }))).toBe("0%");
  });

  it("adds errors, which the rate leaves out", () => {
    expect(rateText(rates({ passed: 1, errors: 2, pass_rate: 1 }))).toBe("100%, 2 errors");
    expect(rateText(rates({ passed: 1, errors: 1, pass_rate: 1 }))).toBe("100%, 1 error");
  });

  it("shows no rate when every attempt was an error", () => {
    expect(rateText(rates({ errors: 3 }))).toBe("no pass rate, 3 errors");
  });
});

describe("changeText", () => {
  it("says how a case moved, with both rates", () => {
    const row = { case_id: "c", name: "n" };
    expect(changeText({ ...row, change: "up", earlier_rate: 0.5, later_rate: 1 })).toBe("better: 50% → 100%");
    expect(changeText({ ...row, change: "down", earlier_rate: 1, later_rate: 0 })).toBe("worse: 100% → 0%");
    expect(changeText({ ...row, change: "same", earlier_rate: 1, later_rate: 1 })).toBe("the same: 100%");
  });

  it("does not call different cases better or worse", () => {
    const row = { case_id: "c", name: "n" };
    expect(changeText({ ...row, change: "changed", earlier_rate: 1, later_rate: 0 })).toBe(
      "the case changed: 100%, then 0%",
    );
    expect(changeText({ ...row, change: "new", earlier_rate: null, later_rate: 1 })).toBe("new: 100%");
    expect(changeText({ ...row, change: "removed", earlier_rate: 1, later_rate: null })).toBe("removed: was 100%");
    expect(changeText({ ...row, change: "no_rate", earlier_rate: null, later_rate: 1 })).toBe(
      "no comparison: no pass rate, then 100%",
    );
  });
});

describe("checks", () => {
  it("offers a blank check of every kind the server knows", () => {
    expect(CHECK_KINDS.map((k) => k.kind)).toEqual([
      "contains",
      "not_contains",
      "matches",
      "tool_called",
      "tool_not_called",
      "end_state",
      "max_model_calls",
      "max_tokens",
      "judge",
    ]);
    for (const { kind } of CHECK_KINDS) expect(blankCheck(kind).kind).toBe(kind);
  });

  it("labels a check for the case list", () => {
    expect(checkLabel({ kind: "contains", text: "391" })).toBe('contains "391"');
    expect(checkLabel({ kind: "tool_called", tool: "calculator" })).toBe("calls calculator");
    expect(checkLabel({ kind: "max_tokens", limit: 1000 })).toBe("at most 1,000 tokens");
    expect(checkLabel({ kind: "judge", question: "Is it right?" })).toBe('judge: "Is it right?"');
  });
});

describe("caseProblems", () => {
  const good = { name: "Case", prompt: "Say hi", approvals: "deny" as const };
  const contains: Check = { kind: "contains", text: "hi" };

  it("accepts a filled-in case", () => {
    expect(caseProblems({ ...good, checks: [contains] })).toEqual([]);
  });

  it("names what is missing", () => {
    expect(caseProblems({ ...good, name: " ", checks: [contains] })).toEqual(["Give the case a name."]);
    expect(caseProblems({ ...good, prompt: "", checks: [contains] })).toEqual(["Give the case a prompt."]);
    expect(caseProblems({ ...good, checks: [] })).toEqual(["Add at least one check."]);
  });

  it("finds a check left blank", () => {
    expect(caseProblems({ ...good, checks: [blankCheck("contains")] })).toEqual(["Check 1 is not filled in."]);
    expect(caseProblems({ ...good, checks: [contains, blankCheck("judge")] })).toEqual(["Check 2 is not filled in."]);
    expect(caseProblems({ ...good, checks: [blankCheck("max_tokens")] })).toEqual(["Check 1 is not filled in."]);
  });

  it("does not ask for what a kind already has", () => {
    expect(caseProblems({ ...good, checks: [blankCheck("end_state")] })).toEqual([]);
  });
});

describe("failedChecks", () => {
  it("lists what went wrong in an attempt, not what passed", () => {
    const attempt: Attempt = {
      eval_id: "e",
      case_id: "c",
      number: 1,
      run_id: "r",
      outcome: "fail",
      reason: "nope",
      llm_calls: 1,
      tool_calls: 0,
      tokens: 1,
      wall_ms: 1,
      checks: [
        { kind: "contains", expected: "a", result: "pass", reason: null, judge_run_id: null },
        { kind: "contains", expected: "b", result: "fail", reason: "nope", judge_run_id: null },
        { kind: "judge", expected: "c", result: "error", reason: "broke", judge_run_id: "j" },
      ],
    };
    expect(failedChecks(attempt).map((c) => c.expected)).toEqual(["b", "c"]);
  });
});

describe("budgetText", () => {
  const budget = { model_calls: 30, tokens: 200000, tool_calls: 30, seconds: 600 };

  it("spells out the limits", () => {
    expect(budgetText({ budget, ask_first: [], default_budget: false })).toBe(
      "30 model calls, 200,000 tokens, 30 tool calls, 600 s",
    );
  });

  it("says when the default stood in for an agent without a budget", () => {
    expect(budgetText({ budget, ask_first: [], default_budget: true })).toBe(
      "30 model calls, 200,000 tokens, 30 tool calls, 600 s (the default: this agent has no budget)",
    );
  });

  it("says when there was none", () => {
    expect(budgetText({ budget: null, ask_first: [], default_budget: false })).toBe("no budget");
  });
});

describe("caseFields", () => {
  it("keeps only what the server lets a client send, which refuses anything else", () => {
    const stored = {
      case_id: "case-1",
      agent_id: "react",
      read_only: false,
      name: "Case",
      prompt: "Say hi",
      approvals: "approve" as const,
      checks: [{ kind: "contains" as const, text: "hi" }],
    };
    expect(caseFields(stored)).toEqual({
      name: "Case",
      prompt: "Say hi",
      approvals: "approve",
      checks: [{ kind: "contains", text: "hi" }],
    });
  });
});
