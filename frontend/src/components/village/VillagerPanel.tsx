"use client";

import { useEffect, useState } from "react";
import { villagerTurns, type Run, type Villager } from "@/lib/api";
import { eventLines, turnLabel, whereText } from "@/lib/village";

/** One villager: who it is, where, what it remembers, and every turn it took. */
export function VillagerPanel({
  villager,
  tick,
  turnsStarted,
  onClose,
  onOpenTurn,
  onEditAgent,
}: {
  villager: Villager;
  tick: number; // refetch the turns after each tick
  turnsStarted: number; // … and as turns start, so a running turn can be opened live
  onClose: () => void;
  onOpenTurn: (run: Run) => void;
  onEditAgent: (agentId: string) => void;
}) {
  const [turns, setTurns] = useState<Run[]>([]);
  useEffect(() => {
    villagerTurns(villager.name).then(setTurns, () => setTurns([]));
  }, [villager.name, tick, turnsStarted]);

  return (
    <section className="flex flex-col gap-3" aria-label={villager.title}>
      <div className="flex items-start gap-2">
        <span className="mt-1 size-3.5 shrink-0 rounded-full" style={{ background: villager.color }} aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-ink">{villager.title}</h2>
          <p className="text-sm text-muted">{whereText(villager)}</p>
        </div>
        <button type="button" onClick={onClose} className="text-sm text-llm hover:underline focus-visible:outline-2 focus-visible:outline-llm">
          All villagers
        </button>
      </div>
      <p className="text-sm leading-relaxed text-ink">{villager.persona}</p>
      {villager.agent_id && (
        <button
          type="button"
          onClick={() => onEditAgent(villager.agent_id!)}
          className="self-start text-sm font-semibold text-llm hover:underline focus-visible:outline-2 focus-visible:outline-llm"
        >
          Edit its agent
        </button>
      )}
      <div>
        <h3 className="mb-1 text-sm font-semibold text-ink">Remembers</h3>
        {villager.events.length === 0 ? (
          <p className="text-sm text-muted">Nothing yet. Start or step the village.</p>
        ) : (
          <ol className="flex flex-col gap-0.5">
            {eventLines(villager).map((e) => (
              <li key={e.key} className="text-sm text-ink">
                <span className="text-muted tabular-nums">{e.time}</span> {e.text}
              </li>
            ))}
          </ol>
        )}
      </div>
      <div>
        <h3 className="mb-1 text-sm font-semibold text-ink">Turns</h3>
        {turns.length === 0 ? (
          <p className="text-sm text-muted">No turns yet.</p>
        ) : (
          <ol className="flex max-h-72 flex-col divide-y divide-rule/60 overflow-auto rounded-md border border-rule">
            {turns.map((turn) => (
              <li key={turn.run_id}>
                <button
                  type="button"
                  onClick={() => onOpenTurn(turn)}
                  className={`w-full truncate px-2 py-1.5 text-left text-sm hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm ${
                    turn.village_action?.reason ? "text-signal-ink" : "text-ink"
                  }`}
                  title="Open this turn: its graph, prompt and answer"
                >
                  {turnLabel(turn)}
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
