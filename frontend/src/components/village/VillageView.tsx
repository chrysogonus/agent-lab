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
import { PERIOD_TINT, clockText, placeAreas, figures, narration, speeches, statusLine, whereText } from "@/lib/village";
import { RunViewer } from "../RunViewer";
import { Ground, Lights, PixelDigits, Pixels, SPRITES, TILE, VillagerSprite } from "./pixels";
import { VillagerPanel } from "./VillagerPanel";

type VillageStream = {
  state: VillageState | null;
  setState: (s: VillageState) => void;
  error: string | null; // shown in the loaded view too: a stale map must say so
  turnsStarted: number; // bumps when a villager turn starts, so an open panel lists it live
};

/** The village's state, kept live by the village stream while shown; reconnects when it drops. */
function useVillage(): VillageStream {
  const [state, setState] = useState<VillageState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [turnsStarted, setTurnsStarted] = useState(0);
  useEffect(() => {
    let stopped = false;
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = (attempt: number) => {
      ws = new WebSocket(villageStreamUrl());
      ws.onopen = () => setError(null); // the server sends the current state first
      ws.onmessage = (message) => {
        const event = JSON.parse(message.data as string) as { type: string; state?: VillageState };
        if (event.type === "state" && event.state) setState(event.state);
        if (event.type === "tick_started") setState((s) => (s ? { ...s, ticking: true } : s));
        if (event.type === "turn_started") setTurnsStarted((n) => n + 1);
      };
      ws.onclose = () => {
        if (stopped) return;
        setError("Lost the connection to the village. Reconnecting…");
        retry = setTimeout(() => connect(attempt + 1), Math.min(1000 * 2 ** attempt, 10000));
      };
    };
    getVillage().then(setState, () => setError("The village is unavailable until the backend is running."));
    connect(0);
    return () => {
      stopped = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, []);
  return { state, setState, error, turnsStarted };
}

function VillageMap({ state, selected, onSelect }: { state: VillageState; selected: string | null; onSelect: (name: string) => void }) {
  const { width, height, rows, places } = state.map;
  const map = rows.join("\n");
  const tint = PERIOD_TINT[state.period];
  const areas = placeAreas(rows);
  const placed = figures(state).sort((a, b) => a.cy - b.cy); // lower on the map is nearer, drawn later
  return (
    <svg
      viewBox={`0 0 ${width * TILE} ${height * TILE}`}
      className="pixel-art block h-auto w-full select-none"
      role="group"
      aria-label={`Village map, ${clockText(state)}`}
    >
      <Ground map={map} />
      <rect width={width * TILE} height={height * TILE} fill={tint.color} opacity={tint.opacity} className="village-tint" aria-hidden />
      <Lights map={map} on={state.period === "evening" || state.period === "night"} />
      {places.map((p) => {
        const area = areas[rows[p.y][p.x]];
        const label = { x: ((area.x0 + area.x1 + 1) / 2) * TILE, y: area.y0 * TILE }; // on the top edge: villagers stand lower
        const w = p.label.length * 4.4 + 8;
        return (
          <g key={p.key} aria-hidden>
            <rect x={label.x - w / 2} y={label.y - 5} width={w} height={10} rx={2} fill="#2a2340" opacity={0.82} />
            <text x={label.x} y={label.y + 2.6} textAnchor="middle" fontSize={7.5} fill="#fffaf0" className="font-pixel">
              {p.label}
            </text>
          </g>
        );
      })}
      {placed.map(({ villager, cx, cy }) => {
        const sprite = SPRITES[villager.name];
        const isSelected = selected === villager.name;
        const nameWidth = villager.name.length * 4.6 + 6;
        return (
          <g
            key={villager.name}
            role="button"
            tabIndex={0}
            aria-label={`${villager.title}, ${whereText(villager).toLowerCase()}`}
            aria-pressed={isSelected}
            onClick={() => onSelect(villager.name)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(villager.name))}
            className="village-figure cursor-pointer outline-none transition-transform duration-500 ease-out motion-reduce:transition-none"
            style={{ transform: `translate(${cx * TILE}px, ${cy * TILE}px)` }}
          >
            <title>{villager.title}</title>
            <rect className="village-ring" pointerEvents="none" x={-10} y={-13} width={20} height={21} rx={3} fill="none" stroke="#fffaf0" strokeWidth={1.5} />
            <rect x={-5} y={4} width={10} height={2} fill="#00000030" />
            <rect x={-4} y={3} width={8} height={4} fill="#00000018" />
            <g className={villager.destination ? "village-walk" : undefined}>
              {sprite ? (
                <Pixels rows={sprite.rows} palette={sprite.palette} x={-8} y={-11} />
              ) : (
                <rect x={-5} y={-9} width={10} height={14} fill={villager.color} stroke="#2a2340" />
              )}
            </g>
            <g className="village-name" pointerEvents="none">
              <rect x={-nameWidth / 2} y={7} width={nameWidth} height={9} rx={2} fill="#fffaf0" stroke="#2a2340" strokeWidth={0.75} />
              <text y={13.6} textAnchor="middle" fontSize={7} fill="#2a2340" className="font-pixel">
                {villager.name}
              </text>
            </g>
            {villager.speech && (
              <g aria-hidden>
                <rect x={-1} y={-25} width={15} height={10} rx={2} fill="#fffaf0" stroke="#2a2340" strokeWidth={1} />
                <rect x={1} y={-16} width={3} height={2} fill="#fffaf0" />
                <rect x={0} y={-15} width={2} height={2} fill="#2a2340" />
                {[2.5, 5.5, 8.5].map((dx) => (
                  <rect key={dx} x={dx} y={-21} width={2} height={2} fill="#2a2340" />
                ))}
              </g>
            )}
            {isSelected && (
              <g className="village-cursor" aria-hidden>
                <path d={`M -4 ${villager.speech ? -34 : -21} h 8 l -4 5 z`} fill="#ffd75e" stroke="#2a2340" strokeWidth={1} />
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/** Under the map, like a game's text box: what was said this tick, or what is going on. */
function DialogBox({ state }: { state: VillageState }) {
  const said = speeches(state);
  return (
    <div className="village-window px-4 py-3 font-pixel text-base leading-snug text-dusk" aria-label="What the villagers say">
      {said.length === 0 ? (
        <p className="text-dusk-muted">{narration(state)}</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {said.map(({ villager, text, to }) => (
            <li key={villager.name} className="flex items-start gap-2">
              <VillagerSprite name={villager.name} size={24} />
              <p className="min-w-0">
                <span className="font-semibold" style={{ color: villager.color }}>
                  {villager.name}
                </span>
                {to && <span className="text-dusk-muted"> to {to}</span>}
                <span className="text-dusk-muted">: </span>
                {text}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The village: the map, the clock and controls, the villagers, and one villager in detail. */
export function VillageView({ onEditAgent }: { onEditAgent: (agentId: string) => void }) {
  const { state, setState, error: streamError, turnsStarted } = useVillage();
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

  const night = state.period === "evening" || state.period === "night";

  return (
    <div className="grid min-h-0 flex-1 gap-4 font-pixel text-dusk lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="flex min-h-0 flex-col gap-3 overflow-auto" aria-label="Village">
        {turn ? (
          <div className="village-window flex min-h-0 flex-1 flex-col gap-3 p-4 font-sans text-ink">
            <button type="button" onClick={() => setTurn(null)} className="village-button self-start">
              Back to the village
            </button>
            <RunViewer key={turn.run_id} initial={turn} onEnded={setTurn} />
          </div>
        ) : (
          <div className="mx-auto flex w-full flex-col gap-3 lg:max-w-[calc((100dvh-15rem)*4/3)]">
            <div className="village-window overflow-hidden p-1.5">
              <div className="overflow-hidden rounded-[5px]">
                <VillageMap state={state} selected={selected} onSelect={(name) => setSelected(name === selected ? null : name)} />
              </div>
            </div>
            <DialogBox state={state} />
          </div>
        )}
      </section>
      <aside className="village-window flex min-h-0 flex-col gap-4 overflow-auto p-5" aria-label="Village controls">
        <div className="flex items-center gap-3">
          <svg viewBox="0 0 12 12" width={36} height={36} className="pixel-art shrink-0" aria-hidden>
            {night ? (
              <path d="M5 1h3v1h1v1H7v1H6v4h1v1h2v1H8v1H5v-1H3V9H2V3h1V2h2z" fill="#ffe9a8" stroke="#2a2340" strokeWidth={0.6} />
            ) : (
              <>
                <path d="M5 0h2v2H5zM5 10h2v2H5zM0 5h2v2H0zM10 5h2v2h-2zM1 1h2v2H1zM9 1h2v2H9zM1 9h2v2H1zM9 9h2v2H9z" fill="#f0a830" />
                <rect x={3} y={3} width={6} height={6} fill="#ffd75e" stroke="#2a2340" strokeWidth={0.6} />
              </>
            )}
          </svg>
          <div>
            <p>
              <PixelDigits text={state.time} />
            </p>
            <p className="mt-2 text-base text-dusk-muted">
              Day {state.day}, {state.period}
            </p>
          </div>
        </div>
        <p className={`text-base ${state.paused_reason && state.paused_reason !== "owner" ? "text-fault" : "text-dusk-muted"}`} role="status">
          {statusLine(state)}
        </p>
        <div className="flex flex-wrap items-center gap-2.5">
          {state.running ? (
            <button type="button" onClick={() => void act(pauseVillage)} className="village-button village-button--go">
              Pause
            </button>
          ) : (
            <button type="button" onClick={() => void act(startVillage)} className="village-button village-button--go">
              Start
            </button>
          )}
          <button type="button" onClick={() => void act(stepVillage)} disabled={state.running || state.ticking} className="village-button">
            Step
          </button>
          <button
            type="button"
            onClick={() => window.confirm("Reset the village? Everyone goes home and the clock starts over; past turns stay.") && void act(resetVillage)}
            className="village-button village-button--danger ml-auto"
          >
            Reset
          </button>
        </div>
        <label className="flex items-center gap-2 text-base text-dusk-muted">
          A tick every
          <input
            type="number"
            min={1}
            max={30}
            value={interval ?? state.interval}
            onChange={(e) => setIntervalText(e.target.value)}
            onBlur={saveInterval}
            onKeyDown={(e) => e.key === "Enter" && saveInterval()}
            className="w-16 rounded-md border-2 border-dusk bg-parchment px-2 py-0.5 font-sans text-base text-dusk tabular-nums focus-visible:outline-3 focus-visible:outline-llm"
            aria-label="Seconds between ticks"
          />
          seconds
        </label>
        {(streamError || error) && (
          <p role="alert" className="text-base text-fault">
            {streamError ?? error}
          </p>
        )}
        <hr className="border-t-2 border-dashed border-dusk-rule" />
        {villager ? (
          <VillagerPanel
            turnsStarted={turnsStarted}
            villager={villager}
            tick={state.tick}
            onClose={() => setSelected(null)}
            onOpenTurn={setTurn}
            onEditAgent={onEditAgent}
          />
        ) : (
          <>
            <ul className="-mx-2 flex flex-col gap-0.5" aria-label="Villagers">
              {state.villagers.map((v) => (
                <li key={v.name}>
                  <button type="button" onClick={() => setSelected(v.name)} className="village-menu-item flex w-full items-center gap-3 rounded-md py-1.5 pr-2 pl-6 text-left">
                    <VillagerSprite name={v.name} size={32} />
                    <span className="min-w-0">
                      <span className="block text-base">{v.title}</span>
                      <span className="block truncate text-sm text-dusk-muted">{whereText(v)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="text-sm text-dusk-muted">Pick a villager to see what it remembers and every turn it took.</p>
          </>
        )}
      </aside>
    </div>
  );
}
