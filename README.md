# Multi-Agent Orchestration System

This project is a Python-based multi-agent orchestration system that turns a user goal into an executable workflow.  
It coordinates specialized agents (planning, research, coding, review, execution, profiling) through a shared orchestrator and message bus.  
The main runtime supports interactive mode, one-shot goal execution, demo mode, and workspace profiling.

## Architecture

| Agent | Role | What it does |
|---|---|---|
| `planner` | Strategic decomposition | Breaks a user goal into flat or phased tasks with dependencies and execution order. |
| `researcher` | Technical research | Runs web search and synthesizes implementation guidance, risks, and code skeleton ideas. |
| `coder` | Code generation | Produces Python source/test files, writes them into workspace project folders, and attempts auto-fixes on failures. |
| `critic` | Quality assurance | Reviews outputs with a scoring rubric (correctness, quality, test coverage, architecture, security) and routes next action. |
| `executor` | Runtime operations | Executes shell/code/file operations, enforces safety checks, and runs produced code in project workspace. |
| `profiler` | User profiling | Scans historical workspace session/project artifacts and generates `user_profile.txt`. |

## Installation

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root. Based on current code:

- `OPENROUTER_API_KEY` (required for OpenRouter-backed models)
- `GROQ_API_KEY` (recommended if you keep `researcher`/`critic` on Groq in `config/settings.py`)

Notes:
- The current `.env.example` includes AWS-related keys, but the active LLM path in this project uses OpenRouter/Groq settings from code.

## Usage

```bash
python main.py "your task"
python main.py --demo
python main.py --profile
```

Additional mode:

```bash
python main.py
```

Runs interactive CLI mode.

## Agent-Model Responsibility Matrix

Configured in `config/settings.py` (`MODEL_ROUTING` + `PROVIDER_CONFIG`) and `core/llm_client.py` fallback logic.

| Agent | Model | Provider | Status |
|---|---|---|---|
| `planner` | `openai/gpt-4o-mini` | `openrouter` | Explicit routing |
| `researcher` | `llama-3.3-70b-versatile` | `groq` | Explicit routing |
| `coder` | `openai/gpt-4o-mini` | `openrouter` | Explicit routing |
| `critic` | `llama-3.3-70b-versatile` | `groq` | Explicit routing |
| `executor` | `openai/gpt-4o-mini` | `openrouter` | Fallback routing (`MODEL_ROUTING["executor"] = None`) |
| `profiler` | `openai/gpt-4o-mini` | `openrouter` | Fallback routing (not explicitly listed in `MODEL_ROUTING`) |

## Project Structure

```text
.
|-- main.py
|-- requirements.txt
|-- agents/
|   |-- planner_agent.py
|   |-- researcher_agent.py
|   |-- coder_agent.py
|   |-- critic_agent.py
|   |-- executor_agent.py
|   `-- profiler_agent.py
|-- core/
|   |-- orchestrator.py
|   |-- base_agent.py
|   |-- llm_client.py
|   |-- memory.py
|   `-- message_bus.py
|-- config/
|   `-- settings.py
|-- tools/
|-- ui/
|-- api/
|-- tests/
`-- workspace/
```

## Entry Point

- Main entry point: `main.py`
