import { describe, expect, it } from "vitest";
import type { AgentInfo, Graph } from "./api";
import {
  copyName,
  draftFields,
  draftFrom,
  draftFromAgent,
  fieldErrors,
  getField,
  nodeSettings,
  sectionNode,
  setField,
} from "./builder";

const graph: Graph = { nodes: [], edges: [] };

function agent(overrides: Partial<AgentInfo>): AgentInfo {
  return {
    id: "routing",
    kind: "template",
    template_id: "routing",
    name: "Routing",
    description: "routes",
    sample_prompt: "2**10?",
    config: {
      router_prompt: "Classify.",
      routes: [
        { name: "math", description: "sums", prompt: "Calc.", tool: "calculator" },
        { name: "general", description: "anything else", prompt: "Answer.", tool: null },
      ],
      fallback: "general",
    },
    graph,
    ...overrides,
  };
}

describe("copyName", () => {
  it("adds (copy), then counts up, ignoring case and spaces", () => {
    expect(copyName("Routing", ["Routing"])).toBe("Routing (copy)");
    expect(copyName("Routing", [" routing (COPY) "])).toBe("Routing (copy 2)");
    expect(copyName("Routing", ["Routing (copy)", "Routing (copy 2)"])).toBe("Routing (copy 3)");
  });
});

describe("drafts", () => {
  it("starts an unsaved copy of a template", () => {
    const template = agent({});
    const draft = draftFrom(template, [template]);
    expect(draft).toMatchObject({ agentId: null, templateId: "routing", name: "Routing (copy)" });
    expect(draft.dirty).toBe(true);
    expect(draft.config).toEqual(template.config);
    expect(draft.config).not.toBe(template.config); // edits never touch the listed agent
  });

  it("duplicates a custom agent under a free name, keeping its template", () => {
    const mine = agent({ id: "custom-1", kind: "custom", name: "Mine" });
    expect(draftFrom(mine, [mine])).toMatchObject({ templateId: "routing", name: "Mine (copy)" });
  });

  it("loads a saved agent unchanged", () => {
    const draft = draftFromAgent(agent({ id: "custom-1", kind: "custom", name: "Mine" }));
    expect(draft).toMatchObject({ agentId: "custom-1", name: "Mine", dirty: false });
    expect(draftFields(draft)).toEqual({
      name: "Mine",
      description: "routes",
      sample_prompt: "2**10?",
      config: draft.config,
    });
  });

  it("sets nested fields immutably and marks the draft changed", () => {
    const draft = draftFromAgent(agent({ kind: "custom" }));
    const next = setField(draft, ["config", "routes", 1, "prompt"], "Be brief.");
    expect(getField(next, ["config", "routes", 1, "prompt"])).toBe("Be brief.");
    expect(getField(draft, ["config", "routes", 1, "prompt"])).toBe("Answer.");
    expect(Array.isArray(getField(next, ["config", "routes"]))).toBe(true);
    expect(next.dirty).toBe(true);
  });
});

describe("nodeSettings", () => {
  const routing = agent({}).config;

  it("opens agent settings for start, end and empty space", () => {
    for (const node of [null, "start", "end"]) {
      expect(nodeSettings("routing", routing, node)).toEqual({ kind: "agent" });
    }
  });

  it("maps nodes to their settings per template", () => {
    expect(nodeSettings("routing", routing, "general")).toEqual({ kind: "route", index: 1 });
    expect(nodeSettings("routing", routing, "router")).toMatchObject({
      kind: "prompt",
      path: ["config", "router_prompt"],
    });
    expect(nodeSettings("routing", routing, "tool:calculator")).toEqual({
      kind: "tool",
      name: "calculator",
    });
    expect(nodeSettings("react", { system_prompt: "s" }, "llm")).toMatchObject({
      path: ["config", "system_prompt"],
    });
    const chain = { steps: [{ name: "outline" }, { name: "draft" }], gate: true };
    expect(nodeSettings("chain", chain, "draft")).toEqual({ kind: "step", index: 1 });
    expect(nodeSettings("chain", chain, "gate")).toEqual({ kind: "gate" });
    const parallel = { aspects: { tone: "t" }, merge_prompt: "m" };
    expect(nodeSettings("parallel", parallel, "tone")).toEqual({ kind: "aspect", name: "tone" });
    expect(nodeSettings("parallel", parallel, "merge")).toMatchObject({
      path: ["config", "merge_prompt"],
    });
    expect(nodeSettings("orchestrator", { worker_prompt: "w" }, "worker")).toMatchObject({
      path: ["config", "worker_prompt"],
    });
  });
});

describe("fieldErrors", () => {
  it("keys messages by their path into the draft, first message wins", () => {
    expect(
      fieldErrors([
        { loc: ["body", "config", "routes", 1, "name"], msg: "String should match pattern" },
        { loc: ["body", "config", "routes", 1, "name"], msg: "second" },
        { loc: ["body", "name"], msg: "name already in use" },
        { loc: ["body", "config"], msg: "Value error, fallback 'x' is not one of the routes" },
      ]),
    ).toEqual({
      "config.routes.1.name": "String should match pattern",
      name: "name already in use",
      config: "fallback 'x' is not one of the routes",
    });
  });
});

describe("sectionNode", () => {
  it("is the inverse of nodeSettings for every node kind", () => {
    const routing = agent({}).config;
    for (const node of ["router", "math", "general", "tool:calculator"]) {
      expect(sectionNode(nodeSettings("routing", routing, node), routing)).toBe(node);
    }
    expect(sectionNode(nodeSettings("react", { system_prompt: "s" }, "llm"), {})).toBe("llm");
    expect(sectionNode({ kind: "agent" }, routing)).toBeNull();
  });

  it("follows a renamed route", () => {
    const draft = setField(draftFromAgent(agent({})), ["config", "routes", 0, "name"], "sums");
    expect(sectionNode({ kind: "route", index: 0 }, draft.config)).toBe("sums");
  });
});
