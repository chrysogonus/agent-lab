/** The village through the year (M10): season colours, growth stages, weather and the festival.
 * All decoration: nothing here is clickable. */

import type { CSSProperties } from "react";
import type { FieldStage, GardenStage, Season, Weather } from "../../lib/api"; // relative, as in pixels.tsx
import { INK, TILE, type Palette } from "./pixels";

// --- season colours ---

export type Look = { grass: string; tuft: string; blade: string; path: string; pebble: string; soil: string; furrow: string };

const LOOKS: Record<Season, Look> = {
  spring: { grass: "#8fd068", tuft: "#5fa144", blade: "#b5e889", path: "#ead39c", pebble: "#cdb27a", soil: "#a0703f", furrow: "#7d532f" },
  summer: { grass: "#86c95f", tuft: "#5fa144", blade: "#a9df7f", path: "#ead39c", pebble: "#cdb27a", soil: "#a0703f", furrow: "#7d532f" },
  autumn: { grass: "#a9b75c", tuft: "#7f8c3c", blade: "#cad07b", path: "#e6cc93", pebble: "#c4a56c", soil: "#9a6a3c", furrow: "#76502d" },
  winter: { grass: "#9fb38a", tuft: "#7b8f6a", blade: "#c1cfb0", path: "#ddd0b0", pebble: "#bfae8a", soil: "#8c6a4a", furrow: "#6c5038" },
};
const SNOW: Look = { grass: "#eef3f7", tuft: "#c9d7e3", blade: "#ffffff", path: "#e7e1d6", pebble: "#c9c0b0", soil: "#e1e6ec", furrow: "#b5c0cb" };

export function lookOf(season: Season, snow: boolean): Look {
  return snow ? SNOW : LOOKS[season];
}

/** Leaf colours per tree (o outline, L leaf, l shine, g shade, d dark); autumn mixes three. */
const LEAVES: Record<Exclude<Season, "winter">, Palette[]> = {
  spring: [
    { L: "#f4b8cf", l: "#ffe3ee", g: "#d985a8", d: "#4a8a46" }, // in blossom
    { L: "#6cc463", l: "#f7b6d2", g: "#4a9a4c", d: "#2f7340" },
  ],
  summer: [{ L: "#5db55a", l: "#8fd47a", g: "#3f8f46", d: "#2c6b38" }],
  autumn: [
    { L: "#e8b830", l: "#ffe27a", g: "#c98a1e", d: "#8f5a14" },
    { L: "#ee8a3a", l: "#ffc07a", g: "#c8642a", d: "#8a3f1c" },
    { L: "#d8503e", l: "#f2938a", g: "#a83a30", d: "#6e2420" },
  ],
};

/** The leaf palettes trees pick from by position, or null for bare winter trees. */
export function leavesOf(season: Season): Palette[] | null {
  return season === "winter" ? null : LEAVES[season];
}

export const BARE_TREE = [
  "................",
  "....s...s..s....",
  ".s..t...t..t..s.",
  ".t..t..t...t..t.",
  "..t.tt.t..tt.t..",
  "...t..tt.t..t...",
  "....t..ttt.t....",
  ".....t.ttt.t....",
  "......tttt......",
  ".......tt.......",
  ".......tt.......",
  "......ottto.....",
  "......otTo......",
  ".....oottoo.....",
  "....xxxxxxxx....",
  "................",
];

// --- fields and flowers ---

const FURROWS = (row: string, alt = row): string[] => [
  "................",
  "................",
  alt,
  row,
  "ffffffffffffffff",
  "................",
  "................",
  "................",
  "................",
  "................",
  alt,
  row,
  "ffffffffffffffff",
  "................",
  "................",
  "................",
];
const EMPTY = "................";
const CLODS = ["................", "...f.......f....", ".......f........", "............f...", "..f.............", "........f.....f.", "....f...........", "................", "..........f.....", ".f.....f........", "...........f....", "....f...........", ".........f....f.", "..f.............", ".......f........", "................"];

/** Rows for one field cell at a stage; `x` alternates greens and grain as before. */
export function fieldRows(stage: FieldStage, x: number, crops: { greens: string[]; wheat: string[] }): string[] {
  switch (stage) {
    case "resting":
      return CLODS;
    case "tilled":
      return FURROWS(EMPTY);
    case "sown":
      return FURROWS("..s...s...s...s.");
    case "sprouting":
      return FURROWS("..g...g...g...g.", "..G...G...G...G.");
    case "growing":
      return crops.greens;
    case "ripe":
      return x % 2 ? crops.wheat : crops.greens;
    case "harvested":
      return FURROWS(".Y.Y.Y.Y.Y.Y.Y.Y");
  }
}

/** Ripe greens turn to pumpkins. */
export const RIPE_GREENS: Palette = { G: "#f08a3c" };

export const WEEDS = [
  "................",
  "..w.........w...",
  ".wWw.......wWw..",
  "..W...........W.",
  "................",
  ".......w........",
  "......wWw.......",
  ".......W........",
  "................",
  "...w.........w..",
  "..wWw.......wWw.",
  "...W.........W..",
  "................",
  ".........w......",
  "........wWw.....",
  ".........W......",
];
export const WEEDS_PALETTE: Palette = { w: "#5b7a2a", W: "#3e5a1c" };

const PLANT_LETTERS = ["p", "r", "v", "y", "w"];

/** The flower beds' colours at a stage: blooming as drawn, or buds, wilted, bare. */
export function gardenPalette(stage: GardenStage, blooming: Palette): Palette {
  const each = (lower: string, upper: string, green: string): Palette => ({
    ...blooming,
    g: green,
    ...Object.fromEntries(PLANT_LETTERS.flatMap((l) => [[l, lower], [l.toUpperCase(), upper]])),
  });
  if (stage === "budding") return each("#a6d98a", "#6fb552", blooming.g);
  if (stage === "wilting") return each("#c9a46a", "#9a7a4a", "#8f9a4a");
  if (stage === "resting") return each(blooming.d, blooming.d, blooming.d);
  return blooming;
}

// --- weather ---

/** A stable spread of n points over the map, the same on every render. */
function scatter(n: number, width: number, seed: number): [number, number][] {
  return Array.from({ length: n }, (_, i) => [((i * 97 + seed * 31) % 101) / 101 * width, ((i * 53 + seed * 17) % 89) / 89]);
}

const TINT: Partial<Record<Weather, [string, number]>> = {
  clouds: ["#56657a", 0.08],
  rain: ["#4c5c70", 0.2],
  storm: ["#2f3a4c", 0.32],
  fog: ["#dfe5ea", 0.18],
  snow: ["#c8d3e0", 0.12],
};

/** Rain, storm, fog, snow or passing cloud shadows over the whole map. */
export function WeatherLayer({ weather, width, height }: { weather: Weather; width: number; height: number }) {
  const tint = TINT[weather];
  const wet = weather === "rain" || weather === "storm";
  return (
    <g pointerEvents="none" aria-hidden>
      {tint && <rect width={width} height={height} fill={tint[0]} opacity={tint[1]} />}
      {weather === "clouds" &&
        [0, 1].map((i) => (
          <g key={i} className="village-cloud" style={{ animationDelay: `-${i * 22}s` }}>
            <rect x={-150} y={40 + i * 150} width={120} height={40} fill="#1f2a3a" opacity={0.1} />
            <rect x={-130} y={28 + i * 150} width={80} height={64} fill="#1f2a3a" opacity={0.1} />
          </g>
        ))}
      {wet &&
        scatter(weather === "storm" ? 60 : 40, width, 1).map(([x, f], i) => (
          <rect key={i} className="village-rain" style={{ animationDelay: `-${f * 0.8}s`, "--still": `${f * height}px` } as CSSProperties} x={x} y={0} width={1} height={5} fill="#d6e6f5" opacity={0.7} />
        ))}
      {weather === "storm" && <rect className="village-flash" width={width} height={height} fill="#ffffff" opacity={0} />}
      {weather === "fog" &&
        [0.18, 0.5, 0.8].map((y, i) => (
          <g key={y} className="village-fog" style={{ animationDelay: `-${i * 9}s` }}>
            {[44, 30, 16].map((h) => (
              <rect key={h} x={-40} y={y * height - h / 2} width={width + 80} height={h} fill="#f4f6f8" opacity={0.1} />
            ))}
          </g>
        ))}
      {weather === "snow" &&
        scatter(40, width, 2).map(([x, f], i) => (
          <rect key={i} className="village-flake" style={{ animationDelay: `-${f * 7}s`, "--still": `${f * height}px` } as CSSProperties} x={x} y={0} width={2} height={2} fill="#ffffff" />
        ))}
    </g>
  );
}

/** Puddles on a few path cells on a wet day, with rings where drops fall. */
export function Puddles({ rows }: { rows: string[] }) {
  const paths = rows.flatMap((row, y) => [...row].flatMap((c, x) => (c === "=" ? [[x, y] as [number, number]] : [])));
  const picks = paths.filter((_, i) => i % 9 === 4);
  return (
    <g pointerEvents="none" aria-hidden>
      {picks.map(([x, y], i) => (
        <g key={`${x},${y}`}>
          <ellipse cx={x * TILE + 8} cy={y * TILE + 9} rx={5} ry={2} fill="#8fb9d6" opacity={0.85} />
          <ellipse className="village-ring-wave" style={{ animationDelay: `${(i % 5) * 0.9}s` }} cx={x * TILE + 8} cy={y * TILE + 9} rx={3} ry={1.2} fill="none" stroke="#e3f1fb" strokeWidth={0.6} opacity={0} />
        </g>
      ))}
    </g>
  );
}

export const WEATHER_WORDS: Record<Weather, string> = {
  sun: "Sunny",
  clouds: "Cloudy",
  rain: "Rain",
  storm: "Storm",
  fog: "Fog",
  snow: "Snow",
};


/** The HUD's weather in 12 x 12 pixels; a clear night shows the moon. */
export function WeatherIcon({ weather, dark }: { weather: Weather; dark: boolean }) {
  const cloud = (fill: string) => <path d="M3 4h4v1h2v1h1v3H1V6h1V5h1z" fill={fill} stroke={INK} strokeWidth={0.6} />;
  return (
    <svg viewBox="0 0 12 12" width={36} height={36} className="pixel-art shrink-0" role="img" aria-label={WEATHER_WORDS[weather]}>
      {weather === "sun" &&
        (dark ? (
          <path d="M5 1h3v1h1v1H7v1H6v4h1v1h2v1H8v1H5v-1H3V9H2V3h1V2h2z" fill="#ffe9a8" stroke={INK} strokeWidth={0.6} />
        ) : (
          <>
            <path d="M5 0h2v2H5zM5 10h2v2H5zM0 5h2v2H0zM10 5h2v2h-2zM1 1h2v2H1zM9 1h2v2H9zM1 9h2v2H1zM9 9h2v2H9z" fill="#f0a830" />
            <rect x={3} y={3} width={6} height={6} fill="#ffd75e" stroke={INK} strokeWidth={0.6} />
          </>
        ))}
      {weather === "clouds" && (
        <>
          {!dark && <rect x={6} y={1} width={4} height={4} fill="#ffd75e" stroke={INK} strokeWidth={0.6} />}
          {cloud("#f4f6f8")}
        </>
      )}
      {(weather === "rain" || weather === "storm") && (
        <>
          {cloud(weather === "storm" ? "#9aa3b2" : "#d5dbe3")}
          {weather === "storm" ? <path d="M6 9h2l-1 1h1l-2 2v-1h-1z" fill="#ffd75e" stroke={INK} strokeWidth={0.3} /> : <path d="M3 10h1v2H3zM6 10h1v2H6zM9 10h1v2H9z" fill="#4fa6de" />}
        </>
      )}
      {weather === "fog" && <path d="M1 3h10v1H1zM2 6h9v1H2zM1 9h10v1H1z" fill="#9aa3b2" />}
      {weather === "snow" && <path d="M5 1h2v10H5zM1 5h10v2H1zM3 3h1v1H3zM8 3h1v1H8zM3 8h1v1H3zM8 8h1v1H8z" fill="#ffffff" stroke={INK} strokeWidth={0.4} />}
    </svg>
  );
}
