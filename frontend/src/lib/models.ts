// Model labels and the model select's options. Pure; see specs/004-model-providers.
import type { ModelInfo, ModelRef, Run } from "./api";

const PROVIDER_LABELS: Record<ModelRef["provider"], string> = {
  local: "Local",
  openai: "OpenAI",
  anthropic: "Anthropic",
};

export function sameRef(a: ModelRef | null, b: ModelRef | null): boolean {
  return a?.provider === b?.provider && a?.model === b?.model;
}

/** "OpenAI · gpt-6-luna". */
export function modelLabel(ref: ModelRef): string {
  return `${PROVIDER_LABELS[ref.provider] ?? ref.provider} · ${ref.model}`;
}

/** "Default (Local · qwen3.5-9b)": what an agent without a pinned model runs on. */
export function defaultLabel(models: ModelInfo[]): string {
  const model = models.find((m) => m.default);
  return model ? `Default (${modelLabel(model)})` : "Default";
}

/** Select values: "" is Default, anything else "provider/model" (ids may contain "/"). */
export function refValue(ref: ModelRef | null): string {
  return ref ? `${ref.provider}/${ref.model}` : "";
}

export function refFromValue(value: string): ModelRef | null {
  if (!value) return null;
  const slash = value.indexOf("/");
  return { provider: value.slice(0, slash) as ModelRef["provider"], model: value.slice(slash + 1) };
}

export type ModelOption = { value: string; label: string; disabled: boolean };
export type ModelGroup = { label: string; options: ModelOption[] };

/** Default first, then one group per provider; a pinned model that is gone stays visible. */
export function modelOptions(
  models: ModelInfo[],
  current: ModelRef | null,
): { default: ModelOption; groups: ModelGroup[] } {
  const groups: ModelGroup[] = [];
  const add = (ref: ModelRef, option: Omit<ModelOption, "value">) => {
    const label = PROVIDER_LABELS[ref.provider] ?? ref.provider;
    let group = groups.find((g) => g.label === label);
    if (!group) groups.push((group = { label, options: [] }));
    group.options.push({ value: refValue(ref), ...option });
  };
  for (const m of models) {
    const notes = [m.external && "external", m.unavailable_reason].filter(Boolean);
    const label = notes.length ? `${m.model} (${notes.join(", ")})` : m.model;
    add(m, { label, disabled: !m.available });
  }
  if (current && !models.some((m) => sameRef(m, current))) {
    add(current, { label: `${current.model} (not configured)`, disabled: true });
  }
  return { default: { value: "", label: defaultLabel(models), disabled: false }, groups };
}

/** The model a run used, from its stored config (no provider: Local, as in every M1–M3 run). */
export function runModel(run: Run): string | null {
  const { model, provider } = run.config;
  if (typeof model !== "string") return null;
  return modelLabel({ provider: (provider as ModelRef["provider"] | undefined) ?? "local", model });
}
