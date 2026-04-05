"""
core/orchestrator.py
The brain of the multi-agent system.
Coordinates all agents using a ReAct loop with dynamic re-planning,
parallel execution, and human-in-the-loop support.
"""
import asyncio
import json
import logging
import os
import re
import sys
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Optional

from core.base_agent import AgentResponse, Task
from core.memory import memory_manager
from core.message_bus import Message, MessageBus, MessageType, Priority, bus
from core.memory_agent import get_memory_agent

# V4 entegrasyonlari
try:
    from agents.tester_agent import TesterAgent
    from agents.linter_agent import LinterAgent
    _TESTER_AVAILABLE = True
except ImportError:
    _TESTER_AVAILABLE = False

try:
    from tools.git_manager import init_repo, commit as git_commit, revert_last
    _GIT_AVAILABLE = True
except ImportError:
    _GIT_AVAILABLE = False

try:
    from tools.requirements_generator import generate as generate_requirements
    _REQ_GEN_AVAILABLE = True
except ImportError:
    _REQ_GEN_AVAILABLE = False

try:
    from tools.project_templates import detect_template, apply_template
    _TEMPLATES_AVAILABLE = True
except ImportError:
    _TEMPLATES_AVAILABLE = False

try:
    from tools.simple_search import get_relevant_context
    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False

MAX_ITERATIONS = 10


def _ws_broadcast(event: dict) -> None:
    """Fire-and-forget broadcast to the WS dashboard. Never raises."""
    try:
        from api.dashboard_ws import event_bus
        import asyncio
        from datetime import datetime, timezone
        event.setdefault("ts", datetime.now(timezone.utc).strftime("%H:%M:%S"))
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(event_bus.broadcast(event))
    except Exception as e:
        logging.warning(f"[WS Broadcast] Dashboard broadcast failed: {e}")
CONFIDENCE_THRESHOLD = 0.6
TASK_TIMEOUT_SECONDS = 360  # Increased from 180 to 360 to accommodate revision cycles
TOTAL_TIMEOUT_SECONDS = 1200
PHASE_PREINSTALL_STDLIB_MODULES = {
    "concurrent",
    "threading",
    "asyncio",
    "os",
    "sys",
    "pathlib",
    "json",
    "re",
    "math",
    "datetime",
    "typing",
    "collections",
    "itertools",
    "functools",
    "abc",
    "io",
    "time",
    "random",
    "string",
    "hashlib",
    "uuid",
    "copy",
    "dataclasses",
}
logger = logging.getLogger(__name__)

ORCHESTRATOR_SYSTEM_PROMPT = """You are MAOS — Multi-Agent Orchestration System.

Your purpose is to transform user goals into working, tested, and documented software outputs. You do not answer in a single response. You plan, delegate, review, execute, and deliver.

## Core Identity

You are not a chatbot. You are a systematic engineering pipeline. When a user gives you a goal, decompose it, route it to the right agents, validate the output, and produce a real result — not a description of what could be done.

You coordinate five specialized agents: Planner, Researcher, Coder, Critic, and Executor. You do not do their jobs yourself. Your role is to sequence them correctly, pass context between them, handle failures, and synthesize the final output.

## Behavior Principles

Be systematic, not reactive. Never jump to code generation without a plan. Never accept code without critic review. Never skip execution if the task requires a working artifact.

Ask before assuming. If a goal is ambiguous in a way that would cause the plan to branch significantly, pause and ask the user. Keep questions minimal — one to three, focused on the most critical unknowns.

Fail loudly, recover gracefully. If an agent fails, log it, explain what happened, and attempt recovery. If recovery is not possible, tell the user clearly and suggest next steps.

Respect the critic. A low critic score is not a failure — it is a signal. Trigger revision. If revision repeatedly fails to meet the threshold, replan the affected tasks.

Memory is not optional. Every session produces a record. Every project has a workspace. Do not treat runs as stateless.

## Communication Style

Speak like a senior engineer giving a status update — clear, direct, no filler. Report progress in Turkish. When asking for input, be specific about what you need and why.

Do not over-explain your internal process unless the user asks. Surface results, not machinery.

## Workflow

1. Receive user goal.
2. Open project workspace under workspace/projects/{slug}.
3. Run Planner to produce a task plan.
4. If critical ambiguities exist, pause and ask the user before proceeding.
5. Execute tasks — parallelize where safe.
6. Pass research context to Coder.
7. Pass Coder output to Critic for scoring.
8. If score is below 6.5: revise. If repeatedly below threshold: replan.
9. Run Executor to write files, run commands, execute tests.
10. Synthesize results. Write session summary and project overview.

## Output Expectations

Every completed run produces a working project directory with all generated files, a session log, and a human-readable project summary in Turkish.
"""


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
        self.user_preferences_context: str = ""
        self.cluster_mode: bool = False  # V4: cluster modu, varsayilan kapali
        self._log_callback = None  # V4: SSE streaming callback
        self.preloaded_plan = None  # V5: Kullanıcı onaylı plan
        
        # Cluster mode için
        self.coder_model_override: Optional[str] = None
        self._critic_scores: list = []
        self._avg_critic_score: float = 0.0
        self._file_write_locks: dict[str, asyncio.Lock] = {}
        self._file_write_locks_guard = asyncio.Lock()
        self._session_lock = asyncio.Lock()  # Guards _session_results and _session_tasks
        self._session_results: list[dict] = []
        self._session_tasks: dict[str, Task] = {}

        # V4: TesterAgent & LinterAgent
        if _TESTER_AVAILABLE:
            self._tester = TesterAgent()
        else:
            self._tester = None
            
        self.linter = LinterAgent()
        
        # GELİŞTİRME 6: UITesterAgent
        try:
            from agents.ui_tester_agent import UITesterAgent
            self.ui_tester = UITesterAgent()
        except ImportError:
            self.ui_tester = None
            
        try:
            from agents.builder_agent import BuilderAgent
            self.builder = self.agents.get("builder", BuilderAgent())
        except ImportError:
            self.builder = self.agents.get("builder", None)
        
        # GELİŞTİRME 6: CriticAgent shortcut
        self.critic = self.agents.get("critic")
        self.security = self.agents.get("security")
        self.optimizer = self.agents.get("optimizer")
        self.docs = self.agents.get("docs")

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

    @staticmethod
    def _extract_file_exports(project_path: str, filenames: list) -> dict:
        """Kayıtlı Python dosyalarından class/function export listelerini AST ile çıkar.
        
        Returns:
            dict: {"board.py": {"classes": ["Board", "Color"], "functions": ["init_board"]}, ...}
        """
        import ast, os
        exports = {}
        
        for fname in filenames:
            if not fname.endswith('.py'):
                continue
            
            # Dosyayı bul: src/ veya tests/ altında olabilir
            for subdir in ['src', 'tests', '']:
                fpath = os.path.join(project_path, subdir, fname)
                if os.path.exists(fpath):
                    break
            else:
                continue
            
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    source = f.read()
                
                tree = ast.parse(source)
                classes = []
                functions = []
                
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, ast.ClassDef):
                        methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith('_')]
                        classes.append(f"{node.name}({', '.join(methods[:5])})" if methods else node.name)
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions.append(node.name)
                
                if classes or functions:
                    exports[fname] = {"classes": classes, "functions": functions}
            except Exception:
                pass
        
        return exports

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

    @staticmethod
    def _parse_json_list_response(raw_text: str) -> list[Any]:
        """Parse JSON list from LLM response, stripping markdown fences."""
        if not raw_text:
            return []

        text = raw_text.strip()
        
        # Strip markdown code fences using explicit pattern
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()

        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else []
        except Exception as e:
            # Log parsing failure for debugging
            print(f"[Orchestrator] ⚠️ JSON list parse error: {e}")
            print(f"[Orchestrator] ⚠️ Raw text (first 200 chars): {repr(raw_text[:200])}")

        # Fallback: try to extract JSON array
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
    def _normalize_clarification_questions(raw_questions: Any) -> list[dict[str, Any]]:
        if isinstance(raw_questions, dict):
            for key in ("questions", "items", "data"):
                nested_questions = raw_questions.get(key)
                if isinstance(nested_questions, list):
                    raw_questions = nested_questions
                    break
            else:
                raw_questions = [raw_questions]
        elif not isinstance(raw_questions, list):
            return []

        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for idx, item in enumerate(raw_questions[:3]):
            if not isinstance(item, dict):
                continue

            question = str(item.get("question", "")).strip()
            if not question:
                continue

            qid = str(item.get("id", f"q{idx + 1}")).strip() or f"q{idx + 1}"
            if qid in seen_ids:
                qid = f"q{idx + 1}"
            seen_ids.add(qid)

            options = item.get("options", [])
            clean_options: list[str] = []
            if isinstance(options, list):
                clean_options = [str(opt).strip() for opt in options if str(opt).strip()][:8]

            q_data: dict[str, Any] = {"id": qid, "question": question}
            if clean_options:
                q_data["options"] = clean_options
            normalized.append(q_data)

        return normalized

    @staticmethod
    def _fallback_clarification_questions(user_goal: str) -> list[dict[str, Any]]:
        """LLM boş/hatalı dönerse kritik belirsizlikler için güvenli fallback üret."""
        goal_lower = (user_goal or "").lower()
        has_url = bool(re.search(r"https?://|www\.|\.com|\.org|\.net|\.io|\.dev", goal_lower))
        is_scraper = any(k in goal_lower for k in ["web scraper", "scraper", "kazıyıcı", "kaziyici"])

        if is_scraper and not has_url:
            return [
                {
                    "id": "q1",
                    "question": "Hangi siteyi veya URL'yi kazımamı istiyorsun?",
                },
                {
                    "id": "q2",
                    "question": "Hangi verileri çekmemi istiyorsun?",
                    "options": ["başlık/link", "fiyat", "tablo verisi", "özel alanlar"],
                },
                {
                    "id": "q3",
                    "question": "Çıktı formatı ne olsun?",
                    "options": ["JSON", "CSV", "TXT"],
                },
            ]

        return []

    @staticmethod
    def _build_plan_summary_for_questions(plan: dict[str, Any]) -> str:
        lines: list[str] = [f"mode: {plan.get('mode', 'flat')}"]

        phases = plan.get("phases", [])
        if phases:
            for phase in phases:
                lines.append(f"phase: {phase.get('name', 'phase')}")
                for task in phase.get("tasks", []):
                    if isinstance(task, Task):
                        lines.append(f"- {task.task_id} | {task.assigned_to} | {task.description}")
                    elif isinstance(task, dict):
                        lines.append(
                            f"- {task.get('task_id', 't')} | {task.get('assigned_to', 'coder')} | {task.get('description', '')}"
                        )
        else:
            for task in plan.get("tasks", []):
                if isinstance(task, Task):
                    lines.append(f"- {task.task_id} | {task.assigned_to} | {task.description}")
                elif isinstance(task, dict):
                    lines.append(
                        f"- {task.get('task_id', 't')} | {task.get('assigned_to', 'coder')} | {task.get('description', '')}"
                    )
        return "\n".join(lines)

    async def _collect_clarification_questions(
        self,
        user_goal: str,
        plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        logger.debug("_collect_clarification_questions called. goal=%r", user_goal[:300])
        planner = self.agents.get("planner")
        if not planner:
            logger.debug("Planner agent not found; returning empty clarification list.")
            return self._fallback_clarification_questions(user_goal)

        prompt = (
            "Aşağıdaki kullanıcı hedefini analiz et:\n"
            f"\"{user_goal}\"\n\n"
            "Bu hedefi başarıyla tamamlamak için kullanıcıdan \n"
            "öğrenmem ZORUNLU olan bilgiler var mı?\n\n"
            "Eğer hedef belirsizse (hangi site, hangi veri, hangi dil,\n"
            "hangi format gibi kritik detaylar eksikse) 2-3 soru üret.\n\n"
            "Eğer hedef yeterince açıksa boş liste döndür.\n\n"
            "SADECE JSON döndür, başka hiçbir şey yazma:\n"
            "[{\"id\": \"q1\", \"question\": \"...\", \"options\": [\"a\", \"b\", \"c\"]}]\n"
            "veya boş ise: []"
        )
        logger.debug("Clarification prompt prepared:\n%s", prompt)

        try:
            raw = await planner._call_llm(  # pylint: disable=protected-access
                messages=[{"role": "user", "content": prompt}],
                system_prompt="Yalnızca JSON liste döndür. Soru yoksa [].",
                temperature=0.1,
                max_tokens=500,
            )
        except Exception as e:
            logger.exception("Clarification question generation failed.")
            await self._emit_status(f"Clarification question generation failed: {e}")
            return self._fallback_clarification_questions(user_goal)

        logger.debug("Clarification raw response:\n%s", raw)
        try:
            parsed = self._parse_json_list_response(raw)
            logger.debug("Clarification parsed payload: %r", parsed)
            normalized = self._normalize_clarification_questions(parsed)
            if not normalized:
                normalized = self._fallback_clarification_questions(user_goal)
            logger.debug("Clarification normalized questions: %r", normalized)
            return normalized
        except Exception:
            logger.exception("Clarification parse/normalize failed; returning empty list.")
            return self._fallback_clarification_questions(user_goal)

    def _ask_clarification_questions_cli(self, questions: list[dict[str, Any]]) -> dict[str, str]:
        """CLI modunda kritik soruları kullanıcıya sırayla sor."""
        answers: dict[str, str] = {}
        if not questions:
            return answers

        if not sys.stdin or not sys.stdin.isatty():
            return answers

        for item in questions:
            qid = str(item.get("id", "")).strip()
            question = str(item.get("question", "")).strip()
            if not qid or not question:
                continue

            print(f"\n❓ {question}")
            options = item.get("options", [])
            if isinstance(options, list) and options:
                print(f"Seçenekler: {', '.join(str(opt) for opt in options)}")

            answer = ""
            while not answer.strip():
                answer = input("Cevabınız: ")
            answers[qid] = answer.strip()

        return answers

    @staticmethod
    def _serialize_plan_task(task: Any) -> Optional[dict[str, Any]]:
        """Task objesini veya task dict'ini JSON yazılabilir hale getir."""
        if isinstance(task, Task):
            return {
                "task_id": task.task_id,
                "description": task.description,
                "assigned_to": task.assigned_to,
                "dependencies": list(task.dependencies or []),
                "priority": getattr(task.priority, "value", task.priority),
                "context": task.context or {},
                "expected_output": (task.context or {}).get("expected_output", ""),
            }

        if isinstance(task, dict):
            return {
                "task_id": task.get("task_id", ""),
                "description": task.get("description", ""),
                "assigned_to": task.get("assigned_to", ""),
                "dependencies": list(task.get("dependencies", []) or []),
                "priority": task.get("priority", ""),
                "context": task.get("context", {}) or {},
                "expected_output": (
                    task.get("expected_output")
                    or (task.get("context", {}) or {}).get("expected_output", "")
                ),
            }

        return None

    def _persist_plan_json(self, project_dir: str, plan: Optional[dict[str, Any]]) -> None:
        """Plan verisini workspace/projects/{slug}/plan.json dosyasina sessizce yaz."""
        if not plan:
            return

        try:
            tasks = [
                item for item in
                (self._serialize_plan_task(task) for task in plan.get("tasks", []))
                if item is not None
            ]

            phases = []
            for phase in plan.get("phases", []) or []:
                if not isinstance(phase, dict):
                    continue
                phase_tasks = [
                    item for item in
                    (self._serialize_plan_task(task) for task in phase.get("tasks", []))
                    if item is not None
                ]
                phases.append({
                    "phase_id": phase.get("phase_id", ""),
                    "name": phase.get("name", ""),
                    "goal": phase.get("goal", ""),
                    "depends_on_phase": phase.get("depends_on_phase"),
                    "tasks": phase_tasks,
                })

            payload = {
                "mode": plan.get("mode", "flat"),
                "raw_plan": plan.get("raw_plan", {}),
                "tasks": tasks,
                "phases": phases,
            }

            plan_json_path = os.path.join(project_dir, "plan.json")
            with open(plan_json_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception:
            pass

    async def _register_session_tasks(self, tasks: list[Task]) -> None:
        """Store tasks for partial timeout reporting."""
        async with self._session_lock:
            for task in tasks:
                self._session_tasks[task.task_id] = task

    async def _record_completed_result(self, results: list[dict], task: Task, result_content: Any) -> None:
        """Track successful task output both locally and for total-timeout partial returns."""
        result_payload = {
            "task_id": task.task_id,
            "agent": task.assigned_to,
            "description": task.description,
            "result": result_content,
            "success": True,
        }
        results.append(result_payload)
        async with self._session_lock:
            self._session_results.append(result_payload)

    @staticmethod
    def _build_task_timeout_response(task: Task) -> AgentResponse:
        """Create a standardized task-timeout response."""
        timeout_message = "Timeout: görev 6 dakikada tamamlanamadı"
        return AgentResponse(
            content=timeout_message,
            success=False,
            error=timeout_message,
            metadata={
                "timed_out": True,
                "task_id": task.task_id,
                "timeout_seconds": TASK_TIMEOUT_SECONDS,
            },
        )

    async def _execute_task_with_timeout(self, task: Task) -> Optional[AgentResponse]:
        """Execute a task with a per-task timeout."""
        try:
            return await asyncio.wait_for(
                self._execute_task_isolated(task),
                timeout=TASK_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            timeout_log = f"[Timeout] Task {task.task_id} iptal edildi"
            print(timeout_log)
            await self._emit_status(timeout_log)
            return self._build_task_timeout_response(task)

    def _build_total_timeout_result(self, user_goal: str) -> dict:
        """Return partial session data when the orchestrator hits the total timeout."""
        if self._critic_scores:
            self._avg_critic_score = sum(self._critic_scores) / len(self._critic_scores)

        completed_task_ids = [
            task_id
            for task_id, task in self._session_tasks.items()
            if self._task_records.get(task_id, TaskRecord(task)).status == TaskStatus.COMPLETED
        ]
        failed_task_ids = [
            task_id
            for task_id, task in self._session_tasks.items()
            if self._task_records.get(task_id, TaskRecord(task)).status == TaskStatus.FAILED
        ]

        if self._session_results:
            partial_output = "\n\n".join(
                f"Task {item['task_id']} ({item['agent']}): {str(item.get('result', ''))[:500]}"
                for item in self._session_results
            )
        else:
            partial_output = "Toplam timeout nedeniyle session durduruldu. Tamamlanan görev yok."

        return {
            "success": False,
            "timed_out": True,
            "error": f"Total timeout: orchestrator {TOTAL_TIMEOUT_SECONDS // 60} dakikayı aştı",
            "output": partial_output,
            "tasks_completed": len(self._session_results),
            "task_details": list(self._session_results),
            "tasks_completed_ids": completed_task_ids,
            "errors_encountered": failed_task_ids,
            "session_id": self._session_id,
            "iterations": self._iteration,
            "avg_critic_score": self._avg_critic_score,
            "project_slug": getattr(self, "current_project_slug", ""),
            "goal": user_goal,
        }

    async def run(self, user_goal: str) -> dict:
        """Run the full session with a hard total timeout and partial-result fallback."""
        self._session_results = []
        self._session_tasks = {}

        try:
            return await asyncio.wait_for(
                self._run_session(user_goal),
                timeout=TOTAL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            timeout_log = (
                f"[Timeout] Session {self._session_id} iptal edildi: "
                f"{TOTAL_TIMEOUT_SECONDS // 60} dakikalık toplam süre aşıldı"
            )
            print(timeout_log)
            await self._emit_status(timeout_log)
            return self._build_total_timeout_result(user_goal)

    async def _run_session(self, user_goal: str) -> dict:
        """
        Main entry point. Accepts user goal and runs the full multi-agent pipeline.
        Returns aggregated final result.
        """
        import re
        import os
        from datetime import datetime, timezone
        from core.llm_client import token_tracker

        token_tracker.reset()
        self.user_preferences_context = ""

        # 1. Görev adından slug üret
        turkish_map = str.maketrans({
            "ş": "s",
            "ğ": "g",
            "ü": "u",
            "ö": "o",
            "ç": "c",
            "ı": "i",
            "İ": "i",
            "Ş": "s",
            "Ğ": "g",
            "Ü": "u",
            "Ö": "o",
            "Ç": "c",
        })
        normalized_goal = user_goal.translate(turkish_map).lower()
        slug = re.sub(r'[^a-z0-9]+', '-', normalized_goal).strip('-')
        if not slug:
            slug = "default"
        slug = slug[:40]
        self.current_project_slug = slug

        # 2. & 3. workspace/projects/{slug}/ klasörünü ve alt klasörleri oluştur
        project_dir = os.path.join("workspace", "projects", slug)
        src_dir = os.path.join(project_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        tests_dir = os.path.join(project_dir, "tests")
        os.makedirs(tests_dir, exist_ok=True)
        
        # BUG FIX: Eski kaynak (src) ve test (tests) dosyalarını temizle
        for d in [src_dir, tests_dir]:
            for fname in os.listdir(d):
                if fname.endswith(".py"):
                    try:
                        os.remove(os.path.join(d, fname))
                    except OSError:
                        pass

        os.makedirs(os.path.join(project_dir, "docs"), exist_ok=True)
        plan_json_path = os.path.join(project_dir, "plan.json")
        if not os.path.exists(plan_json_path):
            with open(plan_json_path, "w", encoding="utf-8") as f:
                f.write("{}")

        # PYTHONPATH (import) hatalarini onlemek icin projeye pytest.ini ekle
        pytest_ini_path = os.path.join(project_dir, "pytest.ini")
        if not os.path.exists(pytest_ini_path):
            with open(pytest_ini_path, "w", encoding="utf-8") as f:
                f.write("[pytest]\npythonpath = src\ntestpaths = tests\nasyncio_mode = auto\n")

        await self._emit_status(f"Starting session {self._session_id}")
        await self._emit_status(f"Goal: {user_goal}")
        await self._emit_status(f"Workspace: {project_dir}")
        _ws_broadcast({"type": "task_start", "task": user_goal[:120], "session_id": self._session_id})

        # V4: Git repo baslatma
        if _GIT_AVAILABLE:
            try:
                init_repo(project_dir)
            except Exception as e:
                print(f"[Git] Baslatilamadi: {e}")

        # V4: Proje sablonu uygulama
        if _TEMPLATES_AVAILABLE:
            try:
                template_name = detect_template(user_goal)
                if template_name:
                    result = apply_template(template_name, project_dir)
                    print(f"[Orchestrator] Sablon uygulandi: {result['description']}")
                    self.shared_context += f"\nSablon kullaniliyor: {template_name}. Sablon dosyalari mevcut, sifirdan yazma."
            except Exception as e:
                print(f"[Template] Hata: {e}")

        # V4: RAG -- /open modunda ilgili dosyalari context'e ekle
        if _RAG_AVAILABLE and self.current_project_path and user_goal:
            try:
                relevant = get_relevant_context(self.current_project_path, user_goal)
                if relevant and relevant != "Ilgili dosya bulunamadi.":
                    self.shared_context += f"\n\nILGILI DOSYALAR:\n{relevant}"
                    print(f"[RAG] Ilgili dosyalar context'e eklendi")
            except Exception as e:
                print(f"[RAG] Hata: {e}")

        # Son 3 session okuma
        last_sessions = memory_manager.get_last_sessions(limit=3)
        past_context = ""
        if last_sessions:
            past_context = "\n\n--- PAST SESSIONS CONTEXT ---\n"
            for s in last_sessions:
                past_context += f"- Goal: {s.get('goal', '')} (Success: {len(s.get('errors_encountered', [])) == 0})\n"

        # V5: Memory Agent - Önceki ilgili projeleri bul
        memory_context = ""
        try:
            memory = get_memory_agent()
            memory_context = memory.format_context(user_goal)
            if memory_context:
                print(f"[Memory] İlgili projeler bulundu, context'e eklendi")
        except Exception as e:
            print(f"[Memory] Hata (devam ediliyor): {e}")

        # Step 1: Plan (Pass past context + project context + memory context)
        plan_input = user_goal + past_context
        if self.shared_context:
            plan_input = user_goal + "\n" + self.shared_context + past_context
        if memory_context:
            plan_input += "\n" + memory_context
        
        # V5: Preloaded plan desteği
        planning_failed = False
        if self.preloaded_plan:
            plan = self.preloaded_plan
            await self._emit_status("📋 Önceden onaylanan plan kullanılıyor")
        else:
            plan = await self._plan(plan_input)
            if not plan:
                planning_failed = True
                plan = {}

        self._persist_plan_json(project_dir, plan)

        # NEW: Run architect agent to generate project contract
        if "architect" in self.agents:
            architect_task = Task(
                task_id="architect_contract",
                description="Generate project architecture contract",
                assigned_to="architect",
                context={
                    "user_goal": user_goal,
                    "plan": plan,
                    "project_slug": slug,
                },
            )
            try:
                architect_response = await asyncio.wait_for(
                    self.agents["architect"].run(architect_task),
                    timeout=60,  # 1 minute timeout for contract generation
                )
                if architect_response.success:
                    await self._emit_status(f"✓ Contract generated: {architect_response.metadata.get('contract_path', 'contract.json')}")
                else:
                    await self._emit_status(f"⚠ Architect failed: {architect_response.error}")
            except asyncio.TimeoutError:
                await self._emit_status("⚠ Architect timeout: continuing without contract")
            except Exception as e:
                await self._emit_status(f"⚠ Architect error: {e}")

        logger.debug("About to call _collect_clarification_questions from run()")
        questions = await self._collect_clarification_questions(
            user_goal=user_goal,
            plan=plan,
        )
        print(f"[CLARIFICATION DEBUG] Sorular: {questions}")
        clarification_questions = questions
        logger.debug("Clarification question count: %d", len(clarification_questions))

        if planning_failed:
            return {"success": False, "error": "Planning failed", "output": None}

        if clarification_questions:
            if sys.stdin and sys.stdin.isatty():
                answers = self._ask_clarification_questions_cli(clarification_questions)
                if answers:
                    self.user_preferences_context = f"Kullanıcı tercihleri: {answers}"
                    self.shared_context = (self.shared_context + "\n" + self.user_preferences_context).strip()
                    plan_input = plan_input + "\n\n" + self.user_preferences_context
                    await self._emit_status("📝 Kullanıcı tercihleri alındı, plan güncelleniyor...")
                    plan = await self._plan(plan_input)
                    if not plan:
                        return {
                            "success": False,
                            "error": "Re-planning failed after clarification answers",
                            "output": None,
                        }
                    self._persist_plan_json(project_dir, plan)
            else:
                logger.debug(
                    "Clarification questions exist but stdin is not interactive; continuing without user answers."
                )

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
        await self._register_session_tasks(tasks)

        # Step 3: Execute with ReAct loop
        final_results = await self._react_loop(tasks, user_goal)

        # Ensure main.py exists after flat execution completes
        await self._ensure_main_py(slug)

        # Step 4: Aggregate results
        final_output = await self._aggregate_results(final_results, user_goal)

        # V4: Flat mode session sonu -- requirements.txt uret
        if _REQ_GEN_AVAILABLE:
            try:
                req_result = generate_requirements(project_dir)
                if req_result["success"] and req_result.get("packages"):
                    print(f"[Orchestrator] requirements.txt olusturuldu: {len(req_result['packages'])} paket")
                    if _GIT_AVAILABLE:
                        git_commit(project_dir, "chore: requirements.txt guncellendi")
            except Exception as e:
                print(f"[Requirements] Hata: {e}")

        # V4: Flat mode son git commit
        if _GIT_AVAILABLE:
            try:
                git_commit(project_dir, f"feat: Proje tamamlandi - {user_goal[:60]}")
            except Exception as e:
                print(f"[Git] Final commit hatasi: {e}")

        # Session kaydetme
        try:
            from datetime import datetime, timezone
            from core.llm_client import token_tracker
            
            all_usage = token_tracker.get_all()
            total_in = sum(d.get("prompt_tokens", 0) for d in all_usage.values())
            total_out = sum(d.get("completion_tokens", 0) for d in all_usage.values())
            total_cost = token_tracker.estimated_cost_usd()
            
            # Critic skorlarının ortalamasını hesapla (cluster mode için)
            if self._critic_scores:
                self._avg_critic_score = sum(self._critic_scores) / len(self._critic_scores)
            
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
                "agent_breakdown": all_usage,
                "avg_critic_score": self._avg_critic_score,
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

            # GELİŞTİRME 6: UI Tester (tüm görevler tamamlandıktan sonra)
            if hasattr(self, 'ui_tester') and self.ui_tester:
                screenshot_path = None  # Başlangıçta None olarak tanımla
                try:
                    from pathlib import Path
                    project_slug = getattr(self, "current_project_slug", "default")
                    project_dir = Path("workspace/projects") / project_slug
                    
                    # Proje dosyalarını kontrol et
                    files = []
                    for ext in ["*.html", "*.css", "*.js", "*.py"]:
                        files.extend([f.name for f in (project_dir / "src").glob(ext)])
                    
                    # Web projesi mi kontrol et
                    has_html = any(f.endswith('.html') for f in files)
                    has_flask = any('flask' in f.lower() or 'app.py' in f for f in files)
                    has_fastapi = any('fastapi' in f.lower() or 'main.py' in f for f in files)
                    
                    # Eğer flet / mobil projesi ise UI test atla (webview değil)
                    goal_lower_ui = user_goal.lower()
                    is_flet_mobile = any(w in goal_lower_ui for w in ["flet", "apk", "android", "mobile", "ios"])
                    
                    if is_flet_mobile:
                        print(f"[Orchestrator] ⏭️  UI test atlandı (Flet / Mobil projeler Web UI desteklemiyor)")
                    elif has_html or has_flask or has_fastapi:
                        print(f"[Orchestrator] 📸 UI test başlatılıyor... (files: {len(files)})")
                        ui_task = Task(
                            task_id="ui_test_final",
                            description="Final UI test after all tasks completed",
                            assigned_to="ui_tester",
                            context={
                                "project_dir": str(project_dir),
                                "files": files,
                                "project_slug": project_slug
                            },
                        )
                        ui_thought = await self.ui_tester.think(ui_task)
                        ui_result = await self.ui_tester.act(ui_thought, ui_task)
                        
                        if ui_result.success and ui_result.metadata.get("screenshot_path"):
                            screenshot_path = ui_result.metadata["screenshot_path"]
                            print(f"[Orchestrator] ✅ Screenshot: {screenshot_path}")
                            
                            # GELİŞTİRME 6: Screenshot boyutunu kontrol et ve gerekirse küçült
                            try:
                                from PIL import Image
                                screenshot_file = Path(screenshot_path)
                                file_size_kb = screenshot_file.stat().st_size / 1024
                                
                                if file_size_kb > 50:
                                    print(f"[Orchestrator] 📏 Screenshot boyutu: {file_size_kb:.1f}KB, küçültülüyor...")
                                    img = Image.open(screenshot_file)
                                    
                                    # Max 800x600 olarak resize et
                                    max_size = (800, 600)
                                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                                    
                                    # Aynı dosyaya kaydet
                                    img.save(screenshot_file, optimize=True, quality=85)
                                    
                                    new_size_kb = screenshot_file.stat().st_size / 1024
                                    print(f"[Orchestrator] ✅ Screenshot küçültüldü: {new_size_kb:.1f}KB")
                                else:
                                    print(f"[Orchestrator] ✅ Screenshot boyutu uygun: {file_size_kb:.1f}KB")
                            except Exception as e:
                                print(f"[Orchestrator] ⚠️  Screenshot resize hatası: {e}")
                            
                            # GELİŞTİRME 6: Critic'e screenshot ile UI quality değerlendirmesi yaptır
                            try:
                                print(f"[Orchestrator] 🎨 Critic UI quality değerlendirmesi başlatılıyor...")
                                critic_task = Task(
                                    task_id="critic_ui_quality",
                                    description="Evaluate UI quality from screenshot",
                                    assigned_to="critic",
                                    context={
                                        "screenshot_path": screenshot_path,
                                        "project_dir": str(project_dir),
                                        "files": files,
                                    },
                                )
                                critic_thought = await self.critic.think(critic_task)
                                critic_result = await self.critic.act(critic_thought, critic_task)
                                
                                # Scores content içinde, metadata'da değil
                                scores = None
                                if isinstance(critic_result.content, dict) and "scores" in critic_result.content:
                                    scores = critic_result.content["scores"]
                                elif critic_result.metadata.get("scores"):
                                    scores = critic_result.metadata["scores"]
                                
                                if critic_result.success and scores:
                                    ui_quality = scores.get("ui_quality", 0)
                                    avg_score = sum(scores.values()) / len(scores)
                                    print(f"[Orchestrator] 🎨 UI Quality Score: {ui_quality}/10")
                                    print(f"[Orchestrator] 📊 Average Score: {avg_score:.1f}/10")
                                    print(f"[Orchestrator] 📊 All Scores: {scores}")
                                else:
                                    print(f"[Orchestrator] ⚠️  Critic UI değerlendirmesi başarısız")
                            except Exception as e:
                                print(f"[Critic] UI değerlendirme hatası: {e}")
                        else:
                            print(f"[Orchestrator] ⚠️  UI test atlandı veya başarısız")
                    else:
                        print(f"[Orchestrator] ⏭️  UI test atlandı (web projesi değil)")
                except Exception as e:
                    print(f"[UITester] Hata: {e}")

            # GÖREV 3: Builder Agent (Mobile Build) Kontrolü
            goal_lower = user_goal.lower()
            if any(w in goal_lower for w in ["flet", "apk", "android", "mobile"]):
                BUILDER_WILL_HANDLE = ["paketle", "package", "apk", "mobil için", "build apk", "paketleme"]
                blocking_failures = False
                has_pending = False
                
                for t in tasks:
                    status = self._task_records[t.task_id].status
                    if status not in (TaskStatus.COMPLETED, TaskStatus.SKIPPED, TaskStatus.FAILED):
                        has_pending = True
                    elif status == TaskStatus.FAILED:
                        desc_lower = t.description.lower()
                        if not any(kw in desc_lower for kw in BUILDER_WILL_HANDLE):
                            blocking_failures = True

                if not blocking_failures and not has_pending:
                    if hasattr(self, 'builder') and self.builder:
                        print(f"[Orchestrator] 📱 Mobile/Flet projesi algılandı, BuilderAgent derlemeyi başlatıyor...")
                        build_task = Task(
                            task_id="builder_final",
                            description="Proje kodlarını mobil uygulama (APK) olarak derle.",
                            assigned_to="builder",
                            context={"project_dir": project_dir, "project_slug": slug}
                        )
                        try:
                            b_thought = await self.builder.think(build_task)
                            b_result = await self.builder.act(b_thought, build_task)
                            if b_result.success:
                                print(f"[Orchestrator] ✅ APK Build Başarılı: {b_result.content.get('result', '')}")
                            else:
                                print(f"[Orchestrator] ⚠️ APK Build Hatası: {b_result.content.get('result', '')}")
                        except Exception as e:
                            print(f"[Orchestrator] ⚠️ BuilderAgent Hata fırlattı: {e}")
                else:
                    print(f"[Orchestrator] ⏭️ Yarım kalan (PENDING/FAILED) görevler olduğu için BuilderAgent tetiklenmedi.")

            summary_msg = f"🏁 Session Complete! Tokens: {total_in} in / {total_out} out | Cost: ${total_cost:.4f}"
            self._log(summary_msg)
            await self._emit_status(summary_msg)

            # V5: Memory Agent - Projeyi kaydet
            try:
                memory = get_memory_agent()
                memory.save_project(slug, user_goal, session_data)
            except Exception as e:
                print(f"[Memory] Kayıt hatası (devam ediliyor): {e}")

        except Exception as e:
            self._log(f"Failed to save session memory: {e}")

        try:
            await self._run_docs_agent(
                user_goal=user_goal,
                project_dir=project_dir,
                slug=slug,
            )
        except Exception as e:
            print(f"[Docs] Hata (devam ediliyor): {e}")

        return final_output

    async def _pre_install_project_deps(self, project_dir: str, slug: str):
        """Proje src/ klasöründeki .py dosyalarından 3rd-party importları tespit et ve pip install yap.
        
        Bu sayede Executor hangi yolla çalıştırırsa çalışsın (shell / run_code),
        gerekli paketler önceden yüklenmiş olur.
        """
        import subprocess, re, os, sys
        from pathlib import Path

        STDLIB = {
            "os", "sys", "re", "json", "time", "datetime", "math", "random",
            "pathlib", "subprocess", "asyncio", "threading", "collections",
            "itertools", "functools", "typing", "abc", "io", "csv", "sqlite3",
            "hashlib", "base64", "urllib", "http", "email", "logging",
            "unittest", "copy", "string", "tkinter", "struct", "socket",
            "ssl", "shutil", "glob", "argparse", "textwrap", "decimal",
            "fractions", "statistics", "enum", "dataclasses", "contextlib",
            "tempfile", "uuid", "heapq", "bisect", "queue", "weakref",
            "gc", "inspect", "ast", "dis", "traceback", "warnings",
        }
        STDLIB.update(PHASE_PREINSTALL_STDLIB_MODULES)
        PACKAGE_MAP = {
            "cv2": "opencv-python", "PIL": "Pillow",
            "sklearn": "scikit-learn", "bs4": "beautifulsoup4",
            "dotenv": "python-dotenv", "aiohttp": "aiohttp",
            "aiofiles": "aiofiles", "aiosqlite": "aiosqlite",
            "httpx": "httpx", "pydantic": "pydantic",
            "colorama": "colorama", "rich": "rich",
            "fastapi": "fastapi", "uvicorn": "uvicorn",
            "flask": "Flask", "django": "Django",
            "sqlalchemy": "sqlalchemy", "alembic": "alembic",
            "pytest": "pytest", "lxml": "lxml",
        }

        # src/ ve tests/ klasörlerini tara
        src_dir = Path(project_dir) / "src"
        all_imports: set[str] = set()
        
        # Proje-içi modül isimlerini topla (pip install denemesini engelle)
        project_modules: set[str] = set()
        if src_dir.exists():
            for py_file in src_dir.glob("*.py"):
                project_modules.add(py_file.stem)  # database.py → "database"
            # Alt dizinleri de ekle (paket importları için)
            for sub_dir in src_dir.iterdir():
                if sub_dir.is_dir() and (sub_dir / "__init__.py").exists():
                    project_modules.add(sub_dir.name)
        if project_modules:
            print(f"[Orchestrator] 📂 Proje modülleri (pip dışı): {project_modules}")

        for py_file in list(src_dir.glob("*.py")) if src_dir.exists() else []:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                found = re.findall(r'^(?:import|from)\s+(\w+)', content, re.MULTILINE)
                all_imports.update(found)
            except Exception:
                pass

        third_party = {pkg for pkg in all_imports if pkg not in STDLIB and pkg not in project_modules}
        if not third_party:
            return

        to_install = [PACKAGE_MAP.get(pkg, pkg) for pkg in third_party]
        # 'src' paketini filtrele (gerçek paket değil)
        to_install = [p for p in to_install if p != 'src']
        if not to_install:
            return
        print(f"[Orchestrator] 📦 Faz öncesi pip install: {to_install}")
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install"] + to_install + ["-q"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                print(f"[Orchestrator] ✅ Paketler yüklendi: {to_install}")
            else:
                print(f"[Orchestrator] ⚠️ Pip kısman başarısız: {result.stderr[:200]}")
        except Exception as e:
            print(f"[Orchestrator] ⚠️ Pre-install hata: {e}")

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
        all_completed_ids: set[str] = set()
        existing_files: list[str] = []   # files created so far
        all_tasks: list[Task] = []
        
        # Proje yolunu ayarla (file export analizi için gerekli)
        self.current_project_path = project_dir

        for phase_idx, phase in enumerate(phases):
            phase_name = phase.get("name", f"Faz {phase_idx + 1}")
            tasks: list[Task] = phase.get("tasks", [])

            await self._emit_status(
                f"📦 [{phase_idx+1}/{len(phases)}] {phase_name} başlıyor — {len(tasks)} görev"
            )

            # Inject existing_files context + dosya API bilgisi into every task
            if existing_files:
                file_list = ", ".join(existing_files)
                
                # Dosyaların export bilgisini çıkar (class/function isimleri)
                file_exports = self._extract_file_exports(
                    self.current_project_path, existing_files
                )
                
                # Export özetini oluştur
                api_summary_lines = []
                for fname, info in file_exports.items():
                    parts = []
                    if info.get("classes"):
                        parts.append(f"classes: {', '.join(info['classes'])}")
                    if info.get("functions"):
                        parts.append(f"functions: {', '.join(info['functions'])}")
                    if parts:
                        api_summary_lines.append(f"  {fname}: {'; '.join(parts)}")
                
                api_summary = "\n".join(api_summary_lines) if api_summary_lines else "(henüz analiz edilemedi)"
                
                for t in tasks:
                    t.context["existing_files"] = file_list
                    t.context["file_api"] = api_summary
                    t.context["phase_info"] = (
                        f"Bu faz '{phase_name}'. "
                        f"Onceki fazlarda oluşturulan dosyalar: {file_list}.\n"
                        f"DOSYA API'leri (import edebileceğin sınıf/fonksiyonlar):\n{api_summary}\n"
                        f"KURAL: Bu dosyaları tekrar YAZMA, sadece IMPORT ET. "
                        f"Yukarıdaki class/function isimlerini AYNEN kullan."
                    )

            # Register task records
            for task in tasks:
                self._task_records[task.task_id] = TaskRecord(task)
                task.context["project_slug"] = slug
                if self.user_preferences_context:
                    task.context["user_preferences"] = self.user_preferences_context
            await self._register_session_tasks(tasks)

            # Her faz başında: proje dosyalarındaki 3rd-party importları otomatik yükle
            await self._pre_install_project_deps(project_dir, slug)

            # Execute phase
            phase_results = await self._react_loop(tasks, user_goal, completed_ids=all_completed_ids)
            all_completed_ids.update(t.task_id for t in tasks if self._task_records[t.task_id].status == TaskStatus.COMPLETED)
            all_results.extend(phase_results)
            all_tasks.extend(tasks)

            # Collect files created in this phase
            for r in phase_results:
                # result dogrudan AgentResponse.content olabilir veya {"result": ...} wrapped
                saved = r.get("result", {})
                if not isinstance(saved, dict):
                    saved = {}
                # Hem wrapped hem dogrudan formatı dene
                file_list = (
                    saved.get("saved_files")
                    or saved.get("content", {}).get("saved_files", [])
                    or r.get("saved_files", [])
                )
                for f in file_list:
                    fname = str(f).split("/")[-1].split("\\")[-1].replace(" (fixed)", "")
                    if fname and fname not in existing_files:
                        existing_files.append(fname)

            await self._emit_status(
                f"✅ {phase_name} tamamlandı — toplam dosya: {len(existing_files)}"
            )

            # Ensure main.py exists after phase completion (before tests run)
            await self._ensure_main_py(slug)

            completed = sum(1 for t in tasks if self._task_records[t.task_id].status == TaskStatus.COMPLETED)
            if completed == 0:
                failed_tasks = [t.task_id for t in tasks if self._task_records[t.task_id].status == TaskStatus.FAILED]
                print(f"[UYARI] {phase_name} fazında hiç görev tamamlanamadı!")
                print(f"[UYARI] Başarısız görevler: {failed_tasks}")

        # Aggregate final output
        final_output = await self._aggregate_results(all_results, user_goal)

        # GÖREV 3: Builder Agent (Mobile Build) Kontrolü (Phased mode)
        goal_lower = user_goal.lower()
        if any(w in goal_lower for w in ["flet", "apk", "android", "mobile"]):
            BUILDER_WILL_HANDLE = ["paketle", "package", "apk", "mobil için", "build apk", "paketleme"]
            blocking_failures = False
            has_pending = False
            
            for t in all_tasks:
                status = self._task_records[t.task_id].status
                if status not in (TaskStatus.COMPLETED, TaskStatus.SKIPPED, TaskStatus.FAILED):
                    has_pending = True
                elif status == TaskStatus.FAILED:
                    desc_lower = t.description.lower()
                    if not any(kw in desc_lower for kw in BUILDER_WILL_HANDLE):
                        blocking_failures = True

            if not blocking_failures and not has_pending:
                if hasattr(self, 'builder') and self.builder:
                    print(f"[Orchestrator] 📱 Mobile/Flet projesi algılandı, BuilderAgent derlemeyi başlatıyor (Phased Mode)...")
                    build_task = Task(
                        task_id="builder_final",
                        description="Proje kodlarını mobil uygulama (APK) olarak derle.",
                        assigned_to="builder",
                        context={"project_dir": project_dir, "project_slug": slug}
                    )
                    try:
                        b_thought = await self.builder.think(build_task)
                        b_result = await self.builder.act(b_thought, build_task)
                        if b_result.success:
                            print(f"[Orchestrator] ✅ APK Build Başarılı: {b_result.content.get('result', '')}")
                        else:
                            print(f"[Orchestrator] ⚠️ APK Build Hatası: {b_result.content.get('result', '')}")
                    except Exception as e:
                        print(f"[Orchestrator] ⚠️ BuilderAgent Hata fırlattı: {e}")
            else:
                print(f"[Orchestrator] ⏭️ Yarım kalan (PENDING/FAILED) görevler olduğu için BuilderAgent tetiklenmedi.")

        # V4: Session sonu requirements.txt uret
        if _REQ_GEN_AVAILABLE:
            try:
                req_result = generate_requirements(project_dir)
                if req_result["success"] and req_result.get("packages"):
                    print(f"[Orchestrator] requirements.txt olusturuldu: {len(req_result['packages'])} paket")
                    # Git commit requirements.txt icin
                    if _GIT_AVAILABLE:
                        git_commit(project_dir, "chore: requirements.txt guncellendi")
            except Exception as e:
                print(f"[Requirements] Hata: {e}")

        # V4: Son git commit
        if _GIT_AVAILABLE:
            try:
                git_commit(project_dir, f"feat: Proje tamamlandi - {user_goal[:60]}")
            except Exception as e:
                print(f"[Git] Final commit hatasi: {e}")

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

            # V5: Memory Agent - Projeyi kaydet (phased mode)
            try:
                memory = get_memory_agent()
                memory.save_project(slug, user_goal, session_data)
            except Exception as e:
                print(f"[Memory] Kayıt hatası (devam ediliyor): {e}")

        except Exception as e:
            self._log(f"Phase session save failed: {e}")

        try:
            await self._run_docs_agent(
                user_goal=user_goal,
                project_dir=project_dir,
                slug=slug,
            )
        except Exception as e:
            print(f"[Docs] Hata (devam ediliyor): {e}")

        # Final check: Ensure main.py exists before returning
        await self._ensure_main_py(slug)

        return final_output

    async def _run_docs_agent(self, user_goal: str, project_dir: str, slug: str) -> None:
        """Tum gorevler tamamlandiktan sonra dokumantasyon uret."""
        docs_agent = self.docs or self.agents.get("docs")
        if not docs_agent:
            return

        docs_task = Task(
            task_id="docs_final",
            description=f"Generate project documentation for goal: {user_goal}",
            assigned_to="docs",
            context={
                "goal": user_goal,
                "project_slug": slug,
                "project_dir": project_dir,
            },
        )

        thought = await docs_agent.think(docs_task)
        docs_response = await docs_agent.act(thought, docs_task)
        if not docs_response.success:
            print(f"[Docs] Dokumantasyon uretilmedi: {docs_response.error}")
            return

        payload = docs_response.content if isinstance(docs_response.content, dict) else {}
        readme_content = str(payload.get("readme_content", "") or "")

        if not readme_content:
            docs_readme = Path(project_dir) / "docs" / "README.md"
            if docs_readme.exists():
                readme_content = docs_readme.read_text(encoding="utf-8", errors="ignore")

        if not readme_content.strip():
            print("[Docs] README icerigi bos, kok README olusturulmadi.")
            return

        readme_path = Path(project_dir) / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        line_count = len(readme_content.splitlines())
        print(f"[Docs] README.md oluşturuldu ({line_count} satır)")

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

    async def _react_loop(self, tasks: list[Task], user_goal: str, completed_ids: set[str] = None) -> list[dict]:
        """
        ReAct loop: Reason → Act → Observe → Reason...
        Handles dependencies, parallel execution, and re-planning.
        
        GELİŞTİRME 3: Paralel Görev Çalıştırma
        - Aynı faz içindeki bağımsız task'lar paralel çalışır
        - Bağımlılık kontrolü: task.dependencies ve task.context.get("depends_on")
        - Paralel/sıralı execution loglanır
        """
        results = []
        completed_ids: set[str] = set(completed_ids) if completed_ids else set()
        self._iteration = 0

        while self._iteration < MAX_ITERATIONS:
            self._iteration += 1
            await self._emit_status(f"⚙️  Iteration {self._iteration}/{MAX_ITERATIONS}")
            _ws_broadcast({"type": "react_step", "step": self._iteration,
                           "thought": f"Iteration {self._iteration}/{MAX_ITERATIONS}"})


            # GELİŞTİRME 3: Find tasks ready to execute (all dependencies satisfied)
            # Hem task.dependencies hem de context["depends_on"] kontrol edilir
            ready_tasks = []
            for t in tasks:
                if t.task_id in completed_ids:
                    continue
                if self._task_records[t.task_id].status != TaskStatus.PENDING:
                    continue
                    
                # Bağımlılık kontrolü
                deps = set(t.dependencies)
                context_deps = t.context.get("depends_on", [])
                if isinstance(context_deps, str):
                    context_deps = [context_deps]
                deps.update(context_deps)
                
                if all(dep in completed_ids for dep in deps):
                    ready_tasks.append(t)

            if not ready_tasks:
                if all(self._task_records[t.task_id].status == TaskStatus.COMPLETED for t in tasks):
                    await self._emit_status("✅ All tasks completed!")
                    break
                elif all(self._task_records[t.task_id].status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED) for t in tasks):
                    await self._emit_status("⚠️  All tasks settled (some may have failed).")
                    break
                else:
                    # Deadlock Detection: ready_tasks yok, fakat PENDING task var ve çalışan task yok
                    in_progress = [t for t in tasks if self._task_records[t.task_id].status == TaskStatus.IN_PROGRESS]
                    pending = [t for t in tasks if self._task_records[t.task_id].status == TaskStatus.PENDING]
                    
                    if not in_progress and pending:
                        deadlocked_ids = [t.task_id for t in pending]
                        print(f"[Orchestrator] ⚠️ Deadlock tespit edildi, bağımlılıklar sıfırlanıyor: {deadlocked_ids}")
                        await self._emit_status(f"⚠️ Deadlock tespit edildi, bağımlılıklar kırılıyor...")
                        
                        for t in pending:
                            t.dependencies = [dep for dep in t.dependencies if dep in completed_ids]
                            if "depends_on" in t.context:
                                context_deps = t.context["depends_on"]
                                if isinstance(context_deps, str):
                                    context_deps = [context_deps]
                                t.context["depends_on"] = [dep for dep in context_deps if dep in completed_ids]
                        continue
                    
                    await asyncio.sleep(0.5)
                    continue

            # Enrich tasks with context from completed results
            for task in ready_tasks:
                await self._enrich_task_context(task, results)
                task.context["project_slug"] = self.current_project_slug

            # GELİŞTİRME 3: Paralel execution logging
            print(f"[Orchestrator] 🚀 {len(ready_tasks)} task paralel çalıştırılıyor: {[t.task_id for t in ready_tasks]}")
            
            # Execute ready tasks (parallel)
            await self._emit_status(
                f"🚀 Executing {len(ready_tasks)} task(s) in parallel: "
                f"{[t.task_id for t in ready_tasks]}"
            )
            batch_results = await asyncio.gather(
                *[self._execute_task_with_timeout(task) for task in ready_tasks],
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
                        await self._record_completed_result(results, task, result.content)
                        await self._emit_status(f"✅ Task {task.task_id} completed by {task.assigned_to}")
                    elif result and result.metadata.get("timed_out"):
                        record.status = TaskStatus.FAILED
                        record.attempts = record.max_attempts
                        completed_ids.add(task.task_id)
                        await self._emit_status(
                            f"❌ Task {task.task_id} failed: Timeout: görev 6 dakikada tamamlanamadı"
                        )
                    else:
                        record.attempts += 1
                        # DEBUG: log agent response on failure
                        _response_preview = getattr(result, "content", None) if result else None
                        # Fix: Ensure _response_preview is sliceable (string or list)
                        if _response_preview and isinstance(_response_preview, (str, list, bytes)):
                            preview_str = repr(_response_preview[:500])
                        else:
                            preview_str = repr(_response_preview)
                        print(f"[DEBUG] Task {task.task_id} failed (attempt {record.attempts}). Agent response: {preview_str}")
                        if record.attempts >= record.max_attempts:
                            # Flet Test Loop Fix
                            task_desc_lower = task.description.lower()
                            is_run_or_test = any(w in task_desc_lower for w in ["çalıştır", "test et", "run", "test"])
                            is_flet = "flet" in user_goal.lower() or "flet" in getattr(self, "shared_context", "").lower()

                            if is_run_or_test and is_flet:
                                print("[Orchestrator] ⚠️ Test hatası görmezden gelindi (Flet projesi)")
                                record.status = TaskStatus.COMPLETED
                                completed_ids.add(task.task_id)
                                await self._record_completed_result(
                                    results,
                                    task,
                                    "Completed with warnings (Flet test error ignored)",
                                )
                                await self._emit_status(f"⚠️ Task {task.task_id} completed with warnings (Flet app)")
                            else:
                                record.status = TaskStatus.FAILED
                                completed_ids.add(task.task_id)
                                await self._emit_status(f"❌ Task {task.task_id} failed after {record.max_attempts} attempts")
                        else:
                            record.status = TaskStatus.PENDING
                            err_str = str(result.error) if result and result.error else ""
                            retry_fix_hint = ""
                            if result and getattr(result, "metadata", None):
                                retry_fix_hint = str(result.metadata.get("fix_hint", "") or "").strip()

                            if retry_fix_hint:
                                task.context["fix_hint"] = retry_fix_hint
                            elif "ModuleNotFoundError" in err_str or "ImportError" in err_str:
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

    def _extract_task_file_paths(self, task: Task) -> list[str]:
        """Task context/description içinden yazma hedefi olabilecek dosya yollarını çıkar."""
        candidates: list[str] = []

        context_keys = (
            "file_path",
            "filepath",
            "path",
            "target_file",
            "target_path",
            "output_file",
            "filename",
            "file",
            "files",
            "paths",
            "target_files",
            "write_file",
        )

        for key in context_keys:
            value = task.context.get(key)
            if not value:
                continue
            if isinstance(value, str):
                candidates.append(value)
            elif isinstance(value, list):
                candidates.extend(str(item) for item in value if isinstance(item, str))

        candidates.extend(
            re.findall(r"(?<!\w)([\w./\\-]+\.[A-Za-z0-9]{1,8})(?!\w)", task.description or "")
        )

        normalized = []
        seen = set()
        for candidate in candidates:
            cleaned = str(candidate).strip().strip("\"'")
            if not cleaned:
                continue
            key = os.path.normpath(cleaned).lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(key)

        return normalized

    async def _get_file_write_lock(self, lock_key: str) -> asyncio.Lock:
        async with self._file_write_locks_guard:
            lock = self._file_write_locks.get(lock_key)
            if lock is None:
                lock = asyncio.Lock()
                self._file_write_locks[lock_key] = lock
            return lock

    @asynccontextmanager
    async def _task_file_write_lock(self, task: Task):
        lock_keys = self._extract_task_file_paths(task)
        if not lock_keys:
            yield
            return

        async with AsyncExitStack() as stack:
            for lock_key in sorted(lock_keys):
                lock = await self._get_file_write_lock(lock_key)
                await stack.enter_async_context(lock)
            yield

    async def _execute_task_isolated(self, task: Task) -> Optional[AgentResponse]:
        """Task'ı hata izolasyonuyla ve dosya-yazma kilidiyle çalıştır."""
        try:
            async with self._task_file_write_lock(task):
                return await self._execute_task(task)
        except Exception as e:
            logger.exception("Task crashed: %s", task.task_id)
            return AgentResponse(
                content=None,
                success=False,
                error=f"Unhandled task execution error: {e}",
            )

    async def _execute_task(self, task: Task) -> Optional[AgentResponse]:
        """GELİŞTİRME 5: Route a task to the appropriate agent and execute it.
        
        Her ajanın aldığı context, o ajanın işiyle ilgili bilgiyle sınırlandırılır.
        """
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

        self._inject_security_feedback_prefix(task)
        await self._emit_status(f"🤖 {agent.name} working on: {task.description[:60]}...")
        _ws_broadcast({"type": "agent_status", "agent": task.assigned_to,
                       "status": "thinking", "task": task.description[:80]})

        # Cluster mode: Coder için model override
        if task.assigned_to == "coder" and self.coder_model_override:
            task.context["model_override"] = self.coder_model_override

        # Coder mevcut dosyalardan (src/) haberdar olsun diye ilk 500 satırları ver
        if task.assigned_to in ("coder", "coder_fast"):
            from pathlib import Path
            project_slug = getattr(self, "current_project_slug", "default")
            project_root = Path("workspace/projects") / project_slug
            src_dir = project_root / "src"

            is_test_task = "test" in task.description.lower() or "test" in task.task_id.lower()

            if is_test_task:
                if src_dir.exists():
                    py_files = [f.name for f in src_dir.glob("*.py") if f.name != "__init__.py"]
                    if py_files:
                        exports = self._extract_file_exports(str(project_root), py_files)
                        api_context = "Mevcut modüller:\n"
                        for fname, info in exports.items():
                            api_context += f"[{fname}]\n"
                            for cls in info.get("classes", []):
                                api_context += f"  - class {cls}\n"
                            for func in info.get("functions", []):
                                api_context += f"  - def {func}\n"
                        task.context["file_api"] = api_context
            else:
                existing_code = {}
                if src_dir.exists():
                    for f in src_dir.glob("*.py"):
                        if f.name != "__init__.py":
                            try:
                                existing_code[f.name] = f.read_text(encoding="utf-8")[:500]
                            except Exception:
                                pass
                if existing_code:
                    task.context["existing_files"] = existing_code

        # GELİŞTİRME 5: Context sıkıştırma - Her ajan için filtrelenmiş context
        original_context_size = len(str(task.context))
        task = self._build_context_for_agent(task)
        filtered_context_size = len(str(task.context))

        original_tokens = original_context_size // 4
        filtered_tokens = filtered_context_size // 4
        
        # Log context details
        context_keys = list(task.context.keys()) if task.context else []
        print(f"[Context] {task.assigned_to} için context: {filtered_tokens:,} token (full: {original_tokens:,} token, tasarruf: {original_tokens - filtered_tokens:,})")
        print(f"[Context] {task.assigned_to} context keys: {context_keys}")
        if filtered_tokens < 50 and task.assigned_to in ("coder", "coder_fast", "researcher"):
            print(f"[Context] ⚠️ UYARI: {task.assigned_to} için context çok düşük ({filtered_tokens} token)!")
            print(f"[Context] Task description: {task.description[:200]}")

        # Execute agent
        response = await agent.run(task)
        _ws_broadcast({"type": "agent_status", "agent": task.assigned_to,
                       "status": "done",
                       "model": getattr(getattr(agent, "_llm", None), "model_key", ""),
                       "success": response.success})

        # V4: Coder tamamlandiysa Tester'i otomatik calistir
        if response.success and task.assigned_to == "coder" and self._tester:
            try:
                print("[Orchestrator] Testler calistiriliyor...")
                test_task = Task(
                    task_id=f"test_{task.task_id}",
                    description=f"{task.task_id} testlerini calistir",
                    assigned_to="tester",
                    context={"project_slug": getattr(self, "current_project_slug", "default")},
                )
                test_thought = await self._tester.think(test_task)
                test_result = await self._tester.act(test_thought, test_task)
                test_data = test_result.content if isinstance(test_result.content, dict) else {}
                print(f"[Orchestrator] Test sonucu: {test_data.get('summary', '')}")

                if not test_result.success and test_data.get("failed", 0) > 0:
                    failed_info = "\n".join(test_data.get("failed_tests", []))
                    task.context["test_failures"] = failed_info
                    print(f"[Orchestrator] {test_data.get('failed', 0)} test basarisiz")
            except Exception as e:
                print(f"[Tester] Hata: {e}")

        # V4: Tester bittikten sonra Linter'i calistir (Coder ise)
        if response.success and task.assigned_to == "coder" and hasattr(self, 'linter'):
            try:
                print("[Orchestrator] Kod kalitesi kontrol ediliyor...")
                lint_task = Task(
                    task_id=f"lint_{task.task_id}",
                    description=f"{task.task_id} lint kontrolü",
                    assigned_to="linter",
                    context={"project_slug": getattr(self, "current_project_slug", "default")},
                )
                # think() + act() — act now requires thought parameter
                lint_thought = await self.linter.think(lint_task)
                lint_result = await self.linter.act(lint_thought, lint_task)
                lint_data = lint_result.content if isinstance(lint_result.content, dict) else {}

                lint_score = lint_data.get("final_score", 0)
                has_critical = bool(lint_data.get("critical_issues"))

                if not lint_result.success or (has_critical and lint_score < 8.0):
                    issues_text = "\n".join(lint_data.get("critical_issues", [])[:5])
                    task.context["lint_issues"] = issues_text
                    task.context["lint_score"] = lint_score
                    print(f"[Orchestrator] Lint skoru dusuk ({lint_score:.1f}/10), Coder'a gonderiliyor")
                    record.status = TaskStatus.PENDING
                    record.attempts += 1
                    response.success = False
                else:
                    print(f"[Orchestrator] Lint: {lint_data.get('summary', '')}")

                self._session_lint_score = lint_data.get("final_score", 0)

            except Exception as e:
                print(f"[Linter] Hata: {e}")

        # V4: Basarili gorev sonrasi git commit
        if response.success and _GIT_AVAILABLE:
            try:
                project_slug = getattr(self, "current_project_slug", "default")
                project_dir = f"workspace/projects/{project_slug}"
                git_commit(project_dir, f"agent({task.assigned_to}): {task.description[:60]}")
            except Exception as e:
                print(f"[Git] Commit hatasi: {e}")

        # Send to critic/security review for coder outputs
        if response.success and response.content and task.assigned_to == "coder":
            critic_response = await self._critic_review(task, response)
            print(f"[Optimizer DEBUG] _critic_review return: {critic_response}")
            response = critic_response
        if response.success and response.content and task.assigned_to == "coder":
            response = await self._security_review(task, response)
        if response.success and response.content and task.assigned_to == "coder":
            response = await self._optimizer_review(task, response)

        return response


    def _build_context_for_agent(self, task: Task) -> Task:
        """GELİŞTİRME 5: Ajan bazlı context sıkıştırma.
        
        Her ajanın aldığı context, o ajanın işiyle ilgili bilgiyle sınırlandırılır.
        
        Kural tablosu:
        - Planner → Sadece kullanıcı hedefini alsın
        - Researcher → Planner çıktısı özeti + kendi görevi (min 100 token)
        - Coder → Researcher bulguları + kendi görevi + varsa önceki dosyalar listesi (min 200 token)
        - Critic → Sadece inceleyeceği kod dosyası + görev tanımı
        - Executor → Sadece çalıştıracağı dosya adı/yolu + komutlar
        - Tester → Sadece test edilecek proje slug'ı
        - Linter → Sadece lint edilecek proje slug'ı
        """
        agent_type = task.assigned_to
        filtered_context = {}
        
        if agent_type == "planner":
            # Planner: Sadece kullanıcı hedefi (zaten task.description'da)
            # Ek context'e ihtiyacı yok
            pass
            
        elif agent_type == "researcher":
            # Researcher: Planner çıktısı özeti + kendi görevi
            # Minimum 100 token context gerekli
            if "planner_output" in task.context:
                planner_text = str(task.context["planner_output"])
                # Minimum 400 karakter (yaklaşık 100 token) sağla
                filtered_context["planner_summary"] = planner_text[:max(400, len(planner_text))]
            if "user_goal" in task.context:
                filtered_context["user_goal"] = task.context["user_goal"]
            
            # FALLBACK: Eğer context boş kalacaksa, task'ın kendi description'ını ekle
            if not filtered_context:
                # İlk task'ta planner_output veya user_goal olmayabilir
                # Bu durumda task'ın kendi description'ı araştırma konusudur
                filtered_context["task_description"] = task.description
                # Eğer varsa project_slug'ı da ekle (proje bağlamı için)
                if "project_slug" in task.context:
                    filtered_context["project_slug"] = task.context["project_slug"]
                
        elif agent_type in ("coder", "coder_fast"):
            # Coder/Coder_Fast: Researcher bulguları + kendi görevi + dosya API'si
            # Minimum 200 token context gerekli (800 karakter)
            
            # ALWAYS inject task description for coder (ensures minimum context)
            filtered_context["task_description"] = task.description
            
            if "research" in task.context:
                research_text = str(task.context["research"])
                # Minimum 800 karakter (yaklaşık 200 token) sağla
                filtered_context["research"] = research_text[:max(800, len(research_text))]
            if "existing_files" in task.context:
                filtered_context["existing_files"] = task.context["existing_files"]
            if "file_api" in task.context:
                filtered_context["file_api"] = task.context["file_api"]
            if "phase_info" in task.context:
                filtered_context["phase_info"] = task.context["phase_info"]
            if "critic_feedback" in task.context:
                filtered_context["critic_feedback"] = task.context["critic_feedback"]
            if "test_failures" in task.context:
                filtered_context["test_failures"] = task.context["test_failures"]
            if "lint_issues" in task.context:
                filtered_context["lint_issues"] = task.context["lint_issues"]
                filtered_context["lint_score"] = task.context.get("lint_score", 0)
            if "fix_hint" in task.context:
                filtered_context["fix_hint"] = task.context["fix_hint"]
            if "model_override" in task.context:
                filtered_context["model_override"] = task.context["model_override"]
            
            # ALWAYS inject user_goal if available (ensures coder knows the overall objective)
            if "user_goal" in task.context:
                filtered_context["user_goal"] = task.context["user_goal"]
            
            if "project_slug" in task.context:
                filtered_context["project_slug"] = task.context["project_slug"]
                
                # NEW: Inject contract if available
                from pathlib import Path
                project_slug = task.context["project_slug"]
                project_root = Path("workspace/projects") / project_slug
                contract_path = project_root / "contract.json"
                
                if contract_path.exists():
                    try:
                        import json
                        contract_text = contract_path.read_text(encoding="utf-8")
                        contract_data = json.loads(contract_text)
                        filtered_context["project_contract"] = contract_data
                        
                        # Log contract injection for debugging
                        print(f"[Orchestrator] Injected contract into {task.task_id}: "
                              f"{len(contract_data.get('data_models', []))} models, "
                              f"{len(contract_data.get('api_endpoints', []))} endpoints, "
                              f"{len(contract_data.get('file_structure', []))} files")
                    except json.JSONDecodeError as e:
                        logging.error(f"[Orchestrator] Contract parse failed for {project_slug}: {e}")
                    except Exception as e:
                        logging.warning(f"[Orchestrator] Could not load contract for {project_slug}: {e}")
                
                # Read existing files in the project to provide context
                src_dir = project_root / "src"
                
                existing_code = {}
                existing_files_list = []
                
                if src_dir.exists():
                    for py_file in src_dir.glob("*.py"):
                        if py_file.name == "__init__.py":
                            continue
                        
                        try:
                            content = py_file.read_text(encoding="utf-8")
                            # Cap at 500 characters to avoid context overflow
                            existing_code[py_file.name] = content[:500]
                            existing_files_list.append(py_file.name)
                        except Exception as e:
                            print(f"[Context] ⚠️ Could not read {py_file.name}: {e}")
                    
                    if existing_code:
                        print(f"[Context] 📁 Coder'a {len(existing_code)} dosya eklendi: {existing_files_list}")
                
                # ALWAYS inject existing_code (even if empty) so coder knows the state
                filtered_context["existing_code"] = existing_code
                if existing_files_list:
                    filtered_context["existing_files"] = existing_files_list
                
        elif agent_type == "critic":
            # Critic: Sadece inceleyeceği kod + görev tanımı
            if "content" in task.context:
                filtered_context["content"] = task.context["content"]
            if "content_type" in task.context:
                filtered_context["content_type"] = task.context["content_type"]
            if "original_task" in task.context:
                filtered_context["original_task"] = task.context["original_task"]
            if "revision_count" in task.context:
                filtered_context["revision_count"] = task.context["revision_count"]
                
        elif agent_type == "executor":
            # Executor: Sadece dosya adı/yolu + komutlar + coder çıktısı
            if "filename" in task.context:
                filtered_context["filename"] = task.context["filename"]
            if "coder_output" in task.context:
                filtered_context["coder_output"] = task.context["coder_output"]
            if "all_previous_results" in task.context:
                # Executor'a tüm sonuçlar gerekli (hangi dosyayı çalıştıracağını bilmesi için)
                filtered_context["all_previous_results"] = task.context["all_previous_results"]
            if "fix_hint" in task.context:
                filtered_context["fix_hint"] = task.context["fix_hint"]
            if "project_slug" in task.context:
                filtered_context["project_slug"] = task.context["project_slug"]
                
        elif agent_type in ["tester", "linter"]:
            # Tester/Linter: Sadece proje slug'ı
            if "project_slug" in task.context:
                filtered_context["project_slug"] = task.context["project_slug"]
        
        else:
            # Bilinmeyen ajan tipi: Tüm context'i koru
            filtered_context = task.context.copy()
        
        # Filtrelenmiş context'i task'a ata
        task.context = filtered_context
        return task


    async def _critic_review(self, task: Task, response: AgentResponse) -> AgentResponse:
        """Have the critic review a response. If score < 7, request revision.
        
        GELİŞTİRME 1: Critic → Coder Feedback Loop
        - Maksimum 3 iterasyon
        - Her iterasyonda Critic feedback'i Coder'a iletilir
        - "approve" gelirse döngüden çık
        - İterasyon sayısı loglanır
        """
        critic = self.agents.get("critic")
        if not critic:
            print(f"[CRITIC RAW] response type: {type(response)}, success: {getattr(response, 'success', 'N/A')}, content: {str(getattr(response, 'content', ''))[:200]}")
            return response

        content = response.content
        if isinstance(content, dict):
            content_str = str(content.get("code_response") or content.get("synthesis") or content)
        else:
            content_str = str(content)

        revision_count = 0
        max_iterations = 2  # OPTİMİZASYON: 3 → 2 (timeout önleme)
        last_critic_response: dict[str, Any] = {}
        
        while revision_count < max_iterations:
            # GELİŞTİRME 1: İterasyon logla
            if revision_count > 0:
                print(f"[Orchestrator] Iterasyon {revision_count}/{max_iterations}")
            
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
                review_data = review_response.content if isinstance(review_response.content, dict) else {}
                last_critic_response = review_data
                print(f"[Optimizer DEBUG] raw critic response: {review_data}")
                
                # BUG FIX 2: routing default "CODER_REVISE" olmalı (EXECUTOR değil!)
                routing = review_data.get("routing", "CODER_REVISE")
                score = review_data.get(
                    "score",
                    review_data.get("average", review_response.metadata.get("score", 0.0))
                )
                try:
                    score = float(score)
                except Exception:
                    score = 0.0
                # BUG FIX 2: approved default False olmalı (True değil!)
                approved = review_data.get("approved", False)  # GELİŞTİRME 1: approved flag
                
                # Critic skorunu kaydet (cluster mode için)
                self._critic_scores.append(score)
                
                await self._emit_status(f"🔍 Critic score: {score}/10 — Routing: {routing}")

                # GELİŞTİRME 1: "approve" gelirse döngüden çık
                if approved or routing in ["EXECUTOR", "EXECUTOR_ANYWAY"]:
                    response.metadata["critic_score"] = score
                    response.metadata["critic_verdict"] = routing
                    response.metadata["critic_raw_response"] = review_data
                    response.metadata["iterations"] = revision_count + 1  # GELİŞTİRME 1: İterasyon sayısı
                    if revision_count > 0:
                        print(f"[Orchestrator] ✅ Critic onayladı ({revision_count + 1} iterasyon)")
                    print(f"[CRITIC RAW] response type: {type(response)}, success: {getattr(response, 'success', 'N/A')}, content: {str(getattr(response, 'content', ''))[:200]}")
                    return response
                    
                elif routing == "PLANNER_REPLAN":
                    response.metadata["critic_score"] = score
                    response.metadata["critic_verdict"] = routing
                    response.metadata["critic_raw_response"] = review_data
                    response.success = False
                    response.error = "Critic rejected the approach (score < 4), replan required."
                    print(f"[CRITIC RAW] response type: {type(response)}, success: {getattr(response, 'success', 'N/A')}, content: {str(getattr(response, 'content', ''))[:200]}")
                    return response

                # GELİŞTİRME 1: CODER_REVISE - Feedback'i Coder'a ilet
                revision_count += 1
                agent = self.agents.get(task.assigned_to)
                if agent:
                    issues = "\n- ".join(review_data.get("issues", []))
                    improvements = "\n- ".join(review_data.get("improvements", []))
                    summary = review_data.get("summary", "")
                    
                    # GELİŞTİRME 1: Detaylı feedback mesajı
                    revision_instructions = (
                        f"Critic Feedback (Skor: {score}/10):\n\n"
                        f"Özet: {summary}\n\n"
                        f"Sorunlar:\n- {issues}\n\n"
                        f"İyileştirme Önerileri:\n- {improvements}\n\n"
                        f"Lütfen bu geri bildirimlere göre kodu revize et."
                    )
                    
                    print(f"[Orchestrator] 🔄 Revizyon gerekli (Skor: {score}/10) - Coder'a geri gönderiliyor...")
                    
                    revised_task = Task(
                        task_id=f"{task.task_id}_rev{revision_count}",
                        description=f"{task.description}\n\n{revision_instructions}",
                        assigned_to=task.assigned_to,
                        context={**task.context, "critic_feedback": revision_instructions},  # GELİŞTİRME 1: Feedback context'e eklendi
                    )
                    response = await agent.run(revised_task)
                    if isinstance(response.content, dict):
                        content_str = str(response.content.get("code_response") or response.content.get("synthesis") or response.content)
                    else:
                        content_str = str(response.content)
            else:
                break

        # GELİŞTİRME 1: 3 iterasyon sonunda hala revise ise devam et (takılı kalma)
        if revision_count >= max_iterations:
            print(f"[Orchestrator] ⚠️ Maksimum iterasyon ({max_iterations}) aşıldı, devam ediliyor...")
            response.metadata["critic_score"] = score if 'score' in locals() else 6.0
            response.metadata["critic_verdict"] = "MAX_ITERATIONS_REACHED"
            response.metadata["critic_raw_response"] = last_critic_response
            response.metadata["iterations"] = revision_count

        final_score = response.metadata.get("critic_score", 0.0)
        if not final_score and "score" in locals():
            final_score = score
        try:
            final_score = float(final_score)
        except Exception:
            final_score = 0.0
        self._critic_scores.append(float(final_score))

        print(f"[CRITIC RAW] response type: {type(response)}, success: {getattr(response, 'success', 'N/A')}, content: {str(getattr(response, 'content', ''))[:200]}")
        return response

    @staticmethod
    def _inject_security_feedback_prefix(task: Task) -> None:
        """Security feedback'i coder prompt'unun başına enjekte et."""
        if task.assigned_to not in ("coder", "coder_fast"):
            return

        security_feedback = str(task.context.get("security_feedback", "")).strip()
        if not security_feedback:
            return

        if task.description.startswith(security_feedback):
            task.context.pop("security_feedback", None)
            return

        task.description = f"{security_feedback}\n\n{task.description}"
        # Context içinde gömülü taşımayı bırak; prompt başında taşınsın.
        task.context.pop("security_feedback", None)

    @staticmethod
    def _extract_python_files_from_response(response: AgentResponse) -> list[str]:
        """Coder cevabından taranacak .py dosya yollarını çıkar."""
        content = response.content if isinstance(response.content, dict) else {}
        candidates = []

        saved_files = content.get("saved_files", [])
        if isinstance(saved_files, str):
            saved_files = [saved_files]
        if isinstance(saved_files, list):
            candidates.extend([str(path) for path in saved_files if path])

        metadata_files = response.metadata.get("files_created", [])
        if isinstance(metadata_files, str):
            metadata_files = [metadata_files]
        if isinstance(metadata_files, list):
            candidates.extend([str(path) for path in metadata_files if path])

        for entry in content.get("files", []):
            if not isinstance(entry, dict):
                continue
            file_name = str(entry.get("file") or entry.get("file_name") or "").strip()
            if file_name:
                candidates.append(file_name)

        py_files: list[str] = []
        seen = set()
        for raw in candidates:
            clean = str(raw).replace(" (fixed)", "").strip()
            if not clean.endswith(".py"):
                continue
            norm = os.path.normpath(clean).lower()
            if norm in seen:
                continue
            seen.add(norm)
            py_files.append(clean)

        return py_files

    async def _security_review(self, task: Task, response: AgentResponse) -> AgentResponse:
        """Critic onayı sonrası Python çıktıları için güvenlik taraması uygula."""
        security = self.security or self.agents.get("security")
        if not security:
            return response

        py_files = self._extract_python_files_from_response(response)
        if not py_files:
            return response

        security_task = Task(
            task_id=f"security_{task.task_id}",
            description=f"Security scan for: {task.description}",
            assigned_to="security",
            context={
                "files": py_files,
                "project_slug": getattr(self, "current_project_slug", "default"),
                "original_task": task.description,
            },
        )

        try:
            security_thought = await security.think(security_task)
            security_response = await security.act(security_thought, security_task)
        except Exception as e:
            print(f"[Security] Tarama hatası: {e}")
            return response

        if not security_response.success:
            print("[Security] Tarama başarısız, kritik blok yapılmadı.")
            return response

        data = security_response.content if isinstance(security_response.content, dict) else {}
        issues = data.get("issues", [])
        if not isinstance(issues, list):
            issues = []

        try:
            score = float(data.get("score", 10.0))
        except Exception:
            score = 10.0

        high_issues = [i for i in issues if str(i.get("severity", "")).upper() == "HIGH"]
        medium_issues = [i for i in issues if str(i.get("severity", "")).upper() == "MEDIUM"]

        print(f"[Security] score: {score:.1f} | {len(high_issues)} HIGH, {len(medium_issues)} MEDIUM")
        await self._emit_status(
            f"[Security] score: {score:.1f} | {len(high_issues)} HIGH, {len(medium_issues)} MEDIUM"
        )

        response.metadata["security_score"] = score
        response.metadata["security_issues"] = issues
        response.metadata["security_high_count"] = len(high_issues)
        response.metadata["security_medium_count"] = len(medium_issues)

        if high_issues:
            security_feedback = (
                "GÜVENLİK AÇIĞI TESPİT EDİLDİ. BUNLARI DÜZELTMEDİKÇE "
                "ONAYLANMAYACAKSIN:\n"
                + "\n".join([f"- {i.get('type', 'SECURITY')}: {i.get('detail', '')}" for i in issues])
            )
            task.context["security_feedback"] = security_feedback
            response.success = False
            response.error = "Security review rejected: HIGH severity issue(s) found."
            print("[Security] 🔄 HIGH bulgu nedeniyle Coder revizyonu istendi.")

        return response

    @staticmethod
    def _resolve_python_file_path(file_ref: str, project_slug: str) -> Optional[Path]:
        """Dosya referansını workspace içindeki gerçek .py dosyasına çözümle."""
        cleaned = str(file_ref or "").replace(" (fixed)", "").strip()
        if not cleaned:
            return None

        path_obj = Path(cleaned)
        candidates = [path_obj]
        if not path_obj.is_absolute():
            project_root = Path("workspace/projects") / project_slug
            candidates.extend([
                project_root / path_obj,
                project_root / "src" / path_obj,
                project_root / "tests" / path_obj,
            ])

        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file() and candidate.suffix == ".py":
                    return candidate
            except Exception:
                continue
        return None

    async def _optimizer_review(self, task: Task, response: AgentResponse) -> AgentResponse:
        """Security review sonrası, yeterli Critic skorlu kodu optimize et."""
        optimizer = self.optimizer or self.agents.get("optimizer")
        if not optimizer:
            return response

        critic_score = self._avg_critic_score if self._avg_critic_score > 0 else (
            self._critic_scores[-1] if self._critic_scores else 0.0
        )
        print(f"[Optimizer DEBUG] _critic_scores: {self._critic_scores}, using: {critic_score}")
        print(f"[Optimizer DEBUG] critic_score={critic_score}, çalışıyor mu: {critic_score >= 6.0}")
        if critic_score < 6.0:
            return response

        project_slug = getattr(self, "current_project_slug", "default")
        py_files = self._extract_python_files_from_response(response)
        if not py_files:
            return response

        total_before = 0.0
        total_after = 0.0
        total_optimizations = 0
        processed = 0
        optimized_paths = []

        for file_ref in py_files:
            resolved_path = self._resolve_python_file_path(file_ref, project_slug)
            if not resolved_path:
                continue

            try:
                original_code = resolved_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if not original_code.strip():
                continue

            optimizer_task = Task(
                task_id=f"optimizer_{task.task_id}_{resolved_path.stem}",
                description=f"Optimize Python code for {resolved_path.name}",
                assigned_to="optimizer",
                context={
                    "file_path": str(resolved_path),
                    "code": original_code,
                    "original_task": task.description,
                },
            )

            try:
                optimizer_thought = await optimizer.think(optimizer_task)
                optimizer_response = await optimizer.act(optimizer_thought, optimizer_task)
            except Exception as e:
                print(f"[Optimizer] Hata ({resolved_path.name}): {e}")
                continue

            if not optimizer_response.success or not isinstance(optimizer_response.content, dict):
                continue

            data = optimizer_response.content
            optimized_code = str(data.get("optimized_code", "") or "")
            optimizations = data.get("optimizations", [])
            if isinstance(optimizations, str):
                optimizations = [optimizations]
            if not isinstance(optimizations, list):
                optimizations = []

            try:
                score_before = float(data.get("score_before", 0.0))
            except Exception:
                score_before = 0.0
            try:
                score_after = float(data.get("score_after", score_before))
            except Exception:
                score_after = score_before

            if optimized_code and optimized_code != original_code:
                try:
                    resolved_path.write_text(optimized_code, encoding="utf-8")
                    optimized_paths.append(str(resolved_path))
                except Exception as e:
                    print(f"[Optimizer] Yazma hatası ({resolved_path.name}): {e}")

            total_before += score_before
            total_after += score_after
            total_optimizations += len([o for o in optimizations if str(o).strip()])
            processed += 1

        if processed > 0:
            avg_before = round(total_before / processed, 1)
            avg_after = round(total_after / processed, 1)
            print(f"[Optimizer] score: {avg_before} → {avg_after} | {total_optimizations} optimizasyon")
            await self._emit_status(f"[Optimizer] score: {avg_before} → {avg_after} | {total_optimizations} optimizasyon")
            response.metadata["optimizer_score_before"] = avg_before
            response.metadata["optimizer_score_after"] = avg_after
            response.metadata["optimizer_optimizations"] = total_optimizations
            response.metadata["optimizer_files"] = optimized_paths

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

        # Add research context to coder tasks
        if task.assigned_to == "coder":
            research_results = [
                r for r in results if r.get("agent") == "researcher" and r.get("success")
            ]
            if research_results:
                task.context["research"] = str(research_results[-1].get("result", ""))

        # Executor'a TÜM önceki sonuçları ver
        if task.assigned_to == "executor":
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
        from core.llm_client import LLMClient, token_tracker
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
                system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
                temperature=0.4,
                max_tokens=2000,
            )
        except Exception as e:
            final_answer = f"Results gathered. Error during synthesis: {e}"

        # Calculate cost for Telegram bot
        total_cost = token_tracker.estimated_cost_usd()

        return {
            "success": True,
            "output": final_answer,
            "tasks_completed": len(results),
            "task_details": results,
            "session_id": self._session_id,
            "iterations": self._iteration,
            "avg_critic_score": self._avg_critic_score,
            "project_slug": self.current_project_slug,  # Telegram bot için
            "cost_usd": total_cost,  # Telegram bot için
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
        
        print(f"[ensure_main_py] Running for {slug}")
        
        project_dir = os.path.join("workspace", "projects", slug)
        src_dir = Path(project_dir) / "src"
        main_py_path = src_dir / "main.py"
        app_py_path = src_dir / "app.py"
        
        # Ensure src directory exists
        src_dir.mkdir(parents=True, exist_ok=True)
        
        # Case 1: main.py already exists - do nothing (preservation)
        if main_py_path.exists():
            print(f"[ensure_main_py] main.py already exists, skipping")
            return
        
        # Case 2: main.py does not exist AND app.py exists - create re-export shim
        if app_py_path.exists():
            shim_content = 'from app import app  # noqa\n'
            with open(main_py_path, "w", encoding="utf-8") as f:
                f.write(shim_content)
            print(f"[ensure_main_py] Created main.py as re-export shim for app.py")
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
        print(f"[ensure_main_py] Created main.py with FastAPI template")
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
            f"  Kod Kalitesi   : {getattr(self, '_session_lint_score', 'N/A')}/10 (Pylint)",
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
