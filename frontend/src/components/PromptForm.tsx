"use client";

import { useState } from "react";
import { API_URL } from "@/lib/api";

/** Mount with key={agentId} so switching agents resets the prompt to the new sample. */
export function PromptForm({
  samplePrompt,
  onRun,
}: {
  samplePrompt: string;
  /** Starts the run (saving unsaved builder changes first); throws to show an error here. */
  onRun: (prompt: string) => Promise<void>;
}) {
  const [prompt, setPrompt] = useState(samplePrompt);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await onRun(prompt.trim());
    } catch (e) {
      setError(
        e instanceof TypeError
          ? `Can't reach the backend at ${API_URL}. Start it with make dev-backend.`
          : String(e instanceof Error ? e.message : e),
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-start">
      <label htmlFor="prompt" className="sr-only">
        Prompt
      </label>
      <textarea
        id="prompt"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
        }}
        rows={2}
        maxLength={4000}
        className="min-h-12 flex-1 resize-y rounded-md border border-rule bg-panel px-3 py-2 text-sm text-ink focus-visible:outline-2 focus-visible:outline-llm"
      />
      <button
        type="submit"
        disabled={pending || !prompt.trim()}
        className="rounded-md bg-ink px-5 py-2 text-sm font-semibold text-panel hover:bg-llm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-llm disabled:opacity-50"
      >
        {pending ? "Starting…" : "Run"}
      </button>
      {error && (
        <p role="alert" className="text-sm text-fault sm:basis-full">
          {error}
        </p>
      )}
    </form>
  );
}
