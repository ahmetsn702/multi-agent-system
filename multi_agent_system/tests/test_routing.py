"""
tests/test_routing.py
Verify MODEL_ROUTING maps each agent to a valid provider and model.
"""
import pytest
from config.settings import MODEL_ROUTING


VALID_PROVIDERS = {"vertex", "blackbox", "openrouter", "groq", "cerebras"}

EXPECTED_AGENTS = [
    "planner", "researcher", "architect", "coder", "coder_fast",
    "critic", "executor", "security", "optimizer", "docs",
    "tester", "linter", "builder", "ui_tester", "profiler",
    "analyzer", "orchestrator",
]


def test_routing_has_all_agents():
    """Every expected agent must have a routing entry."""
    for agent_id in EXPECTED_AGENTS:
        assert agent_id in MODEL_ROUTING, f"Missing routing for {agent_id}"


@pytest.mark.parametrize("agent_id", EXPECTED_AGENTS)
def test_routing_has_model(agent_id):
    """Each routing entry must have a non-empty model string."""
    entry = MODEL_ROUTING.get(agent_id)
    assert entry is not None, f"No routing for {agent_id}"
    assert "model" in entry, f"No model key for {agent_id}"
    assert isinstance(entry["model"], str) and len(entry["model"]) > 0


@pytest.mark.parametrize("agent_id", EXPECTED_AGENTS)
def test_routing_has_valid_provider(agent_id):
    """Each routing entry must have a recognized provider."""
    entry = MODEL_ROUTING[agent_id]
    provider = entry.get("provider", "")
    assert provider in VALID_PROVIDERS, f"Unknown provider '{provider}' for {agent_id}"


def test_vertex_agents_use_gemini():
    """Vertex provider agents should use gemini models."""
    for agent_id, entry in MODEL_ROUTING.items():
        if entry.get("provider") == "vertex":
            assert "gemini" in entry["model"].lower(), (
                f"{agent_id} uses vertex but model is '{entry['model']}'"
            )


def test_blackbox_agents_have_prefix():
    """Blackbox provider agents should have blackboxai/ prefix in model."""
    for agent_id, entry in MODEL_ROUTING.items():
        if entry.get("provider") == "blackbox":
            assert entry["model"].startswith("blackboxai/"), (
                f"{agent_id} uses blackbox but model '{entry['model']}' lacks prefix"
            )


def test_no_duplicate_models_same_provider():
    """Informational: check routing diversity — not all agents use the same model."""
    models = set()
    for entry in MODEL_ROUTING.values():
        models.add(entry["model"])
    # At minimum we should use more than 1 distinct model
    assert len(models) >= 2, "All agents route to the same model"
