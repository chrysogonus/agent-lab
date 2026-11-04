# Models

[← README](../README.md)

Glasshouse talks to **Claude** (Anthropic's Messages API) and to any **OpenAI-compatible** chat
endpoint. Both clients are written by hand in `backend/src/agent_lab/llm/`. Settings live in
`.env` (copy `.env.example`); restart the backend after changing them.

```mermaid
flowchart LR
    A[Agent] --> D{its model}
    D -- "Default" --> DM{"DEFAULT_MODEL<br/>(unset: Claude with a key, else local)"}
    DM --> A2["Anthropic<br/>ANTHROPIC_MODELS + ANTHROPIC_API_KEY"]
    DM --> L["Local server<br/>LLM_BASE_URL / LLM_MODEL"]
    DM --> O["OpenAI<br/>OPENAI_MODELS + OPENAI_API_KEY"]
    D -- "picked in agent settings" --> A2
    D -- "picked in agent settings" --> L
    D -- "picked in agent settings" --> O
```

## Pick a model server

| Option | Setup |
|---|---|
| **vLLM in Docker** (default) | `make dev-llm` serves 4-bit Qwen3.5 9B as `qwen3.5-9b` on 127.0.0.1:8001. Needs an NVIDIA GPU with ~11 GiB free and the NVIDIA container runtime; the first start downloads ~11 GB. Logs: `docker logs -f agent-lab-vllm`; remove: `make stop-llm`. |
| **Ollama** | `LLM_BASE_URL=http://localhost:11434/v1` and `LLM_MODEL=qwen3:8b` |
| **Anything else OpenAI-compatible** | set `LLM_BASE_URL`, `LLM_MODEL` and, if needed, `LLM_API_KEY` |

vLLM batches requests that arrive together, so parallel branches really run at the same time.

## Settings

| Variable | Example | What it does |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:8001/v1` | the local OpenAI-compatible endpoint |
| `LLM_MODEL` | `qwen3.5-9b` | its default model |
| `LLM_API_KEY` | *(empty)* | key for that endpoint; empty for local servers |
| `LLM_MODELS` | `qwen3:14b,llama3.3` | further models served by the same endpoint |
| `OPENAI_MODELS` | `gpt-6-luna` | OpenAI models to offer; listed but not pickable without a key |
| `OPENAI_API_KEY` | `sk-…` | enables the OpenAI models |
| `OPENAI_REASONING_OFF` | `none` | `reasoning_effort` sent when an agent's thinking is off; empty sends nothing |
| `ANTHROPIC_API_KEY` | `sk-ant-…` | enables the Claude models, and makes the first one the default |
| `ANTHROPIC_MODELS` | `claude-sonnet-5-5` | Claude models to offer (default: `claude-sonnet-5-5`); listed but not pickable without a key |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com/v1` | the Messages API address |
| `DEFAULT_MODEL` | `anthropic/claude-sonnet-5-5` | the model of templates, "Default" agents and the village (default: the first Claude model with a key, else the local `LLM_MODEL`); the backend refuses to start if it is not configured |
| `AGENT_LAB_DB` | `data/agent_lab.db` | the SQLite file, relative to `backend/` |

## Good to know

- Templates always run on the default model; a custom agent runs on "Default" or the model picked
  in its agent settings. The run header, past runs and span details show which model answered.
- An agent on an OpenAI or Claude model sends its prompts and tool results to that provider.
  The village uses the default model too, so a running village on Claude costs money every turn.
- **On Claude**, the lab sends:
  - adaptive thinking with summaries shown in the trace; with **Model thinking** off, Claude's
    lowest setting (`between_tools`), since Sonnet 5.5 cannot turn thinking off completely;
  - effort `medium` and at most 16,000 output tokens per call;
  - server-side fallback: a request Claude declines for some safety reasons is answered by the
    fallback model, and the span's model shows which one answered. Any other decline ends the
    run with an error;
  - Claude's thinking blocks back unchanged with the tool calls they led to, as the API requires.
- There are no retries yet: a rate limit or busy server ends the run with an error (M17).
- Keys stay in `.env` (ignored by git), are removed from every span and are never returned by
  the API.
- Some models refuse tools while thinking (`gpt-6-luna`: "Function tools with reasoning_effort
  are not supported"); turn **Model thinking** off for tool-calling agents on them.
- The tests never use a real model: they replay scripted answers (`FakeLLM`).
