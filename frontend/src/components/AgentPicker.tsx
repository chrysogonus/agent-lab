import type { AgentInfo } from "@/lib/api";

function Choice({
  agent,
  selected,
  onSelect,
}: {
  agent: AgentInfo;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <label
      className={`cursor-pointer rounded-full border px-3 py-1 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-llm ${
        selected ? "border-llm bg-llm text-panel" : "border-rule bg-panel text-ink hover:border-llm"
      }`}
    >
      <input
        type="radio"
        name="agent"
        value={agent.id}
        checked={selected}
        onChange={() => onSelect(agent.id)}
        className="sr-only"
      />
      {agent.name}
    </label>
  );
}

export function AgentPicker({
  agents,
  selected,
  onSelect,
}: {
  agents: AgentInfo[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const groups = [
    { title: "Templates", agents: agents.filter((a) => a.kind === "template") },
    { title: "My agents", agents: agents.filter((a) => a.kind === "custom") },
  ].filter((g) => g.agents.length > 0);
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="sr-only">Agent or workflow</legend>
      {groups.map((group) => (
        <div key={group.title} role="group" aria-label={group.title} className="flex flex-wrap items-center gap-2">
          <span className="w-20 shrink-0 text-sm text-muted">
            {group.title}
          </span>
          {group.agents.map((agent) => (
            <Choice key={agent.id} agent={agent} selected={agent.id === selected} onSelect={onSelect} />
          ))}
        </div>
      ))}
    </fieldset>
  );
}
