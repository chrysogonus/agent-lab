"use client";

import { useState } from "react";
import type { AgentInfo, GraphNode, ToolInfo } from "@/lib/api";
import {
  draftFromAgent,
  nodeSettings,
  sectionNode,
  setField,
  type Draft,
  type Path,
  type Section,
} from "@/lib/builder";
import { useGraphPreview } from "@/lib/use-graph-preview";
import { AgentSettings } from "./builder/AgentSettings";
import type { Form } from "./builder/fields";
import { NodeSettings } from "./builder/NodeSettings";
import { GraphView } from "./GraphView";

const NOTHING = new Set<string>();

const KIND_STRIPE: Record<GraphNode["kind"], string> = {
  start: "border-step",
  end: "border-step",
  llm: "border-llm",
  tool: "border-tool",
  code: "border-step",
};

function sectionTitle(section: Section, node: string | null): string {
  switch (section.kind) {
    case "agent":
      return "Agent settings";
    case "prompt":
      return section.title.charAt(0).toUpperCase() + section.title.slice(1);
    case "step":
      return `Step ${section.index + 1}: ${node}`;
    case "route":
      return `Route: ${node}`;
    case "aspect":
      return `Aspect: ${node}`;
    case "gate":
      return "Gate";
    case "tool":
      return `Tool: ${section.name}`;
  }
}

const BUTTON =
  "rounded-md px-3 py-1.5 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-llm disabled:opacity-50";

/**
 * The selected agent's graph and settings. A template is shown read-only until customized;
 * a custom agent (or a fresh copy) is edited as `draft`. Mount with key={agent id}.
 */
export function AgentBuilder({
  agent,
  draft,
  tools,
  saveErrors,
  busy,
  onChange,
  onCustomize,
  onSave,
  onDiscard,
  onDuplicate,
  onDelete,
}: {
  agent: AgentInfo;
  draft: Draft | null;
  tools: ToolInfo[];
  saveErrors: Record<string, string>;
  busy: boolean;
  onChange: (draft: Draft) => void;
  onCustomize: () => void;
  onSave: () => void;
  onDiscard: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const [opened, setSection] = useState<Section>({ kind: "agent" });
  const preview = useGraphPreview(agent.template_id, draft?.config ?? null);
  const shown = draft ?? draftFromAgent(agent);
  // A removed list item leaves its section without a node: show the agent settings instead.
  const section: Section =
    opened.kind !== "agent" && sectionNode(opened, shown.config) == null ? { kind: "agent" } : opened;
  const graph = preview.graph ?? agent.graph;
  const form: Form = {
    draft: shown,
    set: (path: Path, value: unknown) => draft && onChange(setField(draft, path, value)),
    update: (edit) => draft && onChange(edit(draft)),
    readOnly: draft == null,
    errors: { ...preview.errors, ...saveErrors },
  };
  const selected = sectionNode(section, shown.config);
  const kind = graph.nodes.find((n) => n.id === selected)?.kind ?? "start";
  const errors = Object.entries(form.errors);

  return (
    <section
      className="flex min-w-0 flex-1 flex-col rounded-lg border border-rule bg-panel"
      aria-label="Agent builder"
    >
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2 border-b border-rule px-4 py-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold break-words text-ink">{shown.name}</h2>
          <p className="text-sm text-muted">
            {draft == null
              ? `${agent.description} Templates are read-only; customize a copy to change it.`
              : shown.description || "No description."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {draft?.dirty && (
            <span className="text-sm text-signal-ink" role="status">
              {draft.agentId == null ? "Not saved yet" : "Unsaved changes"}
            </span>
          )}
          {draft == null ? (
            <button type="button" onClick={onCustomize} className={`${BUTTON} bg-ink text-panel hover:bg-llm`}>
              Customize
            </button>
          ) : (
            <>
              {draft.dirty && (
                <button type="button" onClick={onDiscard} disabled={busy} className={`${BUTTON} text-ink hover:bg-paper`}>
                  Discard
                </button>
              )}
              {draft.agentId != null && (
                <>
                  <button type="button" onClick={onDuplicate} disabled={busy} className={`${BUTTON} text-ink hover:bg-paper`}>
                    Duplicate
                  </button>
                  <button type="button" onClick={onDelete} disabled={busy} className={`${BUTTON} text-fault hover:bg-fault/10`}>
                    Delete
                  </button>
                </>
              )}
              <button
                type="button"
                onClick={onSave}
                disabled={busy || !draft.dirty}
                className={`${BUTTON} bg-ink text-panel hover:bg-llm`}
              >
                {busy ? "Saving…" : "Save"}
              </button>
            </>
          )}
        </div>
      </div>
      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="h-80 min-w-0 lg:h-auto lg:min-h-96">
          {/* key: React Flow fits the view only on mount, so refit when nodes change */}
          <GraphView
            key={graph.nodes.map((n) => n.id).join()}
            graph={graph}
            active={NOTHING}
            visited={NOTHING}
            taken={NOTHING}
            selected={selected}
            onNodeClick={(node) => setSection(nodeSettings(agent.template_id, shown.config, node))}
          />
        </div>
        <aside
          className={`flex flex-col gap-4 overflow-auto border-t-4 p-4 lg:border-t-0 lg:border-l-4 ${KIND_STRIPE[kind]}`}
          aria-label="Settings"
        >
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold text-ink">{sectionTitle(section, selected)}</h3>
            {section.kind !== "agent" && (
              <button
                type="button"
                onClick={() => setSection({ kind: "agent" })}
                className="text-sm text-llm hover:underline focus-visible:outline-2 focus-visible:outline-llm"
              >
                Agent settings
              </button>
            )}
          </div>
          {section.kind === "agent" ? (
            <AgentSettings form={form} tools={tools} onOpen={setSection} />
          ) : (
            <NodeSettings form={form} section={section} tools={tools} />
          )}
          {section.kind === "agent" && (
            <p className="text-sm text-muted">Click a node in the graph to see its settings.</p>
          )}
          {errors.length > 0 && (
            <div role="alert" className="text-sm text-fault">
              <p>Fix these settings before saving:</p>
              <ul className="mt-1 list-disc pl-5">
                {errors.map(([path, message]) => (
                  <li key={path}>
                    {message} {path && <span className="text-muted">({path})</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
