"use client";

import { useCallback, useState } from "react";
import { PromptForm } from "@/components/PromptForm";
import { RunViewer } from "@/components/RunViewer";
import type { Run } from "@/lib/api";

export default function Home() {
  const [current, setCurrent] = useState<Run | null>(null);
  const onEnded = useCallback(() => {}, []);

  return (
    <div className="flex min-h-dvh flex-col gap-4 p-4 lg:h-dvh">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:gap-6">
        <h1 className="pt-2 text-xl font-semibold tracking-tight text-ink">Agent Lab</h1>
        <PromptForm onStarted={setCurrent} />
      </header>
      <main className="flex min-h-0 flex-1 gap-4">
        {current ? (
          <RunViewer key={current.run_id} initial={current} onEnded={onEnded} />
        ) : (
          <p className="text-sm text-muted">Run the agent to watch each step here.</p>
        )}
      </main>
    </div>
  );
}
