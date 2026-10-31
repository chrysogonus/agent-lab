// Village view logic: map tiles, figures, speech and panel lines. Pure; components stay thin.
import type { Run, VillageEvent, VillageState, Villager } from "./api";

export type CellKind = "grass" | "path" | "water" | "place";

export function cellKind(char: string): CellKind {
  if (char === "~") return "water";
  if (char === "=") return "path";
  if (char === ".") return "grass";
  return "place";
}

// Soft tiles so the villagers' colors stand out; each place has its own tint for orientation.
export const TILE_FILL: Record<string, string> = {
  ".": "#dfe8d3",
  "=": "#ebe1c9",
  "~": "#bcd3e6",
  T: "#e1dbee",
  S: "#ece5d3",
  M: "#f2e1cb",
  P: "#d8c9b2",
  F: "#e7dfb0",
  G: "#f2d8e2",
};

/** The map darkens toward the night, so the time can be read from it. */
export const PERIOD_SHADE: Record<VillageState["period"], number> = {
  morning: 0,
  midday: 0,
  afternoon: 0.04,
  evening: 0.16,
  night: 0.34,
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
    const offset = shared > 1 ? (index - (shared - 1) / 2) * 0.32 : 0;
    return { villager, cx: villager.x + 0.5 + offset, cy: villager.y + 0.5 };
  });
}

/** "Hilde → Jonas: …" or "Hilde: …" for this tick's speech; null when silent. */
export function speechText(villager: Villager): string | null {
  if (!villager.speech) return null;
  const who = villager.speech.to ? `${villager.name} → ${villager.speech.to}` : villager.name;
  return `${who}: ${villager.speech.text}`;
}

/** The bubble shows the start; the full words are in the panel and the turn. */
export function bubbleText(text: string, max = 46): string {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
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
