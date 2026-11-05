// Builder state: a draft custom agent and the edits on it. Pure; components stay thin.
// Field names match the API's, so a 422 `loc` is a path into the draft.
import type { AgentConfig, AgentFields, AgentInfo, Budget, FieldErrorDetail, ModelRef } from "./api";
import { blockAt, findBlock } from "./blocks";

export type Draft = {
  casesFrom: string | null; // a new agent copies this agent's or template's test cases
  budget?: Budget | null; // unset: a new agent gets the default; null: no budget
  agentId: string | null; // null until the first save
  templateId: string;
  name: string;
  description: string;
  sample_prompt: string;
  config: AgentConfig;
  model: ModelRef | null; // null: follows the default model
  dirty: boolean;
};

/** A path into the draft, e.g. ["name"] or ["config", "routes", 1, "prompt"]. */
export type Path = (string | number)[];

/** What the settings panel shows for a clicked node. */
export type Section =
  | { kind: "agent" }
  | { kind: "prompt"; path: Path; title: string }
  | { kind: "step"; index: number }
  | { kind: "route"; index: number }
  | { kind: "aspect"; index: number }
  | { kind: "gate" }
  | { kind: "tool"; name: string }
  | { kind: "block"; path: Path }; // block agents: the block at that draft path

const sameName = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

/** "<name> (copy)", then "(copy 2)", … — the first one no listed agent uses. */
export function copyName(name: string, names: string[]): string {
  const taken = (candidate: string) => names.some((n) => sameName(n, candidate));
  if (!taken(`${name} (copy)`)) return `${name} (copy)`;
  let n = 2;
  while (taken(`${name} (copy ${n})`)) n += 1;
  return `${name} (copy ${n})`;
}

/** A new, unsaved custom agent starting from an agent's settings (a template or a duplicate). */
export function draftFrom(source: AgentInfo, agents: AgentInfo[]): Draft {
  return {
    casesFrom: source.id,
    // A template's null means it has none to give; a saved agent's is a choice a copy keeps.
    budget: source.kind === "template" ? undefined : source.budget,
    agentId: null,
    templateId: source.template_id,
    name: copyName(source.name, agents.map((a) => a.name)),
    description: source.description,
    sample_prompt: source.sample_prompt,
    config: structuredClone(source.config),
    model: source.model,
    dirty: true,
  };
}

export function draftFromAgent(agent: AgentInfo): Draft {
  return {
    casesFrom: null,
    budget: agent.budget,
    agentId: agent.id,
    templateId: agent.template_id,
    name: agent.name,
    description: agent.description,
    sample_prompt: agent.sample_prompt,
    config: structuredClone(agent.config),
    model: agent.model,
    dirty: false,
  };
}

export function draftFields({ name, description, sample_prompt, config, model, budget }: Draft): AgentFields {
  const fields = { name, description, sample_prompt, config, model };
  return budget === undefined ? fields : { ...fields, budget };
}

export function getField(draft: Draft, path: Path): unknown {
  let value: unknown = draft;
  for (const key of path) value = (value as Record<string | number, unknown> | undefined)?.[key];
  return value;
}

function setIn(target: unknown, path: Path, value: unknown): unknown {
  if (path.length === 0) return value;
  const [key, ...rest] = path;
  if (Array.isArray(target)) {
    const copy = [...(target as unknown[])];
    copy[key as number] = setIn(copy[key as number], rest, value);
    return copy;
  }
  const copy = { ...(target as Record<string, unknown>) };
  copy[key] = setIn(copy[key], rest, value);
  return copy;
}

/** Returns a new draft with the value at `path` replaced, marked as changed. */
export function setField(draft: Draft, path: Path, value: unknown): Draft {
  return { ...(setIn(draft, path, value) as Draft), dirty: true };
}

type Named = { name: string };

/** The panel section a node click opens; start, end and empty space show the agent settings. */
export function nodeSettings(templateId: string, config: AgentConfig, nodeId: string | null): Section {
  if (nodeId == null || nodeId === "start" || nodeId === "end") return { kind: "agent" };
  if (nodeId.startsWith("tool:")) return { kind: "tool", name: nodeId.slice("tool:".length) };
  if (templateId === "blocks") {
    const path = findBlock(config, nodeId);
    return path ? { kind: "block", path } : { kind: "agent" };
  }
  if (templateId === "react" && nodeId === "llm") {
    return { kind: "prompt", path: ["config", "system_prompt"], title: "System prompt" };
  }
  if (templateId === "chain") {
    if (nodeId === "gate") return { kind: "gate" };
    const index = (config.steps as Named[]).findIndex((s) => s.name === nodeId);
    if (index >= 0) return { kind: "step", index };
  }
  if (templateId === "routing") {
    const index = (config.routes as Named[]).findIndex((r) => r.name === nodeId);
    if (index >= 0) return { kind: "route", index };
  }
  if (templateId === "parallel") {
    const index = Object.keys(config.aspects as Record<string, string>).indexOf(nodeId);
    if (index >= 0) return { kind: "aspect", index };
  }
  // router, merge, orchestrator, worker, synthesizer, generator, evaluator: "<node>_prompt".
  const field = `${nodeId}_prompt`;
  if (typeof config[field] === "string") {
    return { kind: "prompt", path: ["config", field], title: `${nodeId} prompt` };
  }
  return { kind: "agent" };
}

/** Field path ("config.routes.1.name", "name") → message, from a 422 detail list. */
export function fieldErrors(detail: FieldErrorDetail[]): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const { loc, msg } of detail) {
    const key = (loc[0] === "body" ? loc.slice(1) : loc).join(".");
    errors[key] ??= msg.replace(/^Value error, /, "");
  }
  return errors;
}

export function pathKey(path: Path): string {
  return path.join(".");
}

/** The graph node a section belongs to (null: agent settings); follows renames of list items. */
export function sectionNode(section: Section, config: AgentConfig): string | null {
  switch (section.kind) {
    case "agent":
      return null;
    case "prompt": {
      const field = String(section.path[section.path.length - 1]);
      return field === "system_prompt" ? "llm" : field.replace(/_prompt$/, "");
    }
    case "step":
      return (config.steps as Named[])[section.index]?.name ?? null;
    case "route":
      return (config.routes as Named[])[section.index]?.name ?? null;
    case "aspect":
      return Object.keys(config.aspects as Record<string, string>)[section.index] ?? null;
    case "gate":
      return "gate";
    case "tool":
      return `tool:${section.name}`;
    case "block":
      return blockAt(config, section.path)?.name ?? null;
  }
}

/** The lists a template lets the owner change. */
export type ListKind = "steps" | "routes" | "aspects";

type Item = Record<string, unknown> & Named;

function items(draft: Draft, kind: ListKind): Item[] {
  const value = draft.config[kind];
  if (kind !== "aspects") return value as Item[];
  return Object.entries(value as Record<string, string>).map(([name, focus]) => ({ name, focus }));
}

function withItems(draft: Draft, kind: ListKind, list: Item[]): Draft {
  const value =
    kind === "aspects" ? Object.fromEntries(list.map((i) => [i.name, i.focus as string])) : list;
  return setField(draft, ["config", kind], value);
}

const NEW_ITEM: Record<ListKind, (name: string) => Item> = {
  steps: (name) => ({ name, prompt: "Describe what this step does.", include_input: false }),
  routes: (name) => ({
    name,
    description: "Describe when the router should pick this route.",
    prompt: "Answer the question briefly.",
    tool: null,
  }),
  aspects: (name) => ({ name, focus: "Describe what this reviewer looks for." }),
};

const PREFIX: Record<ListKind, string> = { steps: "step", routes: "route", aspects: "aspect" };

/** Appends an item named "<kind>-N" with the first free N, and placeholder text to replace. */
export function addItem(draft: Draft, kind: ListKind): Draft {
  const list = items(draft, kind);
  let n = 1;
  while (list.some((i) => i.name === `${PREFIX[kind]}-${n}`)) n += 1;
  return withItems(draft, kind, [...list, NEW_ITEM[kind](`${PREFIX[kind]}-${n}`)]);
}

/** Whether removing keeps the agent valid: one step or aspect, two routes, and the fallback. */
export function canRemove(draft: Draft, kind: ListKind, index: number): boolean {
  const list = items(draft, kind);
  if (kind === "routes") return list.length > 2 && list[index]?.name !== draft.config.fallback;
  return list.length > 1;
}

export function removeItem(draft: Draft, kind: ListKind, index: number): Draft {
  return withItems(
    draft,
    kind,
    items(draft, kind).filter((_, i) => i !== index),
  );
}

/** Moves a chain step up (-1) or down (+1); order is the chain's order. */
export function moveItem(draft: Draft, index: number, delta: -1 | 1): Draft {
  const list = [...items(draft, "steps")];
  const to = index + delta;
  if (to < 0 || to >= list.length) return draft;
  [list[index], list[to]] = [list[to], list[index]];
  return withItems(draft, "steps", list);
}

/** Renames an item; the fallback follows its route. */
export function renameItem(draft: Draft, kind: ListKind, index: number, name: string): Draft {
  const list = items(draft, kind);
  const old = list[index].name;
  // shortcut: aspects are keyed by name, so a name another aspect has is not applied yet.
  if (kind === "aspects" && list.some((i, j) => j !== index && i.name === name)) return draft;
  const next = withItems(
    draft,
    kind,
    list.map((item, i) => (i === index ? { ...item, name } : item)),
  );
  return kind === "routes" && draft.config.fallback === old
    ? setField(next, ["config", "fallback"], name)
    : next;
}

/** Gives the ReAct agent a tool, or takes it away. */
export function toggleTool(draft: Draft, name: string): Draft {
  const tools = draft.config.tools as string[];
  return setField(
    draft,
    ["config", "tools"],
    tools.includes(name) ? tools.filter((t) => t !== name) : [...tools, name],
  );
}
