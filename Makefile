.PHONY: install check check-backend check-frontend dev-llm dev-backend dev-frontend

ENV_FILE := $(if $(wildcard .env),--env-file ../.env,)

VLLM_IMAGE := vllm/vllm-openai:v0.31.0
VLLM_MODEL := RedHatAI/Qwen3.5-9B-quantized.w4a16

install:
	cd backend && uv sync
	cd frontend && pnpm install

check: check-backend check-frontend

check-backend:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd backend && uv run pyright
	cd backend && uv run pytest

check-frontend:
	cd frontend && pnpm lint
	cd frontend && pnpm typecheck
	cd frontend && pnpm test

# vLLM on 127.0.0.1:8001, serving the model as "qwen3.5-9b". Weights come from the Hugging Face
# cache; compile caches persist in ~/.cache/agent-lab-vllm (the container's home). The GPU share
# leaves room for other programs (~3-4 GiB on the dev machine); 4 sequences = the widest fan-out.
dev-llm:
	docker run --rm --name agent-lab-vllm --gpus all --ipc=host \
		--user $$(id -u):$$(id -g) -e HOME=/home/lab -e HF_HOME=/hf \
		-v $(HOME)/.cache/huggingface:/hf -v $(HOME)/.cache/agent-lab-vllm:/home/lab \
		-p 127.0.0.1:8001:8000 $(VLLM_IMAGE) \
		--model $(VLLM_MODEL) --served-model-name qwen3.5-9b --language-model-only \
		--max-model-len 8192 --gpu-memory-utilization 0.78 --max-num-seqs 4 \
		--max-num-batched-tokens 2048 \
		--reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder

dev-backend:
	cd backend && uv run $(ENV_FILE) uvicorn agent_lab.main:app --host 127.0.0.1 --port 8000 --reload

dev-frontend:
	cd frontend && pnpm dev
