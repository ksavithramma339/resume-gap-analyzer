.PHONY: install playground run test

install:
	uv sync --python python

playground:
	uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents

run:
	uv run python -m uvicorn app.agent:app --host 127.0.0.1 --port 18081

test:
	uv run pytest tests/
