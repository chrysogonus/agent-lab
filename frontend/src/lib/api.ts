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
};

export type AgentConfig = Record<string, unknown>; // a template's editable fields

export type AgentInfo = {
  id: string;
  kind: "template" | "custom";
  template_id: string;
  name: string;
  description: string;
  sample_prompt: string;
  config: AgentConfig;
  graph: Graph;
};

export type ToolInfo = { name: string; description: string };

/** What the builder saves; `template_id` only when creating. */
export type AgentFields = {
  name: string;
  description: string;
  sample_prompt: string;
  config: AgentConfig;
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

export function streamUrl(runId: string): string {
  return `${API_URL.replace(/^http/, "ws")}/runs/${runId}/stream`;
}

export async function startRun(prompt: string, agentId: string): Promise<Run> {
  const response = await fetch(`${API_URL}/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ prompt, agent_id: agentId }),
  });
  if (!response.ok) throw new Error(`Starting the run failed (HTTP ${response.status}).`);
  return response.json();
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
