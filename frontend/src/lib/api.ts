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
};

export type AgentInfo = {
  id: string;
  name: string;
  description: string;
  sample_prompt: string;
  graph: Graph;
};

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
