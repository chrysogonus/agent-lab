import type { ToolInfo } from "@/lib/api";
import {
  addItem,
  canRemove,
  moveItem,
  removeItem,
  toggleTool,
  type ListKind,
  type Section,
} from "@/lib/builder";
import type { Form } from "./fields";
import { ToolCheckboxes } from "./ToolChoices";

const LISTS: Record<ListKind, { title: string; add: string; open: (index: number) => Section }> = {
  steps: { title: "Steps, in order", add: "Add step", open: (index) => ({ kind: "step", index }) },
  routes: { title: "Routes", add: "Add route", open: (index) => ({ kind: "route", index }) },
  aspects: {
    title: "Aspects, reviewed at the same time",
    add: "Add aspect",
    open: (index) => ({ kind: "aspect", index }),
  },
};

const SMALL =
  "rounded px-1.5 py-0.5 text-sm text-muted hover:bg-paper hover:text-ink focus-visible:outline-2 focus-visible:outline-llm disabled:opacity-30 disabled:hover:bg-transparent";

/** The items of a list-shaped template (chain steps, routes, aspects): open, add, remove, move. */
export function ItemList({
  form,
  kind,
  onOpen,
}: {
  form: Form;
  kind: ListKind;
  onOpen: (section: Section) => void;
}) {
  const { title, add, open } = LISTS[kind];
  const config = form.draft.config;
  const names =
    kind === "aspects"
      ? Object.keys(config.aspects as Record<string, string>)
      : (config[kind] as { name: string }[]).map((i) => i.name);
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1 text-sm font-medium text-ink">{title}</legend>
      <ol className="flex flex-col divide-y divide-rule/60 rounded-md border border-rule">
        {names.map((name, index) => (
          <li key={`${index}:${name}`} className="flex items-center gap-1 px-2 py-1">
            <button
              type="button"
              onClick={() => onOpen(open(index))}
              className="min-w-0 flex-1 truncate rounded px-1 py-0.5 text-left text-sm text-llm hover:underline focus-visible:outline-2 focus-visible:outline-llm"
            >
              {name || "(no name)"}
            </button>
            {kind === "routes" && (
              <label className="flex items-center gap-1 text-sm text-muted">
                <input
                  type="radio"
                  name="fallback"
                  checked={config.fallback === name}
                  disabled={form.readOnly}
                  onChange={() => form.set(["config", "fallback"], name)}
                  className="accent-llm"
                />
                fallback
              </label>
            )}
            {!form.readOnly && kind === "steps" && (
              <>
                <button
                  type="button"
                  aria-label={`Move ${name} up`}
                  disabled={index === 0}
                  onClick={() => form.update((d) => moveItem(d, index, -1))}
                  className={SMALL}
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={`Move ${name} down`}
                  disabled={index === names.length - 1}
                  onClick={() => form.update((d) => moveItem(d, index, 1))}
                  className={SMALL}
                >
                  ↓
                </button>
              </>
            )}
            {!form.readOnly && (
              <button
                type="button"
                aria-label={`Remove ${name}`}
                disabled={!canRemove(form.draft, kind, index)}
                title={
                  kind === "routes" && config.fallback === name
                    ? "Pick another fallback first"
                    : undefined
                }
                onClick={() => form.update((d) => removeItem(d, kind, index))}
                className={SMALL}
              >
                Remove
              </button>
            )}
          </li>
        ))}
      </ol>
      {!form.readOnly && (
        <button
          type="button"
          onClick={() => form.update((d) => addItem(d, kind))}
          className="self-start rounded-md px-2 py-1 text-sm font-semibold text-llm hover:bg-paper focus-visible:outline-2 focus-visible:outline-llm"
        >
          {add}
        </button>
      )}
    </fieldset>
  );
}

/** Which tools the ReAct agent may call. */
export function ToolPicker({ form, tools }: { form: Form; tools: ToolInfo[] }) {
  const chosen = form.draft.config.tools as string[];
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1 text-sm font-medium text-ink">Tools it may call</legend>
      <ToolCheckboxes
        tools={tools}
        chosen={chosen}
        disabled={form.readOnly}
        onToggle={(name) => form.update((d) => toggleTool(d, name))}
      />
    </fieldset>
  );
}
