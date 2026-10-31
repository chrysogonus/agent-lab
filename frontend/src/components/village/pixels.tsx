// The village's pixel art, drawn in code: tiles, places, scenery and the four villagers.
// One map cell is a 16 x 16 pixel tile; the map's SVG viewBox counts pixels.
import { memo, type ReactNode } from "react";
import { cellKind, placeAreas, type Area } from "../../lib/village"; // relative: the sprite test runs without path aliases

export const TILE = 16;
export const INK = "#2a2340"; // the outline of everything

type Palette = Record<string, string>;

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

// Scenery stands on grass cells off the main routes; a cell that is not grass is skipped.
const TREES: [number, number][] = [[0, 0], [9, 0], [19, 0], [18, 2], [0, 5], [1, 7], [19, 6], [19, 9], [5, 13], [8, 14], [1, 14], [16, 3]];
const LAMPS: [number, number][] = [[5, 5], [10, 8], [12, 11]];

function hash(x: number, y: number): number {
  return (x * 7 + y * 13 + x * y) % 3;
}

function Defs() {
  // A tile's ground overlaps the next tile by half a pixel, so no seams show when the map is scaled.
  const tile = (id: string, fill: string, overlay?: ReactNode) => (
    <g key={id} id={id}>
      <rect width={TILE + 0.5} height={TILE + 0.5} fill={fill} />
      {overlay}
    </g>
  );
  return (
    <defs>
      {GRASS_TILES.map((rows, i) => tile(`vt-grass${i}`, C.grass, <Pixels rows={rows} palette={GRASS_PALETTE} />))}
      {tile("vt-path", C.path, <Pixels rows={PATH_TILE} palette={{ p: C.pebble, q: "#f6e6bd" }} />)}
      {tile("vt-water", C.water)}
      <g id="vt-waves-a">
        <Pixels rows={WAVES_A} palette={{ w: C.wave }} />
      </g>
      <g id="vt-waves-b">
        <Pixels rows={WAVES_B} palette={{ w: C.wave }} />
      </g>
      {tile("vt-stone", C.stone, <Pixels rows={STONE_TILE} palette={{ j: C.joint }} />)}
      {tile("vt-greens", C.soil, <Pixels rows={CROPS.greens} palette={CROP_PALETTE} />)}
      {tile("vt-wheat", C.soil, <Pixels rows={CROPS.wheat} palette={CROP_PALETTE} />)}
      {tile("vt-flowers", C.grass, <Pixels rows={FLOWER_BED} palette={FLOWER_PALETTE} />)}
      <g id="vt-planks">
        <rect width={TILE + 0.5} height={TILE + 0.5} fill={C.wood} />
        {[0, 4, 8, 12].map((y) => (
          <g key={y}>
            <rect y={y} width={TILE} height={1} fill="#d39257" />
            <rect y={y + 3} width={TILE} height={1} fill={C.plankGap} />
          </g>
        ))}
      </g>
      <g id="vt-tree">
        <Pixels rows={TREE} palette={TREE_PALETTE} />
      </g>
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

function TownHall({ area }: { area: Area }) {
  // stands on the row above the town hall's cells; villagers wait on its forecourt
  const x = area.x0 * TILE;
  const y = (area.y0 - 1) * TILE;
  const w = (area.x1 - area.x0 + 1) * TILE;
  const bands = [8, 6, 4, 2, 0];
  return (
    <g>
      <rect x={x + w / 2} y={y} width={1} height={8} fill={INK} />
      <rect x={x + w / 2 + 1} y={y} width={7} height={4} fill="#4f7fd0" />
      {bands.map((inset, i) => (
        <g key={inset}>
          <rect x={x + inset} y={y + 5 + i * 2} width={w - inset * 2} height={2} fill={i === bands.length - 1 ? C.roofDark : C.roof} />
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
      {townHallWindows(area).map(([wx, wy]) => (
        <g key={wx}>
          <rect x={wx - 1} y={wy - 1} width={10} height={8} fill={INK} />
          <rect x={wx} y={wy} width={8} height={6} fill={C.glass} />
          <rect x={wx + 4} y={wy} width={1} height={6} fill={INK} />
        </g>
      ))}
    </g>
  );
}

function townHallWindows(area: Area): [number, number][] {
  const x = area.x0 * TILE;
  const y = (area.y0 - 1) * TILE + 22; // below the name plate on the wall
  const w = (area.x1 - area.x0 + 1) * TILE;
  return [
    [x + 6, y],
    [x + w - 14, y],
  ];
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

/** Everything that does not change between ticks: ground, places and scenery. */
export const Ground = memo(function Ground({ map }: { map: string }) {
  const rows = map.split("\n");
  const areas = placeAreas(rows);
  const cells = rows.flatMap((row, y) => [...row].map((char, x) => ({ char, x, y })));
  const water = cells.filter((c) => c.char === "~" || c.char === "P");
  const free = ([x, y]: [number, number]) => rows[y]?.[x] === ".";
  return (
    <g>
      <Defs />
      {cells.map(({ char, x, y }) => {
        const kind = cellKind(char);
        const id =
          kind === "grass" ? `vt-grass${hash(x, y)}` : kind === "path" ? "vt-path" : kind === "water" ? "vt-water" : char === "F" ? (x % 2 ? "vt-wheat" : "vt-greens") : (PLACE_TILE[char] ?? "vt-grass0");
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
      {areas.T && <TownHall area={areas.T} />}
      {TREES.filter(free).map(([x, y]) => (
        <use key={`tree-${x},${y}`} href="#vt-tree" x={x * TILE} y={y * TILE} />
      ))}
      {LAMPS.filter(free).map(([x, y]) => (
        <use key={`lamp-${x},${y}`} href="#vt-lamp" x={x * TILE} y={y * TILE} />
      ))}
    </g>
  );
});

/** Lit windows and lamps, drawn above the night tint; shown from the evening on. */
export function Lights({ map, on }: { map: string; on: boolean }) {
  const rows = map.split("\n");
  const hall = placeAreas(rows).T;
  return (
    <g className="transition-opacity duration-1000" opacity={on ? 1 : 0} aria-hidden>
      {hall &&
        townHallWindows(hall).map(([x, y]) => (
          <g key={x}>
            <rect x={x - 3} y={y - 3} width={14} height={12} fill={C.lit} opacity={0.25} />
            <rect x={x} y={y} width={8} height={6} fill={C.lit} />
            <rect x={x + 4} y={y} width={1} height={6} fill={INK} />
          </g>
        ))}
      {LAMPS.filter(([x, y]) => rows[y]?.[x] === ".").map(([x, y]) => (
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
