"""
agents/planner_agent.py
PlannerAgent: Breaks down complex user goals into executable subtasks.
"""
import json
import uuid
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus

SYSTEM_PROMPT = """You are the Planner agent inside MAOS — Multi-Agent Orchestration System.

Your job is to take a user goal and produce a structured, executable task plan. You do not write code. You do not do research. You think about what needs to happen and in what order.

## Core Responsibility

Given a goal, produce a task plan the orchestrator can execute. Every task must be concrete, scoped, and assignable to a specific agent (researcher, coder, critic, executor).

Vague tasks like "implement the backend" are not acceptable. Break them down until each task is something a single agent can complete in one pass.

## Plan Types

For small, well-defined goals: produce a flat task list.
For large or multi-phase goals: produce a phased plan. Phases are sequential. Tasks within a phase may be parallel.

## Task Structure

Each task must include:
- id: unique identifier (e.g., p1_t1)
- description: what needs to be done, in one or two sentences
- agent: which agent handles this (researcher, coder, coder_fast, executor)
- depends_on: list of task IDs that must complete first
- context_needed: what information this task needs from previous tasks

## Behavior Principles

Do not over-plan. A plan with thirty tasks for a simple goal is a bad plan. Aim for the minimum number of tasks that correctly covers the goal.

Do not under-plan. Missing a critical step — like forgetting tests or skipping environment setup — will cause downstream failures.

If the goal is genuinely unclear in a way that would produce two very different plans, flag it. Return a clarification request with the specific question that needs answering.

Think about failure modes. If a task is likely to fail or produce variable output, plan for a review or retry step after it.

## Output Format

Return your plan as structured JSON only. No prose around it.

Example phased plan:
{
  "type": "phased",
  "goal_summary": "one sentence summary",
  "phases": [
    {
      "phase_id": "p1",
      "name": "Veri Katmanı",
      "tasks": [
        {
          "id": "p1_t1",
          "description": "Research best Python libraries for PDF parsing",
          "agent": "researcher",
          "depends_on": [],
          "context_needed": []
        },
        {
          "id": "p1_t2",
          "description": "Write PDF parser module using selected library",
          "agent": "coder",
          "depends_on": ["p1_t1"],
          "context_needed": ["p1_t1.output"]
        }
      ]
    }
  ]
}

Clarification request format:
{
  "type": "clarification",
  "questions": [
    "Should the output be a REST API or a CLI tool?"
  ]
}
"""


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
        return ThoughtProcess(
            reasoning="Plan üretimi act() içinde tek LLM çağrısıyla yapılacak.",
            plan=[task.description],
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
                    task_id=t.get("task_id") or t.get("id") or str(uuid.uuid4())[:8],
                    description=t.get("description", ""),
                    assigned_to=t.get("assigned_to") or t.get("agent", "coder"),
                    dependencies=t.get("dependencies") or t.get("depends_on", []),
                    context={
                        "expected_output": t.get("expected_output", ""),
                        "context_needed": t.get("context_needed", []),
                    },
                    priority=priority_map.get(t.get("priority", "normal"), Priority.NORMAL),
                ))
            return result

        def _minimize_dependencies(raw_tasks: list) -> list:
            """Gereksiz zincir bağımlılıkları kırarak paralel çalışmayı artır."""
            if not isinstance(raw_tasks, list):
                return []

            task_ids = []
            for item in raw_tasks:
                if isinstance(item, dict) and item.get("task_id"):
                    task_ids.append(str(item.get("task_id")))
            valid_ids = set(task_ids)

            def _to_dep_list(value) -> list[str]:
                if isinstance(value, str):
                    deps = [value]
                elif isinstance(value, list):
                    deps = [str(v) for v in value if str(v).strip()]
                else:
                    deps = []
                # Order-preserving dedupe
                seen = set()
                normalized = []
                for dep in deps:
                    dep = str(dep).strip()
                    if not dep or dep in seen:
                        continue
                    seen.add(dep)
                    normalized.append(dep)
                return normalized

            hard_dep_keywords = (
                "test", "pytest", "calistir", "çalıştır", "run", "dogrula", "doğrula",
                "entegr", "integr", "birlestir", "birleştir", "merge", "paket", "build",
                "deploy", "düzelt", "duzelt", "fix", "refactor"
            )

            # 1) Normalize dependency ids
            for item in raw_tasks:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("task_id", "")).strip()
                deps = _to_dep_list(item.get("dependencies", []))
                deps = [dep for dep in deps if dep in valid_ids and dep != item_id]
                item["dependencies"] = deps

            # 2) Non-final tasks: drop soft dependencies unless clearly required
            for item in raw_tasks:
                if not isinstance(item, dict):
                    continue
                assigned = str(item.get("assigned_to", "")).lower()
                if assigned == "executor":
                    continue

                deps = item.get("dependencies", [])
                if not deps:
                    continue

                desc = str(item.get("description", "")).lower()
                has_hard_keyword = any(k in desc for k in hard_dep_keywords)
                explicitly_refs_dep = any(dep.lower() in desc for dep in deps)
                if not has_hard_keyword and not explicitly_refs_dep:
                    item["dependencies"] = []

            # 3) Executor/test tasks should depend on all producer tasks
            producer_ids = [
                str(item.get("task_id"))
                for item in raw_tasks
                if isinstance(item, dict) and str(item.get("assigned_to", "")).lower() != "executor"
            ]
            for item in raw_tasks:
                if not isinstance(item, dict):
                    continue
                assigned = str(item.get("assigned_to", "")).lower()
                if assigned != "executor":
                    continue

                desc = str(item.get("description", "")).lower()
                if any(k in desc for k in ("test", "pytest", "calistir", "çalıştır", "run", "doğrula", "dogrula")):
                    current = item.get("dependencies", [])
                    merged = []
                    seen = set()
                    for dep in current + producer_ids:
                        dep = str(dep).strip()
                        if not dep or dep in seen:
                            continue
                        seen.add(dep)
                        merged.append(dep)
                    item["dependencies"] = merged

            return raw_tasks

        parsed = {}
        task_objects = []
        phases = []

        for attempt in range(3):
            task_objects = []
            phases = []

            response_text = await self._call_llm(
                messages=messages,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=4000,  # Planner icin daha genis ama kontrollu alan
            )

            # Check if response is None
            if response_text is None:
                print(f"[Planner] LLM None döndürdü (deneme {attempt+1}), tekrar deneniyor...")
                await asyncio.sleep(1)
                continue

            # Thinking modeller <think>...</think> blogu cikariyor — bunlari temizle
            import re
            clean_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL).strip()
            if clean_text != response_text:
                print(f"[Planner] Thinking blogu temizlendi ({len(response_text)-len(clean_text)} karakter)")

            parsed = self._parse_json_response(clean_text)

            # Qwen3/Kimi gibi modeller zaman zaman JSON yerine duz metin dondurur
            if not isinstance(parsed, dict):
                print(f"[Planner] JSON parse basarisiz (deneme {attempt+1}), tekrar deneniyor...")
                messages = messages[:-1] + [{
                    "role": "user",
                    "content": messages[-1]["content"] + "\n\nKRITIK: Yalnizca gecerli JSON dondur. Hicbir aciklama, markdown veya metin ekleme. Sadece { ile baslayan JSON."
                }]
                await asyncio.sleep(1)
                continue

            raw_phases = parsed.get("phases") if isinstance(parsed.get("phases"), list) else []

            if raw_phases:
                # Build phase objects
                flattened_phase_tasks = []
                for ph in raw_phases:
                    raw_phase_tasks = _minimize_dependencies(ph.get("tasks", []))
                    ph["tasks"] = raw_phase_tasks
                    phase_tasks = _make_tasks(raw_phase_tasks)
                    if phase_tasks:
                        flattened_phase_tasks.extend(phase_tasks)
                        phases.append({
                            "phase_id": ph.get("phase_id", f"phase_{len(phases)+1}"),
                            "name": ph.get("name", f"Faz {len(phases)+1}"),
                            "goal": ph.get("goal", ""),
                            "depends_on_phase": ph.get("depends_on_phase", None),
                            "tasks": phase_tasks,
                        })
                if phases:
                    task_objects = flattened_phase_tasks
                    break
            else:
                # Flat mode
                raw_flat_tasks = _minimize_dependencies(parsed.get("tasks", []))
                parsed["tasks"] = raw_flat_tasks
                task_objects = _make_tasks(raw_flat_tasks)
                if task_objects:
                    phases = []
                    break

            if not task_objects and not phases:
                print(f"[Planner] Empty plan (deneme {attempt+1}), tekrar deneniyor...")
                if attempt == 2:
                    raise ValueError("Empty plan, retrying...")

                messages = messages[:-1] + [{
                    "role": "user",
                    "content": messages[-1]["content"] + "\n\nKRITIK: Bos plan dondurme. En az bir task veya en az bir phase/task uret."
                }]
                await asyncio.sleep(1)
                continue

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

    async def _reflect(self, task: Task, response: AgentResponse) -> str:
        """Planner reflection çağrısını küçük tut."""
        try:
            reflection_prompt = (
                f"Task: {task.description}\n\n"
                f"Plan output: {str(response.content)[:400]}\n\n"
                "1 kısa cümlede plan yeterli mi söyle."
            )
            return await self._call_llm(
                messages=[{"role": "user", "content": reflection_prompt}],
                system_prompt="Kısa ve net değerlendir.",
                temperature=0.1,
                max_tokens=50,
            )
        except Exception:
            return "Reflection unavailable."

    async def create_plan(self, goal: str) -> dict:
        """
        Sadece plan üret, çalıştırma.
        Kullanıcıya gösterilmek üzere plan döndür.
        
        Returns:
            dict: Plan JSON'u (tasks, phases, mode, vb.)
        """
        task = Task(
            task_id="plan_preview",
            description=goal,
            assigned_to="planner",
            context={},
        )
        
        response = await self.act(ThoughtProcess(
            reasoning="Plan oluşturuluyor",
            plan=[],
            tool_calls=[],
            confidence=0.9
        ), task)
        
        return response.content if response.success else {}

