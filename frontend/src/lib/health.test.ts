import { describe, expect, it } from "vitest";
import type { DayHealth } from "./api";
import { healthRow, healthTitle, refusalLines } from "./health";

const day = (fields: Partial<DayHealth>): DayHealth => ({
  day: 66,
  final: true,
  trail: true,
  decisions: 200,
  waits: 80,
  failed_calls: 1,
  calls: { decision: 201, plan: 6, reflect: 4, chronicle: 1, meeting: 5 },
  refusals: [
    { reason: "<villager> is not next to you", count: 30 },
    { reason: "you already said that", count: 7 },
  ],
  conversations: { count: 12, lines: [2, 4, 10], median_lines: 4 },
  repeated_lines: 7,
  plan_adherence: { kept: 9, entries: 12 },
  meeting: { present: ["Hilde", "Greta", "Lina"], votes: 2, outcome: "decided: A market stand" },
  trades: 3,
  loads_set_down: 2,
  loads_worked_in: 1,
  load_minutes: 40,
  given_back: 0,
  weather_slips: ["storm"],
  stuck_hours: 1.5,
  ...fields,
});

describe("village health", () => {
  it("turns a day into the table's cells", () => {
    expect(healthRow(day({}))).toEqual([
      { label: "Decisions", value: "200" },
      { label: "Waits", value: "40%" },
      { label: "Refusals", value: "37" },
      { label: "Talk lines", value: "4" },
      { label: "Plan kept", value: "75%" },
      { label: "Trades", value: "3" },
      { label: "Loads", value: "2 / 1" },
      { label: "Stuck hours", value: "1.5" },
      { label: "Weather slips", value: "1" },
    ]);
  });

  it("shows a missing number as a dash, with why", () => {
    const cells = healthRow(day({ trail: false, plan_adherence: null, loads_worked_in: null, stuck_hours: null, weather_slips: null, decisions: 0, waits: 0 }));
    const byLabel = Object.fromEntries(cells.map((c) => [c.label, c]));
    expect(byLabel["Plan kept"]).toEqual({ label: "Plan kept", value: "–", why: "no day trail for this day (before M13)" });
    expect(byLabel["Loads"].value).toBe("2 / –");
    expect(byLabel["Stuck hours"].value).toBe("–");
    expect(byLabel["Weather slips"]).toEqual({ label: "Weather slips", value: "–", why: "the chronicle is not written yet" });
    expect(byLabel["Waits"].value).toBe("–");
  });

  it("titles a day and lists its refusals", () => {
    expect(healthTitle(day({}))).toBe("Day 66");
    expect(healthTitle(day({ final: false }))).toBe("Day 66 (so far)");
    expect(refusalLines(day({}))).toEqual(["30 × someone is not next to you", "7 × you already said that"]);
  });
});
