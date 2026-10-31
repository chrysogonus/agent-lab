import type { ModelInfo, ToolInfo } from "@/lib/api";
import type { Path, Section } from "@/lib/builder";
import { ModelSelect, NumberField, TextField, Toggle, type Form } from "./fields";
import { ItemList, ToolPicker } from "./ItemList";

// The limits each template lets the owner change; the server checks the allowed range.
const LIMITS: Record<string, [Path, string][]> = {
  react: [[["config", "max_iterations"], "Max iterations"]],
  orchestrator: [[["config", "max_subtasks"], "Max subtasks"]],
  evaluator: [[["config", "max_rounds"], "Max rounds"]],
};

export function AgentSettings({
  form,
  tools,
  models,
  onOpen,
}: {
  form: Form;
  tools: ToolInfo[];
  models: ModelInfo[];
  onOpen: (section: Section) => void;
}) {
  const { templateId } = form.draft;
  return (
    <div className="flex flex-col gap-4">
      <TextField form={form} path={["name"]} label="Name" />
      <TextField form={form} path={["description"]} label="Description" />
      <TextField form={form} path={["sample_prompt"]} label="Sample prompt" multiline />
      <ModelSelect form={form} models={models} />
      <Toggle
        form={form}
        path={["config", "reasoning"]}
        label="Model thinking"
        hint="Slower, and the reasoning shows up in the spans."
      />
      {templateId === "react" && <ToolPicker form={form} tools={tools} />}
      {templateId === "chain" && <ItemList form={form} kind="steps" onOpen={onOpen} />}
      {templateId === "routing" && <ItemList form={form} kind="routes" onOpen={onOpen} />}
      {templateId === "parallel" && <ItemList form={form} kind="aspects" onOpen={onOpen} />}
      {templateId === "chain" && (
        <>
          <Toggle form={form} path={["config", "gate"]} label="Check the first step's output" hint="A code gate: the chain stops unless that output has enough bullet lines." />
          <NumberField form={form} path={["config", "gate_min_bullets"]} label="Minimum bullet lines" />
        </>
      )}
      {(LIMITS[templateId] ?? []).map(([path, label]) => (
        <NumberField key={label} form={form} path={path} label={label} />
      ))}
      {templateId === "parallel" && (
        <TextField
          form={form}
          path={["config", "review_prompt"]}
          label="Review prompt (every aspect)"
          multiline
          mono
          hint="{aspect} and {focus} are filled in per aspect."
        />
      )}
      {templateId === "chain" && (
        <TextField
          form={form}
          path={["config", "input_label"]}
          label="Input label"
          hint="How steps that include the original input name it."
        />
      )}
    </div>
  );
}
