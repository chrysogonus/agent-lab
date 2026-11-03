"use client";

import { useCallback, useEffect, useState } from "react";
import { listServers, reconnectServer, reloadServers, type McpServer, type McpServers } from "@/lib/api";
import { stateLabel } from "@/lib/tools";

const STATE_DOT: Record<McpServer["state"], string> = {
  connecting: "bg-signal",
  connected: "bg-tool",
  failed: "bg-fault",
};

const ACTION =
  "rounded-md border border-rule px-2.5 py-1 text-sm font-semibold text-ink hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm disabled:opacity-40";

const KIND: Record<McpServer["kind"], string> = { internal: "built in", stdio: "local program", http: "address" };

function ServerCard({ server, onReconnect }: { server: McpServer; onReconnect?: () => void }) {
  const about = [
    KIND[server.kind],
    server.protocol_version && `MCP ${server.protocol_version}`,
    server.server_info?.name && `${server.server_info.name} ${server.server_info.version ?? ""}`.trim(),
  ].filter(Boolean);
  return (
    <li className="flex flex-col gap-3 rounded-lg border border-rule bg-panel p-4">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <h2 className="text-lg font-semibold text-ink">{server.name}</h2>
        <span className="flex items-center gap-1.5 pt-1 text-sm text-muted">
          <span className={`size-2 shrink-0 rounded-full ${STATE_DOT[server.state]}`} aria-hidden />
          <span className={server.state === "failed" ? "text-fault" : undefined}>{stateLabel(server)}</span>
        </span>
        {onReconnect && (
          <button type="button" onClick={onReconnect} className={`${ACTION} ml-auto`}>
            Reconnect
          </button>
        )}
      </div>
      <p className="-mt-2 text-sm break-all text-muted">
        <code>{server.target}</code>
        {about.length > 0 && <> · {about.join(" · ")}</>}
        {server.state === "connected" && !server.watching && server.kind !== "internal" && (
          <> · not watched for tool changes (press Reconnect)</>
        )}
      </p>
      {server.state === "connected" &&
        (server.tools.length === 0 ? (
          <p className="text-sm text-muted">No tools.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {server.tools.map((tool) => (
              <li key={tool.name} className="text-sm">
                <code className="font-semibold text-ink">{tool.config_name}</code>
                {tool.description && <span className="text-muted"> — {tool.description}</span>}
                {Object.keys(tool.parameters.properties ?? {}).length > 0 && (
                  <span className="block text-xs text-muted">
                    arguments: {Object.keys(tool.parameters.properties ?? {}).join(", ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        ))}
      {server.log.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted">Last connect ({server.log.length} messages)</summary>
          <ol className="mt-2 flex flex-col gap-1.5">
            {server.log.map((entry, i) => (
              <li key={i}>
                <span className="text-xs font-semibold text-muted">{entry.direction === "out" ? "lab →" : "← server"}</span>
                <pre className="overflow-x-auto rounded bg-paper p-2 text-xs text-ink">
                  {typeof entry.message === "string" ? entry.message : JSON.stringify(entry.message, null, 2)}
                </pre>
              </li>
            ))}
          </ol>
        </details>
      )}
    </li>
  );
}

/** The MCP servers the lab is connected to, their tools and their last connect (FR-005, FR-011). */
export function ToolsView({ onChanged }: { onChanged: () => void }) {
  const [listing, setListing] = useState<McpServers | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    (work: Promise<unknown> = Promise.resolve()) =>
      work
        .then(listServers)
        .then((next) => {
          setListing(next);
          setError(null);
          onChanged(); // the pickers' tools follow the servers
        })
        .catch(() => setError("The servers are unavailable until the backend is running.")),
    [onChanged],
  );

  useEffect(() => {
    load();
  }, [load]);
  const connecting = listing?.servers.some((s) => s.state === "connecting") ?? false;
  useEffect(() => {
    if (!connecting) return;
    const timer = window.setTimeout(load, 1000);
    return () => window.clearTimeout(timer);
  }, [connecting, listing, load]);

  return (
    <section aria-label="Tools" className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="flex-1 text-sm text-muted">
          Servers come from <code className="text-ink">{listing?.file ?? "the servers file"}</code>. Edit it, then reload.
        </p>
        <button type="button" onClick={() => load(reloadServers())} className={ACTION}>
          Reload
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-fault">
          {error}
        </p>
      )}
      {listing?.file_error && (
        <p role="alert" className="rounded-md border border-fault/40 p-3 text-sm text-fault">
          {listing.file_error}
        </p>
      )}
      <ul className="flex flex-col gap-3">
        {listing?.servers.map((server) => (
          <ServerCard
            key={server.name}
            server={server}
            onReconnect={server.kind === "internal" ? undefined : () => load(reconnectServer(server.name))}
          />
        ))}
      </ul>
    </section>
  );
}
