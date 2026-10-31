# Quickstart / validation: M4

Prerequisites: as M3 (`make dev-llm`, `make dev`). For the OpenAI part, add to `.env`:

```bash
OPENAI_API_KEY=sk-...        # never committed; redacted from every span
OPENAI_MODELS=gpt-6-luna     # whatever ids your account offers
# OPENAI_REASONING_OFF=none  # empty it if a model rejects reasoning_effort
```

Then restart the backend (`.env` is read at startup only).

## Automated

```bash
make check
```

Expected: all gates pass, with no real provider called. Notable tests: per-provider request
bodies recorded with a mock transport (thinking off, strict schema rewrite, tools, no foreign
parameters; SC-003); local requests and the golden template file unchanged (FR-009); model
selection, "Default" resolution and validation on save and run start; the 401/429/500/timeout/
connection-refused runs end `error` (SC-004); no key in any span, run, stream event or API
response (SC-005); model labels and options in vitest.

## Manual

1. Without `OPENAI_API_KEY` but with `OPENAI_MODELS` set: open a custom agent; the model list
   shows "Default (Local · qwen3.5-9b)", the local models, and the OpenAI models disabled with
   "no API key" (US3-1).
2. Old agents: every agent saved in M3 shows "Default"; running one gives the same
   `config_version` as its last M3 run (FR-004, FR-006).
3. With the key: pick the OpenAI model in a custom routing agent, save, run the sample prompt.
   The run header, the model spans and the past-runs entry show `OpenAI · gpt-6-luna`; switching
   from Local to OpenAI and starting takes under 30 s (US1-1–3, SC-001).
4. Customize each of the six templates, pin the OpenAI model and run the sample prompt: each
   completes (SC-002). If a model rejects `reasoning_effort`, the span shows OpenAI's message;
   adjust `OPENAI_REASONING_OFF` and record the value that works.
5. Compare a Local and an OpenAI run of the same agent in the past-runs list: model, calls,
   tokens and wall time are visible without opening either; their `config_version`s differ
   (US1-3, SC-006).
6. Set a wrong key and run: the model span shows the 401 message, the run ends `error`, the next
   run starts normally; the key appears nowhere in the span or the stored run (US3-3, US3-4).
7. Remove the model from `OPENAI_MODELS`, restart, open the pinned agent: the model shows
   "not configured"; Run is rejected with a message naming the model (US3-2).
8. Set `DEFAULT_MODEL=openai/gpt-6-luna` without a key: the backend refuses to start and names
   `DEFAULT_MODEL` (edge case).
