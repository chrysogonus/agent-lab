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
