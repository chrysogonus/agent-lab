import { describe, expect, it } from "vitest";
import type { Run, VillageState, Villager } from "./api";
import {
  cellKind,
  clockText,
  eventLines,
  figures,
  narration,
  placeAreas,
  speeches,
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
  last_action: null,
  speech: null,
  events: [],
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
  map: { width: 20, height: 15, rows: [], places: [] },
  villagers: [],
  ...fields,
});

describe("map", () => {
  it("reads cells", () => {
    expect(["~", "=", ".", "T"].map(cellKind)).toEqual(["water", "path", "grass", "place"]);
  });

  it("boxes each place's cells", () => {
    expect(placeAreas(["..TT", "=.TT", "~~P."])).toEqual({ T: { x0: 2, y0: 0, x1: 3, y1: 1 }, P: { x0: 2, y0: 2, x1: 2, y1: 2 } });
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
});

describe("words", () => {
  it("lists this tick's speeches, or narrates when nobody spoke", () => {
    const talking = state({
      villagers: [villager({ speech: { text: "Fish?", to: "Jonas" } }), villager({ name: "Jonas" })],
    });
    expect(speeches(talking).map((s) => [s.villager.name, s.text, s.to])).toEqual([["Hilde", "Fish?", "Jonas"]]);
    expect(speeches(state({ villagers: [villager({})] }))).toEqual([]);
    expect(narration(state({ tick: 0 }))).toMatch(/Start the village/);
    expect(narration(state({ tick: 3, ticking: true }))).toBe("The villagers are thinking…");
  });

  it("states the clock and the village's status", () => {
    expect(clockText(state({}))).toBe("Day 1, 07:20, morning");
    expect(statusLine(state({ ticking: true, running: true }))).toBe("Ticking…");
    expect(statusLine(state({ running: true, interval: 5 }))).toBe("Running, a tick every 5 s");
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
    expect(eventLines(v).map((e) => `${e.time} ${e.text}`)).toEqual(['06:20 Jonas to you: "Fish!"', "06:10 You arrived at the market."]);
    expect(tickTime(144)).toBe("06:00");
  });

  it("labels turns by what they did", () => {
    const turn = (fields: Partial<Run>) => ({ village_tick: 3, status: "completed", village_action: null, ...fields }) as Run;
    expect(turnLabel(turn({ village_action: { action: "move", place: "pier" } }))).toBe("06:30 walks to the pier");
    expect(turnLabel(turn({ village_action: { action: "say", text: "Hi", to: "Lina" } }))).toBe("06:30 says to Lina: Hi");
    expect(turnLabel(turn({ village_action: { action: "wait", reason: "unknown place 'harbour'" } }))).toBe(
      "06:30 waited: unknown place 'harbour'",
    );
    expect(turnLabel(turn({ status: "running" }))).toBe("06:30 thinking…");
  });
});
