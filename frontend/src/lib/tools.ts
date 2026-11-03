// Tools from MCP servers (M16): grouping for the pickers and labels for the Tools view.
import type { McpServer, ToolInfo } from "./api";

export type ToolGroup = { server: string; tools: ToolInfo[] };

/** Tools by server: the lab's own first, then the others by name; each keeps its listed order. */
export function groupTools(tools: ToolInfo[]): ToolGroup[] {
  const groups = new Map<string, ToolInfo[]>();
  for (const tool of tools) groups.set(tool.server, [...(groups.get(tool.server) ?? []), tool]);
  const order = (s: string) => (s === "lab" ? "" : s);
  return [...groups.entries()]
    .sort(([a], [b]) => order(a).localeCompare(order(b)))
    .map(([server, list]) => ({ server, tools: list }));
}

/** The chosen tool names no connected server offers; `lab/x` names the built-in `x`. */
export function unavailableTools(names: string[], tools: ToolInfo[]): string[] {
  const offered = new Set(tools.map((t) => t.name));
  return names.filter((n) => !offered.has(n) && !offered.has(n.replace(/^lab\//, "")));
}

export function stateLabel(server: Pick<McpServer, "state" | "reason">): string {
  if (server.state === "connecting") return "connecting…";
  return server.state === "failed" ? `failed: ${server.reason}` : "connected";
}
