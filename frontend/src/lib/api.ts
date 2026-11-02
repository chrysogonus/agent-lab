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

// The village (M6, M7). See specs/007-village-life/contracts/http-api.md.
export type VillageAction =
  | { action: "move"; place: string; reason?: string }
  | { action: "find"; villager: string; reason?: string }
  | { action: "say"; text: string; to: string | null; reason?: string }
  | { action: "goodbye"; text: string | null; place?: string; villager?: string; ignored?: string; reason?: string }
  | { action: "wait"; reason?: string }
  | { action: "reflect"; learnings?: string[]; views?: Record<string, string>; reason?: string }
  | { action: "chronicle"; day: number; title?: string; text?: string; reason?: string }
  | { action: "plan"; revision: number; entries?: string[]; reason?: string } // M11
  | { action: "work"; place: string; reason?: string }
  | { action: "give"; to: string | null; goods: Goods; reason?: string }
  | { action: "buy"; goods: BuildingGoods; paid: BasketGoods; reason?: string } // M12
  | { action: "propose"; proposals?: string[]; reason?: string }
  | { action: "vote"; project?: string; reason?: string }
  | { action: "decide"; project?: string; reason?: string; against?: boolean; by?: "hilde" | "vote" };

export type VillageEvent = {
  tick: number;
  kind:
    | "woke" | "bedtime" | "slept" | "set_off" | "arrived" | "met" | "found" | "missed" | "heard" | "said" | "ended" | "waited" | "reflected" | "festival"
    | "planned" | "worked" | "basket" | "gave" | "received" // M11
    | "traded" | "proposed" | "meeting"; // M12
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
  work: string; // its work place key (M9)
  last_action: VillageAction | null;
  speech: { text: string; to: string | null; tick: number } | null;
  events: VillageEvent[];
  asleep: boolean;
  state: "asleep" | "bedtime" | "deciding" | "talking" | "working" | "walking" | "idle";
  wake: string; // "05:00"
  bed: string;
  goal: string | null; // "walking to the market", "going home", "looking for Lina"
  talking_with: string[];
  beliefs: { villager: string; text: string; view: string | null }[];
  learnings: { day: number; text: string }[]; // oldest first (M8)
  views: { villager: string; text: string; day: number }[];
  memories: { day: number; time: string; kind: "conversation" | "found" | "missed" | "met" | "reflection" | "festival" | "meeting" | "built"; text: string }[]; // newest first
  plan: Plan | null; // today's plan (M11)
  basket: Goods | null; // one thing at a time, kept overnight: a basket (M11) or a load (M12)
  working: "fields" | "flower_garden" | "pier" | null; // where it works until it walks off
};

// M11: plans and purpose. See specs/011-plans-and-purpose/contracts/http-api.md.
export type PlanEntry = { time: string; place: string | null; villager: string | null; purpose: string }; // place: its label or "home"
export type BasketGoods = "fish" | "vegetables" | "flowers";
export type Stalls = Record<BasketGoods, number>; // goods set out on the square for the festival
export type Plan = { entries: PlanEntry[]; current: number | null; next: number | null; revisions: number };

// M12: building together. See specs/012-building-together/contracts/http-api.md.
export type BuildingGoods = "wood" | "paint" | "saplings";
export type Goods = BasketGoods | BuildingGoods;
export type Trader = { stock: Record<BuildingGoods, number>; leaves: string };
export type MeetingProposal = { key: string; name: string; reason: string; run_id: string | null };
export type MeetingVote = { villager: string; key: string | null; name: string | null; reason: string; run_id: string | null }; // key null: not counted
export type MeetingDecision = { key: string; name: string; reason: string; against: boolean; by: "hilde" | "vote"; run_id: string | null };
export type Meeting = {
  day: number;
  kind: "vote" | "review";
  proposals: MeetingProposal[];
  votes: MeetingVote[];
  present: string[];
  decision: MeetingDecision | null;
  outcome: string | null; // "decided", "called off: …", "reviewed", "nothing left to build", "no decision"
};

// M10: seasons, weather, growth and the chronicle. See specs/010-village-seasons/contracts/http-api.md.
export type Season = "spring" | "summer" | "autumn" | "winter";
export type Weather = "sun" | "clouds" | "rain" | "storm" | "fog" | "snow";
export type FieldStage = "resting" | "tilled" | "sown" | "sprouting" | "growing" | "ripe" | "harvested";
export type GardenStage = "resting" | "budding" | "blooming" | "wilting";
export type ChronicleEntry = {
  day: number;
  year: number;
  season: Season;
  day_of_season: number;
  weather: Weather;
  title: string;
  text: string;
  run_id: string;
};

export type VillageLine = { tick: number; time: string; from: string; to: string | null; text: string };

export type VillageState = {
  tick: number;
  day: number;
  time: string;
  period: "morning" | "midday" | "afternoon" | "evening" | "night";
  calendar: { year: number; season: Season; day_of_season: number; festival_in: number | null };
  weather: Weather;
  snow_cover: boolean;
  sky: "morning" | "midday" | "afternoon" | "evening" | "night"; // the light, shifted by the season
  dark: boolean; // lamps and windows lit
  growth: { fields: { stage: FieldStage; neglected: boolean }; flower_garden: { stage: GardenStage } };
  chronicle: ChronicleEntry[]; // newest first, at most 28
  stalls: Stalls; // M11
  trader: Trader | null; // M12: at the market from 09:00 to 14:00
  meeting: Meeting | null; // the latest town hall meeting
  next_meeting: number; // the day of the next one
  running: boolean;
  ticking: boolean;
  interval: number;
  paused_reason: string | null;
  log: VillageLine[]; // newest last
  map: {
    width: number;
    height: number;
    rows: string[];
    places: { key: string; label: string; x: number; y: number }[];
    homes: { villager: string; letter: string; door: [number, number] }[];
  };
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

export const getRun = (runId: string): Promise<Run> =>
  send<{ run: Run }>("GET", `/runs/${runId}`).then((detail) => detail.run);

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
