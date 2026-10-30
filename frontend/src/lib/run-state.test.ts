import { describe, expect, it } from "vitest";
import type { Graph, Run, Span, SpanKind } from "./api";
import {
  activeNode,
  applyEvent,
  durationMs,
  edgeKey,
  emptyView,
  spanRows,
  takenEdges,
} from "./run-state";

// Same shape as the backend's build_graph(["calculator", "get_weather"]).
const graph: Graph = {
  nodes: [
    { id: "start", label: "start", kind: "start", x: 0, y: 0 },
    { id: "llm", label: "reason (LLM)", kind: "llm", x: 240, y: 0 },
    { id: "end", label: "end", kind: "end", x: 480, y: 0 },
    { id: "tool:calculator", label: "calculator", kind: "tool", x: 130, y: 180 },
    { id: "tool:get_weather", label: "get_weather", kind: "tool", x: 350, y: 180 },
  ],
  edges: [
    { source: "start", target: "llm" },
    { source: "llm", target: "end" },
    { source: "llm", target: "tool:calculator" },
    { source: "tool:calculator", target: "llm" },
    { source: "llm", target: "tool:get_weather" },
    { source: "tool:get_weather", target: "llm" },
  ],
};

function span(
  id: string,
  node: string,
  started: number,
  ended: number | null = started + 1,
  parent: string | null = null,
  kind: SpanKind = "step",
): Span {
  return {
    trace_id: "t",
    span_id: id,
    parent_span_id: parent,
    run_id: "r",
    agent_id: "react",
    node_id: node,
    config_version: "v",
    kind,
    name: id,
    input: null,
    output: null,
    error: null,
    started_at: started,
    ended_at: ended,
    tokens_in: null,
    tokens_out: null,
    model: null,
    attributes: {},
  };
}

function bySpanId(...spans: Span[]): Record<string, Span> {
  return Object.fromEntries(spans.map((s) => [s.span_id, s]));
}

function edges(...pairs: [string, string][]): Set<string> {
  return new Set(pairs.map(([s, t]) => edgeKey(s, t)));
}

describe("applyEvent", () => {
  it("upserts spans by id", () => {
    const started = applyEvent(emptyView, { type: "span_started", span: span("a", "llm", 1, null) });
    const ended = applyEvent(started, { type: "span_ended", span: span("a", "llm", 1, 2) });
    expect(Object.keys(ended.spans)).toEqual(["a"]);
    expect(ended.spans.a.ended_at).toBe(2);
  });

  it("keeps an ended span when a stale start event arrives", () => {
    // The stream sends stored spans, then live events, so the same span can arrive twice.
    const ended = applyEvent(emptyView, { type: "span_ended", span: span("a", "llm", 1, 2) });
    expect(applyEvent(ended, { type: "span_started", span: span("a", "llm", 1, null) })).toBe(ended);
  });

  it("records the finished run and stream errors", () => {
    const run = { run_id: "r", status: "completed" } as Run;
    expect(applyEvent(emptyView, { type: "run_ended", run }).run).toBe(run);
    expect(applyEvent(emptyView, { type: "error", message: "unknown run" }).error).toBe(
      "unknown run",
    );
  });
});

describe("spanRows", () => {
  it("orders depth-first with children in start order", () => {
    const spans = bySpanId(
      span("root", "start", 0, 10),
      span("it2", "llm", 5, 9, "root"),
      span("it1", "llm", 1, 4, "root"),
      span("chat1", "llm", 1, 2, "it1", "llm"),
      span("tool1", "tool:calculator", 3, 4, "it1", "tool"),
    );
    expect(spanRows(spans).map((r) => [r.span.span_id, r.depth])).toEqual([
      ["root", 0],
      ["it1", 1],
      ["chat1", 2],
      ["tool1", 2],
      ["it2", 1],
    ]);
  });

  it("shows a span whose parent has not arrived yet at the top level", () => {
    const rows = spanRows(bySpanId(span("child", "llm", 1, 2, "missing")));
    expect(rows).toEqual([{ span: expect.objectContaining({ span_id: "child" }), depth: 0 }]);
  });
});

describe("activeNode", () => {
  it("is the node of the most recently started running span", () => {
    const spans = bySpanId(
      span("root", "start", 0, null),
      span("it1", "llm", 1, null, "root"),
      span("tool", "tool:calculator", 2, null, "it1", "tool"),
    );
    expect(activeNode(spans)).toBe("tool:calculator");
  });

  it("is null once everything has ended", () => {
    expect(activeNode(bySpanId(span("root", "start", 0, 1)))).toBeNull();
  });
});

describe("takenEdges", () => {
  it("marks one tool per turn", () => {
    const spans = bySpanId(
      span("root", "start", 0),
      span("it1", "llm", 1),
      span("chat1", "llm", 2),
      span("calc", "tool:calculator", 3),
      span("it2", "llm", 4),
      span("chat2", "llm", 5),
      span("end", "end", 6),
    );
    expect(takenEdges(graph, spans)).toEqual(
      edges(
        ["start", "llm"],
        ["llm", "tool:calculator"],
        ["tool:calculator", "llm"],
        ["llm", "end"],
      ),
    );
  });

  it("marks both edges of every tool called in a single turn", () => {
    const spans = bySpanId(
      span("root", "start", 0),
      span("it1", "llm", 1),
      span("chat1", "llm", 2),
      span("calc", "tool:calculator", 3),
      span("weather", "tool:get_weather", 4),
      span("it2", "llm", 5),
    );
    expect(takenEdges(graph, spans)).toEqual(
      edges(
        ["start", "llm"],
        ["llm", "tool:calculator"],
        ["llm", "tool:get_weather"],
        ["tool:calculator", "llm"],
        ["tool:get_weather", "llm"],
      ),
    );
  });

  it("marks only declared edges", () => {
    // Unknown tools are attributed to the llm node; the iteration cap ends right after a tool.
    const spans = bySpanId(
      span("root", "start", 0),
      span("chat1", "llm", 1),
      span("unknown", "llm", 2),
      span("calc", "tool:calculator", 3),
      span("end", "end", 4),
    );
    expect(takenEdges(graph, spans)).toEqual(
      edges(["start", "llm"], ["llm", "tool:calculator"]),
    );
  });

  it("is empty before any span arrives", () => {
    expect(takenEdges(graph, {}).size).toBe(0);
  });
});

describe("durationMs", () => {
  it("uses the end time, or now while running", () => {
    expect(durationMs(span("a", "llm", 1, 1.25), 99)).toBe(250);
    expect(durationMs(span("a", "llm", 1, null), 1.5)).toBe(500);
  });
});
