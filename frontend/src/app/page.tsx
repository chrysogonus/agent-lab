"use client";

import { useCallback, useEffect, useState } from "react";
import { AgentPicker } from "@/components/AgentPicker";
import { GraphView } from "@/components/GraphView";
import { PromptForm } from "@/components/PromptForm";
import { RunList } from "@/components/RunList";
import { RunViewer } from "@/components/RunViewer";
import { listAgents, listRuns, type AgentInfo, type Run } from "@/lib/api";
import { agentPreview } from "@/lib/run-state";

const NOTHING = new Set<string>();

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [current, setCurrent] = useState<Run | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [agentId, setAgentId] = useState("react");

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
  }, []);

  const preview = agentPreview(agents, agentId);

  const select = (id: string) => {
    setAgentId(id);
    setCurrent(null); // show the picked agent's preview instead of the open run
  };

  const started = (run: Run) => {
    setCurrent(run);
    setRuns((r) => [run, ...r]);
  };

  return (
    <div className="flex min-h-dvh flex-col gap-4 p-4 lg:h-dvh">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:gap-6">
        <h1 className="pt-2 text-xl font-semibold tracking-tight text-ink">Agent Lab</h1>
        <div className="flex flex-1 flex-col gap-2">
          <AgentPicker agents={agents} selected={agentId} onSelect={select} />
          <PromptForm
            key={preview ? agentId : "loading"}
            agentId={agentId}
            samplePrompt={preview?.sample_prompt ?? ""}
            onStarted={started}
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
            <RunList runs={runs} agents={agents} current={current?.run_id ?? null} onOpen={setCurrent} />
          )}
        </nav>
        <main className="flex min-h-0 min-w-0 flex-1">
          {current ? (
            <RunViewer key={current.run_id} initial={current} onEnded={refresh} />
          ) : preview ? (
            <section
              className="flex h-96 min-w-0 flex-1 flex-col rounded-lg border border-rule bg-panel"
              aria-label="Selected agent"
            >
              <div className="border-b border-rule px-4 py-3">
                <h2 className="text-base font-semibold text-ink">{preview.name}</h2>
                <p className="text-sm text-muted">{preview.description}</p>
              </div>
              <div className="min-h-0 flex-1">
                <GraphView graph={preview.graph} active={NOTHING} visited={NOTHING} taken={NOTHING} />
              </div>
            </section>
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
