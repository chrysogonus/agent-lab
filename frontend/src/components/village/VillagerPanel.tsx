"use client";

import { useEffect, useState } from "react";
import { villagerTurns, type Run, type Villager } from "@/lib/api";
import { eventLines, turnLabel, whereText } from "@/lib/village";
import { VillagerSprite } from "./pixels";

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
    <section className="flex flex-col gap-4" aria-label={villager.title}>
      <div className="flex items-start gap-3">
        <div className="rounded-md border-2 border-dusk bg-[#b7e08f] p-1" style={{ boxShadow: `inset 0 -6px 0 ${villager.color}33` }}>
          <VillagerSprite name={villager.name} size={56} />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-xl leading-tight" style={{ color: villager.color }}>
            {villager.title}
          </h2>
          <p className="text-base text-dusk-muted">{whereText(villager)}</p>
        </div>
        <button type="button" onClick={onClose} className="village-button village-button--small">
          Back
        </button>
      </div>
      <p className="font-sans text-sm leading-relaxed text-dusk">{villager.persona}</p>
      {villager.agent_id && (
        <button type="button" onClick={() => onEditAgent(villager.agent_id!)} className="village-button self-start">
          Edit its agent
        </button>
      )}
      <div>
        <h3 className="mb-1.5 text-lg">Remembers</h3>
        {villager.events.length === 0 ? (
          <p className="text-sm text-dusk-muted">Nothing yet. Start or step the village.</p>
        ) : (
          <ol className="flex flex-col gap-1 font-sans">
            {eventLines(villager).map((e) => (
              <li key={e.key} className="text-sm text-dusk">
                <span className="font-pixel text-dusk-muted tabular-nums">{e.time}</span> {e.text}
              </li>
            ))}
          </ol>
        )}
      </div>
      <div>
        <h3 className="mb-1.5 text-lg">Turns</h3>
        {turns.length === 0 ? (
          <p className="text-sm text-dusk-muted">No turns yet.</p>
        ) : (
          <ol className="flex max-h-72 flex-col overflow-auto rounded-md border-2 border-dusk-rule font-sans">
            {turns.map((turn) => (
              <li key={turn.run_id} className="border-b border-dusk-rule/70 last:border-b-0">
                <button
                  type="button"
                  onClick={() => onOpenTurn(turn)}
                  className={`village-menu-item w-full truncate py-1.5 pr-2 pl-6 text-left text-sm ${turn.village_action?.reason ? "text-signal-ink" : "text-dusk"}`}
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
