import { describe, expect, it } from "vitest";
import type { Run, VillageState, Villager } from "./api";
import {
  activity,
  cellKind,
  clockText,
  dayOf,
  rhythm,
  eventLines,
  figures,
  logLines,
  narration,
  placeAreas,
  sleepText,
  stateText,
  statusLine,
  tickTime,
  turnLabel,
  whereText,
} from "./village";

const villager = (fields: Partial<Villager>): Villager => ({
  name: "Hilde",
  title: "Mayor Hilde",
  color: "#7c4dcc",
  initial: "H",
  persona: "You are Hilde.",
  agent_id: "custom-1",
  x: 1,
  y: 1,
  place: "town_hall",
  destination: null,
  work: "town_hall",
  last_action: null,
  speech: null,
  events: [],
  asleep: false,
  state: "idle",
  wake: "07:30",
  bed: "23:00",
  goal: null,
  talking_with: [],
  beliefs: [],
  learnings: [],
  views: [],
  memories: [],
  ...fields,
});

const state = (fields: Partial<VillageState>): VillageState => ({
  tick: 8,
  day: 1,
  time: "07:20",
  period: "morning",
  running: false,
  ticking: false,
  interval: 5,
  paused_reason: null,
  log: [],
  map: { width: 32, height: 22, rows: [], places: [], homes: [] },
  villagers: [],
  ...fields,
});

describe("map", () => {
  it("reads cells", () => {
    expect(["~", "=", ".", "T", "t", "i", "B", "h"].map(cellKind)).toEqual(["water", "path", "grass", "place", "tree", "lamp", "building", "building"]);
  });

  it("boxes each place's cells", () => {
    expect(placeAreas(["..TT", "=.TT", "~~P.", "hh.t"])).toEqual({
      T: { x0: 2, y0: 0, x1: 3, y1: 1 },
      P: { x0: 2, y0: 2, x1: 2, y1: 2 },
      h: { x0: 0, y0: 3, x1: 1, y1: 3 },
    });
  });

  it("puts each villager at its cell and spreads villagers who share one", () => {
    const shared = state({
      villagers: [villager({ x: 5, y: 5 }), villager({ name: "Jonas", x: 5, y: 5 }), villager({ name: "Lina", x: 2, y: 3 })],
    });
    const [a, b, c] = figures(shared);
    expect(a.cy).toBe(5.5);
    expect(a.cx).toBeLessThan(5.5);
    expect(b.cx).toBeGreaterThan(5.5);
    expect([c.cx, c.cy]).toEqual([2.5, 3.5]);
  });

  it("picks what each figure is doing", () => {
    expect(activity(villager({ state: "walking", place: null }), true)).toBe("walking");
    expect(activity(villager({ state: "bedtime", place: null }), true)).toBe("walking");
    expect(activity(villager({ state: "walking", place: null }), false)).toBe("idle"); // between two moves
    expect(activity(villager({ state: "talking" }), false)).toBe("talking");
    expect(activity(villager({ state: "deciding" }), false)).toBe("thinking");
    expect(activity(villager({ state: "idle" }), false)).toBe("working"); // idle at the town hall, its work place
    expect(activity(villager({ state: "idle", place: "market" }), false)).toBe("idle");
  });

  it("gives each villager its own rhythm", () => {
    const offsets = ["Hilde", "Jonas", "Greta", "Lina"].map(rhythm);
    expect(new Set(offsets).size).toBe(4);
    expect(offsets.every((o) => o >= 0 && o < 5)).toBe(true);
    expect(rhythm("Hilde")).toBe(rhythm("Hilde"));
  });

  it("leaves sleeping villagers inside their houses", () => {
    const night = state({ villagers: [villager({ asleep: true }), villager({ name: "Jonas", x: 5, y: 5 })] });
    expect(figures(night).map((f) => [f.villager.name, f.cx])).toEqual([["Jonas", 5.5]]);
  });
});

describe("words", () => {
  it("shows the last lines said, or narrates before anyone spoke", () => {
    const log = [1, 2, 3, 4, 5].map((tick) => ({ tick, time: tickTime(tick), from: "Hilde", to: null, text: `Line ${tick}` }));
    expect(logLines(state({ log })).map((l) => l.text)).toEqual(["Line 2", "Line 3", "Line 4", "Line 5"]);
    expect(narration(state({ villagers: [villager({ asleep: true })] }))).toMatch(/Everyone is asleep/);
    expect(narration(state({ villagers: [villager({})] }))).toMatch(/right next to each other/);
  });

  it("says what a villager is doing and when it sleeps", () => {
    expect(stateText(villager({ state: "asleep", asleep: true }))).toBe("Asleep at home");
    expect(stateText(villager({ state: "bedtime" }))).toBe("Going home to bed");
    expect(stateText(villager({ state: "deciding" }))).toBe("Thinking…");
    expect(stateText(villager({ state: "talking", talking_with: ["Greta", "Lina"] }))).toBe("Talking with Greta and Lina");
    expect(stateText(villager({ state: "walking", goal: "looking for Lina" }))).toBe("Looking for Lina");
    expect(stateText(villager({ state: "idle" }))).toBe("At the town hall");
    expect(sleepText(villager({}))).toBe("Up at 07:30, in bed at 23:00");
  });

  it("states the clock and the village's status", () => {
    expect(clockText(state({}))).toBe("Day 1, 07:20, morning");
    expect(statusLine(state({ ticking: true, running: true }))).toBe("Stepping…");
    expect(statusLine(state({ running: true, interval: 5 }))).toBe("Running, a step every 5 s");
    expect(statusLine(state({ paused_reason: "owner" }))).toBe("Paused");
    expect(statusLine(state({ paused_reason: "no viewer for 60 s" }))).toBe("Paused: no viewer for 60 s");
  });

  it("says where a villager is", () => {
    expect(whereText(villager({}))).toBe("At the town hall");
    expect(whereText(villager({ place: null, destination: "flower_garden" }))).toBe("Walking to the flower garden");
    expect(whereText(villager({ place: null }))).toBe("Between places");
  });
});

describe("panel", () => {
  it("lists events newest first with their time", () => {
    const v = villager({
      events: [
        { tick: 1, kind: "arrived", text: "You arrived at the market." },
        { tick: 2, kind: "heard", text: 'Jonas to you: "Fish!"', from: "Jonas", to: "Hilde" },
      ],
    });
    expect(eventLines(v).map((e) => `${e.time} ${e.text}`)).toEqual(['04:50 Jonas to you: "Fish!"', "04:40 You arrived at the market."]);
    expect(tickTime(147)).toBe("05:00");
  });

  it("labels turns by what they did", () => {
    const turn = (fields: Partial<Run>) => ({ village_tick: 3, status: "completed", village_action: null, ...fields }) as Run;
    expect(turnLabel(turn({ village_action: { action: "move", place: "pier" } }))).toBe("05:00 walks to the pier");
    expect(turnLabel(turn({ village_action: { action: "move", place: "home" } }))).toBe("05:00 walks home");
    expect(turnLabel(turn({ village_action: { action: "find", villager: "Lina" } }))).toBe("05:00 goes looking for Lina");
    expect(turnLabel(turn({ village_action: { action: "say", text: "Hi", to: "Lina" } }))).toBe("05:00 says to Lina: Hi");
    expect(turnLabel(turn({ village_action: { action: "goodbye", text: "Bye!" } }))).toBe("05:00 says goodbye: Bye!");
    expect(turnLabel(turn({ village_action: { action: "wait", reason: "unknown place 'harbour'" } }))).toBe(
      "05:00 waited: unknown place 'harbour'",
    );
    expect(turnLabel(turn({ status: "running" }))).toBe("05:00 thinking…");
    expect(turnLabel(turn({ village_tick: 105, village_action: { action: "reflect", learnings: ["x"], views: {} } }))).toBe(
      "22:00 reflects on day 1",
    );
    expect(turnLabel(turn({ village_action: { action: "reflect", reason: "the answer is not JSON" } }))).toBe(
      "05:00 could not reflect: the answer is not JSON",
    );
    expect(dayOf(116)).toBe(1);
    expect(dayOf(117)).toBe(2);
  });
});
