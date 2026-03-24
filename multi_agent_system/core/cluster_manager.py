"""
ClusterManager: Cluster modunu yönetir.
main.py veya API'den çağrılır.
"""
import os
import re
from pathlib import Path


def should_use_clusters(goal: str) -> bool:
    """
    Cluster modu kullanılmalı mı?
    Uzun veya kritik görevler için True döner.
    """
    cluster_keywords = [
        "profesyonel", "production", "gerçek", "ciddi",
        "kapsamlı", "büyük", "tam", "complete", "full",
        "enterprise", "deploy", "canlı", "karmaşık",
        "advanced", "comprehensive"
    ]
    goal_lower = goal.lower()
    return any(kw in goal_lower for kw in cluster_keywords)


async def run_with_clusters(goal: str) -> dict:
    """Cluster modu ile çalıştır."""
    from core.orchestrator import Orchestrator
    from core.cluster_runner import ClusterRunner
    
    runner = ClusterRunner(
        orchestrator_class=Orchestrator,
        llm_client_class=None,
        settings=None,
    )
    
    slug_base = re.sub(r'[^\w-]', '-', goal[:40].lower())
    return await runner.run(goal=goal, slug_base=slug_base)
