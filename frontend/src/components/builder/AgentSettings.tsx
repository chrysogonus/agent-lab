import type { Path } from "@/lib/builder";
import { NumberField, TextField, Toggle, type Form } from "./fields";

// The limits each template lets the owner change; the server checks the allowed range.
const LIMITS: Record<string, [Path, string][]> = {
  react: [[["config", "max_iterations"], "Max iterations"]],
  orchestrator: [[["config", "max_subtasks"], "Max subtasks"]],
  evaluator: [[["config", "max_rounds"], "Max rounds"]],
};

export function AgentSettings({ form }: { form: Form }) {
  const { templateId } = form.draft;
  return (
    <div className="flex flex-col gap-4">
      <TextField form={form} path={["name"]} label="Name" />
      <TextField form={form} path={["description"]} label="Description" />
      <TextField form={form} path={["sample_prompt"]} label="Sample prompt" multiline />
      <Toggle
        form={form}
        path={["config", "reasoning"]}
        label="Model thinking"
        hint="Slower, and the reasoning shows up in the spans."
      />
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
