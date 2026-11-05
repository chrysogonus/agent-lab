"use client";

import { useState } from "react";
import { answerApproval, type OpenApproval } from "@/lib/api";
import { FIELD } from "./builder/fields";

const BUTTON =
  "rounded-md border border-rule px-2.5 py-1 text-sm font-semibold text-ink hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm disabled:opacity-40";

/** One paused tool call: the owner lets it go out, or denies it with an optional reason. */
export function ApprovalCard({
  approval,
  onAnswered,
}: {
  approval: OpenApproval;
  onAnswered: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const answer = async (decision: "approve" | "deny") => {
    setBusy(true);
    try {
      await answerApproval(approval.approval_id, decision, decision === "deny" && reason ? reason : null);
      onAnswered();
    } catch {
      setError("This request is no longer open.");
      onAnswered();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      role="group"
      aria-label={`Approve the call to ${approval.tool}`}
      className="flex flex-col gap-2 border-t border-rule px-4 py-3"
    >
      <p className="text-sm text-ink">
        This run wants to call <code className="font-semibold">{approval.tool}</code>. It waits for you
        until {new Date(approval.expires_at * 1000).toLocaleTimeString()}, then it is denied.
      </p>
      <pre className="max-h-40 overflow-auto rounded-md bg-paper p-2 font-mono text-xs whitespace-pre-wrap break-words text-ink">
        {JSON.stringify(approval.arguments, null, 2)}
      </pre>
      <label className="flex flex-col gap-1 text-sm font-medium text-ink">
        Why not (optional, the model reads it)
        <input
          value={reason}
          maxLength={500}
          onChange={(e) => setReason(e.target.value)}
          className={FIELD}
        />
      </label>
      {error && (
        <p role="alert" className="text-sm text-fault">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <button type="button" disabled={busy} className={BUTTON} onClick={() => void answer("approve")}>
          Approve
        </button>
        <button type="button" disabled={busy} className={BUTTON} onClick={() => void answer("deny")}>
          Deny
        </button>
      </div>
    </div>
  );
}
