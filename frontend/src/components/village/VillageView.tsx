"use client";

import { useEffect, useState } from "react";
import {
  getVillage,
  pauseVillage,
  resetVillage,
  setVillageInterval,
  startVillage,
  stepVillage,
  villageStreamUrl,
  type Run,
  type VillageState,
} from "@/lib/api";
import {
  PERIOD_SHADE,
  TILE_FILL,
  bubbleText,
  clockText,
  figures,
  speechText,
  statusLine,
  whereText,
} from "@/lib/village";
import { RunViewer } from "../RunViewer";
import { VillagerPanel } from "./VillagerPanel";

const BUTTON =
  "rounded-md px-3 py-1.5 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-llm disabled:opacity-40";

/** The village's state: fetched once, then kept live by the village stream while shown. */
function useVillage(): [VillageState | null, (s: VillageState) => void, string | null] {
  const [state, setState] = useState<VillageState | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let closed = false;
    getVillage().then(setState, () => setError("The village is unavailable until the backend is running."));
    const ws = new WebSocket(villageStreamUrl());
    ws.onmessage = (message) => {
      const event = JSON.parse(message.data as string) as { type: string; state?: VillageState; tick?: number };
      if (event.type === "state" && event.state) setState(event.state);
      if (event.type === "tick_started") setState((s) => (s ? { ...s, ticking: true } : s));
    };
    ws.onclose = () => !closed && setError("Lost the connection to the village; reload to reconnect.");
    return () => {
      closed = true;
      ws.close();
    };
  }, []);
  return [state, setState, error];
}

function VillageMap({ state, selected, onSelect }: { state: VillageState; selected: string | null; onSelect: (name: string) => void }) {
  const { width, height, rows, places } = state.map;
  const placed = figures(state);
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full select-none" role="group" aria-label={`Village map, ${clockText(state)}`}>
      {rows.map((row, y) =>
        [...row].map((char, x) => <rect key={`${x},${y}`} x={x} y={y} width={1.02} height={1.02} fill={TILE_FILL[char] ?? TILE_FILL["."]} />),
      )}
      <rect width={width} height={height} fill="#1b2a4a" opacity={PERIOD_SHADE[state.period]} className="transition-opacity duration-1000" aria-hidden />
      {places.map((p) => (
        <text key={p.key} x={p.x + 0.12} y={p.y + 0.42} fontSize={0.34} className="fill-ink" style={{ paintOrder: "stroke" }} stroke="#ffffffcc" strokeWidth={0.08} aria-hidden>
          {p.label}
        </text>
      ))}
      {placed.map(({ villager, cx, cy }) => (
        <g
          key={villager.name}
          role="button"
          tabIndex={0}
          aria-label={`${villager.title}, ${whereText(villager).toLowerCase()}`}
          aria-pressed={selected === villager.name}
          onClick={() => onSelect(villager.name)}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(villager.name))}
          className="cursor-pointer outline-none transition-transform duration-500 ease-out motion-reduce:transition-none [&:focus-visible>circle]:stroke-llm"
          style={{ transform: `translate(${cx}px, ${cy}px)` }}
        >
          <circle r={0.38} fill={villager.color} stroke={selected === villager.name ? "#1b2430" : "#ffffff"} strokeWidth={0.07} />
          <text textAnchor="middle" dy={0.15} fontSize={0.42} fontWeight={600} fill="#ffffff">
            {villager.initial}
          </text>
          <text textAnchor="middle" y={0.78} fontSize={0.3} className="fill-ink" style={{ paintOrder: "stroke" }} stroke="#ffffffcc" strokeWidth={0.07}>
            {villager.name}
          </text>
        </g>
      ))}
      {placed.map(({ villager, cx, cy }) => {
        const said = speechText(villager);
        if (!said) return null;
        const text = bubbleText(said);
        const w = Math.min(text.length * 0.17 + 0.5, 8.5);
        const x = Math.min(Math.max(cx - w / 2, 0.1), width - w - 0.1);
        return (
          <g key={`say-${villager.name}`} aria-hidden>
            <rect x={x} y={cy - 1.45} width={w} height={0.62} rx={0.18} fill="#ffffff" stroke={villager.color} strokeWidth={0.05} />
            <path d={`M ${cx - 0.12} ${cy - 0.84} L ${cx} ${cy - 0.6} L ${cx + 0.12} ${cy - 0.84} Z`} fill="#ffffff" />
            <text x={x + 0.25} y={cy - 1.04} fontSize={0.3} className="fill-ink">
              {text}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** The village: the map, the clock and controls, the villagers, and one villager in detail. */
export function VillageView({ onEditAgent }: { onEditAgent: (agentId: string) => void }) {
  const [state, setState, streamError] = useVillage();
  const [selected, setSelected] = useState<string | null>(null);
  const [turn, setTurn] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [interval, setIntervalText] = useState<string | null>(null);

  const act = async (call: () => Promise<VillageState>) => {
    setError(null);
    try {
      setState(await call());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (!state) {
    return <p className="text-sm text-muted">{streamError ?? "Loading the village…"}</p>;
  }
  const villager = state.villagers.find((v) => v.name === selected) ?? null;
  const saveInterval = () => {
    const seconds = Number(interval);
    if (interval !== null && Number.isInteger(seconds) && seconds !== state.interval) void act(() => setVillageInterval(seconds));
    setIntervalText(null);
  };

  return (
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="flex min-h-0 flex-col overflow-auto rounded-lg border border-rule bg-panel" aria-label="Village">
        {turn ? (
          <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
            <button type="button" onClick={() => setTurn(null)} className="self-start text-sm font-semibold text-llm hover:underline focus-visible:outline-2 focus-visible:outline-llm">
              Back to the village
            </button>
            <RunViewer key={turn.run_id} initial={turn} onEnded={setTurn} />
          </div>
        ) : (
          <div className="p-3">
            <VillageMap state={state} selected={selected} onSelect={(name) => setSelected(name === selected ? null : name)} />
          </div>
        )}
      </section>
      <aside className="flex min-h-0 flex-col gap-4 overflow-auto rounded-lg border border-rule bg-panel p-4" aria-label="Village controls">
        <div>
          <p className="text-lg font-semibold text-ink">{clockText(state)}</p>
          <p className={`text-sm ${state.paused_reason && state.paused_reason !== "owner" ? "text-signal-ink" : "text-muted"}`} role="status">
            {statusLine(state)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {state.running ? (
            <button type="button" onClick={() => void act(pauseVillage)} className={`${BUTTON} bg-ink text-panel hover:bg-llm`}>
              Pause
            </button>
          ) : (
            <button type="button" onClick={() => void act(startVillage)} className={`${BUTTON} bg-ink text-panel hover:bg-llm`}>
              Start
            </button>
          )}
          <button type="button" onClick={() => void act(stepVillage)} disabled={state.running || state.ticking} className={`${BUTTON} text-ink hover:bg-paper`}>
            Step
          </button>
          <label className="flex items-center gap-1.5 text-sm text-muted">
            Every
            <input
              type="number"
              min={1}
              max={30}
              value={interval ?? state.interval}
              onChange={(e) => setIntervalText(e.target.value)}
              onBlur={saveInterval}
              onKeyDown={(e) => e.key === "Enter" && saveInterval()}
              className="w-14 rounded-md border border-rule bg-panel px-2 py-1 text-sm text-ink tabular-nums focus-visible:outline-2 focus-visible:outline-llm"
              aria-label="Seconds between ticks"
            />
            s
          </label>
          <button
            type="button"
            onClick={() => window.confirm("Reset the village? Everyone goes home and the clock starts over; past turns stay.") && void act(resetVillage)}
            className={`${BUTTON} ml-auto text-fault hover:bg-fault/10`}
          >
            Reset
          </button>
        </div>
        {error && (
          <p role="alert" className="text-sm text-fault">
            {error}
          </p>
        )}
        {villager ? (
          <VillagerPanel
            villager={villager}
            tick={state.tick}
            onClose={() => setSelected(null)}
            onOpenTurn={setTurn}
            onEditAgent={onEditAgent}
          />
        ) : (
          <ul className="flex flex-col gap-1" aria-label="Villagers">
            {state.villagers.map((v) => (
              <li key={v.name}>
                <button
                  type="button"
                  onClick={() => setSelected(v.name)}
                  className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm"
                >
                  <span className="mt-1 size-3 shrink-0 rounded-full" style={{ background: v.color }} aria-hidden />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-ink">{v.title}</span>
                    <span className="block truncate text-sm text-muted">{speechText(v) ?? whereText(v)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {!villager && <p className="text-sm text-muted">Click a villager to see what it remembers and every turn it took.</p>}
      </aside>
    </div>
  );
}
