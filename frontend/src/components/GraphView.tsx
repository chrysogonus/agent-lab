"use client";

import "@xyflow/react/dist/style.css";
import {
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import type { Graph, GraphNode } from "@/lib/api";
import { edgeKey } from "@/lib/run-state";

type NodeState = "active" | "visited" | "idle";
type LabNodeData = { label: string; kind: GraphNode["kind"]; state: NodeState };

const KIND_COLOR: Record<GraphNode["kind"], string> = {
  start: "var(--color-step)",
  end: "var(--color-step)",
  llm: "var(--color-llm)",
  tool: "var(--color-tool)",
};

// Hidden handles: left/right for the main line, top/bottom pairs for the llm <-> tool loop.
const HANDLES = [
  { id: "l", type: "target", position: Position.Left },
  { id: "r", type: "source", position: Position.Right },
  { id: "t-in", type: "target", position: Position.Top, left: "35%" },
  { id: "t-out", type: "source", position: Position.Top, left: "65%" },
  { id: "b-out", type: "source", position: Position.Bottom, left: "35%" },
  { id: "b-in", type: "target", position: Position.Bottom, left: "65%" },
] as const;

function LabNode({ data }: NodeProps<Node<LabNodeData>>) {
  const color = KIND_COLOR[data.kind];
  return (
    <div
      className={`lab-node flex size-full items-center justify-center rounded-md border-2 bg-panel px-3 text-sm font-medium text-ink ${
        data.state === "active" ? "lab-node--active" : ""
      }`}
      style={{
        borderColor: data.state === "idle" ? "var(--color-rule)" : color,
        boxShadow: data.state === "visited" ? `inset 4px 0 0 ${color}` : undefined,
      }}
    >
      {HANDLES.map((h) => (
        <Handle
          key={h.id}
          id={h.id}
          type={h.type}
          position={h.position}
          isConnectable={false}
          style={{ opacity: 0, ...("left" in h ? { left: h.left } : {}) }}
        />
      ))}
      {data.label}
    </div>
  );
}

const nodeTypes = { lab: LabNode };

// Fixed sizes: React Flow drops measured sizes when it receives new node objects each render.
const NODE_WIDTH = 150;
const NODE_HEIGHT = 44;

function handlesFor(source: GraphNode, target: GraphNode) {
  if (source.kind === "llm" && target.kind === "tool") return { sourceHandle: "b-out", targetHandle: "t-in" };
  if (source.kind === "tool" && target.kind === "llm") return { sourceHandle: "t-out", targetHandle: "b-in" };
  return { sourceHandle: "r", targetHandle: "l" };
}

export function GraphView({
  graph,
  active,
  visited,
  taken,
}: {
  graph: Graph;
  active: string | null;
  visited: Set<string>;
  taken: Set<string>;
}) {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const nodes: Node<LabNodeData>[] = graph.nodes.map((n) => ({
    id: n.id,
    type: "lab",
    position: { x: n.x, y: n.y },
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    data: {
      label: n.label,
      kind: n.kind,
      state: n.id === active ? "active" : visited.has(n.id) ? "visited" : "idle",
    },
  }));
  const edges: Edge[] = graph.edges.map((e) => {
    const isTaken = taken.has(edgeKey(e.source, e.target));
    const color = isTaken ? "var(--color-llm)" : "var(--color-rule)";
    return {
      id: edgeKey(e.source, e.target),
      source: e.source,
      target: e.target,
      ...handlesFor(byId.get(e.source)!, byId.get(e.target)!),
      style: { stroke: color, strokeWidth: isTaken ? 2 : 1.5, strokeDasharray: isTaken ? undefined : "4 4" },
      markerEnd: { type: MarkerType.ArrowClosed, color },
    };
  });
  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.25 }}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      aria-label="Agent graph"
    />
  );
}
