import { describe, expect, it } from "vitest";
import type { ModelInfo, Run } from "./api";
import { defaultLabel, modelLabel, modelOptions, refFromValue, refValue, runModel, sameRef } from "./models";

function info(fields: Partial<ModelInfo>): ModelInfo {
  return {
    provider: "local",
    provider_label: "Local",
    model: "qwen3.5-9b",
    external: false,
    available: true,
    unavailable_reason: null,
    default: false,
    ...fields,
  };
}

const local = info({ default: true });
const luna = info({ provider: "openai", provider_label: "OpenAI", model: "gpt-6-luna", external: true });

describe("labels", () => {
  it("names provider and model", () => {
    expect(modelLabel({ provider: "openai", model: "gpt-6-luna" })).toBe("OpenAI · gpt-6-luna");
    expect(modelLabel({ provider: "anthropic", model: "claude-sonnet-5-5" })).toBe(
      "Anthropic · claude-sonnet-5-5",
    );
    expect(defaultLabel([local, luna])).toBe("Default (Local · qwen3.5-9b)");
  });

  it("round-trips select values, including ids with a slash", () => {
    const ref = { provider: "local" as const, model: "Qwen/Qwen3-8B" };
    expect(refFromValue(refValue(ref))).toEqual(ref);
    expect(refValue(null)).toBe("");
    expect(refFromValue("")).toBeNull();
    expect(sameRef(null, null)).toBe(true);
    expect(sameRef(ref, { ...ref, provider: "openai" })).toBe(false);
  });
});

describe("modelOptions", () => {
  it("puts Default first and groups by provider, marking external models", () => {
    expect(modelOptions([local, luna], null)).toEqual({
      default: { value: "", label: "Default (Local · qwen3.5-9b)", disabled: false },
      groups: [
        { label: "Local", options: [{ value: "local/qwen3.5-9b", label: "qwen3.5-9b", disabled: false }] },
        {
          label: "OpenAI",
          options: [{ value: "openai/gpt-6-luna", label: "gpt-6-luna (external)", disabled: false }],
        },
      ],
    });
  });

  it("shows unavailable models disabled, with the reason", () => {
    const noKey = { ...luna, available: false, unavailable_reason: "no API key" };
    const [, openai] = modelOptions([local, noKey], null).groups;
    expect(openai.options).toEqual([
      { value: "openai/gpt-6-luna", label: "gpt-6-luna (external, no API key)", disabled: true },
    ]);
  });

  it("keeps a pinned model that is no longer configured visible", () => {
    const gone = { provider: "openai" as const, model: "gpt-5" };
    const { groups } = modelOptions([local], gone);
    expect(groups[1]).toEqual({
      label: "OpenAI",
      options: [{ value: "openai/gpt-5", label: "gpt-5 (not configured)", disabled: true }],
    });
  });

  it("lists the same id under each provider", () => {
    const shared = [info({ model: "shared", default: true }), { ...luna, model: "shared" }];
    const values = modelOptions(shared, null).groups.map((g) => g.options[0].value);
    expect(values).toEqual(["local/shared", "openai/shared"]);
  });
});

describe("runModel", () => {
  const run = (config: Record<string, unknown>) => ({ config }) as Run;

  it("reads the stored config; no provider means Local, as in M1–M3 runs", () => {
    expect(runModel(run({ model: "qwen3.5-9b" }))).toBe("Local · qwen3.5-9b");
    expect(runModel(run({ model: "gpt-6-luna", provider: "openai" }))).toBe("OpenAI · gpt-6-luna");
    expect(runModel(run({}))).toBeNull();
  });
});
