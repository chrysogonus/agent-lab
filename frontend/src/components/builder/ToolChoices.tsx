import type { ToolInfo } from "@/lib/api";
import { groupTools, unavailableTools } from "@/lib/tools";

const UNAVAILABLE = "unavailable";

/** Checkboxes for tools, under a heading per server; a chosen tool no server offers stays listed. */
export function ToolCheckboxes({
  tools,
  chosen,
  disabled,
  onToggle,
}: {
  tools: ToolInfo[];
  chosen: string[];
  disabled: boolean;
  onToggle: (name: string) => void;
}) {
  const missing = unavailableTools(chosen, tools).map((name) => ({ name, server: UNAVAILABLE, description: "", parameters: {} }));
  return groupTools([...tools, ...missing]).map((group) => (
    <div key={group.server} className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold tracking-wide text-muted uppercase">
        {group.server === UNAVAILABLE ? "not connected" : group.server}
      </span>
      {group.tools.map((tool) => (
        <label key={tool.name} className="flex items-start gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={chosen.includes(tool.name)}
            disabled={disabled}
            onChange={() => onToggle(tool.name)}
            className="mt-0.5 size-4 accent-llm"
          />
          <span>
            {tool.name}
            {group.server === UNAVAILABLE ? (
              <span className="block text-fault">(unavailable): its server is not connected</span>
            ) : (
              <span className="block text-muted">{tool.description}</span>
            )}
          </span>
        </label>
      ))}
    </div>
  ));
}

/** `<option>`s for a tool select: an `<optgroup>` per server, and the chosen tool if unavailable. */
export function ToolOptions({ tools, value }: { tools: ToolInfo[]; value: string | null }) {
  const missing = value ? unavailableTools([value], tools) : [];
  return (
    <>
      {groupTools(tools).map((group) => (
        <optgroup key={group.server} label={group.server}>
          {group.tools.map((tool) => (
            <option key={tool.name} value={tool.name}>
              {tool.name}
            </option>
          ))}
        </optgroup>
      ))}
      {missing.map((name) => (
        <option key={name} value={name}>
          {name} (unavailable)
        </option>
      ))}
    </>
  );
}
