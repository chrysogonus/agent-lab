import type { Span } from "@/lib/api";
import { durationMs } from "@/lib/run-state";

function Payload({ title, value }: { title: string; value: unknown }) {
  if (value == null) return null;
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <section className="mt-4">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      <pre className="mt-1 max-h-80 overflow-auto rounded-md bg-paper p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words text-ink">
        {text}
      </pre>
    </section>
  );
}

export function SpanDetail({ span }: { span: Span | null }) {
  if (!span) {
    return <p className="text-sm text-muted">Select a span to see its input and output.</p>;
  }
  const facts: [string, string][] = [
    ["Kind", span.kind],
    ["Node", span.node_id],
    ["Latency", span.ended_at == null ? "running" : `${durationMs(span, span.ended_at)} ms`],
    ["Provider", String(span.attributes["gen_ai.provider.name"] ?? "–")],
    ["Model", span.model ?? "–"],
    ["Tokens in / out", span.tokens_in == null ? "–" : `${span.tokens_in} / ${span.tokens_out ?? "–"}`],
    ["Config", span.config_version],
  ];
  return (
    <div>
      <h2 className="text-base font-semibold break-words text-ink">{span.name}</h2>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {facts.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted">{label}</dt>
            <dd className="tabular-nums text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      {span.error && (
        <p className="mt-4 rounded-md border border-fault/40 bg-fault/10 p-3 text-sm text-fault">
          {span.error}
        </p>
      )}
      <Payload title="Input" value={span.input} />
      <Payload title="Output" value={span.output} />
    </div>
  );
}
