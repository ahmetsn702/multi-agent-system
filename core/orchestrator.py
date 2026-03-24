"""
core/orchestrator.py
The brain of the multi-agent system.
Coordinates all agents using a ReAct loop with dynamic re-planning,
parallel execution, and human-in-the-loop support.
"""
import asyncio
import json
import re
import uuid
from typing import Any, Callable, Optional

from core.base_agent import AgentResponse, Task, emit_log_event
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
        self.state: str = "RUNNING"
        self.pending_questions: list[dict[str, Any]] = []
        self.user_answers: dict[str, str] = {}
        self.user_preferences_context: str = ""
        self._resume_event = asyncio.Event()
        self._resume_event.set()

    @staticmethod
    def _task_title(task: Task) -> str:
        maybe_title = None
        if isinstance(task.context, dict):
            maybe_title = task.context.get("title")
        return str(maybe_title or task.description or task.task_id)

    async def _run_agent_with_logs(self, agent_key: str, task: Task) -> AgentResponse:
        """Run a single agent task with pre/post live log events and token delta."""
        import time
        from core.llm_client import token_tracker

        agent = self.agents.get(agent_key)
        if not agent:
            return AgentResponse(
                content=None,
                success=False,
                error=f"No agent available for: {agent_key}",
            )

        task_title = self._task_title(task)
        before_tokens = int(token_tracker.get(agent_key).get("total_tokens", 0))

        await emit_log_event(
            agent_name=agent_key,
            stage="act",
            message=f"görev alındı: {task_title[:140]}",
            tokens_used=0,
        )

        started_at = time.perf_counter()
        try:
            response = await agent.run(task)
        except Exception as e:
            elapsed = time.perf_counter() - started_at
            await emit_log_event(
                agent_name=agent_key,
                stage="act",
                message=f"hata ({elapsed:.1f}s): {str(e)[:140]}",
                tokens_used=0,
            )
            raise

        elapsed = time.perf_counter() - started_at
        after_tokens = int(token_tracker.get(agent_key).get("total_tokens", 0))
        await emit_log_event(
            agent_name=agent_key,
            stage="act",
            message=f"tamamlandı ({elapsed:.1f}s)",
            tokens_used=max(0, after_tokens - before_tokens),
        )
        return response

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

    def get_state(self) -> str:
        return self.state

    def get_pending_questions(self) -> list[dict[str, Any]]:
        return [dict(q) for q in self.pending_questions]

    def get_user_answers(self) -> dict[str, str]:
        return dict(self.user_answers)

    def submit_clarification_answers(self, answers: dict[str, str]) -> tuple[bool, list[str]]:
        """Store user answers and resume execution when all pending questions are answered."""
        if self.state != "PAUSED" or not self.pending_questions:
            return False, []
        if not isinstance(answers, dict):
            return False, [q["id"] for q in self.pending_questions]

        question_ids = [str(q.get("id", "")).strip() for q in self.pending_questions]
        expected_ids = {qid for qid in question_ids if qid}

        for qid, value in answers.items():
            if qid in expected_ids:
                answer_text = str(value).strip()
                if answer_text:
                    self.user_answers[qid] = answer_text

        missing = sorted(qid for qid in expected_ids if qid not in self.user_answers)
        if missing:
            return False, missing

        self.user_preferences_context = f"Kullanıcı tercihleri: {self.user_answers}"
        self.pending_questions = []
        self.state = "RUNNING"
        self._resume_event.set()
        return True, []

    @staticmethod
    def _parse_json_list_response(raw_text: str) -> list[Any]:
        if not raw_text:
            return []

        text = raw_text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()

        # Try direct JSON list parse first
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            pass

        # Fallback: extract first JSON-like list block
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start:end + 1])
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return []

    @staticmethod
    def _normalize_questions(raw_questions: list[Any]) -> list[dict[str, Any]]:
        questions: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for idx, item in enumerate(raw_questions[:3]):
            if not isinstance(item, dict):
                continue

            qid = str(item.get("id", f"q{idx + 1}")).strip() or f"q{idx + 1}"
            if qid in seen_ids:
                qid = f"q{idx + 1}"
            seen_ids.add(qid)

            question = str(item.get("question", "")).strip()
            if not question:
                continue

            options_raw = item.get("options", [])
            options: list[str] = []
            if isinstance(options_raw, list):
                options = [str(opt).strip() for opt in options_raw if str(opt).strip()][:8]

            q_obj: dict[str, Any] = {"id": qid, "question": question}
            if options:
                q_obj["options"] = options
            questions.append(q_obj)
        return questions

    @staticmethod
    def _build_plan_summary(plan: dict[str, Any]) -> str:
        mode = plan.get("mode", "flat")
        lines = [f"mode: {mode}"]

        phases = plan.get("phases", [])
        if phases:
            for phase in phases:
                phase_name = phase.get("name", "Faz")
                lines.append(f"phase: {phase_name}")
                for task in phase.get("tasks", []):
                    if isinstance(task, Task):
                        task_id = task.task_id
                        assigned_to = task.assigned_to
                        description = task.description
                    else:
                        task_id = str(task.get("task_id", "t"))
                        assigned_to = str(task.get("assigned_to", "coder"))
                        description = str(task.get("description", ""))
                    lines.append(
                        f"- {task_id} | {assigned_to} | {description}"
                    )
        else:
            for task in plan.get("tasks", []):
                if isinstance(task, Task):
                    task_id = task.task_id
                    assigned_to = task.assigned_to
                    description = task.description
                else:
                    task_id = str(task.get("task_id", "t"))
                    assigned_to = str(task.get("assigned_to", "coder"))
                    description = str(task.get("description", ""))
                lines.append(f"- {task_id} | {assigned_to} | {description}")
        return "\n".join(lines)

    async def _collect_clarification_questions(
        self,
        user_goal: str,
        plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        planner = self.agents.get("planner")
        if not planner:
            return []

        plan_summary = self._build_plan_summary(plan)
        prompt = (
            "Bu planı inceliyorsun. Kullanıcıya sormadan ilerleyemeyeceğin 1-3 kritik soru var mı?\n"
            "Varsa JSON listesi döndür:\n"
            "[{\"id\": \"q1\", \"question\": \"...\", \"options\": [\"...\"]}]\n"
            "Yoksa boş liste döndür: []\n"
            "Sadece gerçekten gerekli sorular, gereksiz soru sorma.\n\n"
            f"Kullanıcı hedefi:\n{user_goal}\n\n"
            f"Plan özeti:\n{plan_summary}"
        )

        try:
            raw = await planner._call_llm(  # pylint: disable=protected-access
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "Yalnızca JSON liste döndür. "
                    "Gereksiz sorular sorma. "
                    "Soru yoksa [] döndür."
                ),
                temperature=0.1,
                max_tokens=500,
            )
        except Exception as e:
            await self._emit_status(f"Clarification question generation failed: {e}")
            return []

        parsed = self._parse_json_list_response(raw)
        return self._normalize_questions(parsed)

    async def run(self, user_goal: str) -> dict:
        """
        Main entry point. Accepts user goal and runs the full multi-agent pipeline.
        Returns aggregated final result.
        """
        import re
        import os
        from datetime import datetime, timezone

        self.state = "RUNNING"
        self.pending_questions = []
        self.user_answers = {}
        self.user_preferences_context = ""
        self._resume_event.set()

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

        # Check if this is an API project and create main.py
        if self._is_api_project(user_goal):
            main_py_path = os.path.join(project_dir, "src", "main.py")
            if not os.path.exists(main_py_path):
                main_py_content = '''from fastapi import FastAPI
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

app = FastAPI(title="Project API")

# Import routers (will be created by coder tasks)
# from routers import router_name
# app.include_router(router_name.router)

# Database initialization
# from database import engine, Base
# Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {"message": "API is running"}
'''
                with open(main_py_path, "w", encoding="utf-8") as f:
                    f.write(main_py_content)
                await self._emit_status(f"📄 Created src/main.py with FastAPI app")

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

        questions = await self._collect_clarification_questions(user_goal=user_goal, plan=plan)
        if questions:
            self.pending_questions = questions
            self.state = "PAUSED"
            self._resume_event.clear()
            await self._emit_status("⏸️ Planner kritik sorular için kullanıcı cevabı bekliyor.")
            await self._resume_event.wait()
            await self._emit_status("▶️ Kullanıcı cevapları alındı, plan güncelleniyor...")

            plan_input_with_answers = plan_input + "\n\n" + self.user_preferences_context
            plan = await self._plan(plan_input_with_answers)
            if not plan:
                return {"success": False, "error": "Replanning failed after clarifications", "output": None}
        else:
            self.pending_questions = []

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
            if self.user_preferences_context:
                task.context["user_preferences"] = self.user_preferences_context
            self._task_records[task.task_id] = TaskRecord(task)

        # Step 3: Execute with ReAct loop
        final_results = await self._react_loop(tasks, user_goal)

        # Ensure main.py exists after execution completes
        await self._ensure_main_py(slug)

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
                if self.user_preferences_context:
                    task.context["user_preferences"] = self.user_preferences_context

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

        # Ensure main.py exists after all phases complete
        await self._ensure_main_py(slug)

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
            response = await self._run_agent_with_logs("planner", plan_task)
            if response.success and response.content:
                plan = response.content
                # Inject file routing hints to prevent conflicts
                self._inject_file_routing_hints(plan)
                return plan
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

    def _inject_file_routing_hints(self, plan: dict) -> None:
        """
        Analyze tasks for domain overlap and inject unique file routing hints.
        This prevents multiple coder tasks from overwriting the same file.
        """
        import re
        from collections import defaultdict

        # Extract tasks from plan (handle both flat and phased plans)
        all_tasks = []
        if "phases" in plan:
            for phase in plan.get("phases", []):
                all_tasks.extend(phase.get("tasks", []))
        else:
            all_tasks = plan.get("tasks", [])

        # Group coder tasks by inferred domain
        domain_groups = defaultdict(list)
        
        for task in all_tasks:
            # Only process coder tasks
            if not isinstance(task, Task):
                continue
            if task.assigned_to != "coder":
                continue
            
            # Infer domain from task description
            description_lower = task.description.lower()
            
            # Common domain keywords to look for
            domain_keywords = [
                "todo", "todos", "task", "tasks",
                "user", "users", "auth", "authentication",
                "product", "products", "item", "items",
                "order", "orders", "payment", "payments",
                "comment", "comments", "post", "posts",
                "message", "messages", "chat",
                "file", "files", "upload", "uploads",
                "api", "endpoint", "route", "router",
            ]
            
            # Find matching domains
            matched_domains = []
            for keyword in domain_keywords:
                # Use word boundaries to avoid partial matches
                if re.search(rf'\b{keyword}s?\b', description_lower):
                    # Normalize to singular form
                    domain = keyword.rstrip('s')
                    matched_domains.append(domain)
            
            # If no specific domain found, use a generic identifier
            if not matched_domains:
                # Try to extract first noun-like word
                words = re.findall(r'\b[a-z]+\b', description_lower)
                if words:
                    matched_domains.append(words[0])
                else:
                    matched_domains.append("general")
            
            # Group by first matched domain
            primary_domain = matched_domains[0]
            domain_groups[primary_domain].append(task)
        
        # Inject routing hints for domains with multiple tasks
        for domain, tasks in domain_groups.items():
            if len(tasks) > 1:
                # Multiple tasks targeting same domain - inject unique hints
                for idx, task in enumerate(tasks, start=1):
                    routing_hint = f"{domain}_{idx}"
                    task.context["file_routing_hint"] = routing_hint
                    self._log(
                        f"🔀 Injected routing hint '{routing_hint}' for task {task.task_id} "
                        f"to prevent file conflicts in domain '{domain}'"
                    )

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

        agent_key = task.assigned_to
        agent = self.agents.get(agent_key)
        if not agent:
            # Try to find best-fit agent from capabilities
            agent = self._find_best_agent(task)
            if not agent:
                return AgentResponse(
                    content=None,
                    success=False,
                    error=f"No agent available for: {task.assigned_to}",
                )
            agent_key = agent.agent_id

        await self._emit_status(f"🤖 {agent.name} working on: {task.description[:60]}...")

        # Check if confidence is too low (human-in-the-loop)
        response = await self._run_agent_with_logs(agent_key, task)

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
            review_response = await self._run_agent_with_logs("critic", review_task)
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
                    # normalized field: use "suggestions" (legacy: "improvements")
                    feedback_items = review_data.get("suggestions") or review_data.get("improvements") or []
                    suggestions = "\n- ".join(feedback_items)
                    revision_instructions = f"Issues:\n- {issues}\nSuggestions:\n- {suggestions}"
                    
                    revised_task = Task(
                        task_id=f"{task.task_id}_rev{revision_count}",
                        description=f"{task.description}\n\nRevision required: {revision_instructions}",
                        assigned_to=task.assigned_to,
                        context=task.context,
                    )
                    response = await self._run_agent_with_logs(task.assigned_to, revised_task)
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
        if self.user_preferences_context:
            task.context["user_preferences"] = self.user_preferences_context

        # Detect revision tasks (task_id contains "_rev")
        is_revision_task = "_rev" in task.task_id and task.assigned_to == "coder"

        if is_revision_task:
            # For revision tasks, limit context to 3000 tokens max
            # Only include: task.description (contains critic feedback), task.context (contains current file)
            # Do NOT add all_previous_results for revisions

            # Estimate token count (rough approximation: 1 token ≈ 4 characters)
            def estimate_tokens(text: str) -> int:
                return len(text) // 4

            def truncate_to_token_limit(text: str, max_tokens: int) -> str:
                """Truncate text to fit within token limit"""
                max_chars = max_tokens * 4
                if len(text) <= max_chars:
                    return text
                return text[:max_chars] + "... [truncated to fit 3000 token limit]"

            # Calculate current context size
            context_str = str(task.context)
            description_str = str(task.description)
            total_text = context_str + description_str
            current_tokens = estimate_tokens(total_text)

            # If over 3000 tokens, truncate context
            if current_tokens > 3000:
                # Prioritize: keep description (critic feedback), truncate context if needed
                description_tokens = estimate_tokens(description_str)
                remaining_tokens = 3000 - description_tokens

                if remaining_tokens > 0:
                    # Truncate context to fit remaining budget
                    truncated_context = truncate_to_token_limit(context_str, remaining_tokens)
                    # Note: We can't directly modify task.context as a whole, but we can add a marker
                    task.context["_context_truncated"] = True
                    task.context["_original_size_tokens"] = current_tokens

            # Skip adding all_previous_results and research for revision tasks
            return

        # Add research context to coder tasks (non-revision)
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

    @staticmethod
    def _is_api_project(user_goal: str) -> bool:
        """
        Detect if the user goal describes an API project.
        
        Args:
            user_goal: The user's project goal description
            
        Returns:
            True if the goal contains API-related keywords, False otherwise
        """
        user_goal_lower = user_goal.lower()
        api_keywords = ["fastapi", "api", "web", "rest", "backend"]
        return any(keyword in user_goal_lower for keyword in api_keywords)

    async def _ensure_main_py(self, slug: str) -> None:
        """
        Ensure main.py exists in the project's src/ directory.
        
        This method implements the fix for app.py vs main.py import mismatch:
        - If main.py exists: do nothing (preservation)
        - If main.py does not exist AND app.py exists: create main.py as re-export shim
        - If neither exists: create full main.py using template
        
        Args:
            slug: The project slug identifier
        """
        import os
        from pathlib import Path
        
        project_dir = os.path.join("workspace", "projects", slug)
        src_dir = Path(project_dir) / "src"
        main_py_path = src_dir / "main.py"
        app_py_path = src_dir / "app.py"
        
        # Ensure src directory exists
        src_dir.mkdir(parents=True, exist_ok=True)
        
        # Case 1: main.py already exists - do nothing (preservation)
        if main_py_path.exists():
            return
        
        # Case 2: main.py does not exist AND app.py exists - create re-export shim
        if app_py_path.exists():
            shim_content = 'from app import app  # noqa\n'
            with open(main_py_path, "w", encoding="utf-8") as f:
                f.write(shim_content)
            await self._emit_status(f"📄 Created src/main.py as re-export shim for app.py")
            return
        
        # Case 3: Neither exists - create full main.py using template
        # This template matches the one in run() method
        main_py_content = '''from fastapi import FastAPI
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

app = FastAPI(title="Project API")

# Import routers (will be created by coder tasks)
# from routers import router_name
# app.include_router(router_name.router)

# Database initialization
# from database import engine, Base
# Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {"message": "API is running"}
'''
        with open(main_py_path, "w", encoding="utf-8") as f:
            f.write(main_py_content)
        await self._emit_status(f"📄 Created src/main.py with FastAPI template")

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

