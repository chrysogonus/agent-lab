import { describe, expect, it } from "vitest";
import type { McpServer, ToolInfo } from "./api";
import { groupTools, stateLabel, unavailableTools } from "./tools";

const tool = (name: string, server: string): ToolInfo => ({ name, server, description: "", parameters: {} });

describe("groupTools", () => {
  it("puts the lab first, then the servers by name, keeping each server's order", () => {
    const tools = [tool("notes/write", "notes"), tool("calculator", "lab"), tool("a/x", "a"), tool("notes/list", "notes"), tool("get_weather", "lab")];
    expect(groupTools(tools).map((g) => [g.server, g.tools.map((t) => t.name)])).toEqual([
      ["lab", ["calculator", "get_weather"]],
      ["a", ["a/x"]],
      ["notes", ["notes/write", "notes/list"]],
    ]);
  });

  it("is empty without tools", () => {
    expect(groupTools([])).toEqual([]);
  });
});

describe("unavailableTools", () => {
  it("names the chosen tools no connected server offers", () => {
    const tools = [tool("calculator", "lab"), tool("notes/read", "notes")];
    expect(unavailableTools(["calculator", "notes/write", "lab/get_weather", "notes/read"], tools)).toEqual([
      "notes/write",
      "lab/get_weather",
    ]);
  });

  it("knows lab/ names of the built-ins", () => {
    expect(unavailableTools(["lab/calculator"], [tool("calculator", "lab")])).toEqual([]);
  });
});

describe("stateLabel", () => {
  const server = (state: McpServer["state"], reason: string | null = null) => ({ state, reason }) as McpServer;
  it("says the state and why a server failed", () => {
    expect(stateLabel(server("connected"))).toBe("connected");
    expect(stateLabel(server("connecting"))).toBe("connecting…");
    expect(stateLabel(server("failed", "cannot start: No such file or directory"))).toBe(
      "failed: cannot start: No such file or directory",
    );
  });
});
