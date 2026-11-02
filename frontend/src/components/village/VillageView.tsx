"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
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
  type Villager,
} from "@/lib/api";
import { GOODS, PACES, PERIOD_SKY, activity, calendarText, clockText, glideMs, figures, isBasket, logLines, narration, newEntries, placeAreas, rhythm, stallsText, stateText, statusLine, traderText } from "@/lib/village";
import { RunViewer } from "../RunViewer";
import { Butterflies, Fireflies, Ground, LakeRings, Lights, PixelDigits, Smoke, Snores, TILE, VillagerFigure, VillagerSprite } from "./pixels";
import { ChroniclePanel } from "./ChroniclePanel";
import { ProjectsPanel } from "./ProjectsPanel";
import { Basket, Festival, Puddles, Stalls, WEATHER_WORDS, WeatherIcon, WeatherLayer } from "./seasons";
import { Load, Trader } from "./building";
import { VillagerPanel } from "./VillagerPanel";

const SEEN_KEY = "village-chronicle-seen";

function readSeen(): string | null {
  try {
    return localStorage.getItem(SEEN_KEY);
  } catch {
    return null; // storage blocked: every entry counts as new
  }
}

function writeSeen(runId: string | null) {
  try {
    if (runId) localStorage.setItem(SEEN_KEY, runId);
  } catch {
    // storage blocked: nothing to remember
  }
}

type VillageStream = {
  state: VillageState | null;
  setState: (s: VillageState) => void;
  error: string | null; // shown in the loaded view too: a stale map must say so
  turnsStarted: number; // bumps when a villager's decision starts, so an open panel lists it live
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
        if (event.type === "decision_started") setTurnsStarted((n) => n + 1);
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
  const { width, height, rows, places, homes } = state.map;
  const map = rows.join("\n");
  const sky = PERIOD_SKY[state.sky];
  const { dark, weather, calendar } = state;
  const wet = weather === "rain" || weather === "storm";
  const warm = calendar.season === "spring" || calendar.season === "summer";
  const areas = placeAreas(rows);
  const owners = new Map(state.villagers.map((v) => [v.name, v]));
  const houses = homes.map((h) => `${h.letter}:${owners.get(h.villager)?.color ?? "#d6584b"}`).join(",");
  const placed = figures(state).sort((a, b) => a.cy - b.cy); // lower on the map is nearer, drawn later
  const glide = glideMs(state);
  return (
    <svg
      viewBox={`0 0 ${width * TILE} ${height * TILE}`}
      className="pixel-art block h-auto w-full select-none"
      role="group"
      aria-label={`Village map, ${clockText(state)}`}
    >
      <defs>
        <linearGradient id="village-sky" x1={0} y1={0} x2={0} y2={1}>
          <stop offset={0} className="village-sky-stop" style={{ stopColor: sky.top.color, stopOpacity: sky.top.opacity }} />
          <stop offset={1} className="village-sky-stop" style={{ stopColor: sky.bottom.color, stopOpacity: sky.bottom.opacity }} />
        </linearGradient>
      </defs>
      <Ground
        map={map}
        houses={houses}
        season={calendar.season}
        snow={state.snow_cover}
        fields={state.growth.fields.stage}
        garden={state.growth.flower_garden.stage}
        neglected={state.growth.fields.neglected}
      />
      {wet && <Puddles rows={rows} />}
      {weather !== "snow" && <LakeRings map={map} />}
      {!dark && warm && !wet && areas.G && <Butterflies area={areas.G} />}
      {homes.map((h) => {
        const owner = owners.get(h.villager);
        const home = owner && !owner.asleep && owner.x === h.door[0] && owner.y === h.door[1];
        return home && areas[h.letter] && <Smoke key={h.letter} area={areas[h.letter]} />;
      })}
      <rect width={width * TILE} height={height * TILE} fill="url(#village-sky)" pointerEvents="none" aria-hidden />
      <Lights map={map} on={dark} />
      {calendar.festival_in === 0 && areas.S && <Festival area={areas.S} lit={dark} />}
      {(calendar.season === "autumn" || GOODS.some((g) => state.stalls[g] > 0)) && areas.S && <Stalls area={areas.S} stalls={state.stalls} />}
      {state.trader && areas.M && <Trader area={areas.M} trader={state.trader} />}
      {dark && calendar.season !== "winter" && !wet && <Fireflies map={map} />}
      {homes.map((h) => owners.get(h.villager)?.asleep && areas[h.letter] && <Snores key={h.letter} area={areas[h.letter]} />)}
      {places.map((p) => {
        const area = areas[rows[p.y][p.x]];
        // On the top edge, where villagers rarely stand; the town hall's sign hangs on its wall,
        // the pier's floats on the water below it (Jonas fishes from its top).
        const edge = p.key === "pier" ? area.y1 + 1.4 : rows[area.y0 - 1]?.[area.x0] === "B" ? area.y0 - 1 : area.y0;
        return <NamePlate key={p.key} x={((area.x0 + area.x1 + 1) / 2) * TILE} y={edge * TILE} text={p.label} />;
      })}
      {homes.map((h) => {
        const area = areas[h.letter];
        return area && <NamePlate key={h.letter} x={((area.x0 + area.x1 + 1) / 2) * TILE} y={area.y0 * TILE + 16} text={h.villager} small />;
      })}
      {placed.map(({ villager, cx, cy }) => {
        const isSelected = selected === villager.name;
        const nameWidth = villager.name.length * 4.6 + 6;
        return (
          <g
            key={villager.name}
            role="button"
            tabIndex={0}
            aria-label={`${villager.title}, ${stateText(villager).toLowerCase()}`}
            aria-pressed={isSelected}
            onClick={() => onSelect(villager.name)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(villager.name))}
            className="village-figure cursor-pointer outline-none transition-transform ease-linear motion-reduce:transition-none"
            style={{ transform: `translate(${cx * TILE}px, ${cy * TILE}px)`, transitionDuration: `${glide}ms` }}
          >
            <title>{villager.title}</title>
            <rect className="village-ring" pointerEvents="none" x={-10} y={-13} width={20} height={21} rx={3} fill="none" stroke="#fffaf0" strokeWidth={1.5} />
            <rect x={-5} y={4} width={10} height={2} fill="#00000030" />
            <rect x={-4} y={3} width={8} height={4} fill="#00000018" />
            <MovingFigure villager={villager} glide={glide} />
            {villager.basket && (isBasket(villager.basket) ? <Basket goods={villager.basket} /> : <Load goods={villager.basket} />)}
            <g className="village-name" pointerEvents="none">
              <rect x={-nameWidth / 2} y={7} width={nameWidth} height={9} rx={2} fill="#fffaf0" stroke="#2a2340" strokeWidth={0.75} />
              <text y={13.6} textAnchor="middle" fontSize={7} fill="#2a2340" className="font-pixel">
                {villager.name}
              </text>
            </g>
            {!villager.speech && villager.state === "deciding" && (
              <g aria-hidden>
                <rect x={0} y={-24} width={10} height={10} rx={3} fill="#fffaf0" stroke="#2a2340" strokeWidth={1} />
                <rect x={-1} y={-14} width={2} height={2} fill="#fffaf0" stroke="#2a2340" strokeWidth={0.5} />
                <text x={5} y={-16.5} textAnchor="middle" fontSize={8} fill="#2a2340" className="font-pixel">
                  ?
                </text>
              </g>
            )}
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
      <WeatherLayer weather={weather} width={width * TILE} height={height * TILE} />
    </svg>
  );
}

/** True while a figure glides to a new cell, plus a moment, so consecutive moves blend. */
function useMoving(x: number, y: number, glide: number): boolean {
  const [moving, setMoving] = useState(false);
  const last = useRef(`${x},${y}`);
  // Read, not depended on: a pace change mid-glide must not cancel the timer that ends it.
  const glideRef = useRef(glide);
  useEffect(() => {
    glideRef.current = glide;
  }, [glide]);
  useEffect(() => {
    const cell = `${x},${y}`;
    if (cell === last.current) return;
    last.current = cell;
    setMoving(true);
    const settle = setTimeout(() => setMoving(false), glideRef.current + 150);
    return () => clearTimeout(settle);
  }, [x, y]);
  return moving;
}

/** The walk plays only while the villager actually moves; standing still, it idles. */
function MovingFigure({ villager, glide }: { villager: Villager; glide: number }) {
  const moving = useMoving(villager.x, villager.y, glide);
  return <VillagerFigure name={villager.name} activity={activity(villager, moving)} rhythm={rhythm(villager.name)} />;
}

function NamePlate({ x, y, text, small = false }: { x: number; y: number; text: string; small?: boolean }) {
  const size = small ? 6.5 : 7.5;
  const w = text.length * size * 0.59 + 8;
  return (
    <g aria-hidden>
      <rect x={x - w / 2} y={y - size * 0.67} width={w} height={size * 1.33} rx={2} fill="#2a2340" opacity={0.82} />
      <text x={x} y={y + size * 0.35} textAnchor="middle" fontSize={size} fill="#fffaf0" className="font-pixel">
        {text}
      </text>
    </g>
  );
}

/** Under the map, like a game's text box: the last lines said in the village, newest last. */
function DialogBox({ state }: { state: VillageState }) {
  const lines = logLines(state);
  const colors = new Map(state.villagers.map((v) => [v.name, v.color]));
  return (
    <div className="village-window px-4 py-3 font-pixel text-base leading-snug text-dusk" aria-label="What the villagers say">
      {lines.length === 0 ? (
        <p className="text-dusk-muted">{narration(state)}</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {lines.map((line) => (
            <li key={`${line.tick}-${line.from}-${line.text}`} className="flex items-start gap-2">
              <VillagerSprite name={line.from} size={24} />
              <p className="min-w-0">
                <span className="text-dusk-muted tabular-nums">{line.time} </span>
                <span className="font-semibold" style={{ color: colors.get(line.from) }}>
                  {line.from}
                </span>
                {line.to && <span className="text-dusk-muted"> to {line.to}</span>}
                <span className="text-dusk-muted">: </span>
                {line.text}
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
  const [chronicleOpen, setChronicleOpen] = useState(false);
  const [projectsOpen, setProjectsOpen] = useState(false);
  // The newest chronicle entry the owner saw; read on the client only (the map renders after load).
  const [seen, setSeen] = useState<string | null>(readSeen);
  const [seenAtOpen, setSeenAtOpen] = useState<string | null>(null);

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
  const markSeen = () => {
    const newest = state.chronicle[0]?.run_id ?? null;
    setSeen(newest);
    writeSeen(newest);
  };
  const openChronicle = () => {
    setSeenAtOpen(seen);
    markSeen();
    setSelected(null);
    setProjectsOpen(false);
    setChronicleOpen(true);
  };
  const openProjects = () => {
    setSelected(null);
    setChronicleOpen(false);
    setProjectsOpen(true);
  };
  const fresh = newEntries(state.chronicle, seen);


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
          <div
            className="mx-auto flex w-full flex-col gap-3 lg:max-w-(--map-max)"
            style={{ "--map-max": `calc((100dvh - 17rem) * ${state.map.width / state.map.height})` } as CSSProperties}
          >
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
          <WeatherIcon weather={state.weather} dark={state.dark} />
          <div>
            <p>
              <PixelDigits text={state.time} />
            </p>
            <p className="mt-2 text-base text-dusk-muted">{calendarText(state)}</p>
            <p className="text-sm text-dusk-muted">
              {WEATHER_WORDS[state.weather]}, {state.period}
              {state.calendar.festival_in === 0 ? ", harvest festival" : ""}
            </p>
            {state.calendar.season === "autumn" && <p className="text-sm text-dusk-muted">{stallsText(state.stalls)}</p>}
            <p className="text-sm text-dusk-muted">{traderText(state)}</p>
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
        <div className="flex items-center gap-2.5 text-base text-dusk-muted" role="group" aria-label="Pace">
          Pace
          {PACES.map((pace) => (
            <button
              key={pace.label}
              type="button"
              aria-pressed={state.interval === pace.seconds}
              onClick={() => state.interval !== pace.seconds && void act(() => setVillageInterval(pace.seconds))}
              className="village-button village-button--small"
            >
              {pace.label}
            </button>
          ))}
        </div>
        {(streamError || error) && (
          <p role="alert" className="text-base text-fault">
            {streamError ?? error}
          </p>
        )}
        <hr className="border-t-2 border-dashed border-dusk-rule" />
        {chronicleOpen ? (
          <ChroniclePanel
            chronicle={state.chronicle}
            seen={seenAtOpen}
            onClose={() => {
              markSeen();
              setChronicleOpen(false);
            }}
            onOpenTurn={setTurn}
          />
        ) : projectsOpen ? (
          <ProjectsPanel state={state} onClose={() => setProjectsOpen(false)} onOpenTurn={setTurn} />
        ) : villager ? (
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
                      <span className="block truncate text-sm text-dusk-muted">{stateText(v)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="text-sm text-dusk-muted">Pick a villager to see what it remembers and every turn it took.</p>
            <div className="flex flex-wrap gap-2.5">
              <button type="button" onClick={openChronicle} className="village-button">
                Read the chronicle{fresh > 0 ? ` (${fresh} new)` : ""}
              </button>
              <button type="button" onClick={openProjects} className="village-button">
                Village projects
              </button>
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
