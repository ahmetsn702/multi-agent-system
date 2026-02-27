"""
agents/planner_agent.py
PlannerAgent: Breaks down complex user goals into executable subtasks.
"""
import json
import uuid
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus

SYSTEM_PROMPT = """Sen kıdemli bir yazılım proje yöneticisisin.
Kullanıcının hedefini analiz edip uygulanabilir alt görevlere bölüyorsun.

──────────────────────────────────────────────
KÜÇÜK PROJE (1-3 özellik): Düz görev listesi döndür
──────────────────────────────────────────────
ÇIKTI:
{
  "mode": "flat",
  "analysis": "kısa analiz",
  "tasks": [
    {
      "task_id": "t1",
      "description": "Görev açıklaması",
      "assigned_to": "researcher|coder|executor",
      "dependencies": [],
      "priority": "high",
      "expected_output": "beklenen çıktı"
    }
  ],
  "execution_order": ["t1"],
  "parallel_groups": [["t1"]]
}

──────────────────────────────────────────────
BÜYÜK PROJE (4+ özellik / birden fazla katman): Fazlara böl
──────────────────────────────────────────────
Büyük projelerde her faz bağımsız çalışır ve önceki fazın dosyalarını kullanır.
Tipik faz düzeni:
  Faz 1: Veritabanı / backend katmanı
  Faz 2: GUI / API katmanı (Faz 1 dosyalarını import eder)
  Faz 3: Raporlar, testler, paketleme

ÇIKTI:
{
  "mode": "phased",
  "analysis": "projenin kısa analizi",
  "phases": [
    {
      "phase_id": "phase_1",
      "name": "Veritabani Katmani",
      "goal": "Bu fazın amacı",
      "tasks": [
        {
          "task_id": "p1_t1",
          "description": "Görev açıklaması",
          "assigned_to": "researcher|coder|executor",
          "dependencies": [],
          "priority": "high",
          "expected_output": "beklenen çıktı"
        }
      ]
    },
    {
      "phase_id": "phase_2",
      "name": "GUI Katmani",
      "goal": "Faz 1 dosyalarini kullanan arayuz",
      "depends_on_phase": "phase_1",
      "tasks": [...]
    }
  ]
}

GENEL KURALLAR:
1. Her fazda minimum 2, maksimum 4 görev olmalı.
2. Araştırma görevi ilk sırada (researcher).
3. Son görev her zaman executor (çalıştır/kaydet).
4. "assigned_to" sadece: researcher, coder, executor
5. SADECE JSON döndür — başka hiçbir şey yazma."""


class PlannerAgent(BaseAgent):
    """
    Decomposes user goals into ordered, dependency-mapped subtask lists.
    Does not use tools — logic only.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="planner",
            name="Planlayıcı Ajan",
            role="Strateji ve Ayrıştırma",
            description="Karmaşık kullanıcı hedeflerini uzman ajanlara atanmak üzere küçük, uygulanabilir alt görevlere böler.",
            capabilities=["task_decomposition", "dependency_mapping", "strategic_planning"],
            bus=bus,
        )

    async def think(self, task: Task) -> ThoughtProcess:
        """Reason about how to decompose the task."""
        context_messages = self.short_term_memory.get_messages()
        messages = context_messages + [
            {"role": "user", "content": f"Decompose this goal into subtasks:\n\n{task.description}"}
        ]

        response_text = await self._call_llm(
            messages=messages,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=2000,
        )

        parsed = self._parse_json_response(response_text)
        tasks = parsed.get("tasks", [])
        plan_steps = [t.get("description", "") for t in tasks]

        return ThoughtProcess(
            reasoning=parsed.get("analysis", "Analyzing task..."),
            plan=plan_steps,
            tool_calls=[],
            confidence=0.9,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """Generate a flat or phased task plan from the goal."""
        from core.message_bus import Priority
        import asyncio

        context_messages = self.short_term_memory.get_messages()
        messages = context_messages + [
            {"role": "user", "content": f"Decompose this goal into subtasks:\n\n{task.description}"}
        ]

        priority_map = {
            "low": Priority.LOW, "normal": Priority.NORMAL,
            "high": Priority.HIGH, "critical": Priority.CRITICAL,
        }

        def _make_tasks(raw_tasks: list) -> list:
            result = []
            for t in raw_tasks:
                result.append(Task(
                    task_id=t.get("task_id", str(uuid.uuid4())[:8]),
                    description=t.get("description", ""),
                    assigned_to=t.get("assigned_to", "coder"),
                    dependencies=t.get("dependencies", []),
                    context={"expected_output": t.get("expected_output", "")},
                    priority=priority_map.get(t.get("priority", "normal"), Priority.NORMAL),
                ))
            return result

        parsed = {}
        task_objects = []
        phases = []

        for attempt in range(3):
            response_text = await self._call_llm(
                messages=messages,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=2000,
            )
            parsed = self._parse_json_response(response_text)
            mode = parsed.get("mode", "flat")

            if mode == "phased" and parsed.get("phases"):
                # Build phase objects
                for ph in parsed["phases"]:
                    phase_tasks = _make_tasks(ph.get("tasks", []))
                    if phase_tasks:
                        phases.append({
                            "phase_id": ph.get("phase_id", f"phase_{len(phases)+1}"),
                            "name": ph.get("name", f"Faz {len(phases)+1}"),
                            "goal": ph.get("goal", ""),
                            "depends_on_phase": ph.get("depends_on_phase", None),
                            "tasks": phase_tasks,
                        })
                if phases:
                    # Expose first phase tasks as default tasks for orchestrator
                    task_objects = phases[0]["tasks"]
                    break
            else:
                # Flat mode
                task_objects = _make_tasks(parsed.get("tasks", []))
                if task_objects:
                    phases = []
                    break

            await asyncio.sleep(1)

        return AgentResponse(
            content={
                "tasks": task_objects,
                "phases": phases,          # non-empty = phased execution
                "mode": "phased" if phases else "flat",
                "raw_plan": parsed,
                "execution_order": parsed.get("execution_order", []),
                "parallel_groups": parsed.get("parallel_groups", []),
            },
            success=True,
            metadata={
                "task_count": len(task_objects),
                "phase_count": len(phases),
                "mode": "phased" if phases else "flat",
            },
        )

