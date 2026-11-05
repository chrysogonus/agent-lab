// Pure view logic shared by live runs and replays: both are built from the same stream events.
import type { AgentInfo, Graph, Run, RunStatus, RunTotals, Span, StreamEvent } from "./api";

export type RunView = {
  run: Run | null; // set when the run has ended
  status: RunStatus | null; // the latest status while it is live
  spans: Record<string, Span>;
  error: string | null;
};

export const emptyView: RunView = { run: null, status: null, spans: {}, error: null };

export function isLive(status: RunStatus): boolean {
  return status === "running" || status === "waiting_approval";
}

export function applyEvent(view: RunView, event: StreamEvent): RunView {
  switch (event.type) {
    case "span_started":
    case "span_ended": {
      const previous = view.spans[event.span.span_id];
      // Snapshot and live events can overlap; never let a "started" undo an "ended".
      if (previous?.ended_at != null && event.span.ended_at == null) return view;
      return { ...view, spans: { ...view.spans, [event.span.span_id]: event.span } };
    }
    case "run_ended":
      return { ...view, run: event.run };
    case "run_status":
      return { ...view, status: event.status };
    case "error":
      return { ...view, error: event.message };
  }
}

export function byStart(spans: Record<string, Span>): Span[] {
  return Object.values(spans).sort((a, b) => a.started_at - b.started_at);
}

/** Depth-first span tree, children in start order. */
export function spanRows(spans: Record<string, Span>): { span: Span; depth: number }[] {
  const children = new Map<string | null, Span[]>();
  for (const span of byStart(spans)) {
    const parent = span.parent_span_id && spans[span.parent_span_id] ? span.parent_span_id : null;
    children.set(parent, [...(children.get(parent) ?? []), span]);
  }
  const rows: { span: Span; depth: number }[] = [];
  const visit = (parent: string | null, depth: number) => {
    for (const span of children.get(parent) ?? []) {
      rows.push({ span, depth });
      visit(span.span_id, depth + 1);
    }
  };
  visit(null, 0);
  return rows;
}

/** Nodes of running spans with no running child: several while branches run in parallel. */
export function activeNodes(spans: Record<string, Span>): Set<string> {
  const running = Object.values(spans).filter((s) => s.ended_at == null);
  const parents = new Set(running.map((s) => s.parent_span_id));
  return new Set(running.filter((s) => !parents.has(s.span_id)).map((s) => s.node_id));
}

/**
 * Edges taken so far. Runs from M2 on record them on spans as `lab.came_from`, which covers
 * fan-out, fan-in and loops. M1 runs lack it, so their edges are inferred: tool calls fan out
 * from the node that requested them and all return to the next non-tool node.
 */
export function takenEdges(graph: Graph, spans: Record<string, Span>): Set<string> {
  const declared = new Set(graph.edges.map((e) => edgeKey(e.source, e.target)));
  const taken = new Set<string>();
  const take = (source: string, target: string) => {
    const key = edgeKey(source, target);
    if (declared.has(key)) taken.add(key);
  };
  const recorded = Object.values(spans).filter((s) => Array.isArray(s.attributes["lab.came_from"]));
  if (recorded.length) {
    for (const span of recorded) {
      for (const source of span.attributes["lab.came_from"] as string[]) take(source, span.node_id);
    }
    return taken;
  }
  const tools = new Set(graph.nodes.filter((n) => n.kind === "tool").map((n) => n.id));
  let caller: string | null = null;
  let pending: string[] = [];
  for (const { node_id } of byStart(spans)) {
    if (tools.has(node_id)) {
      if (caller) take(caller, node_id);
      pending.push(node_id);
      continue;
    }
    if (pending.length) pending.forEach((tool) => take(tool, node_id));
    else if (caller) take(caller, node_id);
    pending = [];
    caller = node_id;
  }
  return taken;
}

/** An edge pointing left, e.g. a feedback loop; drawn below the nodes so it stays visible. */
export function isBackEdge(graph: Graph, edge: { source: string; target: string }): boolean {
  const x = (id: string) => graph.nodes.find((n) => n.id === id)?.x ?? 0;
  return x(edge.source) > x(edge.target);
}

export function edgeKey(source: string, target: string): string {
  return `${source}->${target}`;
}

export function durationMs(span: Span, now: number): number {
  return Math.round(((span.ended_at ?? now) - span.started_at) * 1000);
}

/** The agent to describe and preview before a run, or null if it is not listed. */
export function agentPreview(agents: AgentInfo[], id: string): AgentInfo | null {
  return agents.find((a) => a.id === id) ?? null;
}

/** Display name for a run's agent; the raw id when the agent is not (or no longer) listed. */
export function agentName(agents: AgentInfo[], id: string): string {
  return agentPreview(agents, id)?.name ?? id;
}

/** Who ran: the name stored with the run (it outlives a deleted agent), else the listed name. */
export function runAgentLabel(run: Run, agents: AgentInfo[]): { name: string; custom: boolean } {
  return {
    name: run.agent_name ?? agentName(agents, run.agent_id),
    custom: run.template_id != null && run.template_id !== run.agent_id,
  };
}

/** Same definition as the backend's stored totals; wall time counts up to `now` while running. */
export function runTotals(spans: Record<string, Span>, run: Run, now: number): RunTotals {
  const all = Object.values(spans);
  const end = run.ended_at ?? Math.max(now, run.started_at);
  return {
    llm_calls: all.filter((s) => s.kind === "llm").length,
    tool_calls: all.filter((s) => s.kind === "tool").length,
    tokens_in: all.reduce((sum, s) => sum + (s.tokens_in ?? 0), 0),
    tokens_out: all.reduce((sum, s) => sum + (s.tokens_out ?? 0), 0),
    wall_ms: Math.round((end - run.started_at) * 1000),
  };
}

export function formatTotals(t: RunTotals): string {
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const parts = [
    plural(t.llm_calls, "model call"),
    plural(t.tool_calls, "tool call"),
    `${t.tokens_in} in / ${t.tokens_out} out tokens`,
  ];
  if (t.wall_ms != null) parts.push(`${(t.wall_ms / 1000).toFixed(1)} s`);
  return parts.join(" · ");
}

const DECIDED_BY: Record<string, string> = {
  owner: "the owner",
  case: "the test case",
  timeout: "nobody: the time ran out",
};

/** What SpanDetail lists about a span; spans keep the rest in `attributes`. */
export function spanFacts(span: Span): [string, string][] {
  const facts: [string, string][] = [
    ["Kind", span.kind],
    ["Node", span.node_id],
    ["Latency", span.ended_at == null ? "running" : `${durationMs(span, span.ended_at)} ms`],
    ["Provider", String(span.attributes["gen_ai.provider.name"] ?? "–")],
    ["Model", span.model ?? "–"],
    ["Tokens in / out", span.tokens_in == null ? "–" : `${span.tokens_in} / ${span.tokens_out ?? "–"}`],
    ["Config", span.config_version],
  ];
  const attempt = span.attributes["lab.retry.attempt"];
  if (attempt != null) facts.push(["Attempt", `${String(attempt)} of 3`]);
  const wait = span.attributes["lab.retry.wait_s"];
  if (wait != null) facts.push(["Waited before the next try", `${String(wait)} s`]);
  const decision = span.attributes["lab.approval.decision"];
  if (decision != null) facts.push(["Decision", String(decision).replace("_", " ")]);
  const by = span.attributes["lab.approval.by"];
  if (by != null) facts.push(["Decided by", DECIDED_BY[String(by)] ?? String(by)]);
  return facts;
}
