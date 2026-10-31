// Block agent edits: a tree of blocks under draft.config.blocks. Pure; components stay thin.
// Paths are full draft paths (["config", "blocks", 0, "routes", 1, "blocks", 0]), so a 422
// `loc` and a block's path share one key space.
import type { AgentConfig, Block, BlockKind, ToolInfo } from "./api";
import { getField, setField, type Draft, type Path } from "./builder";

export const KIND_LABELS: Record<BlockKind, string> = {
  model: "Model call",
  tool: "Tool call",
  check: "Check",
  router: "Router",
  parallel: "Parallel group",
  loop: "Loop",
};

const RESERVED = new Set(["start", "end", "input", "previous", "feedback", "item"]);
const TEXT_FIELDS = ["system", "message", "prompt", "planner", "judge"] as const;

/** A container's block lists: their path relative to the block and a reader-facing label. */
export function childLists(block: Block): { path: Path; label: string; blocks: Block[] }[] {
  switch (block.kind) {
    case "router":
      return block.routes.map((r, i) => ({ path: ["routes", i, "blocks"], label: `Route ${r.name}`, blocks: r.blocks }));
    case "parallel":
      if (block.mode === "branches") {
        return (block.branches ?? []).map((b, i) => ({ path: ["branches", i, "blocks"], label: `Branch ${b.name}`, blocks: b.blocks }));
      }
      return [{ path: ["body"], label: "Each item", blocks: block.body ?? [] }];
    case "loop":
      return [{ path: ["body"], label: "Repeat", blocks: block.body }];
    default:
      return [];
  }
}

/** Every block with its full path, in run order (containers before their contents). */
export function allBlocks(config: AgentConfig): { path: Path; block: Block }[] {
  const found: { path: Path; block: Block }[] = [];
  const walk = (blocks: Block[], listPath: Path) =>
    blocks.forEach((block, i) => {
      const path = [...listPath, i];
      found.push({ path, block });
      for (const list of childLists(block)) walk(list.blocks, [...path, ...list.path]);
    });
  walk((config.blocks as Block[] | undefined) ?? [], ["config", "blocks"]);
  return found;
}

export function blockAt(config: AgentConfig, path: Path): Block | undefined {
  return getField({ config } as unknown as Draft, path) as Block | undefined;
}

export function findBlock(config: AgentConfig, name: string): Path | null {
  return allBlocks(config).find((b) => b.block.name === name)?.path ?? null;
}

/** `base`, or `base-2`, `base-3`, … — the first name no block uses (nor a reserved word). */
export function freeName(taken: Set<string>, base: string): string {
  if (!taken.has(base) && !RESERVED.has(base)) return base;
  let n = 2;
  while (taken.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

/** A valid new block of `kind`; it and any blocks inside it get names not in `taken`. */
export function defaultBlock(kind: BlockKind, taken: Set<string>, tools: ToolInfo[] = []): Block {
  const names = new Set(taken);
  const name = (base: string) => {
    const free = freeName(names, base);
    names.add(free);
    return free;
  };
  const model = (): Block => ({
    kind: "model",
    name: name("step"),
    system: "Answer briefly.",
    message: "{previous}",
    tools: [],
    max_iterations: 4,
  });
  switch (kind) {
    case "model":
      return model();
    case "tool": {
      const tool = tools[0]?.name ?? "calculator";
      return { kind, name: name("tool"), tool, arguments: argumentsFor(tool, tools) };
    }
    case "check":
      return { kind, name: name("check"), rule: "max_words", value: 100 };
    case "router": {
      const own = name("router");
      return {
        kind,
        name: own,
        prompt: "Classify the request.",
        routes: [
          { name: "first", description: "one kind of request", blocks: [model()] },
          { name: "other", description: "anything else", blocks: [model()] },
        ],
        fallback: "other",
      };
    }
    case "parallel": {
      const own = name("group");
      return {
        kind,
        name: own,
        mode: "branches",
        branches: [
          { name: "a", blocks: [model()] },
          { name: "b", blocks: [model()] },
        ],
        planner: null,
        max_items: null,
        body: null,
      };
    }
    case "loop": {
      const own = name("loop");
      return {
        kind,
        name: own,
        body: [model()],
        exit: "judge",
        judge: "Approve the answer if it is good; otherwise say what to improve.",
        check: null,
        max_rounds: 3,
      };
    }
  }
}

/** One `{previous}` argument per parameter of the tool. */
export function argumentsFor(tool: string, tools: ToolInfo[]): Record<string, string> {
  const properties = tools.find((t) => t.name === tool)?.parameters.properties ?? { expression: {} };
  return Object.fromEntries(Object.keys(properties).map((key) => [key, "{previous}"]));
}

function names(config: AgentConfig): Set<string> {
  return new Set(allBlocks(config).map((b) => b.block.name));
}

const listOf = (draft: Draft, listPath: Path) => getField(draft, listPath) as Block[];

/** Inserts a new block of `kind` at `index` of the list at `listPath`. */
export function addBlock(draft: Draft, listPath: Path, index: number, kind: BlockKind, tools: ToolInfo[] = []): Draft {
  const list = [...listOf(draft, listPath)];
  list.splice(index, 0, defaultBlock(kind, names(draft.config), tools));
  return setField(draft, listPath, list);
}

/** Lists never become empty: the server rejects an empty route, branch or body. */
export function canRemoveBlock(draft: Draft, path: Path): boolean {
  return listOf(draft, path.slice(0, -1)).length > 1;
}

export function removeBlock(draft: Draft, path: Path): Draft {
  const listPath = path.slice(0, -1);
  return setField(draft, listPath, listOf(draft, listPath).filter((_, i) => i !== path.at(-1)));
}

/** Moves a block one place up or down within its own list. */
export function moveBlock(draft: Draft, path: Path, delta: -1 | 1): Draft {
  const listPath = path.slice(0, -1);
  const list = [...listOf(draft, listPath)];
  const from = path.at(-1) as number;
  const to = from + delta;
  if (to < 0 || to >= list.length) return draft;
  [list[from], list[to]] = [list[to], list[from]];
  return setField(draft, listPath, list);
}

/** Renames a block and rewrites `{old}` to `{new}` in every prompt and argument template. */
export function renameBlock(draft: Draft, path: Path, name: string): Draft {
  const old = (getField(draft, path) as Block).name;
  const rewrite = (text: string) => (old ? text.split(`{${old}}`).join(`{${name}}`) : text);
  const fix = (block: Block): Block => {
    const copy = { ...block } as Record<string, unknown>;
    for (const field of TEXT_FIELDS) {
      if (typeof copy[field] === "string") copy[field] = rewrite(copy[field] as string);
    }
    if (block.kind === "tool") {
      copy.arguments = Object.fromEntries(Object.entries(block.arguments).map(([k, v]) => [k, rewrite(v)]));
    }
    if (block.kind === "router") copy.routes = block.routes.map((r) => ({ ...r, blocks: r.blocks.map(fix) }));
    if (block.kind === "parallel") {
      copy.branches = block.branches?.map((b) => ({ ...b, blocks: b.blocks.map(fix) })) ?? null;
      copy.body = block.body?.map(fix) ?? null;
    }
    if (block.kind === "loop") copy.body = block.body.map(fix);
    return copy as Block;
  };
  const renamed = setField(draft, [...path, "name"], name);
  return setField(renamed, ["config", "blocks"], (renamed.config.blocks as Block[]).map(fix));
}

/** Errors at a block or anything inside it (key: dotted draft path, as from `fieldErrors`). */
export function blockErrors(errors: Record<string, string>, path: Path): [string, string][] {
  const key = path.join(".");
  return Object.entries(errors).filter(([k]) => k === key || k.startsWith(`${key}.`));
}

// --- Container settings: routes, branches, group mode, loop exit, check rules ---

const MAX_LIST = 6;

export function canAddRoute(block: Block): boolean {
  return block.kind === "router" && block.routes.length < MAX_LIST;
}

export function addRoute(draft: Draft, path: Path, tools: ToolInfo[] = []): Draft {
  const router = getField(draft, path) as Block & { kind: "router" };
  const taken = new Set(router.routes.map((r) => r.name));
  const name = freeName(taken, "route");
  const blocks = [defaultBlock("model", names(draft.config), tools)];
  return setField(draft, [...path, "routes"], [...router.routes, { name, description: `${name} requests`, blocks }]);
}

/** A router keeps two routes and its fallback; pick another fallback first. */
export function canRemoveRoute(block: Block, index: number): boolean {
  return block.kind === "router" && block.routes.length > 2 && block.routes[index]?.name !== block.fallback;
}

export function removeRoute(draft: Draft, path: Path, index: number): Draft {
  const router = getField(draft, path) as Block & { kind: "router" };
  return setField(draft, [...path, "routes"], router.routes.filter((_, i) => i !== index));
}

/** Renaming the fallback route renames the fallback with it. */
export function renameRoute(draft: Draft, path: Path, index: number, name: string): Draft {
  const router = getField(draft, path) as Block & { kind: "router" };
  const renamed = setField(draft, [...path, "routes", index, "name"], name);
  return router.fallback === router.routes[index].name ? setField(renamed, [...path, "fallback"], name) : renamed;
}

export function canAddBranch(block: Block): boolean {
  return block.kind === "parallel" && block.mode === "branches" && (block.branches?.length ?? 0) < MAX_LIST;
}

export function addBranch(draft: Draft, path: Path, tools: ToolInfo[] = []): Draft {
  const group = getField(draft, path) as Block & { kind: "parallel" };
  const branches = group.branches ?? [];
  const name = freeName(new Set(branches.map((b) => b.name)), "branch");
  const blocks = [defaultBlock("model", names(draft.config), tools)];
  return setField(draft, [...path, "branches"], [...branches, { name, blocks }]);
}

export function canRemoveBranch(block: Block): boolean {
  return block.kind === "parallel" && (block.branches?.length ?? 0) > 1;
}

export function removeBranch(draft: Draft, path: Path, index: number): Draft {
  const group = getField(draft, path) as Block & { kind: "parallel" };
  return setField(draft, [...path, "branches"], (group.branches ?? []).filter((_, i) => i !== index));
}

/** Switches a parallel group's mode; the blocks of the first list move to the new one. */
export function setMode(draft: Draft, path: Path, mode: "branches" | "per_item"): Draft {
  const group = getField(draft, path) as Block & { kind: "parallel" };
  if (group.mode === mode) return draft;
  const blocks = (group.mode === "branches" ? group.branches?.[0]?.blocks : group.body) ?? [];
  const switched =
    mode === "branches"
      ? { ...group, mode, branches: [{ name: "a", blocks }], planner: null, max_items: null, body: null }
      : { ...group, mode, branches: null, planner: "Split the request into independent parts.", max_items: 3, body: blocks };
  return setField(draft, path, switched);
}

/** Switches a loop's exit between a judge prompt and a check. */
export function setExit(draft: Draft, path: Path, exit: "judge" | "check"): Draft {
  const loop = getField(draft, path) as Block & { kind: "loop" };
  if (loop.exit === exit) return draft;
  const fields =
    exit === "judge"
      ? { judge: "Approve the answer if it is good; otherwise say what to improve.", check: null }
      : { judge: null, check: { rule: "max_words" as const, value: 100 } };
  return setField(draft, path, { ...loop, exit, ...fields });
}

const RULE_DEFAULTS = { min_bullets: 3, max_words: 100, contains: "", valid_json: null } as const;

/** Sets a check rule (at a check block or a loop's `check`) with a fitting default value. */
export function setRule(draft: Draft, rulePath: Path, rule: keyof typeof RULE_DEFAULTS): Draft {
  const current = getField(draft, rulePath) as Record<string, unknown>;
  return setField(draft, rulePath, { ...current, rule, value: RULE_DEFAULTS[rule] });
}
