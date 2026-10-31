import type { ToolInfo } from "@/lib/api";
import { getField, pathKey, type Section } from "@/lib/builder";
import { NumberField, TextField, Toggle, type Form } from "./fields";

function ToolSelect({ form, index, tools }: { form: Form; index: number; tools: ToolInfo[] }) {
  const path = ["config", "routes", index, "tool"];
  const id = `field-${pathKey(path)}`;
  const value = getField(form.draft, path);
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        Tool
      </label>
      <select
        id={id}
        value={typeof value === "string" ? value : ""}
        disabled={form.readOnly}
        onChange={(e) => form.set(path, e.target.value || null)}
        className="rounded-md border border-rule bg-panel px-2.5 py-1.5 text-sm text-ink focus-visible:outline-2 focus-visible:outline-llm disabled:bg-paper"
      >
        <option value="">No tool: answer in one call</option>
        {tools.map((t) => (
          <option key={t.name} value={t.name}>
            {t.name}
          </option>
        ))}
      </select>
    </div>
  );
}

// What the code adds to a prompt before the model reads it.
const PROMPT_HINTS: Record<string, string> = {
  router_prompt: "Each route's name and description are added after this, the fallback last.",
  orchestrator_prompt: "{min_subtasks} and {max_subtasks} are filled in from the subtask limit.",
};

/** The settings of the clicked node; structural edits (add, remove, move) live in the lists. */
export function NodeSettings({
  form,
  section,
  tools,
}: {
  form: Form;
  section: Exclude<Section, { kind: "agent" }>;
  tools: ToolInfo[];
}) {
  switch (section.kind) {
    case "prompt":
      return (
        <TextField
          form={form}
          path={section.path}
          label="Prompt"
          multiline
          mono
          hint={PROMPT_HINTS[String(section.path[section.path.length - 1])]}
        />
      );
    case "step": {
      const at = ["config", "steps", section.index];
      return (
        <div className="flex flex-col gap-4">
          <TextField form={form} path={[...at, "name"]} label="Name" hint="Lowercase letters, digits and hyphens." />
          <TextField form={form} path={[...at, "prompt"]} label="Prompt" multiline mono />
          {section.index > 0 && (
            <Toggle
              form={form}
              path={[...at, "include_input"]}
              label="Also give it the original input"
              hint="Otherwise it gets only the previous step's output."
            />
          )}
        </div>
      );
    }
    case "route": {
      const at = ["config", "routes", section.index];
      return (
        <div className="flex flex-col gap-4">
          <TextField form={form} path={[...at, "name"]} label="Name" hint="The label the router answers with." />
          <TextField form={form} path={[...at, "description"]} label="When to use it" hint="The router reads this." />
          <TextField form={form} path={[...at, "prompt"]} label="Handler prompt" multiline mono />
          <ToolSelect form={form} index={section.index} tools={tools} />
        </div>
      );
    }
    case "aspect":
      return (
        <TextField
          form={form}
          path={["config", "aspects", section.name]}
          label={`What the ${section.name} reviewer looks for`}
          multiline
        />
      );
    case "gate":
      return (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted">
            A code check after the first step: the chain stops unless that output has enough bullet lines.
          </p>
          <Toggle form={form} path={["config", "gate"]} label="Check the first step's output" />
          <NumberField form={form} path={["config", "gate_min_bullets"]} label="Minimum bullet lines" />
        </div>
      );
    case "tool": {
      const tool = tools.find((t) => t.name === section.name);
      return <p className="text-sm text-ink">{tool?.description ?? "Unknown tool."}</p>;
    }
  }
}
