"use client";

import { useCallback, useEffect, useState } from "react";
import { AgentBuilder } from "@/components/AgentBuilder";
import { VillageView } from "@/components/village/VillageView";
import { AgentPicker } from "@/components/AgentPicker";
import { PromptForm } from "@/components/PromptForm";
import { RunList } from "@/components/RunList";
import { RunViewer } from "@/components/RunViewer";
import {
  createAgent,
  deleteAgent,
  listAgents,
  listRuns,
  blocksFrom,
  listModels,
  newBlockAgent,
  listTools,
  startRun,
  updateAgent,
  ValidationError,
  type AgentInfo,
  type Run,
  type ModelInfo,
  type ToolInfo,
} from "@/lib/api";
import { copyName, draftFields, draftFrom, draftFromAgent, fieldErrors, type Draft } from "@/lib/builder";
import { agentPreview } from "@/lib/run-state";

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [current, setCurrent] = useState<Run | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [agentId, setAgentId] = useState("react");
  // The custom agent being edited (or a fresh copy of a template); null shows the agent read-only.
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  // Bumped when an agent is picked: the prompt box then shows that agent's sample prompt.
  const [picks, setPicks] = useState(0);
  const [view, setView] = useState<"agents" | "village">("agents");

  const refresh = useCallback(() => {
    listRuns()
      .then((r) => {
        setRuns(r);
        setListError(null);
      })
      .catch(() => setListError("Past runs are unavailable until the backend is running."));
  }, []);

  useEffect(refresh, [refresh]);
  useEffect(() => {
    // Without the backend there is nothing to pick; refresh() already reports that.
    listAgents().then(setAgents, () => {});
    listTools().then(setTools, () => {});
    listModels().then(setModels, () => {});
  }, []);
  useEffect(() => {
    if (!draft?.dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [draft?.dirty]);

  const preview = agentPreview(agents, agentId);
  // An unsaved block agent (new, or opened from a template) has no listed agent to show.
  const [blockSource, setBlockSource] = useState<AgentInfo | null>(null);
  const builderAgent = blockSource ?? preview;

  /** Asks before unsaved builder changes are thrown away; true when it is fine to go on. */
  const mayLeave = () =>
    !draft?.dirty || window.confirm(`Discard the unsaved changes to "${draft.name}"?`);

  const edit = (agent: AgentInfo | null) => {
    setDraft(agent?.kind === "custom" ? draftFromAgent(agent) : null);
    setSaveErrors({});
    setBlockSource(null);
  };

  /** Opens an unsaved block agent from the server: a new one, or a block copy of `fromId`. */
  const openBlocks = async (fromId: string | null) => {
    if (!mayLeave()) return;
    try {
      const source = fromId ? await blocksFrom(fromId) : await newBlockAgent();
      setCurrent(null);
      setSaveErrors({});
      setBlockSource(source);
      const names = agents.map((a) => a.name);
      const name = names.includes(source.name) ? copyName(source.name, names) : source.name;
      setDraft(fromId ? draftFrom(source, agents) : { ...draftFromAgent(source), agentId: null, dirty: true, name });
      setPicks((n) => n + 1);
    } catch (e) {
      setSaveErrors({
        "": e instanceof ValidationError ? e.message : "Can't reach the backend to open a block agent.",
      });
    }
  };

  const select = (id: string) => {
    if (id === agentId && !current && !blockSource) return;
    if (!mayLeave()) return;
    setAgentId(id);
    setPicks((n) => n + 1);
    setCurrent(null); // show the picked agent instead of the open run
    edit(agentPreview(agents, id));
  };

  const open = (run: Run) => {
    if (!mayLeave()) return;
    if (draft?.dirty) edit(preview); // the changes were discarded
    setCurrent(run);
  };

  const editAgain = (id: string) => {
    setCurrent(null);
    if (id !== agentId) {
      setAgentId(id);
      setPicks((n) => n + 1);
      edit(agentPreview(agents, id));
    }
  };

  /** Saves the draft; the saved agent, or null when the server rejected it. */
  const save = async (): Promise<AgentInfo | null> => (draft ? saveDraft(draft) : null);

  const saveDraft = async (draft: Draft): Promise<AgentInfo | null> => {
    setSaving(true);
    try {
      const saved = draft.agentId
        ? await updateAgent(draft.agentId, draftFields(draft))
        : await createAgent(draft.templateId, draftFields(draft));
      setAgents(await listAgents());
      setAgentId(saved.id);
      setDraft(draftFromAgent(saved));
      setSaveErrors({});
      setBlockSource(null); // now a listed agent
      return saved;
    } catch (e) {
      setSaveErrors(
        e instanceof ValidationError
          ? fieldErrors(e.detail)
          : { "": e instanceof TypeError ? "Can't reach the backend to save." : String(e) },
      );
      return null;
    } finally {
      setSaving(false);
    }
  };

  const duplicate = async () => {
    if (!preview || !mayLeave()) return;
    const copy = draftFrom(preview, agents); // the saved agent, not unsaved edits
    setDraft(copy);
    await saveDraft(copy);
  };

  const remove = async () => {
    if (!preview || !window.confirm(`Delete "${preview.name}"? Its past runs stay listed.`)) return;
    try {
      await deleteAgent(preview.id);
    } catch {
      setSaveErrors({ "": "Can't reach the backend to delete." });
      return;
    }
    setAgents(await listAgents());
    setAgentId(preview.template_id); // its template is the closest thing left
    setPicks((n) => n + 1);
    edit(null);
  };

  const run = async (prompt: string) => {
    let id = agentId;
    if (draft?.dirty) {
      const saved = await save();
      if (!saved) return; // the builder shows what to fix
      id = saved.id;
    }
    const started = await startRun(prompt, id);
    setCurrent(started);
    setRuns((r) => [started, ...r]);
  };

  const runAgent = current && agentPreview(agents, current.agent_id);

  const switchTo = (next: "agents" | "village") => {
    if (next === view || (next === "village" && !mayLeave())) return;
    if (next === "village") edit(preview); // unsaved builder changes were discarded
    setView(next);
    if (next === "agents") listAgents().then(setAgents, () => {}); // villager agents may be new
  };

  /** "Edit its agent" in the village: open that villager's block agent in the builder. */
  const editVillagerAgent = (id: string) => {
    listAgents().then((list) => {
      setAgents(list);
      setView("agents");
      setCurrent(null);
      setAgentId(id);
      setPicks((n) => n + 1);
      edit(agentPreview(list, id));
    }, () => {});
  };

  const viewSwitch = (
    <nav aria-label="View" className="flex shrink-0 gap-1 rounded-full border border-rule bg-panel p-0.5 sm:mt-1.5">
      {(["agents", "village"] as const).map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={view === v}
          onClick={() => switchTo(v)}
          className={`rounded-full px-3 py-1 text-sm focus-visible:outline-2 focus-visible:outline-llm ${
            view === v ? "bg-ink text-panel" : "text-ink hover:bg-paper"
          }`}
        >
          {v === "agents" ? "Agents" : "Village"}
        </button>
      ))}
    </nav>
  );

  if (view === "village") {
    return (
      <div className="flex min-h-dvh flex-col gap-4 p-4 lg:h-dvh">
        <header className="flex items-start gap-6">
          <h1 className="pt-2 text-xl font-semibold tracking-tight text-ink">Agent Lab</h1>
          {viewSwitch}
        </header>
        <VillageView onEditAgent={editVillagerAgent} />
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh flex-col gap-4 p-4 lg:h-dvh">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:gap-6">
        <h1 className="pt-2 text-xl font-semibold tracking-tight text-ink">Agent Lab</h1>
        {viewSwitch}
        <div className="flex flex-1 flex-col gap-2">
          <AgentPicker
            agents={agents}
            selected={blockSource ? "" : agentId}
            onSelect={select}
            onNewBlockAgent={() => void openBlocks(null)}
          />
          <PromptForm
            key={preview ? picks : "loading"}
            samplePrompt={draft?.sample_prompt ?? preview?.sample_prompt ?? ""}
            onRun={run}
          />
        </div>
      </header>
      <div className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row">
        <nav
          className="max-h-60 shrink-0 overflow-auto rounded-lg border border-rule bg-panel lg:max-h-none lg:w-64"
          aria-label="Past runs"
        >
          <h2 className="border-b border-rule px-3 py-2 text-sm font-semibold text-ink">Past runs</h2>
          {listError ? (
            <p className="p-3 text-sm text-muted">{listError}</p>
          ) : (
            <RunList runs={runs} agents={agents} current={current?.run_id ?? null} onOpen={open} />
          )}
        </nav>
        <main className="flex min-h-0 min-w-0 flex-1">
          {current ? (
            <RunViewer
              key={current.run_id}
              initial={current}
              onEnded={refresh}
              onEdit={
                runAgent?.kind === "custom" ? () => editAgain(runAgent.id) : undefined
              }
            />
          ) : builderAgent ? (
            <AgentBuilder
              key={`${builderAgent.id}:${draft?.agentId ?? (draft ? "new" : "view")}:${blockSource ? "blocks" : ""}`}
              agent={builderAgent}
              draft={draft}
              tools={tools}
              models={models}
              saveErrors={saveErrors}
              busy={saving}
              onChange={(d) => {
                setDraft(d);
                setSaveErrors({});
              }}
              onCustomize={() => setDraft(draftFrom(builderAgent, agents))}
              onSave={() => void save()}
              onDiscard={() => edit(preview)}
              onDuplicate={() => void duplicate()}
              onDelete={() => void remove()}
              onOpenAsBlocks={
                !blockSource && builderAgent.template_id !== "blocks"
                  ? () => void openBlocks(builderAgent.id)
                  : undefined
              }
            />
          ) : (
            <p className="text-sm text-muted">
              Pick an agent and run it, or open a past run to replay it.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
