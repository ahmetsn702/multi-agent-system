# config/settings.py

# OpenRouter model IDs
GPT4O_MINI = "openai/gpt-4o-mini"

# Groq model IDs
LLAMA_70B_GROQ = "llama-3.3-70b-versatile"

# Provider Config — her provider'ın base URL ve env key bilgisi
PROVIDER_CONFIG = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "env_key": "OPENROUTER_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "env_key": "GROQ_API_KEY",
    },
}

# Model Routing Config — ajan → model + provider eşleştirmesi
MODEL_ROUTING = {
    "planner":    {"model": "openai/gpt-4o-mini",       "provider": "openrouter"},
    "researcher": {"model": "llama-3.3-70b-versatile",  "provider": "groq"},
    "coder":      {"model": "openai/gpt-4o-mini",       "provider": "openrouter"},
    "critic":     {"model": "anthropic/claude-sonnet-4-6", "provider": "openrouter"},
    "executor":   None,
}

# Token Budget — per-model limits
TOKEN_BUDGET = {
    "openai/gpt-4o-mini": {
        "max_input": 128000,
        "max_output": 4000,
        "per_agent": {
            "planner":    1500,
            "researcher": 1200,
            "coder":      4000,
            "critic":     600,
            "executor":   0,
        }
    },
    "llama-3.3-70b-versatile": {
        "max_input": 128000,
        "max_output": 4000,
        "per_agent": {
            "researcher": 1200,
            "critic":     600,
        }
    },
    "qwen/qwen3-30b-a3b": {
        "max_input": 32000,
        "max_output": 4000,
        "per_agent": {
            "planner": 1500,
        }
    },
    "anthropic/claude-sonnet-4-6": {
        "max_input": 200000,
        "max_output": 8000,
        "per_agent": {
            "critic": 600,
        }
    },
}

# Pricing (USD per 1M tokens)
PRICING = {
    "openai/gpt-4o-mini":       {"input": 0.15, "output": 0.60},
    "llama-3.3-70b-versatile":  {"input": 0.0,  "output": 0.0},   # Groq free
    "qwen/qwen3-30b-a3b":       {"input": 0.0,  "output": 0.0},   # Free via OpenRouter
    "anthropic/claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
}
