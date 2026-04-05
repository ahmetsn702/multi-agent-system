# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MAOS (Multi-Agent Orchestration System) turns user goals into working software projects. 17 specialized agents coordinate via a ReAct (Reason-Act-Observe) loop: planning, research, architecture, coding, quality scoring, security analysis, and execution — all autonomous.

**Hybrid provider strategy:** Vertex AI (Gemini 2.5 Flash, free tier) for core pipeline + Blackbox (Claude Haiku, Qwen, Devstral) for auxiliary agents. Average cost: $0.00–$0.30 per project.

## Codebase Structure

**All active code lives in `multi_agent_system/`.** The root `_legacy/` directory contains the old OpenRouter + Groq codebase (6 agents) — do not modify it.

## Commands

```bash
# Install dependencies
pip install -r multi_agent_system/requirements.txt

# GCP auth (required for Vertex AI agents)
gcloud auth application-default login

# Run the system
cd multi_agent_system
python main.py "Build a CLI todo app"    # Single goal
python main.py                           # Interactive mode
python main.py --demo                    # Demo (Hacker News scraper)
python main.py --profile                 # Workspace profiling

# Web dashboard
cd multi_agent_system && python -m api.main_api    # FastAPI on :8000

# Telegram bot
cd multi_agent_system && python -m telegram_bot.bot

# Tests (from multi_agent_system/)
cd multi_agent_system
pytest                                   # All tests (126+)
pytest -v                                # Verbose
pytest tests/test_api.py                 # API endpoint tests
pytest tests/test_auth.py                # Auth & session tests
pytest tests/test_routing.py             # Model routing tests
pytest tests/test_tools.py               # Tool unit tests
pytest tests/test_agents.py              # Agent unit tests
pytest tests/test_message_bus.py         # Message bus tests
pytest tests/scripts/                    # Integration tests
pytest tests/test_foo.py::test_bar       # Single test function
```

## Architecture

### ReAct Execution Flow

```
User Goal -> Orchestrator.run(goal)
  -> Planner (decompose into tasks/phases)
  -> Per task:
      Researcher -> Architect -> Coder -> Critic (score 1-10)
        >= 7.0 -> approved
        4.0-6.9 -> revision (back to Coder, max 2x)
        < 4.0 -> replan (back to Planner)
      -> Security -> Executor -> Tester
  -> Store in memory -> Return project directory
```

**Key constants** (in `orchestrator.py`): MAX_ITERATIONS=10, CONFIDENCE_THRESHOLD=0.6, TASK_TIMEOUT=360s, TOTAL_TIMEOUT=1200s.

### Agent System

All agents inherit from `core/base_agent.py:BaseAgent` and implement two abstract methods:
- `async think(task: Task) -> ThoughtProcess` — reason about the task
- `async act(thought, task) -> AgentResponse` — execute the plan

Agents register tools via `self.register_tool("name", callable)` and communicate through `core/message_bus.py` (async pub/sub with priority queue, logged to `messages.jsonl`).

### LLM Client Factory

`LLMClient(agent_id)` uses `__new__` to return either `VertexAIClient` (google-genai SDK) or httpx-based client (Blackbox/Groq/Cerebras) based on `MODEL_ROUTING` in `config/settings.py`. Callers don't know the difference.

### Memory System

Two tiers in `core/memory.py`:
- **ShortTermMemory**: per-agent sliding window (last 10 interactions), used for LLM context
- **LongTermMemory**: shared persistent key-value store (`memory/shared_memory.json`), thread-safe with asyncio lock

Vector memory via ChromaDB in `core/vector_memory.py` / `core/memory_agent.py`.

### Generated Output

Each run produces `workspace/projects/{slug}/` containing generated code, tests, logs, and plan.json.

## Development Rules

- Python 3.10+, async/await throughout, type hints on all functions
- Path management: use `Path(__file__).parent`, never hardcode paths
- Personal paths (`C:\Users\...`) must never appear in code or reports
- New agents: inherit from `BaseAgent`, add routing entry to `config/settings.py:MODEL_ROUTING`
- Vertex AI agents get `VertexAIClient` automatically via factory pattern

## Commit Convention

`feat:`, `fix:`, `chore:`, `docs:`, `security:` prefixes. Turkish commit messages accepted.

## Environment Setup

Copy `multi_agent_system/.env.example` to `.env` and fill in:
- `VERTEX_PROJECT` + `VERTEX_LOCATION` (required — core pipeline)
- `BLACKBOX_API_KEY` (required — auxiliary agents)
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_USER_ID` (optional)

Auth: `gcloud auth application-default login` for Vertex AI.

## Known Bugs

- Coder sometimes generates `app.py` imports in tests when entry point is `main.py`
- Critic agent occasionally times out
- Orchestrator may overwrite existing `main.py` in generated projects
