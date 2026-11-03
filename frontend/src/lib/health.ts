// Village health (M13): how the numbers of a day read in the health panel. Pure.
import type { DayHealth } from "./api";

export type HealthCell = { label: string; value: string; why?: string };

const NO_TRAIL = "no day trail for this day (before M13)";

function percent(part: number, whole: number): string {
  return whole ? `${Math.round((100 * part) / whole)}%` : "–";
}

/** The table's cells for one day; a missing number is "–", with why. */
export function healthRow(day: DayHealth): HealthCell[] {
  const refusals = day.refusals.reduce((sum, r) => sum + r.count, 0);
  const plan = day.plan_adherence;
  const cells: HealthCell[] = [
    { label: "Decisions", value: String(day.decisions) },
    { label: "Waits", value: percent(day.waits, day.decisions) },
    { label: "Refusals", value: String(refusals) },
    { label: "Talk lines", value: day.conversations.median_lines == null ? "–" : String(day.conversations.median_lines) },
    plan ? { label: "Plan kept", value: percent(plan.kept, plan.entries) } : { label: "Plan kept", value: "–", why: NO_TRAIL },
    { label: "Trades", value: String(day.trades) },
    { label: "Loads", value: `${day.loads_set_down} / ${day.loads_worked_in ?? "–"}` },
    day.stuck_hours == null ? { label: "Stuck hours", value: "–", why: NO_TRAIL } : { label: "Stuck hours", value: String(day.stuck_hours) },
    day.weather_slips == null
      ? { label: "Weather slips", value: "–", why: "the chronicle is not written yet" }
      : { label: "Weather slips", value: String(day.weather_slips.length) },
  ];
  return cells;
}

/** "Day 66", or "Day 67 (so far)" for the day in progress. */
export function healthTitle(day: DayHealth): string {
  return `Day ${day.day}${day.final ? "" : " (so far)"}`;
}

/** "30 × someone is not next to you", most first. */
export function refusalLines(day: DayHealth): string[] {
  return day.refusals.map((r) => `${r.count} × ${r.reason.replaceAll("<villager>", "someone").replaceAll("<goods>", "goods")}`);
}

/** Every number of a day, for its detail: the table's cells and the rest. */
export function healthDetail(day: DayHealth): HealthCell[] {
  const { calls, meeting } = day;
  const total = calls.decision + calls.plan + calls.reflect + calls.chronicle + calls.meeting;
  const talks = day.conversations;
  return [
    ...healthRow(day).filter((c) => c.label !== "Weather slips"),
    { label: "Conversations", value: talks.count ? `${talks.count} (lines ${talks.lines.join(", ")})` : "0" },
    { label: "Repeated lines", value: String(day.repeated_lines) },
    day.load_minutes == null ? { label: "Load time", value: "–", why: "no load bought and set down" } : { label: "Load time", value: `${day.load_minutes} min` },
    { label: "Given straight back", value: String(day.given_back) },
    { label: "Meeting", value: meeting ? `${meeting.present.length} came, ${meeting.votes} voted, ${meeting.outcome}` : "none" },
    { label: "Happenings", value: `${day.happenings.count} (${day.happenings.dealt} dealt with)` },
    { label: "Boat trips", value: String(day.boat_trips) },
    { label: "Whispers", value: `${day.whispers.count} (${day.whispers.followed} followed by an action)` },
    {
      label: "Model calls",
      value: `${total}: ${calls.decision} decisions, ${calls.plan} plans, ${calls.reflect} reflections, ${calls.chronicle} chronicle, ${calls.meeting} meeting runs (${day.failed_calls} failed)`,
    },
    day.weather_slips == null
      ? { label: "Weather slips", value: "–", why: "the chronicle is not written yet" }
      : { label: "Weather slips", value: day.weather_slips.join(", ") || "none" },
  ];
}
