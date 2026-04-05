# MAOS — Multi-Agent Orchestration System

Autonomous software generation system. Describe what you want, get working code with tests.

17 specialized AI agents coordinate via a ReAct (Reason-Act-Observe) loop to plan, research, architect, code, review, secure, and execute — producing complete project directories with source code, tests, and documentation.

## Architecture

```
User Goal
    |
    v
+------------------+
|   Orchestrator    |  ReAct loop controller
+------------------+
    |
    v
+------------------+     +------------------+     +------------------+
|    Planner       | --> |   Researcher     | --> |   Architect      |
| (task breakdown) |     | (web search)     |     | (file contracts) |
+------------------+     +------------------+     +------------------+
    |
    v  (per task)
+------------------+     +------------------+     +------------------+
|     Coder        | --> |     Critic       | --> |    Security      |
| (code generation)|     | (score 1-10)     |     | (static scan)    |
+------------------+     +------------------+     +------------------+
    |                         |
    |  score < 7 ? revise     |  score >= 7 ? approve
    +<------------------------+
    |
    v
+------------------+     +------------------+     +------------------+
|    Executor      | --> |     Tester       | --> |      Docs        |
| (run & debug)    |     | (pytest runner)  |     | (README gen)     |
+------------------+     +------------------+     +------------------+
    |
    v
  workspace/projects/{slug}/
    src/         tests/        docs/
    main.py      test_main.py  README.md
```

## Features

- **17 agents**: Planner, Researcher, Architect, Coder, Coder Fast, Critic, Executor, Security, Optimizer, Docs, Tester, Linter, Builder, UI Tester, Profiler, Analyzer, Orchestrator
- **Hybrid LLM routing**: Vertex AI (Gemini 2.5 Flash) for core pipeline, Blackbox (Claude Haiku, Qwen, Devstral) for auxiliary agents
- **Quality gate**: Critic scores code 1-10; < 7 triggers revision, < 4 triggers replan
- **Auto-fix pipeline**: Syntax checking, truncation repair, LLM-based error correction
- **Security scanning**: Regex-based static analysis for secrets, injection, unsafe APIs
- **Web dashboard**: FastAPI + WebSocket real-time monitoring
- **Telegram bot**: Send a goal, receive a ZIP with generated project
- **Vector memory**: ChromaDB semantic search across past projects
- **Cost tracking**: Per-project token and cost accounting ($0.00-$0.30/project)

## Quick Start

```bash
# Clone
git clone https://github.com/your-username/Multi-Agent.git
cd Multi-Agent/multi_agent_system

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env: set VERTEX_PROJECT, VERTEX_LOCATION, BLACKBOX_API_KEY

# Authenticate GCP
gcloud auth application-default login

# Run
python main.py "Build a CLI todo app in Python"
```

## Usage

```bash
# Interactive mode
python main.py

# Single goal
python main.py "Flask REST API with SQLite"

# Demo project
python main.py --demo

# Web dashboard
python -m api.main_api          # http://localhost:8000

# Telegram bot
python -m telegram_bot.bot
```

## Testing

```bash
cd multi_agent_system
pytest                          # 126+ tests
pytest -v                       # verbose
pytest tests/test_api.py        # API tests
pytest tests/test_auth.py       # auth tests
pytest tests/test_routing.py    # model routing
pytest tests/test_tools.py      # tool tests
```

## Project Structure

```
multi_agent_system/
  agents/           # 17 specialized agents
  api/              # FastAPI web dashboard + WebSocket
  config/           # MODEL_ROUTING, pricing, settings
  core/             # BaseAgent, Orchestrator, LLMClient, MessageBus, Memory
  telegram_bot/     # Telegram interface
  tools/            # Code runner, file manager, shell, web search, etc.
  tests/            # 126+ unit and integration tests
  workspace/        # Generated projects output
  main.py           # CLI entry point
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `VERTEX_PROJECT` | Yes | GCP project ID for Vertex AI |
| `VERTEX_LOCATION` | Yes | GCP region (e.g. `us-central1`) |
| `BLACKBOX_API_KEY` | Yes | Blackbox API key for auxiliary agents |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token |
| `TELEGRAM_USER_ID` | No | Allowed Telegram user ID |
| `WEB_PASSWORD` | No | Web dashboard login password |
| `MAOS_USER_NAME` | No | User name for profiler agent |

## License

MIT
