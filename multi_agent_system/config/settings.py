# config/settings.py

# OpenRouter model IDs
GPT4O_MINI       = "openai/gpt-4o-mini"
GPT_OSS_120B     = "openai/gpt-oss-120b"
SEED_MINI        = "bytedance-seed/seed-2.0-mini"
DEEPSEEK_V3      = "deepseek/deepseek-v3-0324:free"

# Qwen3 modelleri (V4 ekleme)
QWEN3_235B       = "qwen/qwen3-235b-a22b-2507"     # Genel + Planner icin
QWEN3_CODER_NEXT = "qwen/qwen3-coder-next"          # Coder icin optimize

# GLM modelleri (Z.ai)
GLM_4_7_FLASH    = "z-ai/glm-4.7-flash"             # Agentic coding, $0.06/$0.40

# Qwen3 Coder modelleri
QWEN3_CODER_30B   = "qwen/qwen3-coder-30b-a3b-instruct"  # HumanEval %89.3, $0.07/$0.27
QWEN3_CODER_480B  = "qwen/qwen3-coder:exacto"              # 480B MoE, 65.5K output, $0.22/$1.80

# xAI modelleri
GROK_4_FAST      = "x-ai/grok-4-fast"               # 2M context, $0.20/$0.50

# Mistral Codestral — coding specialist
CODESTRAL_2508   = "mistralai/codestral-2508"       # 256K output, $0.30/$0.90, coding #45

# MoonshotAI — Thinking modeli (Planner icin)
KIMI_K2_THINKING = "moonshotai/kimi-k2-thinking"    # 131K ctx, $0.47/$2.0, Agentic reasoning

# MiniMax
# MINIMAX_M25   = "minimax/minimax-m2.5"            # OpenRouter format
MINIMAX_M25      = "blackboxai/minimax/minimax-m2.5"
MINIMAX_M21      = "blackboxai/minimax/minimax-m2.1"

# Claude Sonnet (Beyin katmanı)
# CLAUDE_SONNET_46 = "anthropic/claude-sonnet-4.6"  # OpenRouter format
CLAUDE_SONNET_46 = "blackboxai/anthropic/claude-sonnet-4.6"

# Gemini 3.1 Pro (Blackbox format)
GEMINI_31_PRO_PREVIEW = "blackboxai/google/gemini-3.1-pro-preview"

# Google Gemini
GEMINI_FLASH_LITE = "google/gemini-3.1-flash-lite-preview"  # 1M ctx, $0.25/$1.50
VERTEX_GEMINI_20_FLASH_001 = "gemini-2.5-flash"
VERTEX_GEMINI_20_FLASH_LITE = "gemini-2.5-flash-lite"

# StepFun modelleri (OpenRouter)
STEP_35_FLASH    = "stepfun/step-3.5-flash"            # Critic icin: hizli, ucuz ($0.012/$0.06)

# Groq model IDs
LLAMA_70B_GROQ     = "llama-3.3-70b-versatile"

# Cerebras model IDs (ücretsiz, çok hızlı)
LLAMA_70B_CEREBRAS   = "gpt-oss-120b"                        # Production
QWEN3_235B_CEREBRAS  = "qwen-3-235b-a22b-instruct-2507"     # 32K output, 1400 tok/sn, ÜCRETSİZ!

# Provider Config
PROVIDER_CONFIG = {
    # "openrouter": {
    #     "base_url": "https://openrouter.ai/api/v1/chat/completions",
    #     "env_key": "OPENROUTER_API_KEY",
    # },
    "blackbox": {
        "base_url": "https://api.blackbox.ai/chat/completions",
        "env_key": "BLACKBOX_API_KEY",
    },
    "vertex": {
        "base_url": "",
        "env_key": "VERTEX_PROJECT",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "env_key": "GROQ_API_KEY",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1/chat/completions",
        "env_key": "CEREBRAS_API_KEY",
    },
}

# Model Routing — ajan → model + provider
MODEL_ROUTING = {
    # Core pipeline (Vertex AI — free tier Gemini 2.5 Flash)
    "planner":      {"model": "gemini-2.5-flash",   "provider": "vertex"},
    "researcher":   {"model": "gemini-2.5-flash",   "provider": "vertex"},
    "architect":    {"model": "gemini-2.5-flash",   "provider": "vertex"},
    "coder":        {"model": "gemini-2.5-flash",   "provider": "vertex"},
    "coder_fast":   {"model": "gemini-2.5-flash",   "provider": "vertex"},
    "critic":       {"model": "gemini-2.5-flash",   "provider": "vertex"},
    "executor":     {"model": "gemini-2.5-flash",   "provider": "vertex"},
    "optimizer":    {"model": "gemini-2.5-flash",   "provider": "vertex"},
    "orchestrator": {"model": VERTEX_GEMINI_20_FLASH_001, "provider": "vertex"},

    # Auxiliary agents (Blackbox — Claude Haiku, Qwen, Devstral)
    "security":     {"model": "blackboxai/anthropic/claude-haiku-4.5",     "provider": "blackbox"},
    "docs":         {"model": "blackboxai/anthropic/claude-haiku-4.5",     "provider": "blackbox"},
    "tester":       {"model": "blackboxai/anthropic/claude-haiku-4.5",     "provider": "blackbox"},
    "linter":       {"model": "blackboxai/qwen/qwen3-coder:free",          "provider": "blackbox"},
    "builder":      {"model": "blackboxai/mistralai/devstral-small",       "provider": "blackbox"},
    "ui_tester":    {"model": "blackboxai/anthropic/claude-haiku-4.5",     "provider": "blackbox"},
    "profiler":     {"model": "blackboxai/anthropic/claude-haiku-4.5",     "provider": "blackbox"},
    "analyzer":     {"model": "blackboxai/anthropic/claude-haiku-4.5",     "provider": "blackbox"},
}

# Per-model HTTP timeout (saniye)
# "Thinking" modeller (Kimi K2, Qwen3 CoT vb.) cok uzun sure dusunuyor —
# onlara yeterli zaman verilmezse timeout hatasıyla sistem yarım kalıyor.
MODEL_TIMEOUTS = {
    KIMI_K2_THINKING:  120,   # 2 dakika (önce: 600) — planner için yeterli
    QWEN3_235B:        120,   # 2 dakika (önce: 300) — planner için yeterli
    CODESTRAL_2508:    120,   # 2 dakika (önce: 180) — coder için yeterli
    CLAUDE_SONNET_46:  120,   # Tek-model deneyinde tum ajanlar icin
    GEMINI_FLASH_LITE: 120,   # 2 dakika — hizli model
    VERTEX_GEMINI_20_FLASH_001: 120,
    VERTEX_GEMINI_20_FLASH_LITE: 120,
    GPT_OSS_120B:      300,   # 5 dakika (önce: 180) — executor için daha uzun
    STEP_35_FLASH:      60,   # 1 dakika — critic icin hizli
}

# Token Budget
TOKEN_BUDGET = {
    GPT4O_MINI: {
        "max_input": 128000,
        "max_output": 4000,
        "per_agent": {
            "planner":    1500,
            "researcher": 1200,
            "executor":   0,
        }
    },
    GPT_OSS_120B: {
        "max_input": 200000,
        "max_output": 8000,
        "per_agent": {
            "planner": 2000,
            "coder":   4000,
            "executor": 500,  # Executor kısa komutlar üretir, 500 yeterli
        }
    },
    "blackboxai/anthropic/claude-sonnet-4.6": {
        "max_input": 200000,
        "max_output": 8000,
        "per_agent": {
            "planner": 4000,
            "critic": 1000,
            "security": 1000,
            "optimizer": 2000,
            "researcher": 2000,
            "coder": 8000,
            "coder_fast": 8000,
            "docs": 4000,
            "executor": 1000,
            "tester": 1000,
            "linter": 1000,
            "builder": 1000,
            "ui_tester": 2000,
            "profiler": 1000,
            "analyzer": 1000,
            "orchestrator": 4000,
        }
    },
    "blackboxai/anthropic/claude-haiku-4.5": {
        "max_input": 200000,
        "max_output": 16000,
    },
    "blackboxai/moonshotai/kimi-k2:free": {
        "max_input": 131072,
        "max_output": 8000,
    },
    "blackboxai/mistralai/codestral-2508": {
        "max_input": 262144,
        "max_output": 16000,
    },
    "blackboxai/qwen/qwen3-coder:free": {
        "max_input": 131072,
        "max_output": 8000,
    },
    "blackboxai/mistralai/devstral-small": {
        "max_input": 131072,
        "max_output": 8000,
    },
    VERTEX_GEMINI_20_FLASH_001: {
        "max_input": 1048576,
        "max_output": 8192,
        "per_agent": {
            "planner": 4000,
            "architect": 4000,
            "coder": 16384,
            "coder_fast": 16384,
            "critic": 2000,
            "orchestrator": 4000,
        }
    },
    VERTEX_GEMINI_20_FLASH_LITE: {
        "max_input": 1048576,
        "max_output": 8192,
        "per_agent": {
            "researcher": 2000,
            "coder_fast": 6000,
            "executor": 1000,
            "optimizer": 2000,
        }
    },
    QWEN3_235B: {
        "max_input": 262000,
        "max_output": 4000,
        "per_agent": {
            "planner": 2000,
        }
    },
    QWEN3_CODER_NEXT: {
        "max_input": 262000,
        "max_output": 8000,
        "per_agent": {
            "coder": 6000,
            "coder_fast": 6000,
        }
    },
    GLM_4_7_FLASH: {
        "max_input": 202000,
        "max_output": 6000,
        "per_agent": {"coder": 6000}
    },
    CODESTRAL_2508: {
        "max_input": 256000,
        "max_output": 32000,   # 256K destekliyor, 32K yeterli
        "per_agent": {"coder": 16000}
    },
    QWEN3_CODER_480B: {
        "max_input": 262000,
        "max_output": 16000,   # 65.5K destekliyor ama 16K yeterli
        "per_agent": {"coder": 12000}
    },
    QWEN3_CODER_30B: {
        "max_input": 131000,
        "max_output": 32000,   # 32K output — kodlar asla kesilmez
        "per_agent": {"coder": 8000}
    },
    LLAMA_70B_CEREBRAS: {
        "max_input": 128000,
        "max_output": 8000,
        "per_agent": {"coder": 8000}
    },
    QWEN3_235B_CEREBRAS: {
        "max_input": 65000,
        "max_output": 32000,   # 32K output ücretsiz — kodlar asla kesilmez!
        "per_agent": {"coder": 16000}
    },

    LLAMA_70B_GROQ: {
        "max_input": 128000,
        "max_output": 4000,
        "per_agent": {
            "researcher": 1200,
            "critic":     600,
        }
    },
    "gemini-2.5-flash": {
        "max_input": 1048576,
        "max_output": 8192,
        "per_agent": {
            "planner":    8192,
            "architect":  4096,
            "coder":      16384,
            "critic":     4096,
            "optimizer":  4096,
            "researcher": 4096,
            "coder_fast": 16384,
            "executor":   4096,
        }
    },
}

# Pricing (USD per 1M tokens)
PRICING = {
    GPT4O_MINI:                              {"input": 0.15,  "output": 0.60},
    GPT_OSS_120B:                            {"input": 0.039, "output": 0.19},
    "blackboxai/anthropic/claude-sonnet-4.6": {"input": 3.0,  "output": 15.0},
    "blackboxai/anthropic/claude-haiku-4.5":  {"input": 0.8,  "output": 4.0},
    "blackboxai/moonshotai/kimi-k2:free":     {"input": 0.0,  "output": 0.0},
    "blackboxai/mistralai/codestral-2508":    {"input": 0.3,  "output": 0.9},
    "blackboxai/qwen/qwen3-coder:free":       {"input": 0.0,  "output": 0.0},
    "blackboxai/mistralai/devstral-small":    {"input": 0.1,  "output": 0.3},
    "deepseek/deepseek-v3-0324:free":        {"input": 0.0,   "output": 0.0},
    "bytedance-seed/seed-2.0-mini":          {"input": 0.10,  "output": 0.40},
    LLAMA_70B_GROQ:                          {"input": 0.0,   "output": 0.0},   # Groq free
    QWEN3_CODER_NEXT:                        {"input": 0.12,  "output": 0.75},  # Qwen3 Coder Next
    QWEN3_235B:                              {"input": 0.071, "output": 0.10},  # Qwen3 235B
    GLM_4_7_FLASH:                           {"input": 0.06,  "output": 0.40},  # GLM 4.7 Flash
    CODESTRAL_2508:                          {"input": 0.30,  "output": 0.90},  # Codestral 2508
    KIMI_K2_THINKING:                        {"input": 0.47,  "output": 2.00},  # Kimi K2 Thinking
    # MINIMAX_M25:                          {"input": 0.295, "output": 1.20},  # MiniMax M2.5
    MINIMAX_M21:                             {"input": 0.295, "output": 1.20},  # MiniMax M2.1
    GEMINI_FLASH_LITE:                       {"input": 0.25,  "output": 1.50},  # Gemini 3.1 Flash Lite
    VERTEX_GEMINI_20_FLASH_001:              {"input": 0.0,   "output": 0.0},
    VERTEX_GEMINI_20_FLASH_LITE:             {"input": 0.0,   "output": 0.0},
    STEP_35_FLASH:                           {"input": 0.10, "output": 0.30},  # StepFun Step-3.5-Flash
    "gemini-2.5-flash":                      {"input": 0.15, "output": 0.60},  # Gemini 2.5 Flash
}



