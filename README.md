# Agent Lab

Learn agent fundamentals by building them by hand, and watch every step live. M1 shipped a
traced ReAct agent with two tools (`calculator`, `get_weather`), an API, and a one-page UI
with the agent graph, a span waterfall, span details and replay of past runs. M2 adds the
five workflow patterns: prompt chaining, routing, parallelization, orchestrator-workers and
evaluator-optimizer. M3 adds a builder: the six agents are templates, and custom agents made
from them can be edited, saved and run.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node 22 and pnpm
- make
- For real runs (tests don't need them): an NVIDIA GPU with ~11 GiB free VRAM, Docker with the
  NVIDIA container runtime, and the `vllm/vllm-openai:v0.31.0` image

## Run

```bash
make install
cp .env.example .env      # point LLM_BASE_URL / LLM_MODEL elsewhere if you like
make dev-llm              # vLLM on http://127.0.0.1:8001, detached (first start downloads ~11 GB)
make dev                  # backend on http://127.0.0.1:8000 and frontend on http://127.0.0.1:3000
```

Open http://127.0.0.1:3000, pick a template (its graph, settings and a sample prompt appear),
press Run, and click spans for their input, output, tokens and latency.

To build your own agent, pick a template and press Customize. Click a node to edit its prompt
and settings; add, remove or reorder chain steps, routes and parallel aspects, pick ReAct's
tools and change limits in the agent settings. The graph redraws as you edit. Save stores the
agent under "My agents"; Run saves first. Duplicate and Delete work on saved agents; past runs
keep the name, config and graph they ran with.
The run header and the past-runs list show model calls, tool calls, tokens and wall time. Past
runs replay from the database (`backend/data/agent_lab.db`).

`make dev-llm` serves `RedHatAI/Qwen3.5-9B-quantized.w4a16` (4-bit Qwen3.5 9B) as `qwen3.5-9b`.
It keeps running in the background and comes back with Docker; follow it with
`docker logs -f agent-lab-vllm`, remove it with `make stop-llm`. `make dev-backend` and
`make dev-frontend` start the two servers separately.
vLLM batches concurrent requests, so parallel branches and workers really run at the same
time. Any OpenAI-compatible endpoint works instead (Ollama: `LLM_BASE_URL=http://localhost:11434/v1`,
`LLM_MODEL=qwen3:8b`): set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`.

### Models

A custom agent runs on "Default" or on a model you pick in its agent settings; templates always
run on the default. The run header, past runs and span details show which model answered.
Configure the list in `.env` (see `.env.example`) and restart the backend after changes:

- `LLM_MODELS`: further model ids served by the local endpoint, comma-separated.
- `OPENAI_MODELS` and `OPENAI_API_KEY`: OpenAI models, e.g. `OPENAI_MODELS=gpt-6-luna`. Without
  the key they are listed but can't be picked. An agent on an OpenAI model sends its prompts and
  tool results to OpenAI. The key stays in `.env` and is redacted from every span.
- `OPENAI_REASONING_OFF`: the `reasoning_effort` sent when an agent's thinking is off (default
  `none`). If a model rejects it, the run fails with OpenAI's message on the span; set the value
  that model accepts, or leave it empty to send nothing.
  Some models refuse tools while thinking on Chat Completions (`gpt-6-luna`: "Function tools
  with reasoning_effort are not supported"); turn "Model thinking" off for tool-calling agents on
  them.
- `DEFAULT_MODEL`: `provider/model`, e.g. `openai/gpt-6-luna` (default: the local `LLM_MODEL`).
  The backend refuses to start when it names a model that isn't configured or has no key.

## Check

```bash
make check   # ruff, ruff format --check, pyright, pytest, eslint, tsc, vitest
```

## API

| | |
|---|---|
| `GET /agents` | templates, then custom agents, with config, sample prompt and graph |
| `GET /tools` | tools an agent can be given |
| `GET /models` | configured models: provider, id, external, available, default (never keys) |
| `POST /agents`, `PUT /agents/{id}`, `DELETE /agents/{id}` | create, update, delete a custom agent (`model`: `{"provider", "model"}` or `null` for Default) |
| `POST /graph` `{"template_id", "config"}` | the graph for an unsaved config (validation errors as `422`) |
| `POST /runs` `{"prompt": "...", "agent_id": "react"}` | start a run of a template or custom agent (`202`) |
| `GET /runs` | past runs with totals, newest first |
| `GET /runs/{id}` | run and its spans |
| `WS /runs/{id}/stream` | stored spans, then live span events, then `run_ended` |

Design and requirements: `specs/001-react-walking-skeleton/` (M1),
`specs/002-workflow-patterns/` (M2), `specs/003-agent-builder/` (M3).
