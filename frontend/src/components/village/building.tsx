/** Building together (M12): the daily trader, carried loads, building plots, sites and what the
 * village has built. All decoration: nothing here is clickable. */

import type { BuildingGoods, Trader as TraderState } from "../../lib/api"; // relative, as in pixels.tsx
import { BUILDING_GOODS, type Area } from "../../lib/village";
import { INK, TILE } from "./pixels";

const PLANK = "#c98b4a";
const PLANK_DARK = "#8a5328";
const PAINT = "#4f7fd6";
const LEAF = "#5db55a";

/** One unit of building goods in a 6 × 5 box: planks, a paint pot or a sapling. */
function Goods({ goods, x, y }: { goods: BuildingGoods; x: number; y: number }) {
  if (goods === "wood") {
    return (
      <g transform={`translate(${x} ${y})`}>
        <rect x={0} y={1} width={6} height={1.5} fill={PLANK} stroke={INK} strokeWidth={0.4} />
        <rect x={0} y={3} width={6} height={1.5} fill={PLANK_DARK} stroke={INK} strokeWidth={0.4} />
      </g>
    );
  }
  if (goods === "paint") {
    return (
      <g transform={`translate(${x} ${y})`}>
        <rect x={1} y={1} width={4} height={4} fill="#d9d4c7" stroke={INK} strokeWidth={0.4} />
        <rect x={1} y={1} width={4} height={1.2} fill={PAINT} />
      </g>
    );
  }
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={1.5} y={3} width={3} height={2} fill="#c4643a" stroke={INK} strokeWidth={0.4} />
      <rect x={2.5} y={0.5} width={1} height={2.5} fill={PLANK_DARK} />
      <rect x={1} y={0} width={4} height={1.5} fill={LEAF} />
    </g>
  );
}

/** The trader's cart in the market's bottom-left corner, with a pile of each of its goods. */
export function Trader({ area, trader }: { area: Area; trader: TraderState }) {
  const x = area.x0 * TILE + 1;
  const y = area.y1 * TILE + 2;
  const stocked = BUILDING_GOODS.filter((g) => trader.stock[g] > 0);
  return (
    <g pointerEvents="none" aria-hidden>
      <rect x={x + 1} y={y + 10} width={13} height={2} fill="#00000025" />
      <rect x={x} y={y + 5} width={14} height={5} fill={PLANK} stroke={INK} strokeWidth={0.5} />
      <rect x={x} y={y + 7} width={14} height={1} fill={PLANK_DARK} />
      <circle cx={x + 3.5} cy={y + 11} r={1.8} fill={PLANK_DARK} stroke={INK} strokeWidth={0.5} />
      <circle cx={x + 10.5} cy={y + 11} r={1.8} fill={PLANK_DARK} stroke={INK} strokeWidth={0.5} />
      <rect x={x + 13.5} y={y + 7} width={2.5} height={0.8} fill={INK} />
      {stocked.map((g, i) => (
        <Goods key={g} goods={g} x={x + 0.5 + i * 4.5} y={y} />
      ))}
    </g>
  );
}

/** A carried load beside a villager's sprite, where a basket would be. */
export function Load({ goods }: { goods: BuildingGoods }) {
  return (
    <g pointerEvents="none" aria-hidden>
      <Goods goods={goods} x={7} y={-2} />
    </g>
  );
}

// --- plots, building sites and what the village has built ---

const FENCE = "#d8c3a0";
const PAINTED = ["#4f9fd8", "#e5729a", "#f2b83a", "#7cc35a", "#a07ad8"];

/** A fenced, empty plot waiting for a building. */
export function Plot({ area }: { area: Area }) {
  const x = area.x0 * TILE + 1;
  const y = area.y0 * TILE + 1;
  const w = (area.x1 - area.x0 + 1) * TILE - 2;
  const h = (area.y1 - area.y0 + 1) * TILE - 2;
  const posts = Array.from({ length: Math.floor(w / 8) + 1 }, (_, i) => x + i * 8);
  return (
    <g pointerEvents="none" aria-hidden>
      <rect x={x} y={y} width={w} height={h} fill="none" stroke={FENCE} strokeWidth={1} />
      {posts.map((px) => (
        <g key={px}>
          <rect x={px - 0.5} y={y - 1.5} width={1.5} height={3} fill={PLANK_DARK} />
          <rect x={px - 0.5} y={y + h - 1.5} width={1.5} height={3} fill={PLANK_DARK} />
        </g>
      ))}
    </g>
  );
}

/** Scaffolding over what is being built, and the loads lying at its site. */
export function Site({ at, site, loads }: { at: Area; site: [number, number]; loads: Partial<Record<BuildingGoods, number>> }) {
  const x = at.x0 * TILE;
  const y = at.y0 * TILE;
  const w = (at.x1 - at.x0 + 1) * TILE;
  const h = (at.y1 - at.y0 + 1) * TILE;
  const lying = BUILDING_GOODS.flatMap((g) => Array.from({ length: Math.min(loads[g] ?? 0, 3) }, () => g));
  return (
    <g pointerEvents="none" aria-hidden>
      {[0, w / 2, w].map((dx) => (
        <rect key={dx} x={x + dx - 1} y={y + 2} width={2} height={h - 2} fill={PLANK} stroke={INK} strokeWidth={0.4} />
      ))}
      {[h / 3, (2 * h) / 3].map((dy) => (
        <rect key={dy} x={x - 1} y={y + dy} width={w + 2} height={1.5} fill={PLANK_DARK} />
      ))}
      {lying.map((g, i) => (
        <Goods key={i} goods={g} x={site[0] * TILE + 1 + (i % 2) * 7} y={site[1] * TILE + 2 + Math.floor(i / 2) * 5} />
      ))}
    </g>
  );
}

function YoungTree({ x, y }: { x: number; y: number }) {
  return (
    <g>
      <rect x={x + 7} y={y + 9} width={2} height={5} fill={PLANK_DARK} />
      <circle cx={x + 8} cy={y + 7} r={4.5} fill={LEAF} stroke={INK} strokeWidth={0.5} />
      <circle cx={x + 6.5} cy={y + 5.5} r={1.5} fill="#8fd47a" />
    </g>
  );
}

/** What the village has built, by kind: fresh paint, young trees, a stand, a house or a boat. */
export function Built({ kind, area, index }: { kind: string; area: Area; index: number }) {
  const x = area.x0 * TILE;
  const y = area.y0 * TILE;
  const w = (area.x1 - area.x0 + 1) * TILE;
  if (kind === "paint") {
    const colour = PAINTED[index % PAINTED.length];
    const wall = (area.y1 - 1) * TILE + 16; // as Building draws its wall
    return (
      <g pointerEvents="none" aria-hidden>
        <rect x={x + 2} y={wall} width={w - 4} height={2} fill={colour} />
        <rect x={x + 2} y={wall + 14} width={w - 4} height={2} fill={colour} />
      </g>
    );
  }
  if (kind === "trees") return <YoungTree x={x} y={y} />;
  if (kind === "stand") {
    return (
      <g pointerEvents="none" aria-hidden>
        <rect x={x + 2} y={y + 3} width={1} height={11} fill={INK} />
        <rect x={x + 13} y={y + 3} width={1} height={11} fill={INK} />
        {[0, 1, 2, 3].map((s) => (
          <rect key={s} x={x + 1 + s * 3.5} y={y + 1} width={3.5} height={3} fill={s % 2 ? "#fffaf0" : "#4f7fd6"} />
        ))}
        <rect x={x + 1} y={y + 9} width={14} height={3} fill={PLANK} stroke={INK} strokeWidth={0.5} />
      </g>
    );
  }
  if (kind === "boat") {
    return (
      <g pointerEvents="none" aria-hidden>
        <path d={`M${x + 1} ${y + 8}h14l-2.5 4h-9z`} fill={PLANK} stroke={INK} strokeWidth={0.6} />
        <rect x={x + 3} y={y + 9} width={10} height={1} fill={PAINT} />
        <rect x={x + 7} y={y + 4} width={1} height={4} fill={PLANK_DARK} />
      </g>
    );
  }
  return null; // buildings: drawn by the village view with the houses' look
}
