// Builder state: a draft custom agent and the edits on it. Pure; components stay thin.
// Field names match the API's, so a 422 `loc` is a path into the draft.
import type { AgentConfig, AgentFields, AgentInfo, FieldErrorDetail } from "./api";

export type Draft = {
  agentId: string | null; // null until the first save
  templateId: string;
  name: string;
  description: string;
  sample_prompt: string;
  config: AgentConfig;
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
  | { kind: "aspect"; name: string }
  | { kind: "gate" }
  | { kind: "tool"; name: string };

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
    agentId: null,
    templateId: source.template_id,
    name: copyName(source.name, agents.map((a) => a.name)),
    description: source.description,
    sample_prompt: source.sample_prompt,
    config: structuredClone(source.config),
    dirty: true,
  };
}

export function draftFromAgent(agent: AgentInfo): Draft {
  return {
    agentId: agent.id,
    templateId: agent.template_id,
    name: agent.name,
    description: agent.description,
    sample_prompt: agent.sample_prompt,
    config: structuredClone(agent.config),
    dirty: false,
  };
}

export function draftFields({ name, description, sample_prompt, config }: Draft): AgentFields {
  return { name, description, sample_prompt, config };
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
  if (templateId === "parallel" && nodeId in (config.aspects as Record<string, string>)) {
    return { kind: "aspect", name: nodeId };
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
      return section.name;
    case "gate":
      return "gate";
    case "tool":
      return `tool:${section.name}`;
  }
}
