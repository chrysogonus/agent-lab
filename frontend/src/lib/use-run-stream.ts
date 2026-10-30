"use client";

import { useEffect, useReducer } from "react";
import { streamUrl } from "./api";
import { applyEvent, emptyView, type RunView } from "./run-state";
import type { StreamEvent } from "./api";

/** Stored spans, then live events, for one run. Mount with `key={runId}` to reset per run. */
export function useRunStream(runId: string): RunView {
  const [view, dispatch] = useReducer(applyEvent, emptyView);
  useEffect(() => {
    const ws = new WebSocket(streamUrl(runId));
    ws.onmessage = (message) => dispatch(JSON.parse(message.data) as StreamEvent);
    ws.onerror = () =>
      dispatch({ type: "error", message: "Lost the connection to the backend stream." });
    return () => {
      // Detach first: closing a still-connecting socket fires onerror, which is not a failure.
      ws.onmessage = null;
      ws.onerror = null;
      ws.close();
    };
  }, [runId]);
  return view;
}
