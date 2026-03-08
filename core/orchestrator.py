"""
core/orchestrator.py
The brain of the multi-agent system.
Coordinates all agents using a ReAct loop with dynamic re-planning,
parallel execution, and human-in-the-loop support.
"""
import asyncio
import uuid
from typing import Any, Callable, Optional

from core.base_agent import AgentResponse, Task
from core.memory import memory_manager
from core.message_bus import Message, MessageBus, MessageType, Priority, bus

MAX_ITERATIONS = 10
CONFIDENCE_THRESHOLD = 0.6


class TaskStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskRecord:
    """Tracks the state of a task during execution."""

    def __init__(self, task: Task):
        self.task = task
        self.status = TaskStatus.PENDING
        self.result: Optional[AgentResponse] = None
        self.attempts: int = 0
        self.max_attempts: int = 3


class Orchestrator:
    """
    Master controller that routes tasks to agents, manages execution,
    and aggregates results. Implements ReAct: Reason → Act → Observe → Reason...
    """

    def __init__(
        self,
        agents: dict,  # {agent_id: BaseAgent}
        message_bus: Optional[MessageBus] = None,
        human_input_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None,
    ):
        self.agents = agents
        self._bus = message_bus or bus
        self._human_input_callback = human_input_callback
        self._status_callback = status_callback
        self._task_records: dict[str, TaskRecord] = {}
        self._session_id = str(uuid.uuid4())[:8]
        self._iteration = 0
        self.project_context: Optional[dict] = None
        self.current_project_path: str = ""
        self.shared_context: str = ""

    def set_project_context(self, project_index: dict):
        """Mevcut proje bağlamını sisteme yükle. /open komutu ile kullanılır."""
        self.project_context = project_index
        self.current_project_path = project_index.get("path", "")

        files_summary = []
        for rel_path, content in project_index.get("files", {}).items():
            lines = len(content.splitlines())
            files_summary.append(f"  - {rel_path} ({lines} satır)")

        self.shared_context = (
            f"\nMEVCUT PROJE YÜKLÜ: {project_index.get('summary', '')}\n"
            f"KLASÖR YAPISI:\n{project_index.get('structure', '')}\n"
            f"DOSYALAR:\n" + "\n".join(files_summary) + "\n"
            f"TALİMAT:\n"
            f"- Yeni dosya oluşturma, mevcut dosyaları düzenle\n"
            f"- Değişiklik yaparken replace_in_file veya replace_lines kullan\n"
            f"- Proje yolu: {project_index.get('path', '')}\n"
        )
        print(f"[Orchestrator] Proje bağlamı yüklendi: {len(project_index.get('files', {}))} dosya")

    def _log(self, msg: str):
        if self._status_callback:
            asyncio.get_event_loop().call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._status_callback(msg))
            )
        print(f"[Orchestrator] {msg}")

    async def _emit_status(self, msg: str):
        if self._status_callback:
            await self._status_callback(msg)
        else:
            print(f"[Orchestrator] {msg}")

    async def run(self, user_goal: str) -> dict:
        """
        Main entry point. Accepts user goal and runs the full multi-agent pipeline.
        Returns aggregated final result.
        """
        import re
        import os
        from datetime import datetime, timezone

        # 1. Görev adından slug üret
        slug = re.sub(r'[^a-z0-9]+', '-', user_goal.lower()).strip('-')
        if not slug:
            slug = "default"
        slug = slug[:40]
        self.current_project_slug = slug

        # 2. & 3. workspace/projects/{slug}/ klasörünü ve alt klasörleri oluştur
        project_dir = os.path.join("workspace", "projects", slug)
        os.makedirs(os.path.join(project_dir, "src"), exist_ok=True)
        os.makedirs(os.path.join(project_dir, "tests"), exist_ok=True)
        os.makedirs(os.path.join(project_dir, "docs"), exist_ok=True)
        plan_json_path = os.path.join(project_dir, "plan.json")
        if not os.path.exists(plan_json_path):
            with open(plan_json_path, "w", encoding="utf-8") as f:
                f.write("{}")

        await self._emit_status(f"Starting session {self._session_id}")
        await self._emit_status(f"Goal: {user_goal}")
        await self._emit_status(f"Workspace: {project_dir}")

        # Son 3 session okuma
        last_sessions = memory_manager.get_last_sessions(limit=3)
        past_context = ""
        if last_sessions:
            past_context = "\n\n--- PAST SESSIONS CONTEXT ---\n"
            for s in last_sessions:
                past_context += f"- Goal: {s.get('goal', '')} (Success: {len(s.get('errors_encountered', [])) == 0})\n"

        # Step 1: Plan (Pass past context + project context)
        plan_input = user_goal + past_context
        if self.shared_context:
            plan_input = user_goal + "\n" + self.shared_context + past_context
        plan = await self._plan(plan_input)
        if not plan:
            return {"success": False, "error": "Planning failed", "output": None}

        # ── Phased or flat execution ──────────────────────────────────────
        phases = plan.get("phases", [])
        mode = plan.get("mode", "flat")

        if mode == "phased" and phases:
            await self._emit_status(f"🗂️  Phased plan: {len(phases)} phases detected")
            return await self._run_phases(
                phases=phases,
                user_goal=user_goal,
                project_dir=project_dir,
                slug=slug,
                session_id=self._session_id,
            )

        # ── Flat execution (original path) ────────────────────────────────
        tasks: list[Task] = plan.get("tasks", [])
        if not tasks:
            return {"success": False, "error": "No tasks generated from plan", "output": None}

        await self._emit_status(f"Plan generated: {len(tasks)} tasks")

        # Step 2: Initialize task records
        for task in tasks:
            self._task_records[task.task_id] = TaskRecord(task)

        # Step 3: Execute with ReAct loop
        final_results = await self._react_loop(tasks, user_goal)

        # Step 4: Aggregate results
        final_output = await self._aggregate_results(final_results, user_goal)

        # Session kaydetme
        try:
            from datetime import datetime, timezone
            from core.llm_client import token_tracker
            
            all_usage = token_tracker.get_all()
            total_in = sum(d.get("prompt_tokens", 0) for d in all_usage.values())
            total_out = sum(d.get("completion_tokens", 0) for d in all_usage.values())
            total_cost = token_tracker.estimated_cost_usd()
            
            session_data = {
                "session_id": self._session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "goal": user_goal,
                "tasks_completed": [t.task_id for t in tasks if self._task_records[t.task_id].status == TaskStatus.COMPLETED],
                "errors_encountered": [t.task_id for t in tasks if self._task_records[t.task_id].status == TaskStatus.FAILED],
                "models_used": {
                    agent: self.agents[agent]._llm.model_key 
                    for agent in self.agents if hasattr(self.agents[agent], '_llm')
                },
                "tokens_used": {"input": total_in, "output": total_out},
                "cost_usd": total_cost,
                "agent_breakdown": all_usage
            }
            # Save session memory to project folder
            memory_manager.save_session(session_data, slug)

            # ── Per-project TXT raporu ────────────────────────────────────
            try:
                self._write_project_summary_txt(
                    project_dir=project_dir,
                    slug=slug,
                    user_goal=user_goal,
                    tasks=tasks,
                    session_data=session_data,
                    final_results=final_results,
                )
            except Exception as e:
                self._log(f"project_summary.txt yazılamadı: {e}")
            # ─────────────────────────────────────────────────────────────

            summary_msg = f"🏁 Session Complete! Tokens: {total_in} in / {total_out} out | Cost: ${total_cost:.4f}"
            self._log(summary_msg)
            await self._emit_status(summary_msg)

        except Exception as e:
            self._log(f"Failed to save session memory: {e}")

        return final_output

    async def _run_phases(
        self,
        phases: list[dict],
        user_goal: str,
        project_dir: str,
        slug: str,
        session_id: str,
    ) -> dict:
        """Run each phase sequentially, passing created files as context to the next."""
        all_results = []
        existing_files: list[str] = []   # files created so far
        all_tasks: list[Task] = []

        for phase_idx, phase in enumerate(phases):
            phase_name = phase.get("name", f"Faz {phase_idx + 1}")
            tasks: list[Task] = phase.get("tasks", [])
            pip_packages = phase.get("pip_packages", [])
            pip_packages = [p for p in pip_packages if p != 'src']

            await self._emit_status(
                f"📦 [{phase_idx+1}/{len(phases)}] {phase_name} başlıyor — {len(tasks)} görev"
            )

            # Inject existing_files context into every task of this phase
            if existing_files:
                file_list = ", ".join(existing_files)
                for t in tasks:
                    t.context["existing_files"] = file_list
                    t.context["phase_info"] = (
                        f"Bu faz '{phase_name}'. "
                        f"Onceki fazlarda oluşturulan dosyalar: {file_list}. "
                        f"Bu dosyaları import et, tekrar yazma."
                    )

            # Register task records
            for task in tasks:
                self._task_records[task.task_id] = TaskRecord(task)
                task.context["project_slug"] = slug
                task.context["pip_packages"] = pip_packages

            # Check for circular dependencies within the same phase
            phase_task_ids = {t.task_id for t in tasks}
            for task in tasks:
                if task.dependencies:
                    # Check if any dependency is in the same phase and still pending
                    circular_deps = []
                    for dep_id in task.dependencies:
                        if dep_id in phase_task_ids:
                            # Dependency is in the same phase
                            dep_record = self._task_records.get(dep_id)
                            if dep_record and dep_record.status == TaskStatus.PENDING:
                                circular_deps.append(dep_id)
                    
                    # If circular dependency detected, clear dependencies
                    if circular_deps:
                        self._log(f"⚠️ Circular dependency detected for task {task.task_id}: {circular_deps}. Clearing dependencies.")
                        task.dependencies = []

            # Execute phase
            phase_results = await self._react_loop(tasks, user_goal)
            all_results.extend(phase_results)
            all_tasks.extend(tasks)

            # Collect files created in this phase
            for r in phase_results:
                saved = r.get("result", {})
                if isinstance(saved, dict):
                    for f in saved.get("saved_files", []):
                        fname = f.split("/")[-1].replace(" (fixed)", "")
                        if fname not in existing_files:
                            existing_files.append(fname)

            await self._emit_status(
                f"✅ {phase_name} tamamlandı — toplam dosya: {len(existing_files)}"
            )

        # Aggregate final output
        final_output = await self._aggregate_results(all_results, user_goal)

        # Save session
        try:
            from datetime import datetime, timezone
            from core.llm_client import token_tracker

            all_usage = token_tracker.get_all()
            total_in = sum(d.get("prompt_tokens", 0) for d in all_usage.values())
            total_out = sum(d.get("completion_tokens", 0) for d in all_usage.values())
            total_cost = token_tracker.estimated_cost_usd()

            session_data = {
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "goal": user_goal,
                "mode": "phased",
                "phase_count": len(phases),
                "tasks_completed": [
                    t.task_id for t in all_tasks
                    if self._task_records.get(t.task_id, TaskRecord(t)).status == TaskStatus.COMPLETED
                ],
                "errors_encountered": [
                    t.task_id for t in all_tasks
                    if self._task_records.get(t.task_id, TaskRecord(t)).status == TaskStatus.FAILED
                ],
                "tokens_used": {"input": total_in, "output": total_out},
                "cost_usd": total_cost,
                "agent_breakdown": all_usage,
            }
            memory_manager.save_session(session_data, slug)

            try:
                self._write_project_summary_txt(
                    project_dir=project_dir,
                    slug=slug,
                    user_goal=user_goal,
                    tasks=all_tasks,
                    session_data=session_data,
                    final_results=all_results,
                )
            except Exception as e:
                self._log(f"project_summary.txt yazılamadı: {e}")

            msg = (
                f"🏁 Phased Complete! {len(phases)} faz | "
                f"Tokens: {total_in}/{total_out} | Cost: ${total_cost:.4f}"
            )
            self._log(msg)
            await self._emit_status(msg)

        except Exception as e:
            self._log(f"Phase session save failed: {e}")

        return final_output

    async def _plan(self, user_goal: str) -> Optional[dict]:
        """Use the planner agent to decompose the goal."""
        planner = self.agents.get("planner")
        if not planner:
            return None

        await self._emit_status("🧠 PlannerAgent: Decomposing goal...")
        plan_task = Task(
            task_id="plan_root",
            description=user_goal,
            assigned_to="planner",
        )

        try:
            response = await planner.run(plan_task)
            if response.success and response.content:
                return response.content
            else:
                await self._emit_status(f"Planning failed internally: {response.error}")
        except Exception as e:
            import traceback
            print("\n" + "="*50)
            print(f"CRITICAL PLANNER ERROR: {str(e)}")
            traceback.print_exc()
            print("="*50 + "\n")
            await self._emit_status(f"Planning error: {e}")
        return None

    async def _react_loop(self, tasks: list[Task], user_goal: str) -> list[dict]:
        """
        ReAct loop: Reason → Act → Observe → Reason...
        Handles dependencies, parallel execution, and re-planning.
        """
        results = []
        completed_ids: set[str] = set()
        self._iteration = 0

        while self._iteration < MAX_ITERATIONS:
            self._iteration += 1
            await self._emit_status(f"⚙️  Iteration {self._iteration}/{MAX_ITERATIONS}")

            # Find tasks ready to execute (all dependencies satisfied)
            ready_tasks = [
                t for t in tasks
                if t.task_id not in completed_ids
                and self._task_records[t.task_id].status == TaskStatus.PENDING
                and all(dep in completed_ids for dep in t.dependencies)
            ]

            if not ready_tasks:
                if all(self._task_records[t.task_id].status == TaskStatus.COMPLETED for t in tasks):
                    await self._emit_status("✅ All tasks completed!")
                    break
                elif all(
                    self._task_records[t.task_id].status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)
                    for t in tasks
                ):
                    await self._emit_status("⚠️  All tasks settled (some may have failed).")
                    break
                else:
                    await asyncio.sleep(0.5)
                    continue

            # Enrich tasks with context from completed results
            for task in ready_tasks:
                await self._enrich_task_context(task, results)
                task.context["project_slug"] = self.current_project_slug

            # Execute ready tasks (parallel)
            await self._emit_status(
                f"🚀 Executing {len(ready_tasks)} task(s) in parallel: "
                f"{[t.task_id for t in ready_tasks]}"
            )
            batch_results = await asyncio.gather(
                *[self._execute_task(task) for task in ready_tasks],
                return_exceptions=True,
            )

            for task, result in zip(ready_tasks, batch_results):
                record = self._task_records[task.task_id]
                if isinstance(result, Exception):
                    record.status = TaskStatus.FAILED
                    record.result = None
                    await self._emit_status(f"❌ Task {task.task_id} failed: {result}")
                else:
                    record.result = result
                    if result and result.success:
                        record.status = TaskStatus.COMPLETED
                        completed_ids.add(task.task_id)
                        results.append({
                            "task_id": task.task_id,
                            "agent": task.assigned_to,
                            "description": task.description,
                            "result": result.content,
                            "success": True,
                        })
                        await self._emit_status(f"✅ Task {task.task_id} completed by {task.assigned_to}")
                    else:
                        record.attempts += 1
                        if record.attempts >= record.max_attempts:
                            record.status = TaskStatus.FAILED
                            completed_ids.add(task.task_id)
                            await self._emit_status(f"❌ Task {task.task_id} failed after {record.max_attempts} attempts")
                        else:
                            record.status = TaskStatus.PENDING
                            err_str = str(result.error) if result and result.error else ""
                            
                            if "ModuleNotFoundError" in err_str or "ImportError" in err_str:
                                task.context["fix_hint"] = "PATH_ERROR: Use sys.path.insert(0, str(Path(__file__).parent.parent / 'src')) for tests"
                            elif "FileNotFoundError" in err_str:
                                self._ensure_directories(task)
                                task.context["fix_hint"] = "FILE_ERROR: Directory was missing, now created. Use Path(__file__).parent / 'filename'."
                            elif "PermissionError" in err_str:
                                task.context["fix_hint"] = "PERMISSION_ERROR: Only write to workspace/ directory"
                                
                            await self._emit_status(f"🔄 Task {task.task_id} retrying (attempt {record.attempts})")

        return results

    def _ensure_directories(self, task: Task):
        """Task'ın proje klasörlerini garanti et"""
        slug = task.context.get("project_slug", "default")
        from tools.file_manager import ensure_project_structure
        ensure_project_structure(slug)

    async def _execute_task(self, task: Task) -> Optional[AgentResponse]:
        """Route a task to the appropriate agent and execute it."""
        record = self._task_records[task.task_id]
        record.status = TaskStatus.IN_PROGRESS

        agent = self.agents.get(task.assigned_to)
        if not agent:
            # Try to find best-fit agent from capabilities
            agent = self._find_best_agent(task)
            if not agent:
                return AgentResponse(
                    content=None,
                    success=False,
                    error=f"No agent available for: {task.assigned_to}",
                )

        await self._emit_status(f"🤖 {agent.name} working on: {task.description[:60]}...")

        # Check if confidence is too low (human-in-the-loop)
        response = await agent.run(task)

        # Send to critic for review if the task produces content
        if response.success and response.content and task.assigned_to in ("coder", "researcher"):
            response = await self._critic_review(task, response)

        return response

    async def _critic_review(self, task: Task, response: AgentResponse) -> AgentResponse:
        """Have the critic review a response. If score < 7, request revision."""
        critic = self.agents.get("critic")
        if not critic:
            return response

        content = response.content
        if isinstance(content, dict):
            content_str = str(content.get("code_response") or content.get("synthesis") or content)
        else:
            content_str = str(content)

        revision_count = 0
        while revision_count < 3:
            review_task = Task(
                task_id=f"review_{task.task_id}_{revision_count}",
                description=f"Review output for: {task.description}",
                assigned_to="critic",
                context={
                    "content": content_str[:2000],
                    "content_type": "code" if task.assigned_to == "coder" else "research",
                    "original_task": task.description,
                    "revision_count": revision_count,
                },
            )
            review_response = await critic.run(review_task)
            if review_response.success:
                review_data = review_response.content or {}
                
                routing = review_data.get("routing", "EXECUTOR")
                score = review_data.get("score", 10)
                
                await self._emit_status(f"🔍 Critic score: {score}/10 — Routing: {routing}")

                if routing in ["EXECUTOR", "EXECUTOR_ANYWAY"]:
                    response.metadata["critic_score"] = score
                    response.metadata["critic_verdict"] = routing
                    return response
                elif routing == "PLANNER_REPLAN":
                    response.metadata["critic_score"] = score
                    response.metadata["critic_verdict"] = routing
                    response.success = False
                    response.error = "Critic rejected the approach (score < 4), replan required."
                    return response

                # Otherwise it's CODER_REVISE
                revision_count += 1
                agent = self.agents.get(task.assigned_to)
                if agent:
                    issues = "\n- ".join(review_data.get("issues", []))
                    suggestions = "\n- ".join(review_data.get("suggestions", []))
                    revision_instructions = f"Issues:\n- {issues}\nSuggestions:\n- {suggestions}"
                    
                    revised_task = Task(
                        task_id=f"{task.task_id}_rev{revision_count}",
                        description=f"{task.description}\n\nRevision required: {revision_instructions}",
                        assigned_to=task.assigned_to,
                        context=task.context,
                    )
                    response = await agent.run(revised_task)
                    if isinstance(response.content, dict):
                        content_str = str(response.content.get("code_response") or response.content.get("synthesis") or response.content)
                    else:
                        content_str = str(response.content)
            else:
                break

        return response

    def _find_best_agent(self, task: Task) -> Any:
        """Find best agent by matching task keywords to capabilities."""
        task_lower = task.description.lower()
        scores = {}
        for agent_id, agent in self.agents.items():
            if agent_id == "planner":
                continue
            score = sum(1 for cap in agent.capabilities if cap.lower() in task_lower)
            scores[agent_id] = score
        if scores:
            best_id = max(scores, key=scores.get)
            if scores[best_id] > 0:
                return self.agents[best_id]
        # Fallback to coder
        return self.agents.get("coder")

    async def _enrich_task_context(self, task: Task, results: list[dict]):
        """Add relevant completed results to task context."""
        # Add research context to coder tasks
        if task.assigned_to == "coder":
            research_results = [
                r for r in results if r.get("agent") == "researcher" and r.get("success")
            ]
            if research_results:
                task.context["research"] = str(research_results[-1].get("result", ""))

        # Executor'a TÜM önceki sonuçları ver
        if task.assigned_to == "executor":
            pip_packages = task.context.get("pip_packages", [])
            pip_packages = [p for p in pip_packages if p != 'src']
            task.context["pip_packages"] = pip_packages

            all_results = {}
            for r in results:
                result_data = r.get("result", {})
                all_results[r["task_id"]] = result_data
            task.context["all_previous_results"] = all_results
            
            # En son coder çıktısını bul
            coder_results = [
                r for r in results
                if r.get("agent") == "coder" and r.get("success")
            ]
            if coder_results:
                latest = coder_results[-1].get("result", {})
                if isinstance(latest, dict):
                    task.context["coder_output"] = (
                        latest.get("code") or
                        latest.get("content") or
                        str(latest)
                    )
                    task.context["filename"] = latest.get(
                        "filename", "script.py"
                    )
                else:
                    task.context["coder_output"] = str(latest)
                    task.context["filename"] = "script.py"

        # Add general context summary
        task.context["completed_tasks"] = [
            {"task_id": r["task_id"], "description": r["description"]}
            for r in results
        ]

    async def _aggregate_results(self, results: list[dict], user_goal: str) -> dict:
        """Combine all agent outputs into a final coherent answer."""
        if not results:
            return {"success": False, "output": "No results produced", "tasks_completed": 0}

        # Build summary using LLM
        from core.llm_client import LLMClient
        llm = LLMClient(agent_id="orchestrator")

        results_summary = "\n\n".join(
            f"Task: {r['description']}\nAgent: {r['agent']}\nResult: {str(r.get('result', ''))[:500]}"
            for r in results
        )

        aggregation_prompt = (
            f"User goal: {user_goal}\n\n"
            f"Completed tasks and results:\n{results_summary}\n\n"
            "Synthesize these results into a clear, comprehensive final answer for the user. "
            "Be specific, include file locations where relevant, and summarize what was accomplished."
        )

        try:
            final_answer = await llm.complete(
                messages=[{"role": "user", "content": aggregation_prompt}],
                system_prompt="You are the final synthesizer. Provide a clear, actionable summary of what was accomplished.",
                temperature=0.4,
                max_tokens=2000,
            )
        except Exception as e:
            final_answer = f"Results gathered. Error during synthesis: {e}"

        return {
            "success": True,
            "output": final_answer,
            "tasks_completed": len(results),
            "task_details": results,
            "session_id": self._session_id,
            "iterations": self._iteration,
        }

    def get_agent_statuses(self) -> list[dict]:
        """Return current status of all agents for UI display."""
        return [agent.get_status_dict() for agent in self.agents.values()]

    def get_task_progress(self) -> dict:
        """Return task completion progress."""
        total = len(self._task_records)
        completed = sum(1 for r in self._task_records.values() if r.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in self._task_records.values() if r.status == TaskStatus.FAILED)
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": total - completed - failed,
            "progress_pct": round((completed / total * 100) if total > 0 else 0, 1),
        }

    def _write_project_summary_txt(
        self,
        project_dir: str,
        slug: str,
        user_goal: str,
        tasks: list,
        session_data: dict,
        final_results: list,
    ) -> None:
        """Write a human-readable project_summary.txt into the project folder."""
        import os
        from datetime import datetime
        from pathlib import Path

        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        txt_path = os.path.join(project_dir, "project_summary.txt")

        # Gather file info from src/ and tests/
        src_dir = Path(project_dir) / "src"
        tests_dir = Path(project_dir) / "tests"
        src_files = [f.name for f in src_dir.glob("*.py")] if src_dir.exists() else []
        test_files = [f.name for f in tests_dir.glob("*.py")] if tests_dir.exists() else []

        # Token / cost info
        total_in = session_data.get("tokens_used", {}).get("input", 0)
        total_out = session_data.get("tokens_used", {}).get("output", 0)
        cost = session_data.get("cost_usd", 0)

        # Task breakdown
        completed_ids = session_data.get("tasks_completed", [])
        failed_ids = session_data.get("errors_encountered", [])

        lines = [
            "=" * 68,
            "  PROJE RAPORU",
            f"  Olusturulma : {now}",
            f"  Oturum ID  : {session_data.get('session_id', '-')}",
            "=" * 68,
            "",
            f"  HEDEF: {user_goal}",
            "",
            "-" * 68,
            "  GOREV OZETI",
            "-" * 68,
        ]

        for task in tasks:
            tid = task.task_id
            agent = task.assigned_to
            desc = task.description[:65]
            if tid in completed_ids:
                status = "[OK]"
            elif tid in failed_ids:
                status = "[HATA]"
            else:
                status = "[ATLANDI]"
            lines.append(f"  {status:<10} ({agent:<12}) {desc}")

        lines += [
            "",
            "-" * 68,
            "  URETILEN DOSYALAR",
            "-" * 68,
        ]

        if src_files:
            lines.append("  Kaynak (src/):")
            for f in src_files:
                lines.append(f"    • {f}")
        if test_files:
            lines.append("  Testler (tests/):")
            for f in test_files:
                lines.append(f"    • {f}")
        if not src_files and not test_files:
            lines.append("  (Dosya bulunamadi)")

        lines += [
            "",
            "-" * 68,
            "  PERFORMANS",
            "-" * 68,
            f"  Toplam Token   : {total_in + total_out:,}  ({total_in:,} girdi / {total_out:,} cikti)",
            f"  Tahmini Maliyet: ${cost:.6f} USD",
            f"  Iterasyon      : {self._iteration}",
            f"  Gorev          : {len(completed_ids)}/{len(tasks)} tamamlandi",
            "",
            "-" * 68,
            "  DOSYA KONUMU",
            "-" * 68,
            f"  {os.path.abspath(project_dir)}",
            "",
            "=" * 68,
        ]

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self._log(f"📄 project_summary.txt kaydedildi: {txt_path}")
