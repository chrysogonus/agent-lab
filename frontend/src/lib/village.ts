// Village view logic: map tiles, figures, speech and panel lines. Pure; components stay thin.
import type { ChronicleEntry, PlanEntry, Run, VillageEvent, VillageState, Villager } from "./api";

export type CellKind = "grass" | "path" | "water" | "tree" | "lamp" | "building" | "place";

/** B is the town hall building, h j g l the villagers' houses (specs/007-village-life). */
export function cellKind(char: string): CellKind {
  if (char === "~") return "water";
  if (char === "=") return "path";
  if (char === ".") return "grass";
  if (char === "t") return "tree";
  if (char === "i") return "lamp";
  if ("Bhjgl".includes(char)) return "building";
  return "place";
}

export type Area = { x0: number; y0: number; x1: number; y1: number };

/** The cells each place or building letter covers, as a box: where it is drawn. */
export function placeAreas(rows: string[]): Record<string, Area> {
  const areas: Record<string, Area> = {};
  rows.forEach((row, y) =>
    [...row].forEach((char, x) => {
      const kind = cellKind(char);
      if (kind !== "place" && kind !== "building") return;
      const a = areas[char];
      areas[char] = a ? { x0: Math.min(a.x0, x), y0: Math.min(a.y0, y), x1: Math.max(a.x1, x), y1: Math.max(a.y1, y) } : { x0: x, y0: y, x1: x, y1: y };
    }),
  );
  return areas;
}

type Light = { color: string; opacity: number };

/** The sky's light over the map, top to bottom: peach mornings, clear middays, a sunset glow
 * from the top in the evening, deep blue nights. */
export const PERIOD_SKY: Record<VillageState["period"], { top: Light; bottom: Light }> = {
  morning: { top: { color: "#ffb36b", opacity: 0.24 }, bottom: { color: "#ffe2b0", opacity: 0.04 } },
  midday: { top: { color: "#fff6d8", opacity: 0.08 }, bottom: { color: "#ffffff", opacity: 0 } },
  afternoon: { top: { color: "#ffcf7a", opacity: 0.16 }, bottom: { color: "#ffe6a8", opacity: 0.04 } },
  evening: { top: { color: "#ff7a59", opacity: 0.36 }, bottom: { color: "#4b2a6b", opacity: 0.4 } },
  night: { top: { color: "#0b1240", opacity: 0.64 }, bottom: { color: "#1a2260", opacity: 0.5 } },
};

export type Activity = "walking" | "talking" | "thinking" | "working" | "idle";

/** What a figure shows: its walk while it glides between cells (also the last cell, though the
 * state already says it arrived), its talk, a thought bubble, its work at its own place, or idling. */
export function activity(villager: Villager, moving: boolean): Activity {
  if (moving) return "walking";
  if (villager.state === "talking") return "talking";
  if (villager.state === "deciding") return "thinking";
  return villager.place === villager.work ? "working" : "idle";
}

const CELLS_PER_STEP = 3; // as backend village/runner.py: a walker moves this often per step
const STEP_GLIDE_MS = 100; // Step moves its walkers 0.1 s apart

/** How long a figure glides to its next cell: until its next move, so walking looks continuous. */
export function glideMs(state: VillageState): number {
  return state.running ? (state.interval * 1000) / CELLS_PER_STEP : STEP_GLIDE_MS;
}

/** A stable offset in seconds per villager, so idle animations do not run in sync. */
export function rhythm(name: string): number {
  return ([...name].reduce((sum, c) => sum * 31 + c.charCodeAt(0), 7) % 50) / 10;
}

export type Figure = { villager: Villager; cx: number; cy: number };

/** One figure per awake villager at its cell centre; villagers sharing a cell are spread apart. */
export function figures(state: VillageState): Figure[] {
  const seen = new Map<string, number>();
  const awake = state.villagers.filter((v) => !v.asleep); // sleepers are inside their houses
  return awake.map((villager) => {
    const key = `${villager.x},${villager.y}`;
    const index = seen.get(key) ?? 0;
    seen.set(key, index + 1);
    const shared = awake.filter((v) => v.x === villager.x && v.y === villager.y).length;
    const offset = shared > 1 ? (index - (shared - 1) / 2) * 0.6 : 0;
    return { villager, cx: villager.x + 0.5 + offset, cy: villager.y + 0.5 };
  });
}

/** The dialog box: the last lines said in the village, newest last. */
export function logLines(state: VillageState, count = 4): VillageState["log"] {
  return state.log.slice(-count);
}

/** What the dialog box says before anyone has spoken. */
export function narration(state: VillageState): string {
  if (state.villagers.every((v) => v.asleep)) return "Everyone is asleep. Start the village to see who gets up first.";
  return "Nobody has said anything yet. Villagers talk when they stand right next to each other.";
}

/** A villager's state in words, for the list: "Asleep at home", "Talking with Greta", … */
export function stateText(villager: Villager): string {
  switch (villager.state) {
    case "asleep":
      return "Asleep at home";
    case "bedtime":
      return "Going home to bed";
    case "deciding":
      return "Thinking…";
    case "talking":
      return `Talking with ${villager.talking_with.join(" and ")}`;
    case "walking":
      return villager.goal ? villager.goal[0].toUpperCase() + villager.goal.slice(1) : "Walking";
    default:
      return whereText(villager);
  }
}

export function sleepText(villager: Villager): string {
  return `Up at ${villager.wake}, in bed at ${villager.bed}`;
}

export function clockText(state: VillageState): string {
  return `Day ${state.day}, ${state.time}, ${state.period}`;
}

/** Seconds per 10-minute step while anyone is awake; nights pass quickly at every pace. */
export const PACES = [
  { label: "Slow", seconds: 15 },
  { label: "Normal", seconds: 5 },
  { label: "Fast", seconds: 2 },
] as const;

export function paceOf(interval: number): (typeof PACES)[number] | null {
  return PACES.find((p) => p.seconds === interval) ?? null;
}

export function statusLine(state: VillageState): string {
  if (state.ticking) return "Stepping…";
  const pace = paceOf(state.interval);
  if (state.running) return pace ? `Running at ${pace.label} pace` : `Running, a step every ${state.interval} s`;
  if (state.paused_reason === "owner" || !state.paused_reason) return "Paused";
  return `Paused: ${state.paused_reason}`;
}

const TICK_MINUTES = 10;

/** "07:10" for a step (the clock starts at 04:30). */
export function tickTime(tick: number): string {
  const minutes = (270 + tick * TICK_MINUTES) % 1440;
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

/** "07:10 You arrived at the market." — newest first. */
export function eventLines(villager: Villager): { key: string; time: string; text: string; kind: VillageEvent["kind"] }[] {
  return [...villager.events]
    .reverse()
    .map((e, i) => ({ key: `${e.tick}-${i}`, time: tickTime(e.tick), text: e.text, kind: e.kind }));
}

const PLACE_LABELS: Record<string, string> = {
  town_hall: "town hall",
  square: "square",
  market: "market",
  pier: "pier",
  fields: "fields",
  flower_garden: "flower garden",
};

export function placeLabel(key: string | null): string | null {
  return key ? (PLACE_LABELS[key] ?? key) : null;
}

/** Where a villager is, in words: "At the market", "Walking to the pier", "Between places". */
export function whereText(villager: Villager): string {
  if (villager.asleep) return "Asleep at home";
  if (villager.place) return `At the ${placeLabel(villager.place)}`;
  if (villager.destination) return `Walking to the ${placeLabel(villager.destination)}`;
  return "Between places";
}

/** The village day a step belongs to (day 1 starts at 04:30 with step 0). */
export function dayOf(tick: number): number {
  return 1 + Math.floor((270 + tick * TICK_MINUTES) / 1440);
}

/** One line for a turn: its time and what it did (or why it waited). */
export function turnLabel(turn: Run): string {
  const time = turn.village_tick == null ? "" : `${tickTime(turn.village_tick)} `;
  const action = turn.village_action;
  if (!action) return `${time}${turn.status === "running" ? "thinking…" : "no action recorded"}`;
  if (action.action === "chronicle") {
    return action.reason ? `${time}could not write the chronicle: ${action.reason}` : `${time}writes the chronicle of day ${action.day}`;
  }
  if (action.action === "plan") {
    if (action.reason) return `${time}could not plan: ${action.reason}`;
    return `${time}${action.revision ? "changes the plan" : "plans the day"}`;
  }
  if (action.action === "reflect") {
    const day = turn.village_tick == null ? "" : ` on day ${dayOf(turn.village_tick)}`;
    return action.reason ? `${time}could not reflect: ${action.reason}` : `${time}reflects${day}`;
  }
  if (action.reason) return `${time}waited: ${action.reason}`;
  if (action.action === "move") return `${time}walks ${action.place === "home" ? "home" : `to the ${placeLabel(action.place)}`}`;
  if (action.action === "find") return `${time}goes looking for ${action.villager}`;
  if (action.action === "goodbye") return `${time}says goodbye${action.text ? `: ${action.text}` : ""}`;
  if (action.action === "say") return `${time}says${action.to ? ` to ${action.to}` : ""}: ${action.text}`;
  return `${time}waits`;
}

/** "07:30 town hall: Go through the list", "11:00 see Jonas: Ask for fish" */
export function planEntryText(entry: PlanEntry): string {
  return `${entry.time} ${entry.villager ? `see ${entry.villager}` : entry.place}: ${entry.purpose}`;
}

/** "Day 3 of autumn, year 1" */
export function calendarText({ calendar }: Pick<VillageState, "calendar">): string {
  return `Day ${calendar.day_of_season} of ${calendar.season}, year ${calendar.year}`;
}

/** Entries written since the owner last looked: newer than the one seen, all if it is gone. */
export function newEntries(chronicle: ChronicleEntry[], seenRunId: string | null): number {
  const seen = chronicle.findIndex((e) => e.run_id === seenRunId);
  return seen === -1 ? chronicle.length : seen;
}
