// Types mirror backend/src/agent_lab (Span, Run, Graph). See specs/00*/contracts.

export type SpanKind = "llm" | "tool" | "route" | "retrieve" | "rerank" | "memory" | "step";

export type Span = {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  run_id: string;
  agent_id: string;
  node_id: string;
  config_version: string;
  kind: SpanKind;
  name: string;
  input: unknown;
  output: unknown;
  error: string | null;
  started_at: number; // epoch seconds
  ended_at: number | null; // null while running
  tokens_in: number | null;
  tokens_out: number | null;
  model: string | null;
  attributes: Record<string, unknown>;
};

export type GraphNode = {
  id: string;
  label: string;
  kind: "start" | "llm" | "tool" | "code" | "end";
  x: number;
  y: number;
};

export type Graph = { nodes: GraphNode[]; edges: { source: string; target: string }[] };

export type RunStatus = "running" | "completed" | "max_iterations" | "error";

export type RunTotals = {
  llm_calls: number;
  tool_calls: number;
  tokens_in: number;
  tokens_out: number;
  wall_ms: number | null; // null while running
};

export type Run = {
  run_id: string;
  agent_id: string;
  config_version: string;
  prompt: string;
  status: RunStatus;
  answer: string | null;
  graph: Graph;
  config: Record<string, unknown>;
  started_at: number;
  ended_at: number | null;
  totals: RunTotals | null; // null on the run returned by POST /runs
  agent_name: string | null; // the agent's name when the run started; null before M3
  template_id: string | null; // null before M3
  village_tick: number | null; // set on a villager's turn (M6)
  villager: string | null;
  village_action: VillageAction | null;
};

// The village (M6). See specs/006-village/contracts/http-api.md.
export type VillageAction =
  | { action: "move"; place: string; reason?: string }
  | { action: "say"; text: string; to: string | null; reason?: string }
  | { action: "wait"; reason?: string };

export type VillageEvent = {
  tick: number;
  kind: "set_off" | "arrived" | "heard" | "said" | "waited";
  text: string;
  from?: string;
  to?: string | null;
};

export type Villager = {
  name: string;
  title: string;
  color: string;
  initial: string;
  persona: string;
  agent_id: string | null;
  x: number;
  y: number;
  place: string | null;
  destination: string | null;
  last_action: VillageAction | null;
  speech: { text: string; to: string | null } | null;
  events: VillageEvent[];
};

export type VillageState = {
  tick: number;
  day: number;
  time: string;
  period: "morning" | "midday" | "afternoon" | "evening" | "night";
  running: boolean;
  ticking: boolean;
  interval: number;
  paused_reason: string | null;
  map: { width: number; height: number; rows: string[]; places: { key: string; label: string; x: number; y: number }[] };
  villagers: Villager[];
};

export type AgentConfig = Record<string, unknown>; // a template's editable fields

/** A model is its provider and id together: the same id may exist on both providers. */
export type ModelRef = { provider: "local" | "openai"; model: string };

export type ModelInfo = ModelRef & {
  provider_label: string;
  external: boolean; // prompts and tool results leave this machine
  available: boolean;
  unavailable_reason: string | null;
  default: boolean;
};

export type AgentInfo = {
  id: string;
  kind: "template" | "custom";
  template_id: string;
  name: string;
  description: string;
  sample_prompt: string;
  config: AgentConfig;
  model: ModelRef | null; // null: follows the default model (templates always)
  graph: Graph;
};

export type ToolInfo = {
  name: string;
  description: string;
  // JSON Schema of the arguments: a tool block shows one field per property.
  parameters: { properties?: Record<string, { description?: string }> };
};

// Block agents (M5): custom agents with template_id "blocks". See specs/005-block-builder.
export type BlockKind = "model" | "tool" | "check" | "router" | "parallel" | "loop";
export type CheckRule = {
  rule: "min_bullets" | "max_words" | "contains" | "valid_json";
  value: number | string | null;
};
export type ModelBlock = {
  kind: "model";
  name: string;
  system: string;
  message: string;
  tools: string[];
  max_iterations: number;
  answer_on_last_call: boolean;
};
export type ToolBlock = { kind: "tool"; name: string; tool: string; arguments: Record<string, string> };
export type CheckBlock = CheckRule & { kind: "check"; name: string };
export type Route = { name: string; description: string; blocks: Block[] };
export type RouterBlock = { kind: "router"; name: string; prompt: string; routes: Route[]; fallback: string };
export type Branch = { name: string; blocks: Block[] };
export type ParallelBlock = {
  kind: "parallel";
  name: string;
  mode: "branches" | "per_item";
  branches: Branch[] | null;
  planner: string | null;
  max_items: number | null;
  body: Block[] | null;
};
export type LoopBlock = {
  kind: "loop";
  name: string;
  body: Block[];
  exit: "judge" | "check";
  judge: string | null;
  check: CheckRule | null;
  max_rounds: number;
};
export type Block = ModelBlock | ToolBlock | CheckBlock | RouterBlock | ParallelBlock | LoopBlock;

/** What the builder saves; `template_id` only when creating. */
export type AgentFields = {
  name: string;
  description: string;
  sample_prompt: string;
  config: AgentConfig;
  model: ModelRef | null;
};

export type FieldErrorDetail = { loc: (string | number)[]; msg: string };

/** A 422 from the backend: every entry names the field it belongs to. */
export class ValidationError extends Error {
  constructor(readonly detail: FieldErrorDetail[]) {
    super(detail.map((d) => d.msg).join("; "));
  }
}

export type StreamEvent =
  | { type: "span_started" | "span_ended"; span: Span }
  | { type: "run_ended"; run: Run }
  | { type: "error"; message: string };

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export function villageStreamUrl(): string {
  return `${API_URL.replace(/^http/, "ws")}/village/stream`;
}

export const getVillage = (): Promise<VillageState> => send("GET", "/village");
export const startVillage = (): Promise<VillageState> => send("POST", "/village/start");
export const pauseVillage = (): Promise<VillageState> => send("POST", "/village/pause");
export const stepVillage = (): Promise<VillageState> => send("POST", "/village/step");
export const resetVillage = (): Promise<VillageState> => send("POST", "/village/reset");
export const setVillageInterval = (seconds: number): Promise<VillageState> =>
  send("PUT", "/village/interval", { seconds });
export const villagerTurns = (name: string): Promise<Run[]> =>
  send("GET", `/village/villagers/${encodeURIComponent(name)}/turns`);

export function streamUrl(runId: string): string {
  return `${API_URL.replace(/^http/, "ws")}/runs/${runId}/stream`;
}

/** A 422 (e.g. the agent's model is no longer available) throws a `ValidationError`. */
export function startRun(prompt: string, agentId: string): Promise<Run> {
  return send("POST", "/runs", { prompt, agent_id: agentId });
}

export async function listRuns(): Promise<Run[]> {
  const response = await fetch(`${API_URL}/runs`);
  if (!response.ok) throw new Error(`Loading past runs failed (HTTP ${response.status}).`);
  return response.json();
}

export async function listAgents(): Promise<AgentInfo[]> {
  const response = await fetch(`${API_URL}/agents`);
  if (!response.ok) throw new Error(`Loading agents failed (HTTP ${response.status}).`);
  return response.json();
}

export async function listTools(): Promise<ToolInfo[]> {
  const response = await fetch(`${API_URL}/tools`);
  if (!response.ok) throw new Error(`Loading tools failed (HTTP ${response.status}).`);
  return response.json();
}

export async function listModels(): Promise<ModelInfo[]> {
  const response = await fetch(`${API_URL}/models`);
  if (!response.ok) throw new Error(`Loading models failed (HTTP ${response.status}).`);
  return response.json();
}

/** An unsaved block agent with one model block. */
export function newBlockAgent(): Promise<AgentInfo> {
  return send("GET", "/blocks/new");
}

/** An unsaved block copy of a template or template-based agent. */
export function blocksFrom(agentId: string): Promise<AgentInfo> {
  return send("GET", `/agents/${encodeURIComponent(agentId)}/blocks`);
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 422) throw new ValidationError((await response.json()).detail);
  if (!response.ok) throw new Error(`${method} ${path} failed (HTTP ${response.status}).`);
  return response.status === 204 ? (undefined as T) : response.json();
}

export function createAgent(templateId: string, fields: AgentFields): Promise<AgentInfo> {
  return send("POST", "/agents", { template_id: templateId, ...fields });
}

export function updateAgent(agentId: string, fields: AgentFields): Promise<AgentInfo> {
  return send("PUT", `/agents/${encodeURIComponent(agentId)}`, fields);
}

export function deleteAgent(agentId: string): Promise<void> {
  return send("DELETE", `/agents/${encodeURIComponent(agentId)}`);
}

export function previewGraph(templateId: string, config: AgentConfig): Promise<Graph> {
  return send("POST", "/graph", { template_id: templateId, config });
}
