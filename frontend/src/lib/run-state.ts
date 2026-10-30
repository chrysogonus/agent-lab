// Pure view logic shared by live runs and replays: both are built from the same stream events.
import type { Graph, Run, Span, StreamEvent } from "./api";

export type RunView = { run: Run | null; spans: Record<string, Span>; error: string | null };

export const emptyView: RunView = { run: null, spans: {}, error: null };

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

/** The node of the most recently started span that is still running. */
export function activeNode(spans: Record<string, Span>): string | null {
  const running = byStart(spans).filter((s) => s.ended_at == null);
  return running.at(-1)?.node_id ?? null;
}

/** Edges taken so far: consecutive node visits that are declared edges of the graph. */
export function takenEdges(graph: Graph, spans: Record<string, Span>): Set<string> {
  const declared = new Set(graph.edges.map((e) => edgeKey(e.source, e.target)));
  const taken = new Set<string>();
  const path = byStart(spans).map((s) => s.node_id);
  for (let i = 1; i < path.length; i++) {
    const key = edgeKey(path[i - 1], path[i]);
    if (declared.has(key)) taken.add(key);
  }
  return taken;
}

export function edgeKey(source: string, target: string): string {
  return `${source}->${target}`;
}

export function durationMs(span: Span, now: number): number {
  return Math.round(((span.ended_at ?? now) - span.started_at) * 1000);
}
