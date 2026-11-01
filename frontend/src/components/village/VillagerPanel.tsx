"use client";

import { useEffect, useState } from "react";
import { villagerTurns, type Run, type Villager } from "@/lib/api";
import { eventLines, planEntryText, sleepText, stateText, turnLabel } from "@/lib/village";
import { VillagerSprite } from "./pixels";

const MEMORIES_SHOWN = 10;

/** One villager: who it is, where, what it learned and remembers, and every turn it took. */
export function VillagerPanel({
  villager,
  tick,
  turnsStarted,
  onClose,
  onOpenTurn,
  onEditAgent,
}: {
  villager: Villager;
  tick: number; // refetch the turns after each step
  turnsStarted: number; // … and as decisions start, so a running one can be opened live
  onClose: () => void;
  onOpenTurn: (run: Run) => void;
  onEditAgent: (agentId: string) => void;
}) {
  const [turns, setTurns] = useState<Run[]>([]);
  const [allMemories, setAllMemories] = useState(false);
  const memories = allMemories ? villager.memories : villager.memories.slice(0, MEMORIES_SHOWN);
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
          <p className="text-base text-dusk-muted">{stateText(villager)}</p>
          <p className="text-sm text-dusk-muted">{sleepText(villager)}</p>
        </div>
        <button type="button" onClick={onClose} className="village-button village-button--small">
          Back
        </button>
      </div>
      <p className="font-sans text-sm leading-relaxed text-dusk">{villager.persona}</p>
      <div>
        <h3 className="mb-1.5 text-lg">Today&apos;s plan</h3>
        {villager.plan === null ? (
          <p className="text-sm text-dusk-muted">No plan yet: villagers plan their day when they wake.</p>
        ) : (
          <ol className="flex flex-col gap-1 font-sans">
            {villager.plan.entries.map((entry, i) => {
              const mark = i === villager.plan!.current ? "now" : i === villager.plan!.next ? "next" : null;
              return (
                <li key={i} className={`text-sm ${mark === "now" ? "text-dusk" : "text-dusk-muted"}`} aria-current={mark === "now" ? "step" : undefined}>
                  {planEntryText(entry)}
                  {mark && <span className="ml-1.5 font-pixel text-xs text-signal-ink">{mark}</span>}
                </li>
              );
            })}
          </ol>
        )}
      </div>
      {villager.agent_id && (
        <button type="button" onClick={() => onEditAgent(villager.agent_id!)} className="village-button self-start">
          Edit its agent
        </button>
      )}
      <div>
        <h3 className="mb-1.5 text-lg">Has learned</h3>
        {villager.learnings.length === 0 ? (
          <p className="text-sm text-dusk-muted">Nothing yet. Villagers learn when they go to bed after a day worth remembering.</p>
        ) : (
          <ol className="flex flex-col gap-1 font-sans">
            {villager.learnings.map((l, i) => (
              <li key={i} className="text-sm text-dusk">
                <span className="font-pixel text-dusk-muted">Day {l.day}</span> {l.text}
              </li>
            ))}
          </ol>
        )}
      </div>
      <div>
        <h3 className="mb-1.5 text-lg">The others</h3>
        <ul className="flex flex-col gap-1.5 font-sans">
          {villager.beliefs.map((b) => (
            <li key={b.villager} className="text-sm text-dusk">
              <span className="font-pixel">{b.villager}</span> {b.text}
              {b.view && <span className="block text-dusk-muted">Thinks: {b.view}</span>}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="mb-1.5 text-lg">Remembers</h3>
        {villager.memories.length === 0 ? (
          <p className="text-sm text-dusk-muted">Nothing lasting yet: conversations, searches and meetings stay here.</p>
        ) : (
          <>
            <ol className="flex flex-col gap-1 font-sans">
              {memories.map((m, i) => (
                <li key={i} className="text-sm text-dusk">
                  <span className="font-pixel text-dusk-muted tabular-nums">
                    Day {m.day} {m.time}
                  </span>{" "}
                  {m.text}
                </li>
              ))}
            </ol>
            {villager.memories.length > MEMORIES_SHOWN && (
              <button type="button" onClick={() => setAllMemories(!allMemories)} className="village-button village-button--small mt-2">
                {allMemories ? "Show fewer" : `Show all ${villager.memories.length}`}
              </button>
            )}
          </>
        )}
      </div>
      <div>
        <h3 className="mb-1.5 text-lg">Lately</h3>
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
