# MAOS — Multi-Agent Orchestration System

A Python-based multi-agent orchestration system that transforms a single user goal into a fully executed software project. MAOS coordinates 17 specialized AI agents through a ReAct reasoning loop, handling everything from planning and research to code generation, quality assurance, and deployment.

> **Give it a goal. Get a working project.**

-----

## How It Works

```
User: "Build a Flask REST API with JWT authentication"
│
┌─────▼─────┐
│ Orchestrator │  ← ReAct Loop (Reason → Act → Observe)
└─────┬─────┘
│
┌──────────┼──────────┬──────────┐
▼          ▼          ▼          ▼
┌────────┐ ┌─────────┐ ┌────────┐ ┌──────────┐
│Planner │→│Researcher│→│Architect│→│  Coder   │
└────────┘ └─────────┘ └────────┘ └────┬─────┘
Decomposes  Web search   System         │
goal into   + RAG        design    Writes code
phased tasks                       with auto-fix
                                        │
┌───────────────────────────────────────┘
▼
┌────────┐  ┌────────┐  ┌────────┐  ┌─────────┐
│ Critic │→ │Security│→ │ Linter │→ │ Tester  │
└────────┘  └────────┘  └────────┘  └────┬────┘
Scores code  Vuln scan   Static      pytest
(1-10)       + audit     analysis    runner
                                        │
┌───────────────────────────────────────┘
▼
┌──────────┐  ┌──────────┐  ┌─────────┐
│ Executor │→ │Optimizer │→ │ Builder │
└──────────┘  └──────────┘  └────┬────┘
Runs code,    Performance    Packaging
fixes errors  tuning         + deploy
                                  │
                           ┌──────▼───┐
                           │  Memory   │
                           └──────────┘
                           Stores project
                           in ChromaDB
```

**Result:** Working project in `workspace/projects/` — tested, linted, and ready to use.

-----

## Key Features

- **17 Specialized Agents** — each with a distinct role, model, and tool set
- **ReAct Reasoning Loop** — agents reason, act, and observe iteratively (max 3 retries)
- **Phased Execution** — complex goals are broken into dependency-aware phases
- **Vector Memory (ChromaDB)** — learns from past projects to improve future results
- **Cost-Optimized Model Routing** — Vertex AI (free tier) for core pipeline, Blackbox for auxiliary agents
- **4 Interfaces** — Web Dashboard, Telegram Bot, REST API, Interactive CLI
- **LLM-Free Agents** — Linter and Tester can run locally with zero token cost
- **Sandbox Isolation** — all file operations scoped to workspace directory
- **Cluster Mode** — parallel model execution for faster results

-----

## Agent Architecture

### Core Pipeline (Vertex AI — Gemini 2.5 Flash)

| Agent | Role | Model | Cost/1M tokens |
|-------|------|-------|----------------|
| **Planner** | Decomposes goals into phased tasks | gemini-2.5-flash | Free* |
| **Researcher** | Web search + RAG knowledge retrieval | gemini-2.5-flash | Free* |
| **Architect** | System design + architecture decisions | gemini-2.5-flash | Free* |
| **Coder** | Code generation with auto-fix | gemini-2.5-flash | Free* |
| **Coder (Fast)** | Simple tasks, quick edits | gemini-2.5-flash | Free* |
| **Critic** | Quality scoring (1-10 rubric) | gemini-2.5-flash | Free* |
| **Executor** | Runtime execution + error resolution | gemini-2.5-flash | Free* |
| **Optimizer** | Performance tuning + refactoring | gemini-2.5-flash | Free* |
| **Orchestrator** | Agent coordination + state management | gemini-2.5-flash | Free* |

### Auxiliary Pipeline (Blackbox)

| Agent | Role | Model | Cost/1M tokens |
|-------|------|-------|----------------|
| **Security** | Vulnerability scanning + audit | Claude Haiku 4.5 | $0.80 / $4.00 |
| **Docs** | Documentation generation | Claude Haiku 4.5 | $0.80 / $4.00 |
| **Tester** | Automated testing (pytest) | Claude Haiku 4.5 | $0.80 / $4.00 |
| **UI Tester** | UI/UX testing | Claude Haiku 4.5 | $0.80 / $4.00 |
| **Profiler** | User profile analysis | Claude Haiku 4.5 | $0.80 / $4.00 |
| **Analyzer** | Code analysis | Claude Haiku 4.5 | $0.80 / $4.00 |
| **Linter** | Static analysis (Flake8 + Pylint) | Qwen3-Coder (free) | $0.00 |
| **Builder** | Build + packaging | Devstral Small | $0.10 / $0.30 |

*\*Vertex AI: GCP free tier / credits*

**Average project cost:** $0.00–$0.10 for small-to-medium projects (Vertex AI free tier).

-----

## Quick Start

```bash
# Clone
git clone https://github.com/ahmetsn702/multi-agent-system.git
cd multi-agent-system/multi_agent_system

# Install dependencies
pip install -r requirements.txt

# Google Cloud auth (required for Vertex AI)
gcloud auth application-default login

# Configure
cp .env.example .env
# Edit .env — add VERTEX_PROJECT, BLACKBOX_API_KEY

# Run
python main.py "Build a CLI todo app with SQLite"
```

### Other Modes

```bash
python main.py                    # Interactive CLI
python main.py --demo             # Demo mode
python main.py --profile          # Workspace profiling
```

### Web Dashboard

```bash
# Starts on http://localhost:8000
python -m api.main_api
```

-----

## Interfaces

### Web Dashboard
Real-time project monitoring with session management, task logs (SSE streaming), and per-model cost tracking.

### Telegram Bot
Send goals directly from Telegram. Supports `/build` command for Flet → APK compilation with automatic file delivery.

### REST API
Full programmatic access with Swagger docs at `/docs`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/run` | POST | Start a new project |
| `/status/{id}` | GET | Session status |
| `/api/sessions` | GET | All sessions |
| `/api/costs` | GET | Cost breakdown |
| `/ws/{id}` | WS | Live log stream |

### CLI
Interactive terminal with real-time log output.

-----

## Project Structure

```
multi-agent-system/
├── multi_agent_system/    # <<< Active codebase >>>
│   ├── agents/            # 17 agent implementations
│   │   ├── planner_agent.py
│   │   ├── researcher_agent.py
│   │   ├── architect_agent.py
│   │   ├── coder_agent.py
│   │   ├── critic_agent.py
│   │   ├── executor_agent.py
│   │   ├── security_agent.py
│   │   ├── optimizer_agent.py
│   │   ├── linter_agent.py
│   │   ├── tester_agent.py
│   │   ├── builder_agent.py
│   │   ├── docs_agent.py
│   │   ├── profiler_agent.py
│   │   ├── analyzer_agent.py
│   │   └── ui_tester_agent.py
│   ├── core/              # Orchestrator, LLM client (Vertex AI + Blackbox), memory, message bus
│   ├── api/               # FastAPI web server + dashboard
│   ├── tools/             # Shell, file, web search, Docker, git tools
│   ├── config/            # Model routing, settings
│   ├── telegram_bot/      # Telegram bot integration
│   ├── tests/             # pytest test suite
│   ├── workspace/         # Generated projects output
│   └── main.py            # CLI entry point
│
├── agents/                # (Legacy) Old agent implementations
├── core/                  # (Legacy) Old core with OpenRouter + Groq
├── config/                # (Legacy) Old settings
├── tests/                 # Root-level tests
└── CLAUDE.md              # Project documentation for AI assistants
```

-----

## Tech Stack

**Backend:** Python 3.12, FastAPI, AsyncIO, Pydantic
**LLM Providers:** Google Vertex AI (Gemini 2.5 Flash), Blackbox (Claude Haiku 4.5, Devstral, Qwen3)
**LLM Communication:** google-genai SDK (Vertex AI), httpx async (Blackbox/Groq)
**Memory:** ChromaDB (vector DB), sentence-transformers (embeddings)
**Quality:** pytest, Flake8, Pylint
**Frontend:** Tailwind CSS, Vanilla JS, Server-Sent Events
**Deployment:** AWS EC2, systemd, Nginx

-----

## Security

- **Sandbox isolation** — all file operations restricted to `workspace/`
- **Auth** — cookie-based web sessions, Telegram user ID whitelist, API password
- **Rate limiting** — exponential backoff on LLM calls, brute-force protection
- **Secret management** — all credentials in `.env`, never committed
- **Security Agent** — automated vulnerability scanning on generated code

-----

## Performance

| Project Complexity | Success Rate | Avg. Time | Avg. Cost |
|--------------------|-------------|-----------|-----------|
| Simple (CLI tools, calculators) | ~95% | 2–5 min | $0.00–$0.02 |
| Medium (Flask APIs, Flet apps) | ~85% | 5–15 min | $0.02–$0.10 |
| Complex (multi-page web apps) | ~70% | 15–30 min | $0.10–$0.30 |

*Costs based on Vertex AI free tier + Blackbox auxiliary usage.*

-----

## License

MIT

-----

## Author

**Ahmed Hüsrev Sayın**
Software Engineering Student — Fırat University
[GitHub](https://github.com/ahmetsn702)
