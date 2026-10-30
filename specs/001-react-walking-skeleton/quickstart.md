# Quickstart / validation: M1

Prerequisites: uv, Python 3.12, Node 22 + pnpm, make. Optional: Ollama with `qwen3:8b`.

## Automated

```bash
make install   # uv sync + pnpm install
make check     # ruff, ruff format --check, pyright, pytest, eslint, tsc --noEmit, vitest
```

Expected: all gates pass; pytest uses only `FakeLLM` / mocked HTTP.

## Manual (real model)

```bash
ollama pull qwen3:8b
cp .env.example .env
make dev-backend    # http://127.0.0.1:8000
make dev-frontend   # http://127.0.0.1:3000
```

1. Enter "What is 17*23 plus the current temperature in Berlin?" and run (FR-020).
2. Graph highlights `llm`, then tool nodes, then `end`; taken edges are marked (FR-021).
3. Waterfall shows the root, iteration, llm and tool spans; running spans animate (FR-022).
4. Click an llm span: messages, response, tokens, model, latency are shown (FR-023).
5. Reload the page, pick the run in "Past runs": identical graph/waterfall (FR-024, SC-003).
6. Prompt "compute 2**999" → calculator error visible on the tool span, run continues.
7. `ss -ltnp | grep -E ':(8000|3000)'` shows both bound to 127.0.0.1 only (FR-019).
