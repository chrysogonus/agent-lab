"use client";

import { useEffect, useState } from "react";
import { previewGraph, ValidationError, type AgentConfig, type Graph } from "./api";
import { fieldErrors } from "./builder";

/** The server's graph for an unsaved config, 300 ms after the last edit, plus its field errors. */
export function useGraphPreview(templateId: string, config: AgentConfig | null) {
  const [graph, setGraph] = useState<Graph | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (config == null) return;
    let current = true;
    const timer = setTimeout(() => {
      previewGraph(templateId, config).then(
        (g) => {
          if (!current) return;
          setGraph(g);
          setErrors({});
        },
        (e) => {
          // Keep the last valid graph; only field errors are worth showing next to inputs.
          if (current && e instanceof ValidationError) setErrors(fieldErrors(e.detail));
        },
      );
    }, 300);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [templateId, config]);
  return { graph: config == null ? null : graph, errors: config == null ? {} : errors };
}
