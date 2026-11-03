import { describe, expect, it } from "vitest";
import type { ChronicleEntry, Happening, Intention, Meeting, Project, Run, VillageState, Villager } from "./api";
import {
  activity,
  cellKind,
  clockText,
  dayOf,
  glideMs,
  rhythm,
  eventLines,
  figures,
  logLines,
  narration,
  placeAreas,
  sleepText,
  stateText,
  statusLine,
  PACES,
  paceOf,
  tickTime,
  turnLabel,
  whereText,
  calendarText,
  newEntries,
  planEntryText,
  stallsText,
  carriedText,
  traderText,
  meetingLines,
  projectLines,
  boxOf,
  builtLines,
  intentionText,
  happeningMarks,
  boatPlace,
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
  plan: null,
  basket: null,
  working: null,
  intention: null,
  keepsakes: [],
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
  map: { width: 32, height: 22, rows: [], places: [], homes: [], catalogue: [] },
  villagers: [],
  calendar: { year: 1, season: "spring", day_of_season: 1, festival_in: null },
  weather: "sun",
  snow_cover: false,
  sky: "morning",
  dark: false,
  growth: { fields: { stage: "resting", neglected: false }, flower_garden: { stage: "budding" } },
  chronicle: [],
  stalls: { fish: 0, vegetables: 0, flowers: 0 },
  trader: null,
  meeting: null,
  next_meeting: 3,
  project: null,
  built: [],
  happenings: [],
  boat: null,
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
    expect(activity(villager({ state: "idle", place: "town_hall" }), true)).toBe("walking"); // gliding into its last cell
    expect(activity(villager({ state: "talking" }), false)).toBe("talking");
    expect(activity(villager({ state: "deciding" }), false)).toBe("thinking");
    expect(activity(villager({ state: "idle" }), false)).toBe("working"); // idle at the town hall, its work place
    expect(activity(villager({ state: "idle", place: "market" }), false)).toBe("idle");
  });

  it("glides each move until the next one", () => {
    expect(glideMs(state({ running: true, interval: 6 }))).toBe(2000);
    expect(glideMs(state({ running: false }))).toBe(100); // Step
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
    expect(statusLine(state({ running: true, interval: 5 }))).toBe("Running at Normal pace");
    expect(statusLine(state({ running: true, interval: 15 }))).toBe("Running at Slow pace");
    expect(statusLine(state({ running: true, interval: 7 }))).toBe("Running, a step every 7 s");
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
    expect(turnLabel(turn({ village_action: { action: "chronicle", day: 3, title: "Rain" } }))).toBe("05:00 writes the chronicle of day 3");
    expect(turnLabel(turn({ village_action: { action: "chronicle", day: 3, reason: "no answer" } }))).toBe(
      "05:00 could not write the chronicle: no answer",
    );
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

describe("paces", () => {
  it("are Slow, Normal and Fast at 15, 5 and 2 seconds a step", () => {
    expect(PACES.map((p) => [p.label, p.seconds])).toEqual([
      ["Slow", 15],
      ["Normal", 5],
      ["Fast", 2],
    ]);
    expect(paceOf(2)?.label).toBe("Fast");
    expect(paceOf(7)).toBeNull();
  });
});

describe("seasons and the chronicle", () => {
  it("names the date", () => {
    expect(calendarText(state({ calendar: { year: 2, season: "autumn", day_of_season: 3, festival_in: 4 } }))).toBe("Day 3 of autumn, year 2");
  });

  it("counts the entries written since the owner last looked", () => {
    const entry = (run_id: string): ChronicleEntry => ({ day: 1, year: 1, season: "spring", day_of_season: 1, weather: "sun", title: "t", text: "x", run_id });
    const chronicle = [entry("c"), entry("b"), entry("a")]; // newest first
    expect(newEntries(chronicle, "a")).toBe(2);
    expect(newEntries(chronicle, "c")).toBe(0);
    expect(newEntries(chronicle, null)).toBe(3);
    expect(newEntries(chronicle, "gone")).toBe(3); // e.g. after a reset
  });
});

describe("plans", () => {
  it("names a place or a villager to see", () => {
    expect(planEntryText({ time: "07:30", place: "town hall", villager: null, purpose: "Go through the list" })).toBe(
      "07:30 town hall: Go through the list",
    );
    expect(planEntryText({ time: "11:00", place: null, villager: "Jonas", purpose: "Ask for fish" })).toBe("11:00 see Jonas: Ask for fish");
  });

  it("labels plan runs among the turns", () => {
    const run = (village_action: Run["village_action"]) =>
      ({ village_tick: 3, status: "completed", village_action }) as Run;
    expect(turnLabel(run({ action: "plan", revision: 0, entries: ["05:00 pier: fish"] }))).toBe("05:00 plans the day");
    expect(turnLabel(run({ action: "plan", revision: 1, entries: ["05:00 pier: fish"] }))).toBe("05:00 changes the plan");
    expect(turnLabel(run({ action: "plan", revision: 0, reason: "a plan needs at least 2 entries" }))).toBe(
      "05:00 could not plan: a plan needs at least 2 entries",
    );
  });
});

describe("work and the festival stalls", () => {
  it("says where a villager works", () => {
    expect(stateText(villager({ state: "working", place: "fields", working: "fields" }))).toBe("Working at the fields");
    expect(stateText(villager({ state: "working", place: "flower_garden", working: "flower_garden" }))).toBe("Working at the flower garden");
  });

  it("labels work and give turns", () => {
    const run = (village_action: Run["village_action"]) => ({ village_tick: 3, status: "completed", village_action }) as Run;
    expect(turnLabel(run({ action: "work", place: "flower_garden" }))).toBe("05:00 works at the flower garden");
    expect(turnLabel(run({ action: "give", to: "Hilde", goods: "fish" }))).toBe("05:00 gives a basket of fish to Hilde");
    expect(turnLabel(run({ action: "give", to: null, goods: "flowers" }))).toBe("05:00 sets out flowers on the festival stalls");
    expect(turnLabel(run({ action: "wait", reason: "your hands are empty" }))).toBe("05:00 waited: your hands are empty");
  });

  it("says what the stalls hold and lack", () => {
    expect(stallsText({ fish: 0, vegetables: 0, flowers: 0 })).toBe(
      "The festival stalls on the square are empty; they still lack fish, vegetables and flowers.",
    );
    expect(stallsText({ fish: 2, vegetables: 0, flowers: 1 })).toBe("The festival stalls on the square hold fish and flowers; they still lack vegetables.");
    expect(stallsText({ fish: 1, vegetables: 1, flowers: 1 })).toBe("The festival stalls on the square hold fish, vegetables and flowers.");
  });
});

describe("the daily trader", () => {
  it("names what a villager carries", () => {
    expect(carriedText("fish")).toBe("basket of fish");
    expect(carriedText("wood")).toBe("load of wood");
    expect(carriedText("saplings")).toBe("load of saplings");
  });

  it("says whether the trader is coming, here or gone", () => {
    expect(traderText(state({ time: "07:20" }))).toBe("A trader comes to the market at 09:00.");
    const stock = { wood: 4, paint: 0, saplings: 1 };
    expect(traderText(state({ time: "10:00", trader: { stock, leaves: "14:00" } }))).toBe(
      "A trader is at the market until 14:00: wood (4) and saplings (1).",
    );
    const sold = { wood: 0, paint: 0, saplings: 0 };
    expect(traderText(state({ time: "10:00", trader: { stock: sold, leaves: "14:00" } }))).toBe(
      "A trader is at the market until 14:00 and has sold everything.",
    );
    expect(traderText(state({ time: "15:00" }))).toBe("The trader has left; the next comes tomorrow at 09:00.");
  });

  it("labels buy turns and gives loads", () => {
    const run = (village_action: Run["village_action"]) => ({ village_tick: 3, status: "completed", village_action }) as Run;
    expect(turnLabel(run({ action: "buy", goods: "wood", paid: "fish" }))).toBe("05:00 trades a basket of fish for a load of wood");
    expect(turnLabel(run({ action: "give", to: "Hilde", goods: "paint" }))).toBe("05:00 gives a load of paint to Hilde");
    expect(turnLabel(run({ action: "wait", reason: "the trader has no paint left" }))).toBe("05:00 waited: the trader has no paint left");
  });
});

describe("the town hall meeting", () => {
  const meeting = (fields: Partial<Meeting>): Meeting => ({
    day: 3,
    kind: "vote",
    proposals: [
      { key: "market_stand", name: "A market stand", reason: "Greta needs it.", run_id: "p1" },
      { key: "paint_lina", name: "Paint Lina's house", reason: "It is grey.", run_id: "p1" },
    ],
    votes: [],
    present: [],
    decision: null,
    outcome: null,
    ...fields,
  });

  it("lists the proposals, who came and the votes", () => {
    const votes = [
      { villager: "Greta", key: "market_stand", name: "A market stand", reason: "I sell there.", run_id: "v1" },
      { villager: "Jonas", key: "market_stand", name: "A market stand", reason: "Why not.", run_id: "v2" },
      { villager: "Lina", key: null, name: null, reason: "a castle is not one of Hilde's proposals", run_id: "v3" },
    ];
    expect(meetingLines(meeting({ votes, present: ["Hilde", "Greta", "Jonas", "Lina"] }))).toEqual([
      { text: "Hilde proposed A market stand: Greta needs it.", runId: "p1" },
      { text: "Hilde proposed Paint Lina's house: It is grey.", runId: null },
      { text: "At the town hall: Hilde, Greta, Jonas and Lina", runId: null },
      { text: "Greta voted for A market stand: I sell there.", runId: "v1" },
      { text: "Jonas voted for A market stand: Why not.", runId: "v2" },
      { text: "Lina's vote did not count: a castle is not one of Hilde's proposals", runId: "v3" },
      { text: "Most votes: A market stand (2)", runId: null },
    ]);
  });

  it("tells the decision, against the vote or by it", () => {
    const against = { key: "paint_lina", name: "Paint Lina's house", reason: "Lina deserves it.", against: true, by: "hilde" as const, run_id: "d1" };
    expect(meetingLines(meeting({ decision: against, outcome: "decided", present: ["Hilde"] })).slice(-1)).toEqual([
      { text: "Hilde chose Paint Lina's house: Lina deserves it. She went against the vote.", runId: "d1" },
    ]);
    const byVote = { ...against, against: false, by: "vote" as const, key: "market_stand", name: "A market stand", reason: "Hilde gave no valid decision; the vote decided" };
    expect(meetingLines(meeting({ decision: byVote, outcome: "decided" })).slice(-1)).toEqual([
      { text: "The vote chose A market stand: Hilde gave no valid decision.", runId: "d1" },
    ]);
  });

  it("says when a meeting was called off or reviewed", () => {
    expect(meetingLines(meeting({ outcome: "called off: Hilde did not come" })).slice(-1)).toEqual([{ text: "Called off: Hilde did not come.", runId: null }]);
    expect(meetingLines(meeting({ kind: "review", proposals: [], outcome: "reviewed" }))).toEqual([
      { text: "A meeting about how the building goes.", runId: null },
      { text: "Nobody came to the town hall.", runId: null },
      { text: "Reviewed.", runId: null },
    ]);
  });

  it("labels proposal, vote and decision runs", () => {
    const run = (village_action: Run["village_action"]) => ({ village_tick: 3, status: "completed", village_action }) as Run;
    expect(turnLabel(run({ action: "propose", proposals: ["A market stand: x", "Paint Lina's house: y"] }))).toBe("05:00 proposes 2 projects for the meeting");
    expect(turnLabel(run({ action: "propose", reason: "no project Hilde proposed can be built" }))).toBe(
      "05:00 could not propose: no project Hilde proposed can be built",
    );
    expect(turnLabel(run({ action: "vote", project: "A market stand", reason: "x" }))).toBe("05:00 votes for A market stand");
    expect(turnLabel(run({ action: "vote", reason: "the answer is not JSON" }))).toBe("05:00 could not vote: the answer is not JSON");
    expect(turnLabel(run({ action: "decide", project: "Paint Lina's house", reason: "x", against: true, by: "hilde" }))).toBe(
      "05:00 decides on Paint Lina's house, against the vote",
    );
    expect(turnLabel(run({ action: "decide", project: "A market stand", reason: "x", against: false, by: "vote" }))).toBe(
      "05:00 decides on A market stand (the vote decided)",
    );
    expect(turnLabel(run({ action: "decide", reason: "no answer" }))).toBe("05:00 could not decide: no answer");
  });
});

describe("the project", () => {
  const project: Project = {
    key: "market_stand",
    name: "A market stand",
    kind: "stand",
    needs: { wood: 3, paint: 1 },
    site: { wood: 1, paint: 0, saplings: 0 },
    used: { wood: 1, paint: 0, saplings: 0 },
    done: 1,
    total: 4,
    tasks: [
      { task: "buy", goods: "wood", villagers: ["Jonas", "Greta"] },
      { task: "build", goods: null, villagers: ["Greta"] },
    ],
    day: 3,
    work: 2,
  };

  it("says what is needed, what lies at the site and who does what", () => {
    expect(projectLines(project)).toEqual([
      "Still to bring: 1 wood and 1 paint",
      "At the building site: 1 wood",
      "Buy wood from the trader: Jonas and Greta",
      "Build at the building site: Greta",
    ]);
    expect(projectLines({ ...project, site: { wood: 0, paint: 0, saplings: 0 }, used: { wood: 3, paint: 1, saplings: 0 }, tasks: [] })).toEqual([
      "Everything has been brought",
      "At the building site: nothing",
      "Hilde has not handed out the work yet",
    ]);
  });

  it("labels work-plan runs", () => {
    const run = (village_action: Run["village_action"]) => ({ village_tick: 3, status: "completed", village_action }) as Run;
    expect(turnLabel(run({ action: "assign", tasks: ["buy wood: Jonas", "build: Greta"] }))).toBe("05:00 hands out 2 tasks");
    expect(turnLabel(run({ action: "assign", reason: "no usable task in the work plan" }))).toBe("05:00 could not hand out the work: no usable task in the work plan");
  });
});

describe("building and what stands", () => {
  it("reads building plots and boxes cells", () => {
    expect(["b", "r"].map(cellKind)).toEqual(["plot", "plot"]);
    expect(placeAreas(["bb.", "bb."])).toEqual({});
    expect(boxOf([[14, 13], [17, 14], [15, 13]])).toEqual({ x0: 14, y0: 13, x1: 17, y1: 14 });
  });

  it("says who builds and what is set down", () => {
    expect(stateText(villager({ state: "working", working: "site", place: null }))).toBe("Building at the site");
    const run = (village_action: Run["village_action"]) => ({ village_tick: 3, status: "completed", village_action }) as Run;
    expect(turnLabel(run({ action: "give", to: null, goods: "paint" }))).toBe("05:00 sets down a load of paint at the building site");
    expect(turnLabel(run({ action: "work", place: "site" }))).toBe("05:00 works at the building site");
    expect(turnLabel(run({ action: "move", place: "site" }))).toBe("05:00 walks to the building site");
  });

  it("lists what has been built", () => {
    expect(builtLines([])).toEqual([]);
    expect(builtLines([{ key: "boat", name: "A rowing boat", kind: "boat", day: 9 }])).toEqual(["Day 9: A rowing boat"]);
  });
});

describe("intentions (M14)", () => {
  const intention = (fields: Partial<Intention>): Intention => ({
    kind: "go",
    place: "market",
    villager: null,
    until: null,
    purpose: null,
    since: "09:30",
    ...fields,
  });

  it("says what a villager is set on", () => {
    expect(intentionText(intention({}))).toBe("Going to the market");
    expect(intentionText(intention({ place: "home" }))).toBe("Going home");
    expect(intentionText(intention({ kind: "work", place: "fields", until: "12:00" }))).toBe("Working at the fields until 12:00");
    expect(intentionText(intention({ kind: "build", place: "site", until: "15:00" }))).toBe("Building at the site until 15:00");
    expect(intentionText(intention({ kind: "bring", place: "site" }))).toBe("Taking a load to the building site");
    expect(intentionText(intention({ kind: "see", place: null, villager: "Greta" }))).toBe("Going to see Greta");
  });

  it("shows the intention as the villager's state while it walks or works", () => {
    const building = intention({ kind: "build", place: "site", until: "15:00" });
    expect(stateText(villager({ state: "walking", goal: "walking to the building site", intention: building }))).toBe("Building at the site until 15:00");
    expect(stateText(villager({ state: "working", working: "site", intention: building }))).toBe("Building at the site until 15:00");
    expect(stateText(villager({ state: "talking", talking_with: ["Lina"], intention: building }))).toBe("Talking with Lina");
  });

  it("labels turns that set out on something", () => {
    const turn = (village_action: Run["village_action"]) => ({ village_tick: 3, status: "completed", village_action }) as Run;
    const until = intention({ kind: "work", place: "fields", until: "12:00" });
    expect(turnLabel(turn({ action: "work", place: "fields", intention: until }))).toBe("05:00 works at the fields until 12:00");
    expect(turnLabel(turn({ action: "build", intention: intention({ kind: "build", place: "site", until: "15:00" }) }))).toBe("05:00 sets out to build at the site until 15:00");
    expect(turnLabel(turn({ action: "build" }))).toBe("05:00 sets out to build at the site");
    expect(turnLabel(turn({ action: "bring" }))).toBe("05:00 takes a load to the building site");
    expect(turnLabel(turn({ action: "find", villager: "Lina", say: "Flowers?" }))).toBe("05:00 goes looking for Lina to say: Flowers?");
    expect(turnLabel(turn({ action: "build", reason: "nothing is being built" }))).toBe("05:00 waited: nothing is being built");
  });
});

describe("happenings (M15)", () => {
  const happening = (fields: Partial<Happening>): Happening => ({
    kind: "animal",
    label: "Greta's goat wandered to the market.",
    cell: [22, 8],
    state: "here",
    by: null,
    concerns: "Greta",
    start: "09:00",
    end: "19:00",
    figure: "animal",
    ...fields,
  });

  it("marks what to draw on the map, centred in its cell", () => {
    const marks = happeningMarks(
      state({ happenings: [happening({}), happening({ kind: "peddler", figure: null, cell: [12, 7] })] }),
    );
    expect(marks).toEqual([{ key: "animal-22-8", figure: "animal", cx: 22.5, cy: 8.5, label: "Greta's goat wandered to the market." }]);
  });

  it("labels leading an animal home and trading with the peddler", () => {
    const turn = (village_action: Run["village_action"]) => ({ village_tick: 3, status: "completed", village_action }) as Run;
    expect(turnLabel(turn({ action: "lead" }))).toBe("05:00 takes a lost animal home");
    expect(turnLabel(turn({ action: "buy", goods: "a lantern", paid: "flowers" }))).toBe("05:00 trades a basket of flowers for a lantern from the peddler");
    expect(turnLabel(turn({ action: "buy", goods: "wood", paid: "fish" }))).toBe("05:00 trades a basket of fish for a load of wood");
  });
});

describe("the boat (M15)", () => {
  it("places the boat at its cell, or nowhere without one", () => {
    expect(boatPlace(state({}))).toBeNull();
    expect(boatPlace(state({ boat: { state: "out", rowers: ["Jonas"], cell: [23, 20] } }))).toEqual({ x: 23 * 16, y: 20 * 16 });
  });

  it("labels rowing", () => {
    const turn = (village_action: Run["village_action"]) => ({ village_tick: 3, status: "completed", village_action }) as Run;
    expect(turnLabel(turn({ action: "row" }))).toBe("05:00 takes the boat out on the lake");
    expect(turnLabel(turn({ action: "row", with: "Greta" }))).toBe("05:00 takes the boat out on the lake with Greta");
  });
});
