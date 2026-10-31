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
import { edgeKey, isBackEdge } from "@/lib/run-state";

type NodeState = "active" | "visited" | "idle";
type LabNodeData = {
  label: string;
  kind: GraphNode["kind"];
  state: NodeState;
  selected: boolean;
  onSelect?: () => void; // set when nodes open their settings (the builder)
};

const KIND_COLOR: Record<GraphNode["kind"], string> = {
  start: "var(--color-step)",
  end: "var(--color-step)",
  llm: "var(--color-llm)",
  tool: "var(--color-tool)",
  code: "var(--color-step)",
};

// Hidden handles: left/right for the main line, top/bottom pairs for llm <-> tool and back edges.
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
  const clickable = data.onSelect != null;
  return (
    <div
      className={`lab-node flex size-full items-center justify-center rounded-md border-2 bg-panel px-3 text-sm font-medium text-ink ${
        data.state === "active" ? "lab-node--active" : ""
      } ${data.selected ? "lab-node--selected" : ""} ${
        clickable ? "cursor-pointer hover:bg-paper focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-llm" : ""
      }`}
      {...(clickable && {
        role: "button",
        tabIndex: 0,
        "aria-pressed": data.selected,
        onKeyDown: (e: React.KeyboardEvent) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            data.onSelect?.();
          }
        },
      })}
      style={{
        borderColor: data.state === "idle" && !data.selected ? "var(--color-rule)" : color,
        borderStyle: data.kind === "code" ? "dashed" : undefined, // code step, no model call
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

// Nodes are rebuilt on every span event. React Flow keeps a node's handle positions (needed to
// draw edges) only when the new node object carries `measured`, so pass a fixed size as both.
const NODE_WIDTH = 150;
const NODE_HEIGHT = 44;

function handlesFor(source: GraphNode, target: GraphNode, back: boolean) {
  // A model's tools sit below it, possibly to either side: vertical handles regardless of x.
  // (A block agent's tool-call block sits in the row and keeps the left-to-right handles.)
  if (source.kind === "llm" && target.kind === "tool" && target.y > source.y) {
    return { sourceHandle: "b-out", targetHandle: "t-in" };
  }
  if (source.kind === "tool" && target.kind === "llm" && source.y > target.y) {
    return { sourceHandle: "t-out", targetHandle: "b-in" };
  }
  if (back) return { sourceHandle: "b-out", targetHandle: "b-in" }; // loop drawn below
  return { sourceHandle: "r", targetHandle: "l" };
}

export function GraphView({
  graph,
  active,
  visited,
  taken,
  selected = null,
  onNodeClick,
}: {
  graph: Graph;
  active: Set<string>;
  visited: Set<string>;
  taken: Set<string>;
  selected?: string | null;
  /** Node clicks (and clicks on empty space, as null) when the graph is a builder's. */
  onNodeClick?: (nodeId: string | null) => void;
}) {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const nodes: Node<LabNodeData>[] = graph.nodes.map((n) => ({
    id: n.id,
    type: "lab",
    position: { x: n.x, y: n.y },
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    measured: { width: NODE_WIDTH, height: NODE_HEIGHT },
    data: {
      label: n.label,
      kind: n.kind,
      state: active.has(n.id) ? "active" : visited.has(n.id) ? "visited" : "idle",
      selected: n.id === selected,
      onSelect: onNodeClick && (() => onNodeClick(n.id)),
    },
  }));
  const edges: Edge[] = graph.edges.map((e) => {
    const isTaken = taken.has(edgeKey(e.source, e.target));
    const color = isTaken ? "var(--color-llm)" : "var(--color-rule)";
    return {
      id: edgeKey(e.source, e.target),
      source: e.source,
      target: e.target,
      ...handlesFor(byId.get(e.source)!, byId.get(e.target)!, isBackEdge(graph, e)),
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
      onNodeClick={onNodeClick && ((_, node) => onNodeClick(node.id))}
      onPaneClick={onNodeClick && (() => onNodeClick(null))}
      aria-label="Agent graph"
    />
  );
}
