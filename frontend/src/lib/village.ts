// Village view logic: map tiles, figures, speech and panel lines. Pure; components stay thin.
import type { Run, VillageEvent, VillageState, Villager } from "./api";

export type CellKind = "grass" | "path" | "water" | "place";

export function cellKind(char: string): CellKind {
  if (char === "~") return "water";
  if (char === "=") return "path";
  if (char === ".") return "grass";
  return "place";
}

export type Area = { x0: number; y0: number; x1: number; y1: number };

/** The cells each place letter covers, as a box: where its building or scenery is drawn. */
export function placeAreas(rows: string[]): Record<string, Area> {
  const areas: Record<string, Area> = {};
  rows.forEach((row, y) =>
    [...row].forEach((char, x) => {
      if (cellKind(char) !== "place") return;
      const a = areas[char];
      areas[char] = a ? { x0: Math.min(a.x0, x), y0: Math.min(a.y0, y), x1: Math.max(a.x1, x), y1: Math.max(a.y1, y) } : { x0: x, y0: y, x1: x, y1: y };
    }),
  );
  return areas;
}

/** The light over the map: warm in the morning, dusky in the evening, dark blue at night. */
export const PERIOD_TINT: Record<VillageState["period"], { color: string; opacity: number }> = {
  morning: { color: "#ffcf8a", opacity: 0.08 },
  midday: { color: "#ffffff", opacity: 0 },
  afternoon: { color: "#ffb070", opacity: 0.07 },
  evening: { color: "#4b2a6b", opacity: 0.3 },
  night: { color: "#101642", opacity: 0.52 },
};

export type Figure = { villager: Villager; cx: number; cy: number };

/** One figure per villager at its cell centre; villagers sharing a cell are spread apart. */
export function figures(state: VillageState): Figure[] {
  const seen = new Map<string, number>();
  return state.villagers.map((villager) => {
    const key = `${villager.x},${villager.y}`;
    const index = seen.get(key) ?? 0;
    seen.set(key, index + 1);
    const shared = state.villagers.filter((v) => v.x === villager.x && v.y === villager.y).length;
    const offset = shared > 1 ? (index - (shared - 1) / 2) * 0.6 : 0;
    return { villager, cx: villager.x + 0.5 + offset, cy: villager.y + 0.5 };
  });
}

/** This tick's speeches, for the dialog box under the map. */
export function speeches(state: VillageState): { villager: Villager; text: string; to: string | null }[] {
  return state.villagers.flatMap((villager) => (villager.speech ? [{ villager, ...villager.speech }] : []));
}

/** What the dialog box says when nobody spoke this tick. */
export function narration(state: VillageState): string {
  if (state.tick === 0 && !state.running) return "Everyone is still at home. Start the village to wake them up.";
  if (state.ticking) return "The villagers are thinking…";
  return state.period === "night" ? "The village is asleep. Nobody is talking." : "Nobody is talking right now.";
}

export function clockText(state: VillageState): string {
  return `Day ${state.day}, ${state.time}, ${state.period}`;
}

export function statusLine(state: VillageState): string {
  if (state.ticking) return "Ticking…";
  if (state.running) return `Running, a tick every ${state.interval} s`;
  if (state.paused_reason === "owner" || !state.paused_reason) return "Paused";
  return `Paused: ${state.paused_reason}`;
}

const TICK_MINUTES = 10;

/** "07:10" for a tick (the clock starts at 06:00). */
export function tickTime(tick: number): string {
  const minutes = (360 + tick * TICK_MINUTES) % 1440;
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
  if (villager.place) return `At the ${placeLabel(villager.place)}`;
  if (villager.destination) return `Walking to the ${placeLabel(villager.destination)}`;
  return "Between places";
}

/** One line for a turn: its time and what it did (or why it waited). */
export function turnLabel(turn: Run): string {
  const time = turn.village_tick == null ? "" : `${tickTime(turn.village_tick)} `;
  const action = turn.village_action;
  if (!action) return `${time}${turn.status === "running" ? "thinking…" : "no action recorded"}`;
  if (action.reason) return `${time}waited: ${action.reason}`;
  if (action.action === "move") return `${time}walks to the ${placeLabel(action.place)}`;
  if (action.action === "say") return `${time}says${action.to ? ` to ${action.to}` : ""}: ${action.text}`;
  return `${time}waits`;
}
