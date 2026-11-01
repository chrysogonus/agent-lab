// The village's pixel art, drawn in code: tiles, places, scenery and the four villagers.
// One map cell is a 16 x 16 pixel tile; the map's SVG viewBox counts pixels.
import { memo, type CSSProperties, type ReactNode } from "react";
import type { FieldStage, GardenStage, Season } from "../../lib/api";
import { cellKind, placeAreas, type Activity, type Area } from "../../lib/village"; // relative: the sprite test runs without path aliases
import { BARE_TREE, RIPE_GREENS, WEEDS, WEEDS_PALETTE, fieldRows, gardenPalette, leavesOf, lookOf } from "./seasons";

export const TILE = 16;
export const INK = "#2a2340"; // the outline of everything

export type Palette = Record<string, string>;

/** Pixel rows ("." is see-through) as one rect per run of equal pixels. */
export function Pixels({ rows, palette, x = 0, y = 0 }: { rows: readonly string[]; palette: Palette; x?: number; y?: number }) {
  const rects: ReactNode[] = [];
  rows.forEach((row, j) => {
    for (let i = 0; i < row.length; ) {
      let k = i + 1;
      while (row[k] === row[i]) k++;
      if (row[i] !== ".") rects.push(<rect key={`${i},${j}`} x={x + i} y={y + j} width={k - i} height={1} fill={palette[row[i]]} />);
      i = k;
    }
  });
  return <>{rects}</>;
}

// --- villagers ---

const SKIN: Palette = { o: INK, e: INK, s: "#f8d3ad", S: "#e3aa82", k: "#f4a0a0", l: "#4a3428" };

export const SPRITES: Record<string, { rows: readonly string[]; palette: Palette }> = {
  Hilde: {
    // the mayor: top hat with a gold band, grey hair, purple coat with the chain of office
    rows: [
      "................",
      ".....oooooo.....",
      ".....oTTTTo.....",
      ".....oTTTTo.....",
      ".....obbbbo.....",
      "...ooTTTTTToo...",
      "..ohhsssssshho..",
      "..ohsessssesho..",
      "..ohsessssesho..",
      "...osksssskso...",
      "....oSssssSo....",
      "...occyccycco...",
      "..osccyyyyccso..",
      "..osccccccccso..",
      "...oCccooccCo...",
      "...ollo..ollo...",
    ],
    palette: { ...SKIN, h: "#d2cce0", T: "#3a3352", b: "#ffd75e", c: "#7c4dcc", C: "#5a33a3", y: "#ffd75e" },
  },
  Jonas: {
    // the fisher: yellow rain hat, brown beard, teal oilskin
    rows: [
      "................",
      "................",
      ".....oooooo.....",
      "....oYYYYYYo....",
      "...oYYYYYYYYo...",
      ".ooZYYYYYYYYZoo.",
      "..ohhsssssshho..",
      "..ohsessssesho..",
      "..ohsessssesho..",
      "...ohssssssho...",
      "....ohhhhhho....",
      "...occcwwccco...",
      "..osccccccccso..",
      "..osCcccccccso..",
      "...oCccooccCo...",
      "...ollo..ollo...",
    ],
    palette: { ...SKIN, h: "#8a5a3a", Y: "#f4c430", Z: "#c99712", c: "#0f7f81", C: "#0a5e60", w: "#fffaf0" },
  },
  Greta: {
    // the farmer: wide straw hat, brown overalls over a pale shirt
    rows: [
      "................",
      "................",
      ".....oooooo.....",
      "....oYYYYYYo....",
      "....obbbbbbo....",
      "ooYYYYYYYYYYYYoo",
      "..ohhsssssshho..",
      "..ohsessssesho..",
      "..ohsessssesho..",
      "...osksssskso...",
      "....oSssssSo....",
      "...owcwwwwcwo...",
      "..oswccccccwso..",
      "..osccCCCCccso..",
      "...occcooccco...",
      "...ollo..ollo...",
    ],
    palette: { ...SKIN, h: "#7a4a26", Y: "#ecd28a", b: "#a35a12", c: "#a35a12", C: "#7d430c", w: "#f3ecd8" },
  },
  Lina: {
    // the flower girl: orange pigtails with a daisy, pink dress and apron
    rows: [
      "...........ww...",
      ".....oooooowfw..",
      "....ohhhhhhoww..",
      "...ohhhhhhhho...",
      ".oohhhhhhhhhhoo.",
      "ohohhsssssshhoho",
      "ohohsesssseshoho",
      "ohohsesssseshoho",
      ".o.osksssskso.o.",
      "....oSssssSo....",
      "...occwwwwcco...",
      "..oscwwwwwwcso..",
      "..oscwwwwwwcso..",
      ".occcccccccccco.",
      ".oCCCCCCCCCCCCo.",
      "...ooso..osoo...",
    ],
    palette: { ...SKIN, h: "#e8743b", w: "#ffffff", f: "#ffd75e", c: "#c22d6f", C: "#931f53" },
  },
};

/** A villager's sprite on its own, e.g. in the menu; unknown names get a plain silhouette. */
export function VillagerSprite({ name, size = 32 }: { name: string; size?: number }) {
  const sprite = SPRITES[name] ?? SPRITES.Lina;
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className="pixel-art shrink-0" aria-hidden>
      <Pixels rows={sprite.rows} palette={sprite.palette} />
    </svg>
  );
}

// --- tiles ---

const C = {
  grass: "#86c95f",
  tuft: "#5fa144",
  blade: "#a9df7f",
  path: "#ead39c",
  pebble: "#cdb27a",
  pathEdge: "#c4a265",
  water: "#4fa6de",
  wave: "#a7dbf5",
  foam: "#e3f5fc",
  stone: "#dcd6c6",
  joint: "#bdb5a3",
  soil: "#a0703f",
  furrow: "#7d532f",
  wood: "#b9773f",
  woodDark: "#7e4a24",
  plankGap: "#8a5328",
  roof: "#d6584b",
  roofDark: "#a83d36",
  wall: "#f4e8cf",
  glass: "#8cc4e8",
  lit: "#ffd75e",
  leaf: "#3f8f46",
  leafLight: "#5db55a",
  leafShine: "#8fd47a",
  leafDark: "#2c6b38",
};

const GRASS_TILES = [
  ["................", "................", "...d............", "..d.d.......l...", "..........l.l...", "................", "................", ".......d........", "......d.d.......", "................", "................", ".............d..", "............d.d.", "..l.............", "................", "................"],
  ["................", "..........d.....", ".........d.d....", "................", "................", "....l...........", "...l.l..........", "................", "................", "............l...", "...........l.l..", "................", "...d............", "..d.d...........", "................", "................"],
  ["................", "................", "......d.........", ".....d.d........", "................", "...........w....", "..........wyw...", "...........w....", "................", "................", "..l.............", ".l.l............", "................", "........d.......", ".......d.d......", "................"],
];
const GRASS_PALETTE = { d: C.tuft, l: C.blade, w: "#ffffff", y: "#ffd75e" };

const PATH_TILE = ["................", "................", "....p...........", "...........q....", "................", "................", "........p.......", "................", "..q.............", "................", "...........p....", "................", "................", "....p......q....", "................", "................"];

const WAVES_A = ["................", "................", "..ww............", "....ww..........", "................", ".........ww.....", "...........ww...", "................", "................", ".ww.............", "...ww...........", "................", "..........ww....", "............ww..", "................", "................"];
const WAVES_B = WAVES_A.map((row) => row.slice(3) + row.slice(0, 3)); // the same waves, drifted

const STONE_TILE = ["jjjjjjjjjjjjjjjj", ".......j........", ".......j........", ".......j........", ".......j........", ".......j........", ".......j........", "jjjjjjjjjjjjjjjj", "j...............", "j...............", "j...............", "j...............", "j...............", "j...............", "j...............", "j..............."];

const CROPS = {
  greens: ["................", "..g...g...g...g.", ".gGg.gGg.gGg.gGg", "..g...g...g...g.", "ffffffffffffffff", "................", "................", "................", "................", "..g...g...g...g.", ".gGg.gGg.gGg.gGg", "..g...g...g...g.", "ffffffffffffffff", "................", "................", "................"],
  wheat: ["..y...y...y...y.", ".yYy.yYy.yYy.yYy", ".yYy.yYy.yYy.yYy", "..g...g...g...g.", "ffffffffffffffff", "................", "................", "................", "..y...y...y...y.", ".yYy.yYy.yYy.yYy", ".yYy.yYy.yYy.yYy", "..g...g...g...g.", "ffffffffffffffff", "................", "................", "................"],
};
const CROP_PALETTE = { g: "#4f9a3c", G: "#7cc35a", y: "#efcd63", Y: "#c99a35", f: C.furrow };

const FLOWER_BED = ["................", ".ddddddddddddd..", ".dpgdrgdvgdygd..", ".dPpdRrdVvdYyd..", ".dgddgddgddgdd..", ".ddddddddddddd..", "................", "................", "................", ".ddddddddddddd..", ".dygdpgdwgdrgd..", ".dYydPpdWwdRrd..", ".dgddgddgddgdd..", ".ddddddddddddd..", "................", "................"];
const FLOWER_PALETTE = { d: "#7a5435", g: "#4f9a3c", p: "#f7a8cc", P: "#e0679d", r: "#f2696b", R: "#c83e45", v: "#c3a2f0", V: "#8f63d4", y: "#ffe27a", Y: "#e8b830", w: "#ffffff", W: "#d9dce8" };

const TREE = ["....oooooooo....", "..ooLLLLLLLLoo..", ".oLLLlLLLLLLLLo.", ".oLLlLLLLLLLLgo.", "oLLLLLLLLLLLgggo", "oLLLLLLLLLLggggo", "oLLLLLLLLLgggggo", "ogLLLLLLLggggggo", "oggLLLLLgggggddo", ".oggggggggggddo.", "..ooggggggddoo..", "....oooooooo....", "......otto......", "......otTo......", ".....oottoo.....", "....xxxxxxxx...."];
const TREE_PALETTE = { o: INK, L: C.leafLight, l: C.leafShine, g: C.leaf, d: C.leafDark, t: "#9a5b2c", T: "#6e3f1e", x: "#00000026" };

const LAMP = ["......oooo......", ".....oyyyyo.....", ".....oyyyyo.....", "......oooo......", ".......oo.......", ".......oo.......", ".......oo.......", ".......oo.......", ".......oo.......", ".......oo.......", ".......oo.......", ".......oo.......", "......oooo......", ".....xxxxxx.....", "................", "................"];

const FOUNTAIN = [".........ll.........", "........lwwl........", ".......l.ww.l.......", "..oooooooSSooooooo..", ".osssssssSSssssssso.", "oswwwwwwwSSwwwwwwwso", "oswlwwwwwwwwwwwlwwso", "oswwwwwlwwwwwwwwwwso", "oSswwwwwwwwwwwwwwsSo", ".oSssssssssssssssSo.", "..oSSSSSSSSSSSSSSo..", "...oooooooooooooo..."];
const FOUNTAIN_PALETTE = { o: INK, s: "#cfc9ba", S: "#a49d8c", w: "#5fb5e8", l: "#c4ecfb" };

const STALL = ["oooooooooooooooo", "oaawwaawwaawwaao", "oaawwaawwaawwaao", "oaawwaawwaawwaao", ".oaaoaaoaaoaaoa.", "..o..o..o..o..o.", ".p............p.", ".p............p.", ".p.GGGGGGGGGG.p.", ".poooooooooooop.", ".pWWWWWWWWWWWWp.", ".pWDDDDDDDDDDWp.", ".pWWWWWWWWWWWWp.", ".poooooooooooop.", "................", "................"];
const STALL_GOODS: [string, Palette][] = [
  // fish, vegetables, flowers
  ["#e85a4f", { G: "#7fa7c4" }],
  ["#4f9a3c", { G: "#f08a3c" }],
  ["#4f7fd0", { G: "#f7a8cc" }],
];

const BOAT = [".oooooooooooooooooo.", "obbbbbbbbbbbbbbbbbbo", "obBBoBBBBBBBBBBoBBbo", ".obbbbbbbbbbbbbbbbo.", "..oBBBBBBBBBBBBBBo..", "...oooooooooooooo..."];
const BOAT_PALETTE = { o: INK, b: "#c98a4f", B: "#9a5f30" };

function hash(x: number, y: number): number {
  return (x * 7 + y * 13 + x * y) % 3;
}

type Year = { season: Season; snow: boolean; fields: FieldStage; garden: GardenStage };

function Defs({ season, snow, fields, garden }: Year) {
  // A tile's ground overlaps the next tile by half a pixel, so no seams show when the map is scaled.
  const look = lookOf(season, snow);
  const leaves = leavesOf(season);
  const grassPalette = { ...GRASS_PALETTE, d: look.tuft, l: look.blade };
  const crop = (x: number) => fieldRows(fields, x, CROPS);
  const cropPalette = { ...CROP_PALETTE, f: look.furrow, s: "#e0c080", ...(fields === "ripe" ? RIPE_GREENS : {}) };
  const tile = (id: string, fill: string, overlay?: ReactNode) => (
    <g key={id} id={id}>
      <rect width={TILE + 0.5} height={TILE + 0.5} fill={fill} />
      {overlay}
    </g>
  );
  return (
    <defs>
      {GRASS_TILES.map((rows, i) => tile(`vt-grass${i}`, look.grass, <Pixels rows={rows} palette={grassPalette} />))}
      {tile("vt-path", look.path, <Pixels rows={PATH_TILE} palette={{ p: look.pebble, q: snow ? "#ffffff" : "#f6e6bd" }} />)}
      {tile("vt-water", C.water)}
      <g id="vt-waves-a">
        <Pixels rows={WAVES_A} palette={{ w: C.wave }} />
      </g>
      <g id="vt-waves-b">
        <Pixels rows={WAVES_B} palette={{ w: C.wave }} />
      </g>
      {tile("vt-stone", C.stone, <Pixels rows={STONE_TILE} palette={{ j: C.joint }} />)}
      {[0, 1].map((x) => {
        const rows = crop(x);
        return tile(`vt-field${x}`, look.soil, <Pixels rows={rows} palette={cropPalette} />);
      })}
      <g id="vt-weeds">
        <Pixels rows={WEEDS} palette={WEEDS_PALETTE} />
      </g>
      {tile("vt-flowers", look.grass, <Pixels rows={FLOWER_BED} palette={gardenPalette(garden, FLOWER_PALETTE)} />)}
      <g id="vt-planks">
        <rect width={TILE + 0.5} height={TILE + 0.5} fill={C.wood} />
        {[0, 4, 8, 12].map((y) => (
          <g key={y}>
            <rect y={y} width={TILE} height={1} fill="#d39257" />
            <rect y={y + 3} width={TILE} height={1} fill={C.plankGap} />
          </g>
        ))}
      </g>
      {(leaves ?? [null]).map((palette, i) => (
        <g key={i} id={`vt-tree${i}`}>
          {palette ? (
            <Pixels rows={TREE} palette={{ ...TREE_PALETTE, ...palette }} />
          ) : (
            <Pixels rows={BARE_TREE} palette={{ ...TREE_PALETTE, s: snow ? "#ffffff" : TREE_PALETTE.t }} />
          )}
        </g>
      ))}
      <g id="vt-lamp">
        <Pixels rows={LAMP} palette={{ o: INK, y: "#efe6c4", x: "#00000026" }} />
      </g>
    </defs>
  );
}

/** Lines along the sides of a cell that border another kind of ground. */
function Edges({ rows, x, y, kind, color, width }: { rows: string[]; x: number; y: number; kind: string; color: string; width: number }) {
  const differs = (nx: number, ny: number) => {
    const char = rows[ny]?.[nx];
    return char !== undefined && cellKind(char) !== kind && !(kind === "water" && char === "P");
  };
  const px = x * TILE;
  const py = y * TILE;
  return (
    <>
      {differs(x, y - 1) && <rect x={px} y={py} width={TILE} height={width} fill={color} />}
      {differs(x, y + 1) && <rect x={px} y={py + TILE - width} width={TILE} height={width} fill={color} />}
      {differs(x - 1, y) && <rect x={px} y={py} width={width} height={TILE} fill={color} />}
      {differs(x + 1, y) && <rect x={px + TILE - width} y={py} width={width} height={TILE} fill={color} />}
    </>
  );
}

const PLACE_TILE: Record<string, string> = { T: "vt-stone", S: "vt-stone", M: "vt-stone", G: "vt-flowers", P: "vt-water" };

/** A building two cells tall whose bottom row is the area's bottom row: the town hall (its
 * row of `B` cells, with a flag) or a villager's house (roof in its owner's color). */
function Building({ area, roof, roofDark, flag }: { area: Area; roof: string; roofDark: string; flag?: boolean }) {
  const x = area.x0 * TILE;
  const y = (area.y1 - 1) * TILE;
  const w = (area.x1 - area.x0 + 1) * TILE;
  const bands = [8, 6, 4, 2, 0];
  return (
    <g>
      {/* a soft shadow on the ground in front of and beside the building */}
      <rect x={x + 3} y={y + 32} width={w - 2} height={3} fill="#1d2a1a" opacity={0.18} />
      <rect x={x + w - 1} y={y + 17} width={3} height={18} fill="#1d2a1a" opacity={0.14} />
      {flag ? (
        <>
          <rect x={x + w / 2} y={y} width={1} height={8} fill={INK} />
          <rect x={x + w / 2 + 1} y={y} width={7} height={4} fill="#4f7fd0" />
        </>
      ) : (
        <rect x={x + w - 14} y={y + 1} width={4} height={6} fill={C.woodDark} stroke={INK} strokeWidth={0.5} />
      )}
      {bands.map((inset, i) => (
        <g key={inset}>
          <rect x={x + inset} y={y + 5 + i * 2} width={w - inset * 2} height={2} fill={i === bands.length - 1 ? roofDark : roof} />
          <rect x={x + inset - 1} y={y + 5 + i * 2} width={1} height={2} fill={INK} />
          <rect x={x + w - inset} y={y + 5 + i * 2} width={1} height={2} fill={INK} />
        </g>
      ))}
      <rect x={x + 8} y={y + 4} width={w - 16} height={1} fill={INK} />
      <rect x={x - 1} y={y + 15} width={w + 2} height={1} fill={INK} />
      <rect x={x + 2} y={y + 16} width={w - 4} height={16} fill={C.wall} />
      <rect x={x + 1} y={y + 16} width={1} height={16} fill={INK} />
      <rect x={x + w - 2} y={y + 16} width={1} height={16} fill={INK} />
      <rect x={x + w / 2 - 5} y={y + 21} width={10} height={11} fill={INK} />
      <rect x={x + w / 2 - 4} y={y + 22} width={8} height={10} fill={C.woodDark} />
      <rect x={x + w / 2 + 2} y={y + 27} width={1} height={1} fill={C.lit} />
      {buildingWindows(area).map(([wx, wy]) => (
        <g key={wx}>
          <rect x={wx - 1} y={wy - 1} width={10} height={8} fill={INK} />
          <rect x={wx} y={wy} width={8} height={6} fill={C.glass} />
          <rect x={wx + 4} y={wy} width={1} height={6} fill={INK} />
        </g>
      ))}
    </g>
  );
}

function buildingWindows(area: Area): [number, number][] {
  const x = area.x0 * TILE;
  const y = (area.y1 - 1) * TILE + 22; // below the name plate on the wall
  const w = (area.x1 - area.x0 + 1) * TILE;
  return [
    [x + 5, y],
    [x + w - 13, y],
  ];
}

/** "#7c4dcc" darkened by `factor` (0–1), for a roof's lower band. */
function darker(hex: string, factor: number): string {
  const channels = [1, 3, 5].map((i) => Math.round(parseInt(hex.slice(i, i + 2), 16) * factor));
  return `#${channels.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

function Garden({ area }: { area: Area }) {
  // a picket fence around the beds, open at the bottom where the path comes in
  const x0 = area.x0 * TILE;
  const y0 = area.y0 * TILE;
  const x1 = (area.x1 + 1) * TILE;
  const y1 = (area.y1 + 1) * TILE;
  const gate = (area.x0 + 1) * TILE;
  const posts: [number, number][] = [];
  for (let x = x0; x < x1; x += 4) posts.push([x, y0], ...(x >= gate && x < gate + TILE ? [] : ([[x, y1 - 4]] as [number, number][])));
  for (let y = y0 + 4; y < y1 - 4; y += 4) posts.push([x0, y], [x1 - 2, y]);
  return (
    <g>
      <rect x={x0} y={y0 + 1} width={x1 - x0} height={1} fill={C.woodDark} />
      <rect x={x0} y={y1 - 3} width={gate - x0} height={1} fill={C.woodDark} />
      <rect x={gate + TILE} y={y1 - 3} width={x1 - gate - TILE} height={1} fill={C.woodDark} />
      <rect x={x0} y={y0} width={1} height={y1 - y0} fill={C.woodDark} />
      <rect x={x1 - 1} y={y0} width={1} height={y1 - y0} fill={C.woodDark} />
      {posts.map(([x, y]) => (
        <rect key={`${x},${y}`} x={x} y={y} width={2} height={4} fill="#f3e3c3" stroke={C.woodDark} strokeWidth={0.5} />
      ))}
    </g>
  );
}

function Market({ area }: { area: Area }) {
  return (
    <g>
      {Array.from({ length: area.x1 - area.x0 + 1 }, (_, i) => {
        const [awning, goods] = STALL_GOODS[i % STALL_GOODS.length];
        return (
          <Pixels
            key={i}
            rows={STALL}
            palette={{ o: INK, a: awning, w: "#fffaf0", p: C.woodDark, W: C.wood, D: C.plankGap, ...goods }}
            x={(area.x0 + i) * TILE}
            y={area.y0 * TILE}
          />
        );
      })}
    </g>
  );
}

function cellsOf(rows: string[], char: string): [number, number][] {
  return rows.flatMap((row, y) => [...row].flatMap((c, x) => (c === char ? [[x, y] as [number, number]] : [])));
}

/** Everything that does not change between steps: ground, places, houses and scenery.
 * `houses` is "letter:color" per home, joined by commas, so the memo compares a string. */
export const Ground = memo(function Ground({ map, houses, neglected, ...year }: { map: string; houses: string; neglected: boolean } & Year) {
  const rows = map.split("\n");
  const trees = leavesOf(year.season)?.length ?? 1;
  const areas = placeAreas(rows);
  const cells = rows.flatMap((row, y) => [...row].map((char, x) => ({ char, x, y })));
  const water = cells.filter((c) => c.char === "~" || c.char === "P");
  return (
    <g>
      <Defs {...year} />
      {cells.map(({ char, x, y }) => {
        const kind = cellKind(char);
        const id =
          kind === "path"
            ? "vt-path"
            : kind === "water"
              ? "vt-water"
              : kind === "place"
                ? char === "F"
                  ? `vt-field${x % 2}`
                  : (PLACE_TILE[char] ?? "vt-grass0")
                : `vt-grass${hash(x, y)}`; // grass, and the ground under trees, lamps and buildings
        return <use key={`${x},${y}`} href={`#${id}`} x={x * TILE} y={y * TILE} />;
      })}
      <g className="village-wave-a">
        {water.map(({ x, y }) => (
          <use key={`${x},${y}`} href="#vt-waves-a" x={x * TILE} y={y * TILE} />
        ))}
      </g>
      <g className="village-wave-b">
        {water.map(({ x, y }) => (
          <use key={`${x},${y}`} href="#vt-waves-b" x={x * TILE} y={y * TILE} />
        ))}
      </g>
      {cells.map(({ char, x, y }) =>
        char === "=" ? (
          <Edges key={`${x},${y}`} rows={rows} x={x} y={y} kind="path" color={C.pathEdge} width={1} />
        ) : char === "~" ? (
          <Edges key={`${x},${y}`} rows={rows} x={x} y={y} kind="water" color={C.foam} width={2} />
        ) : null,
      )}
      {cells
        .filter((c) => c.char === "P")
        .map(({ x, y }) => (
          <g key={`pier-${x},${y}`}>
            <use href="#vt-planks" x={x * TILE} y={y * TILE} />
            <rect x={x * TILE} y={y * TILE + TILE} width={2} height={3} fill={C.woodDark} />
            <rect x={x * TILE + TILE - 2} y={y * TILE + TILE} width={2} height={3} fill={C.woodDark} />
          </g>
        ))}
      {areas.P && <Pixels rows={BOAT} palette={BOAT_PALETTE} x={(areas.P.x1 + 1) * TILE + 2} y={areas.P.y1 * TILE + 5} />}
      {areas.G && <Garden area={areas.G} />}
      {areas.S && <Pixels rows={FOUNTAIN} palette={FOUNTAIN_PALETTE} x={((areas.S.x0 + areas.S.x1 + 1) / 2) * TILE - 10} y={((areas.S.y0 + areas.S.y1 + 1) / 2) * TILE - 6} />}
      {areas.M && <Market area={areas.M} />}
      {areas.B && <Building area={areas.B} roof={C.roof} roofDark={C.roofDark} flag />}
      {houses
        .split(",")
        .filter(Boolean)
        .map((house) => {
          const [letter, color] = house.split(":");
          return areas[letter] && <Building key={letter} area={areas[letter]} roof={color} roofDark={darker(color, 0.7)} />;
        })}
      {neglected && cellsOf(rows, "F").map(([x, y]) => <use key={`weeds-${x},${y}`} href="#vt-weeds" x={x * TILE} y={y * TILE} />)}
      {cellsOf(rows, "t").map(([x, y]) => (
        <use key={`tree-${x},${y}`} href={`#vt-tree${(x * 5 + y * 3) % trees}`} x={x * TILE} y={y * TILE} />
      ))}
      {cellsOf(rows, "i").map(([x, y]) => (
        <use key={`lamp-${x},${y}`} href="#vt-lamp" x={x * TILE} y={y * TILE} />
      ))}
    </g>
  );
});

/** Lit windows and lamps, drawn above the night tint; shown from the evening on. */
export function Lights({ map, on }: { map: string; on: boolean }) {
  const rows = map.split("\n");
  const hall = placeAreas(rows).B;
  return (
    <g className="transition-opacity duration-1000" opacity={on ? 1 : 0} aria-hidden>
      {hall &&
        buildingWindows(hall).map(([x, y]) => (
          <g key={x}>
            <rect x={x - 3} y={y - 3} width={14} height={12} fill={C.lit} opacity={0.25} />
            <rect x={x} y={y} width={8} height={6} fill={C.lit} />
            <rect x={x + 4} y={y} width={1} height={6} fill={INK} />
          </g>
        ))}
      {cellsOf(rows, "i").map(([x, y]) => (
        <g key={`${x},${y}`}>
          {/* a wide and a tall box overlap into a stepped, roughly round glow */}
          <rect x={x * TILE - 4} y={y * TILE - 2} width={24} height={10} fill={C.lit} opacity={0.14} />
          <rect x={x * TILE + 1} y={y * TILE - 7} width={14} height={20} fill={C.lit} opacity={0.14} />
          <rect x={x * TILE + 4} y={y * TILE - 2} width={8} height={8} fill={C.lit} opacity={0.2} />
          <rect x={x * TILE + 6} y={y * TILE + 1} width={4} height={2} fill="#fff6c8" />
        </g>
      ))}
    </g>
  );
}

/** "Zz" over the roof of a house whose owner sleeps. */
export function Snores({ area }: { area: Area }) {
  const x = (area.x1 + 1) * TILE - 12;
  const y = (area.y1 - 1) * TILE + 2;
  return (
    <g className="village-snore" aria-hidden>
      <text x={x} y={y} fontSize={7} fill="#fffaf0" stroke={INK} strokeWidth={1.5} style={{ paintOrder: "stroke" }} className="font-pixel">
        z
      </text>
      <text x={x + 5} y={y - 5} fontSize={9} fill="#fffaf0" stroke={INK} strokeWidth={1.5} style={{ paintOrder: "stroke" }} className="font-pixel">
        Z
      </text>
    </g>
  );
}

// The clock's digits, 3 x 5 pixels each: the pixel font's 3 and 5 read as 8 and S.
const GLYPHS: Record<string, string[]> = {
  "0": ["ooo", "o.o", "o.o", "o.o", "ooo"],
  "1": [".o.", "oo.", ".o.", ".o.", "ooo"],
  "2": ["ooo", "..o", "ooo", "o..", "ooo"],
  "3": ["ooo", "..o", ".oo", "..o", "ooo"],
  "4": ["o.o", "o.o", "ooo", "..o", "..o"],
  "5": ["ooo", "o..", "ooo", "..o", "ooo"],
  "6": ["ooo", "o..", "ooo", "o.o", "ooo"],
  "7": ["ooo", "..o", "..o", ".o.", ".o."],
  "8": ["ooo", "o.o", "ooo", "o.o", "ooo"],
  "9": ["ooo", "o.o", "ooo", "..o", "ooo"],
  ":": [".", "o", ".", "o", "."],
};

/** Digits drawn as pixels, `height` CSS pixels tall; the text itself is for screen readers. */
export function PixelDigits({ text, height = 30 }: { text: string; height?: number }) {
  let x = 0;
  const glyphs = [...text].map((char, i) => {
    const rows = GLYPHS[char] ?? GLYPHS["0"];
    const glyph = <Pixels key={i} rows={rows} palette={{ o: INK }} x={x} />;
    x += rows[0].length + 1;
    return glyph;
  });
  const width = x - 1;
  return (
    <span className="inline-block leading-none">
      <svg viewBox={`0 0 ${width} 5`} height={height} width={(height / 5) * width} className="pixel-art" aria-hidden>
        {glyphs}
      </svg>
      <span className="sr-only">{text}</span>
    </span>
  );
}

// --- villagers in motion (M9) ---

const EYE = "e";

/** A villager drawn from its sprite: eyes apart, so they can blink and glance; while walking the
 * feet take turns lifting; at work it holds its prop. */
export function VillagerFigure({ name, activity, rhythm }: { name: string; activity: Activity; rhythm: number }) {
  const sprite = SPRITES[name] ?? SPRITES.Lina;
  const skin = sprite.palette.s;
  const face = sprite.rows.map((row) => row.replaceAll(EYE, "s"));
  const eyes = sprite.rows.map((row) => row.replace(/[^e]/g, "."));
  const walking = activity === "walking";
  const body = walking ? face.slice(0, 14) : face;
  const lift = (row: string, from: number) => [...row].map((c, i) => (i >= from && i < from + 8 ? "." : c)).join("");
  const style = { "--rhythm": `-${rhythm}s` } as CSSProperties;
  return (
    <g style={style} className={walking ? "village-walk" : activity === "talking" ? "village-talk" : "village-breathe"}>
      <g transform="translate(-8 -11)">
        <Pixels rows={body} palette={sprite.palette} />
        {walking && (
          <>
            <g className="village-step-a">
              <Pixels rows={[face[14], lift(face[15], 0)]} palette={sprite.palette} y={14} />
            </g>
            <g className="village-step-b">
              <Pixels rows={[face[14], lift(face[15], 8)]} palette={sprite.palette} y={14} />
            </g>
          </>
        )}
        <g className="village-glance">
          <Pixels rows={eyes} palette={{ e: INK }} />
        </g>
        <g className="village-blink">
          <Pixels rows={eyes} palette={{ e: skin }} />
        </g>
      </g>
      {activity === "working" && <WorkProp name={name} />}
    </g>
  );
}

/** What each villager works with at its own place, around its hands (x ±6, y 0). */
function WorkProp({ name }: { name: string }) {
  if (name === "Jonas") {
    return (
      <g aria-hidden>
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
          <rect key={i} x={6 + i} y={-1 - i * 1.4} width={1} height={1.6} fill="#7e4a24" />
        ))}
        <line x1={14} y1={-12} x2={17} y2={7} stroke="#e8f4ff" strokeWidth={0.4} />
        <g className="village-float">
          <rect x={16} y={6} width={2} height={1} fill="#e5484d" />
          <rect x={16} y={7} width={2} height={1} fill="#ffffff" />
        </g>
      </g>
    );
  }
  if (name === "Greta") {
    return (
      <g className="village-hoe" aria-hidden>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <rect key={i} x={6 + i * 0.8} y={-2 + i * 1.3} width={1} height={1.5} fill="#9a5b2c" />
        ))}
        <rect x={9} y={5} width={4} height={1.5} fill="#8a8f98" stroke={INK} strokeWidth={0.3} />
      </g>
    );
  }
  if (name === "Lina") {
    return (
      <g className="village-can" aria-hidden>
        <rect x={6} y={-2} width={5} height={4} rx={0.5} fill="#5fa8c9" stroke={INK} strokeWidth={0.4} />
        <rect x={10.5} y={-1.5} width={3} height={1} fill="#5fa8c9" stroke={INK} strokeWidth={0.3} />
        {[0, 1, 2].map((i) => (
          <rect key={i} className="village-drop" style={{ animationDelay: `${i * 0.25}s` }} x={13.5} y={0} width={0.8} height={1.2} fill="#a7dbf5" />
        ))}
      </g>
    );
  }
  return (
    <g className="village-paper" aria-hidden>
      <rect x={-3} y={-3} width={6} height={7} fill="#fffaf0" stroke={INK} strokeWidth={0.4} />
      {[-1.5, 0, 1.5].map((dy) => (
        <rect key={dy} x={-2} y={dy} width={4} height={0.5} fill="#8492a6" />
      ))}
    </g>
  );
}

// --- the living world (M9): all decoration, none of it clickable ---

/** Puffs rising from the chimney of a house whose owner is home and awake. */
export function Smoke({ area }: { area: Area }) {
  const x = (area.x1 + 1) * TILE - 12;
  const y = (area.y1 - 1) * TILE;
  return (
    <g pointerEvents="none" aria-hidden>
      {[0, 1, 2].map((i) => (
        <circle key={i} className="village-smoke" style={{ animationDelay: `${i * 1.1}s` }} cx={x} cy={y} r={1.8 + i * 0.5} fill="#cfd4dc" stroke="#9aa1ad" strokeWidth={0.3} opacity={0} />
      ))}
    </g>
  );
}

const BUTTERFLY_COLORS = ["#f7a8cc", "#ffe27a", "#c3a2f0"];

/** Butterflies over the flower garden, by day. */
export function Butterflies({ area }: { area: Area }) {
  const w = (area.x1 - area.x0 + 1) * TILE;
  const h = (area.y1 - area.y0 + 1) * TILE;
  return (
    <g pointerEvents="none" aria-hidden>
      {BUTTERFLY_COLORS.map((color, i) => (
        <g key={color} transform={`translate(${area.x0 * TILE + ((i + 1) * w) / 4} ${area.y0 * TILE + h / 2 - 4 + i * 3})`}>
          <g className="village-flutter-path" style={{ animationDelay: `-${i * 2.3}s` }}>
            <g className="village-flutter">
              <rect x={-2} y={-1} width={1.6} height={2} fill={color} />
              <rect x={0.4} y={-1} width={1.6} height={2} fill={color} />
            </g>
            <rect x={-0.4} y={-1} width={0.8} height={2} fill={INK} />
          </g>
        </g>
      ))}
    </g>
  );
}

/** Rings where fish jump, on a few water cells far from the shore. */
export function LakeRings({ map }: { map: string }) {
  const rows = map.split("\n");
  const open = cellsOf(rows, "~").filter(([x, y]) =>
    [-1, 0, 1].every((dy) => [-1, 0, 1].every((dx) => rows[y + dy]?.[x + dx] === "~")),
  );
  const picks = [0.2, 0.55, 0.85].map((f) => open[Math.floor(f * open.length)]).filter(Boolean);
  return (
    <g pointerEvents="none" aria-hidden>
      {picks.map(([x, y], i) => (
        <ellipse key={`${x},${y}`} className="village-ring-wave" style={{ animationDelay: `${i * 1.7}s` }} cx={x * TILE + 8} cy={y * TILE + 8} rx={6} ry={2.5} fill="none" stroke="#d8f1fc" strokeWidth={0.8} opacity={0} />
      ))}
    </g>
  );
}

/** Fireflies near the water and the trees, in the evening and at night. */
export function Fireflies({ map }: { map: string }) {
  const rows = map.split("\n");
  const shore = cellsOf(rows, "~").filter(([x, y]) => [rows[y - 1]?.[x], rows[y]?.[x - 1]].some((c) => c && c !== "~"));
  const spots = [...cellsOf(rows, "t"), ...shore];
  const picks = [0.05, 0.18, 0.31, 0.44, 0.57, 0.7, 0.83, 0.96].map((f) => spots[Math.floor(f * spots.length)]).filter(Boolean);
  return (
    <g pointerEvents="none" aria-hidden>
      {picks.map(([x, y], i) => (
        <g key={`${x},${y}`} className="village-firefly" style={{ animationDelay: `-${i * 0.9}s` }}>
          <circle cx={x * TILE + 8} cy={y * TILE + 2} r={2.2} fill="#fff3a0" opacity={0.25} />
          <rect x={x * TILE + 7.5} y={y * TILE + 1.5} width={1} height={1} fill="#fffbd0" />
        </g>
      ))}
    </g>
  );
}
