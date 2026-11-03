import { describe, expect, it } from "vitest";
import type { AgentInfo, Block, ModelBlock, ToolInfo } from "./api";
import {
  addBlock,
  allBlocks,
  argumentsFor,
  blockAt,
  blockErrors,
  canRemoveBlock,
  childLists,
  defaultBlock,
  findBlock,
  freeName,
  moveBlock,
  removeBlock,
  renameBlock,
  addRoute,
  addBranch,
  canRemoveRoute,
  removeRoute,
  renameRoute,
  setExit,
  setMode,
  setRule,
} from "./blocks";
import { draftFromAgent, nodeSettings, sectionNode, type Draft } from "./builder";

const model = (name: string, fields: Partial<ModelBlock> = {}): ModelBlock => ({
  kind: "model",
  name,
  system: "Help.",
  message: "{previous}",
  tools: [],
  max_iterations: 4,
  answer_on_last_call: false,
  ...fields,
});

const tools: ToolInfo[] = [
  { name: "calculator", server: "lab", description: "math", parameters: { properties: { expression: {} } } },
  { name: "get_weather", server: "lab", description: "weather", parameters: { properties: { city: {} } } },
];

function draft(blocks: Block[]): Draft {
  const agent: AgentInfo = {
    id: "custom-1",
    kind: "custom",
    template_id: "blocks",
    name: "Mine",
    description: "",
    sample_prompt: "hi",
    config: { reasoning: false, blocks },
    model: null,
    graph: { nodes: [], edges: [] },
  };
  return draftFromAgent(agent);
}

const routed = (): Draft =>
  draft([
    model("first"),
    {
      kind: "router",
      name: "route",
      prompt: "Classify.",
      routes: [
        { name: "x", description: "x", blocks: [model("in-x", { message: "{first}" })] },
        { name: "y", description: "y", blocks: [model("in-y"), model("after-y")] },
      ],
      fallback: "y",
    },
    model("last", { message: "{route} and {first}" }),
  ]);

describe("finding blocks", () => {
  it("lists every block with its full path, containers before their contents", () => {
    expect(allBlocks(routed().config).map((b) => [b.block.name, b.path.join(".")])).toEqual([
      ["first", "config.blocks.0"],
      ["route", "config.blocks.1"],
      ["in-x", "config.blocks.1.routes.0.blocks.0"],
      ["in-y", "config.blocks.1.routes.1.blocks.0"],
      ["after-y", "config.blocks.1.routes.1.blocks.1"],
      ["last", "config.blocks.2"],
    ]);
  });

  it("finds a block by name and reads it back", () => {
    const { config } = routed();
    const path = findBlock(config, "after-y")!;
    expect(blockAt(config, path)?.name).toBe("after-y");
    expect(findBlock(config, "nope")).toBeNull();
  });

  it("opens the clicked node's block and follows it by path", () => {
    const { config } = routed();
    const section = nodeSettings("blocks", config, "in-y");
    expect(section).toEqual({ kind: "block", path: ["config", "blocks", 1, "routes", 1, "blocks", 0] });
    expect(sectionNode(section, config)).toBe("in-y");
    expect(nodeSettings("blocks", config, "tool:calculator")).toEqual({ kind: "tool", name: "calculator" });
    expect(nodeSettings("blocks", config, "start")).toEqual({ kind: "agent" });
  });

  it("labels each container list", () => {
    const loop = defaultBlock("loop", new Set());
    const group = defaultBlock("parallel", new Set());
    expect(childLists(loop).map((l) => l.label)).toEqual(["Repeat"]);
    expect(childLists(group).map((l) => l.label)).toEqual(["Branch a", "Branch b"]);
    expect(childLists(model("m"))).toEqual([]);
  });
});

describe("names", () => {
  it("picks the first free name and skips reserved words", () => {
    expect(freeName(new Set(), "step")).toBe("step");
    expect(freeName(new Set(["step", "step-2"]), "step")).toBe("step-3");
    expect(freeName(new Set(), "input")).toBe("input-2");
  });

  it("gives a new container and its inner blocks unique names", () => {
    const router = defaultBlock("router", new Set(["step"]));
    const inner = childLists(router).flatMap((l) => l.blocks.map((b) => b.name));
    expect([router.name, ...inner]).toEqual(["router", "step-2", "step-3"]);
  });

  it("fills one argument per tool parameter", () => {
    expect(argumentsFor("get_weather", tools)).toEqual({ city: "{previous}" });
    expect(defaultBlock("tool", new Set(), tools)).toMatchObject({ tool: "calculator", arguments: { expression: "{previous}" } });
  });
});

describe("edits", () => {
  it("adds a block after another, inside a route, with a free name", () => {
    const start = routed();
    const added = addBlock(start, ["config", "blocks", 1, "routes", 0, "blocks"], 1, "tool", tools);
    const route = (added.config.blocks as Block[])[1];
    expect(route.kind === "router" && route.routes[0].blocks.map((b) => b.name)).toEqual(["in-x", "tool"]);
    expect(added.dirty).toBe(true);
    expect(start.config).toEqual(routed().config); // the input is not mutated
  });

  it("moves within a list and keeps lists from becoming empty", () => {
    const d = routed();
    const moved = moveBlock(d, ["config", "blocks", 1, "routes", 1, "blocks", 1], -1);
    expect(allBlocks(moved.config).map((b) => b.block.name).slice(3, 5)).toEqual(["after-y", "in-y"]);
    expect(moveBlock(d, ["config", "blocks", 0], -1)).toBe(d);
    expect(canRemoveBlock(d, ["config", "blocks", 1, "routes", 0, "blocks", 0])).toBe(false);
    const removed = removeBlock(d, ["config", "blocks", 1, "routes", 1, "blocks", 0]);
    expect(allBlocks(removed.config).map((b) => b.block.name)).not.toContain("in-y");
  });

  it("renames a block and its references everywhere", () => {
    const renamed = renameBlock(routed(), ["config", "blocks", 0], "intro");
    const byName = Object.fromEntries(allBlocks(renamed.config).map((b) => [b.block.name, b.block]));
    expect(byName.intro).toBeDefined();
    expect((byName["in-x"] as ModelBlock).message).toBe("{intro}");
    expect((byName.last as ModelBlock).message).toBe("{route} and {intro}");
  });

  it("collects the errors of a block and its contents", () => {
    const errors = {
      "config.blocks.1.prompt": "empty",
      "config.blocks.1.routes.0.blocks.0.message": "unknown reference",
      "config.blocks.10.name": "other block",
      name: "taken",
    };
    expect(blockErrors(errors, ["config", "blocks", 1]).map(([k]) => k)).toEqual([
      "config.blocks.1.prompt",
      "config.blocks.1.routes.0.blocks.0.message",
    ]);
  });
});

describe("container settings", () => {
  const at: (string | number)[] = ["config", "blocks", 1];

  it("adds routes up to six and keeps two plus the fallback", () => {
    let d = routed();
    expect(canRemoveRoute(blockAt(d.config, at)!, 1)).toBe(false); // y is the fallback
    d = addRoute(d, at, tools);
    const router = blockAt(d.config, at)!;
    expect(router.kind === "router" && router.routes.map((r) => r.name)).toEqual(["x", "y", "route"]);
    expect(canRemoveRoute(router, 0)).toBe(true);
    const fewer = removeRoute(d, at, 0);
    expect(allBlocks(fewer.config).map((b) => b.block.name)).not.toContain("in-x");
  });

  it("renames the fallback with its route", () => {
    const router = blockAt(renameRoute(routed(), at, 1, "other").config, at)!;
    expect(router.kind === "router" && [router.routes[1].name, router.fallback]).toEqual(["other", "other"]);
  });

  it("switches a group between branches and per-item, keeping the first list's blocks", () => {
    const d = draft([defaultBlock("parallel", new Set())]);
    const path: (string | number)[] = ["config", "blocks", 0];
    const perItem = setMode(d, path, "per_item");
    const group = blockAt(perItem.config, path)!;
    expect(group).toMatchObject({ mode: "per_item", branches: null, max_items: 3 });
    expect(group.kind === "parallel" && group.body?.map((b) => b.name)).toEqual(["step"]);
    const back = blockAt(setMode(perItem, path, "branches").config, path)!;
    expect(back).toMatchObject({ mode: "branches", planner: null, body: null });
    const more = blockAt(addBranch(d, path, tools).config, path)!;
    expect(more.kind === "parallel" && more.branches?.map((b) => b.name)).toEqual(["a", "b", "branch"]);
  });

  it("switches a loop's exit and a rule's default value", () => {
    const d = draft([defaultBlock("loop", new Set())]);
    const path: (string | number)[] = ["config", "blocks", 0];
    const checked = setExit(d, path, "check");
    expect(blockAt(checked.config, path)).toMatchObject({ exit: "check", judge: null, check: { rule: "max_words", value: 100 } });
    const json = setRule(checked, [...path, "check"], "valid_json");
    expect(blockAt(json.config, path)).toMatchObject({ check: { rule: "valid_json", value: null } });
  });
});
