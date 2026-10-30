# Agent Lab

Learn agent fundamentals by building them by hand, and watch every step live. M1 ships a
traced ReAct agent with two tools (`calculator`, `get_weather`), an API, and a one-page UI
with the agent graph, a span waterfall, span details and replay of past runs.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node 22 and pnpm
- make
- [Ollama](https://ollama.com) for real runs (tests don't need it)

## Run

```bash
make install
ollama pull qwen3:8b
cp .env.example .env      # point LLM_BASE_URL / LLM_MODEL elsewhere if you like
make dev-backend          # terminal 1: http://127.0.0.1:8000
make dev-frontend         # terminal 2: http://127.0.0.1:3000
```

Open http://127.0.0.1:3000, run a prompt such as "What is 17*23 plus the current temperature
in Berlin?", and click spans for their input, output, tokens and latency. Past runs replay from
the database (`backend/data/agent_lab.db`).

Any OpenAI-compatible endpoint works: set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`.

## Check

```bash
make check   # ruff, ruff format --check, pyright, pytest, eslint, tsc, vitest
```

## API

| | |
|---|---|
| `POST /runs` `{"prompt": "..."}` | start a run, returns it (`202`) |
| `GET /runs` | past runs, newest first |
| `GET /runs/{id}` | run and its spans |
| `WS /runs/{id}/stream` | stored spans, then live span events, then `run_ended` |

Design and requirements: `specs/001-react-walking-skeleton/`.
