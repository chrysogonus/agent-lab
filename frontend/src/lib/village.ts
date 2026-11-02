// Village view logic: map tiles, figures, speech and panel lines. Pure; components stay thin.
import type { BasketGoods, BuildingGoods, ChronicleEntry, Goods, Meeting, PlanEntry, Project, Run, Stalls, Task, VillageEvent, VillageState, Villager } from "./api";

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
    case "working":
      return `Working at the ${placeLabel(villager.working)}`;
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

type MeetingAction = Extract<NonNullable<Run["village_action"]>, { action: "propose" | "vote" | "decide" | "assign" }>;

function meetingLabel(time: string, action: MeetingAction): string {
  if (action.action === "assign") {
    return action.tasks ? `${time}hands out ${action.tasks.length} tasks` : `${time}could not hand out the work: ${action.reason}`;
  }
  if (action.action === "propose") {
    return action.proposals ? `${time}proposes ${action.proposals.length} projects for the meeting` : `${time}could not propose: ${action.reason}`;
  }
  if (action.action === "vote") return action.project ? `${time}votes for ${action.project}` : `${time}could not vote: ${action.reason}`;
  if (!action.project) return `${time}could not decide: ${action.reason}`;
  return `${time}decides on ${action.project}${action.by === "vote" ? " (the vote decided)" : action.against ? ", against the vote" : ""}`;
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
  if (action.action === "propose" || action.action === "vote" || action.action === "decide" || action.action === "assign") return meetingLabel(time, action);
  if (action.reason) return `${time}waited: ${action.reason}`;
  if (action.action === "move") return `${time}walks ${action.place === "home" ? "home" : `to the ${placeLabel(action.place)}`}`;
  if (action.action === "find") return `${time}goes looking for ${action.villager}`;
  if (action.action === "goodbye") return `${time}says goodbye${action.text ? `: ${action.text}` : ""}`;
  if (action.action === "say") return `${time}says${action.to ? ` to ${action.to}` : ""}: ${action.text}`;
  if (action.action === "work") return `${time}works at the ${placeLabel(action.place)}`;
  if (action.action === "give") {
    return action.to ? `${time}gives a ${carriedText(action.goods)} to ${action.to}` : `${time}sets out ${action.goods} on the festival stalls`;
  }
  if (action.action === "buy") return `${time}trades a ${carriedText(action.paid)} for a ${carriedText(action.goods)}`;
  return `${time}waits`;
}

/** "07:30 town hall: Go through the list", "11:00 see Jonas: Ask for fish" */
export function planEntryText(entry: PlanEntry): string {
  return `${entry.time} ${entry.villager ? `see ${entry.villager}` : entry.place}: ${entry.purpose}`;
}

export const GOODS: BasketGoods[] = ["fish", "vegetables", "flowers"];
export const BUILDING_GOODS: BuildingGoods[] = ["wood", "paint", "saplings"];

export function isBasket(goods: Goods): goods is BasketGoods {
  return (GOODS as Goods[]).includes(goods);
}

/** "basket of fish" or "load of wood": a villager carries one of either at a time. */
export function carriedText(goods: Goods): string {
  return `${isBasket(goods) ? "basket" : "load"} of ${goods}`;
}

/** Whether the day's trader is coming, at the market (with what it has left) or gone. */
export function traderText(state: Pick<VillageState, "trader" | "time">): string {
  const { trader } = state;
  if (trader) {
    const stock = BUILDING_GOODS.filter((g) => trader.stock[g] > 0).map((g) => `${g} (${trader.stock[g]})`);
    return stock.length ? `A trader is at the market until ${trader.leaves}: ${listed(stock)}.` : `A trader is at the market until ${trader.leaves} and has sold everything.`;
  }
  return state.time < "14:00" ? "A trader comes to the market at 09:00." : "The trader has left; the next comes tomorrow at 09:00.";
}

function listed(items: string[]): string {
  return items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items.at(-1)}` : (items[0] ?? "");
}

/** As the villagers are told: "The festival stalls on the square hold fish; they still lack …" */
export function stallsText(stalls: Stalls): string {
  const held = GOODS.filter((g) => stalls[g] > 0);
  const lacking = GOODS.filter((g) => stalls[g] === 0);
  const text = `The festival stalls on the square ${held.length ? `hold ${listed(held)}` : "are empty"}`;
  return text + (lacking.length ? `; they still lack ${listed(lacking)}.` : ".");
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

export type MeetingLine = { text: string; runId: string | null };

/** The latest town hall meeting as lines for the projects panel, each with the run behind it. */
export function meetingLines(meeting: Meeting): MeetingLine[] {
  const lines: MeetingLine[] = [];
  if (meeting.kind === "review") lines.push({ text: "A meeting about how the building goes.", runId: null });
  meeting.proposals.forEach((p, i) => lines.push({ text: `Hilde proposed ${p.name}: ${p.reason}`, runId: i === 0 ? p.run_id : null }));
  lines.push({ text: meeting.present.length ? `At the town hall: ${listed(meeting.present)}` : "Nobody came to the town hall.", runId: null });
  for (const v of meeting.votes) {
    lines.push({ text: v.name ? `${v.villager} voted for ${v.name}: ${v.reason}` : `${v.villager}'s vote did not count: ${v.reason}`, runId: v.run_id });
  }
  const counts = new Map<string, number>();
  for (const v of meeting.votes) if (v.name) counts.set(v.name, (counts.get(v.name) ?? 0) + 1);
  if (counts.size) {
    const ranked = [...counts].sort((a, b) => b[1] - a[1]).map(([name, n]) => `${name} (${n})`);
    lines.push({ text: `Most votes: ${ranked.join(", ")}`, runId: null });
  }
  const d = meeting.decision;
  if (d) {
    const text = d.by === "vote" ? `The vote chose ${d.name}: Hilde gave no valid decision.` : `Hilde chose ${d.name}: ${d.reason}${d.against ? " She went against the vote." : ""}`;
    lines.push({ text, runId: d.run_id });
  } else if (meeting.outcome) {
    lines.push({ text: `${meeting.outcome[0].toUpperCase()}${meeting.outcome.slice(1)}.`, runId: null });
  }
  return lines;
}

/** "Buy wood from the trader", "Build at the building site" */
export function taskText(task: Task): string {
  if (task.task === "buy") return `Buy ${task.goods} from the trader`;
  if (task.task === "bring") return `Bring ${task.goods} to the building site`;
  return "Build at the building site";
}

function loads(counts: Partial<Record<BuildingGoods, number>>): string {
  return listed(BUILDING_GOODS.filter((g) => (counts[g] ?? 0) > 0).map((g) => `${counts[g]} ${g}`));
}

/** The project being built, for the projects panel: what is still needed, at the site, and who does what. */
export function projectLines(project: Project): string[] {
  const left = Object.fromEntries(BUILDING_GOODS.map((g) => [g, (project.needs[g] ?? 0) - project.site[g] - project.used[g]]));
  const stillNeeded = loads(left);
  return [
    stillNeeded ? `Still to bring: ${stillNeeded}` : "Everything has been brought",
    `At the building site: ${loads(project.site) || "nothing"}`,
    ...(project.tasks.length ? project.tasks.map((t) => `${taskText(t)}: ${listed(t.villagers)}`) : ["Hilde has not handed out the work yet"]),
  ];
}
