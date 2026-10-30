"use client";

import type { Span, SpanKind } from "@/lib/api";
import { durationMs, spanRows } from "@/lib/run-state";
import { useNow } from "@/lib/use-now";

const KIND_BAR: Partial<Record<SpanKind, string>> = {
  llm: "bg-llm",
  tool: "bg-tool",
};

export function Waterfall({
  spans,
  selected,
  onSelect,
}: {
  spans: Record<string, Span>;
  selected: string | null;
  onSelect: (spanId: string) => void;
}) {
  const rows = spanRows(spans);
  const running = rows.some((r) => r.span.ended_at == null);
  const tick = useNow(running);
  if (rows.length === 0) {
    return <p className="p-4 text-sm text-muted">Spans appear here as the agent works.</p>;
  }
  const t0 = Math.min(...rows.map((r) => r.span.started_at));
  const latest = Math.max(...rows.map((r) => r.span.ended_at ?? r.span.started_at));
  const now = running ? Math.max(tick, latest) : latest;
  const total = Math.max(now - t0, 0.001);

  return (
    <ol className="divide-y divide-rule/60" aria-label="Span waterfall">
      {rows.map(({ span, depth }) => {
        const end = span.ended_at ?? now;
        const left = ((span.started_at - t0) / total) * 100;
        const width = Math.max(((end - span.started_at) / total) * 100, 0.6);
        const bar = span.error
          ? "bg-fault"
          : span.ended_at == null
            ? "bg-signal lab-running"
            : (KIND_BAR[span.kind] ?? "bg-step");
        return (
          <li key={span.span_id}>
            <button
              type="button"
              onClick={() => onSelect(span.span_id)}
              aria-pressed={selected === span.span_id}
              className={`grid w-full grid-cols-[minmax(10rem,2fr)_3fr_4.5rem] items-center gap-3 px-3 py-1.5 text-left text-sm hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm ${
                selected === span.span_id ? "bg-paper" : ""
              }`}
            >
              <span className="truncate" style={{ paddingLeft: `${depth * 0.9}rem` }}>
                {span.name}
              </span>
              <span className="relative h-3 rounded-sm bg-rule/40">
                <span
                  className={`absolute inset-y-0 rounded-sm ${bar}`}
                  style={{ left: `${left}%`, width: `${width}%` }}
                />
              </span>
              <span className="text-right tabular-nums text-muted">
                {durationMs(span, now)} ms
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
