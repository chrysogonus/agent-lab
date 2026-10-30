import type { AgentInfo } from "@/lib/api";

export function AgentPicker({
  agents,
  selected,
  onSelect,
}: {
  agents: AgentInfo[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  return (
    <fieldset className="flex flex-wrap gap-2">
      <legend className="sr-only">Agent or workflow</legend>
      {agents.map((agent) => (
        <label
          key={agent.id}
          className={`cursor-pointer rounded-full border px-3 py-1 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-llm ${
            agent.id === selected
              ? "border-llm bg-llm text-panel"
              : "border-rule bg-panel text-ink hover:border-llm"
          }`}
        >
          <input
            type="radio"
            name="agent"
            value={agent.id}
            checked={agent.id === selected}
            onChange={() => onSelect(agent.id)}
            className="sr-only"
          />
          {agent.name}
        </label>
      ))}
    </fieldset>
  );
}
