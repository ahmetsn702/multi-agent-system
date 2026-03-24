# MAOS — Multi-Agent Orchestration System

A Python-based multi-agent orchestration system that transforms a single user goal into a fully executed software project. MAOS coordinates 9 specialized AI agents through a ReAct reasoning loop, handling everything from planning and research to code generation, quality assurance, and deployment.

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
┌─────────────────┼─────────────────┐
▼                 ▼                 ▼
┌─────────┐     ┌──────────┐     ┌─────────┐
│ Planner │────▶│Researcher│────▶│  Coder  │
└─────────┘     └──────────┘     └────┬────┘
Decomposes       Web search +         │
goal into        RAG lookup      Writes code
phased tasks                     with auto-fix
│
┌─────────────────┼──────────────┘
▼                 ▼
┌─────────┐     ┌──────────┐     ┌──────────┐
│  Critic │────▶│  Linter  │────▶│  Tester  │
└─────────┘     └──────────┘     └────┬─────┘
Scores code      Flake8 +             │
(1-10 rubric)    Pylint          pytest runner
Rejects < 5.0    (no LLM)       (no LLM)
│
┌────▼─────┐
│ Executor  │
└────┬─────┘
Runs code,
fixes runtime
errors
│
┌────▼─────┐
│  Memory   │
└──────────┘
Stores project
in ChromaDB
```

**Result:** Working project in `workspace/projects/` — tested, linted, and ready to use.

-----

## Key Features

- **9 Specialized Agents** — each with a distinct role, model, and tool set
- **ReAct Reasoning Loop** — agents reason, act, and observe iteratively (max 3 retries)
- **Phased Execution** — complex goals are broken into dependency-aware phases
- **Vector Memory (ChromaDB)** — learns from past projects to improve future results
- **Cost-Optimized Model Routing** — each agent uses the cheapest model that meets its needs
- **4 Interfaces** — Web Dashboard, Telegram Bot, REST API, Interactive CLI
- **LLM-Free Agents** — Linter and Tester run locally with zero token cost
- **Sandbox Isolation** — all file operations scoped to workspace directory

-----

## Agent Architecture

|Agent           |Role                                  |Model                    |Cost/1M tokens|
|----------------|--------------------------------------|-------------------------|--------------|
|**Planner**     |Decomposes goals into phased tasks    |Qwen3-30B-A3B            |$0.07         |
|**Researcher**  |Web search + RAG knowledge retrieval  |GPT-OSS-120B             |$0.04         |
|**Coder**       |Code generation with auto-fix         |Codestral-2508 (256K ctx)|$0.30         |
|**Coder (Fast)**|Simple tasks, quick edits             |Gemini Flash Lite        |$0.25         |
|**Critic**      |Quality scoring (1-10 rubric)         |Step-3.5-Flash           |$0.10         |
|**Executor**    |Runtime execution + error resolution  |GPT-OSS-120B             |$0.04         |
|**Linter**      |Static analysis (Flake8 + Pylint)     |*None (local)*           |$0.00         |
|**Tester**      |Automated testing (pytest)            |*None (local)*           |$0.00         |
|**Memory**      |Stores successful projects in ChromaDB|*None (local)*           |$0.00         |

**Average project cost:** $0.05–$0.15 for small-to-medium projects.

-----

## Quick Start

```bash
# Clone
git clone https://github.com/ahmetsn702/multi-agent-system.git
cd multi-agent-system

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Add your API keys (OpenRouter, Groq, etc.)

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

|Endpoint       |Method|Description        |
|---------------|------|-------------------|
|`/run`         |POST  |Start a new project|
|`/status/{id}` |GET   |Session status     |
|`/api/sessions`|GET   |All sessions       |
|`/api/costs`   |GET   |Cost breakdown     |
|`/ws/{id}`     |WS    |Live log stream    |

### CLI
Interactive terminal with real-time log output.

-----

## Project Structure

```
multi-agent-system/
├── agents/          # 9 agent implementations
│   ├── planner_agent.py
│   ├── researcher_agent.py
│   ├── coder_agent.py
│   ├── critic_agent.py
│   ├── executor_agent.py
│   ├── linter_agent.py
│   ├── tester_agent.py
│   ├── builder_agent.py
│   └── memory_agent.py
├── core/            # Orchestrator, LLM client, memory, message bus
├── api/             # FastAPI web server + dashboard
├── tools/           # Shell, file, web search, Docker tools
├── config/          # Model routing, settings
├── tests/           # pytest test suite
├── workspace/       # Generated projects output
└── main.py          # CLI entry point
```

-----

## Tech Stack

**Backend:** Python 3.12, FastAPI, AsyncIO, Pydantic  
**LLM Communication:** httpx (async), SSE streaming, OpenRouter, Groq  
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

-----

## Performance

|Project Complexity             |Success Rate|Avg. Time|Avg. Cost  |
|-------------------------------|------------|---------|-----------|
|Simple (CLI tools, calculators)|~95%        |2–5 min  |$0.02–$0.05|
|Medium (Flask APIs, Flet apps) |~85%        |5–15 min |$0.05–$0.15|
|Complex (multi-page web apps)  |~70%        |15–30 min|$0.15–$0.50|

-----

## License

MIT

-----

## Author

**Ahmed Hüsrev Sayın**  
Software Engineering Student — Fırat University  
[GitHub](https://github.com/ahmetsn702)
