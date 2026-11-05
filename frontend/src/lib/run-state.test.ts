import { describe, expect, it } from "vitest";
import type { AgentInfo, Graph, Run, Span, SpanKind } from "./api";
import {
  activeNodes,
  agentName,
  agentPreview,
  runAgentLabel,
  applyEvent,
  durationMs,
  edgeKey,
  emptyView,
  formatTotals,
  isBackEdge,
  runTotals,
  spanRows,
  takenEdges,
  isLive,
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

function from(s: Span, ...sources: string[]): Span {
  return { ...s, attributes: { "lab.came_from": sources } };
}

// Same shape as the backend's evaluator workflow graph.
const loopGraph: Graph = {
  nodes: [
    { id: "start", label: "start", kind: "start", x: 0, y: 0 },
    { id: "generator", label: "generator", kind: "llm", x: 220, y: 0 },
    { id: "evaluator", label: "evaluator", kind: "llm", x: 440, y: 0 },
    { id: "end", label: "end", kind: "end", x: 660, y: 0 },
  ],
  edges: [
    { source: "start", target: "generator" },
    { source: "generator", target: "evaluator" },
    { source: "evaluator", target: "end" },
    { source: "evaluator", target: "generator" },
  ],
};

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

describe("activeNodes", () => {
  it("is the node of the innermost running span", () => {
    const spans = bySpanId(
      span("root", "start", 0, null),
      span("it1", "llm", 1, null, "root"),
      span("tool", "tool:calculator", 2, null, "it1", "tool"),
    );
    expect(activeNodes(spans)).toEqual(new Set(["tool:calculator"]));
  });

  it("holds every branch running in parallel", () => {
    const spans = bySpanId(
      span("root", "start", 0, null),
      span("sections", "start", 1, null, "root"),
      span("a", "clarity", 2, null, "sections", "llm"),
      span("b", "tone", 2, null, "sections", "llm"),
      span("c", "claims", 2, null, "sections", "llm"),
    );
    expect(activeNodes(spans)).toEqual(new Set(["clarity", "tone", "claims"]));
  });

  it("drops a branch once it ends", () => {
    const spans = bySpanId(
      span("root", "start", 0, null),
      span("a", "clarity", 1, 2, "root", "llm"),
      span("b", "tone", 1, null, "root", "llm"),
    );
    expect(activeNodes(spans)).toEqual(new Set(["tone"]));
  });

  it("is empty once everything has ended", () => {
    expect(activeNodes(bySpanId(span("root", "start", 0, 1))).size).toBe(0);
  });
});

describe("agentPreview and agentName", () => {
  const agents: AgentInfo[] = [
    {
      id: "react",
      kind: "template",
      template_id: "react",
      name: "ReAct agent",
      description: "loop",
      sample_prompt: "2+2?",
      config: {},
      model: null,
      graph,
      budget: null,
      ask_first: [],
    },
  ];

  it("finds a listed agent", () => {
    expect(agentPreview(agents, "react")?.sample_prompt).toBe("2+2?");
    expect(agentName(agents, "react")).toBe("ReAct agent");
  });

  it("falls back for an unknown agent", () => {
    expect(agentPreview(agents, "gone")).toBeNull();
    expect(agentName(agents, "gone")).toBe("gone");
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

describe("takenEdges from lab.came_from", () => {
  const parallel: Graph = {
    nodes: ["start", "a", "b", "merge", "end"].map((id, i) => ({
      id,
      label: id,
      kind: "llm" as const,
      x: i * 100,
      y: 0,
    })),
    edges: [
      { source: "start", target: "a" },
      { source: "start", target: "b" },
      { source: "a", target: "merge" },
      { source: "b", target: "merge" },
      { source: "a", target: "end" },
      { source: "b", target: "end" },
      { source: "merge", target: "end" },
    ],
  };

  it("marks fan-out and fan-in, not the unused exits", () => {
    const spans = bySpanId(
      span("root", "start", 0),
      from(span("a", "a", 1), "start"),
      from(span("b", "b", 1), "start"),
      from(span("merge", "merge", 2), "a", "b"),
      from(span("end", "end", 3), "merge"),
    );
    expect(takenEdges(parallel, spans)).toEqual(
      edges(["start", "a"], ["start", "b"], ["a", "merge"], ["b", "merge"], ["merge", "end"]),
    );
  });

  it("marks the loop edge of a revision round", () => {
    const spans = bySpanId(
      span("root", "start", 0),
      from(span("g1", "generator", 1), "start"),
      from(span("v1", "evaluator", 2), "generator"),
      from(span("g2", "generator", 3), "evaluator"),
      from(span("v2", "evaluator", 4), "generator"),
      from(span("end", "end", 5), "evaluator"),
    );
    expect(takenEdges(loopGraph, spans)).toEqual(
      edges(
        ["start", "generator"],
        ["generator", "evaluator"],
        ["evaluator", "generator"],
        ["evaluator", "end"],
      ),
    );
  });

  it("ignores an edge the graph does not declare", () => {
    const spans = bySpanId(from(span("x", "end", 1), "start"));
    expect(takenEdges(loopGraph, spans).size).toBe(0);
  });
});

describe("isBackEdge", () => {
  it("is true only for edges pointing left", () => {
    expect(isBackEdge(loopGraph, { source: "evaluator", target: "generator" })).toBe(true);
    expect(isBackEdge(loopGraph, { source: "generator", target: "evaluator" })).toBe(false);
    // Tools sit below their caller at the same x: not a back edge.
    expect(isBackEdge(graph, { source: "llm", target: "llm" })).toBe(false);
  });
});

describe("runTotals and formatTotals", () => {
  const run = { run_id: "r", started_at: 10, ended_at: null } as Run;
  const spans = bySpanId(
    { ...span("c1", "llm", 10, 11, null, "llm"), tokens_in: 100, tokens_out: 20 },
    { ...span("c2", "llm", 11, null, null, "llm"), tokens_in: 50 },
    span("t1", "tool:calculator", 11, 12, null, "tool"),
    span("root", "start", 10, null),
  );

  it("counts calls and tokens; wall time runs to now while running", () => {
    expect(runTotals(spans, run, 12.5)).toEqual({
      llm_calls: 2,
      tool_calls: 1,
      tokens_in: 150,
      tokens_out: 20,
      wall_ms: 2500,
    });
  });

  it("stops the wall clock when the run ends", () => {
    expect(runTotals(spans, { ...run, ended_at: 13 }, 99).wall_ms).toBe(3000);
  });

  it("formats with plurals and an optional wall time", () => {
    const t = { llm_calls: 1, tool_calls: 2, tokens_in: 5, tokens_out: 6, wall_ms: 1234 };
    expect(formatTotals(t)).toBe("1 model call · 2 tool calls · 5 in / 6 out tokens · 1.2 s");
    expect(formatTotals({ ...t, wall_ms: null })).toBe(
      "1 model call · 2 tool calls · 5 in / 6 out tokens",
    );
  });
});

describe("durationMs", () => {
  it("uses the end time, or now while running", () => {
    expect(durationMs(span("a", "llm", 1, 1.25), 99)).toBe(250);
    expect(durationMs(span("a", "llm", 1, null), 1.5)).toBe(500);
  });
});

describe("runAgentLabel", () => {
  const agents = [{ id: "react", name: "ReAct agent" }] as AgentInfo[];
  const run = (fields: Partial<Run>) => ({ agent_id: "react", agent_name: null, template_id: null, ...fields }) as Run;

  it("prefers the stored name, so deleted custom agents keep theirs", () => {
    expect(runAgentLabel(run({ agent_id: "custom-1", agent_name: "Mine", template_id: "chain" }), agents)).toEqual({
      name: "Mine",
      custom: true,
    });
  });

  it("names template runs and runs from before M3 from the agents list", () => {
    expect(runAgentLabel(run({ agent_name: "ReAct agent", template_id: "react" }), agents)).toEqual({
      name: "ReAct agent",
      custom: false,
    });
    expect(runAgentLabel(run({}), agents)).toEqual({ name: "ReAct agent", custom: false });
  });
});

describe("a run's status while it lives", () => {
  it("records a status change without treating the run as ended", () => {
    const view = applyEvent(emptyView, { type: "run_status", run_id: "r", status: "waiting_approval" });
    expect(view.status).toBe("waiting_approval");
    expect(view.run).toBeNull(); // RunViewer calls onEnded only once `run` is set
  });

  it("counts waiting for an approval as live and every end as not", () => {
    expect(isLive("running")).toBe(true);
    expect(isLive("waiting_approval")).toBe(true);
    for (const status of ["completed", "max_iterations", "over_budget", "stopped", "interrupted", "error"] as const) {
      expect(isLive(status)).toBe(false);
    }
  });
});
