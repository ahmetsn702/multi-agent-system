"""
ClusterRunner: 2 farklı model ile aynı görevi paralel çalıştırır.
Judge Agent en iyi sonucu seçer.
"""
import asyncio
import copy
from pathlib import Path
from typing import Optional


class ClusterRunner:
    """İki cluster'ı paralel çalıştırır, Judge en iyisini seçer."""
    
    def __init__(self, orchestrator_class, llm_client_class, settings):
        self.orchestrator_class = orchestrator_class
        self.llm_client_class = llm_client_class
        self.settings = settings
    
    async def run(self, goal: str, slug_base: str) -> dict:
        """
        İki cluster'ı paralel çalıştır.
        
        Returns: En iyi cluster'ın sonucu
        """
        configs = [
            {
                "coder_model": "openai/gpt-oss-120b",
                "slug_suffix": "_cluster_a",
                "label": "Cluster A (gpt-oss-120b)",
            },
            {
                "coder_model": "x-ai/grok-4-fast",
                "slug_suffix": "_cluster_b",
                "label": "Cluster B (grok-4-fast)",
            },
        ]
        
        print(f"[ClusterRunner] 🚀 2 cluster paralel başlatılıyor...")
        print(f"[ClusterRunner] A: {configs[0]['coder_model']}")
        print(f"[ClusterRunner] B: {configs[1]['coder_model']}")
        
        # Paralel çalıştır
        tasks = [
            self._run_single(goal, slug_base + cfg["slug_suffix"], cfg)
            for cfg in configs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Hataları filtrele
        valid = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                print(f"[ClusterRunner] ❌ {configs[i]['label']} başarısız: {r}")
            else:
                valid.append(r)
        
        if not valid:
            raise RuntimeError("Her iki cluster da başarısız oldu!")
        
        if len(valid) == 1:
            print(f"[ClusterRunner] Tek geçerli sonuç kullanılıyor")
            return valid[0]
        
        # Judge: En iyi sonucu seç
        best = await self._judge(valid)
        print(f"[ClusterRunner] 🏆 Kazanan: {best.get('cluster_label', '?')}")
        return best
    
    async def _run_single(self, goal: str, slug: str, config: dict) -> dict:
        """Tek bir cluster çalıştır."""
        try:
            from core.message_bus import bus
            from agents.planner_agent import PlannerAgent
            from agents.researcher_agent import ResearcherAgent
            from agents.coder_agent import CoderAgent
            from agents.critic_agent import CriticAgent
            from agents.executor_agent import ExecutorAgent
            
            # Ajanları oluştur
            agents = {
                "planner": PlannerAgent(bus=bus),
                "researcher": ResearcherAgent(bus=bus),
                "coder": CoderAgent(agent_id="coder", bus=bus),
                "coder_fast": CoderAgent(agent_id="coder_fast", bus=bus),
                "critic": CriticAgent(bus=bus),
                "executor": ExecutorAgent(bus=bus),
            }
            
            # Orchestrator oluştur
            orch = self.orchestrator_class(agents=agents)
            
            # Coder modelini override et
            orch.coder_model_override = config["coder_model"]
            
            # Çalıştır (user_goal parametresi kullan)
            result = await orch.run(user_goal=goal)
            result["cluster_label"] = config["label"]
            result["cluster_model"] = config["coder_model"]
            result["project_slug"] = slug
            
            return result
        except Exception as e:
            raise RuntimeError(f"{config['label']} hatası: {e}")
    
    async def _judge(self, results: list) -> dict:
        """İki sonucu karşılaştır, en iyisini seç."""
        # Critic puanlarını karşılaştır
        scores = []
        for r in results:
            avg_score = r.get("avg_critic_score", 0)
            files_created = len(r.get("task_details", []))
            tasks_completed = r.get("tasks_completed", 0)
            cost = r.get("cost_usd", 999)
            
            # Composite skor: kalite + dosya sayısı - maliyet etkisi
            composite = (avg_score * 0.6) + (files_created * 0.3) + (tasks_completed * 0.1)
            scores.append(composite)
            
            print(
                f"[Judge] {r.get('cluster_label', '?')}: "
                f"Critic={avg_score:.1f} | Dosya={files_created} | "
                f"Composite={composite:.2f}"
            )
        
        best_idx = scores.index(max(scores))
        winner = results[best_idx]
        print(f"[Judge] 🏆 Kazanan composite skor: {scores[best_idx]:.2f}")
        
        return winner
