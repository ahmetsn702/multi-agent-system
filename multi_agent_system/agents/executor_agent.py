"""
agents/executor_agent.py
ExecutorAgent — Devin AI tarzı interaktif terminal döngüsü.

Model tek seferlik değil, iteratif çalışır:
  1. Görevi alır
  2. Bir tool_call JSON yazar (shell / read_file / write_file / list_dir / done)
  3. Çıktıyı görür
  4. Bir sonraki adıma karar verir
  5. "done" diyene veya max_steps'e kadar devam eder
"""
import json
import re
import sys
from pathlib import Path
from typing import Optional

from core.base_agent import AgentResponse, AgentStatus, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus

SYSTEM_PROMPT = """Sen MAOS Executor ajanısın. Görevin: shell komutları çalıştırıp sonuçları gözlemlemek.

🎯 TEMEL PRENSIP: Her response'da SADECE 1 tool call yap.

📝 ÇIKTI FORMATI (ZORUNLU):
SADECE JSON döndür. Açıklama, markdown, text YASAK.
JSON'u TAMAMEN bitir, asla yarıda kesme.

{{"tool": "bash", "command": "KOMUT"}}
veya
{{"tool": "done", "result": "ÖZET"}}

🔄 ÇALIŞMA AKIŞI:
1. Bir komut çalıştır
2. Çıktıyı GÖZLEMLE
3. Sonraki adımı belirle
4. Maksimum 4 komut toplam

✅ DONE ÇAĞIR:
- Test çalıştırdıysan ve sonuç gördüysen (pass/fail)
- Görev tamamlandıysa
- Aynı komutu 2. kez çalıştırmadan önce

🚫 ASLA YAPMA:
- Aynı komutu tekrar çalıştırma (başarısız olduysa farklı yaklaşım dene)
- 4'ten fazla komut çalıştırma
- Test sonuçlarını görmeden done çağırma

💻 WINDOWS KOMUTLARI:
- dir (ls yerine)
- type (cat yerine)
- del (rm yerine)
- copy (cp yerine)

ÖRNEK:
{{"tool": "bash", "command": "cd src && python -m pytest test_main.py -v"}}

Project structure:
{project_structure}"""
MAX_STEPS = 8  # Reduced from 15 to prevent excessive iterations
ERROR_PATTERNS = {
    "403": {
        "patterns": ["403", "Forbidden"],
        "fix_hint": "API key geçersiz veya yetkisiz",
    },
    "404": {
        "patterns": ["404", "Not Found"],
        "fix_hint": "Endpoint veya URL hatalı",
    },
    "429": {
        "patterns": ["429", "rate limit"],
        "fix_hint": "Rate limit, 60s bekle",
    },
    "ModuleNotFoundError": {
        "patterns": ["ModuleNotFoundError"],
        "fix_hint": "pip install {modul_adi} çalıştır",
    },
    "VersionConflict": {
        "patterns": ["VersionConflict", "version conflict"],
        "fix_hint": "Paket versiyonu uyumsuz",
    },
    "TimeoutError": {
        "patterns": ["timeout", "TimeoutError"],
        "fix_hint": "Bağlantı zaman aşımı",
    },
    "ConnectionError": {
        "patterns": ["ConnectionError", "refused"],
        "fix_hint": "Sunucu bağlantısı reddedildi",
    },
    "PermissionError": {
        "patterns": ["PermissionError"],
        "fix_hint": "Dosya yazma izni yok",
    },
    "SyntaxError": {
        "patterns": ["SyntaxError"],
        "fix_hint": "Kod sözdizimi hatası",
    },
}


class ExecutorAgent(BaseAgent):
    """
    Devin AI tarzı interaktif terminal ajanı.
    
    Her adımda LLM bir tool_call JSON üretir, biz onu çalıştırır
    ve sonucu tekrar LLM'e gösteririz. Bu döngü "done" dönene kadar sürer.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="executor",
            name="Yürütücü Ajan",
            role="İnteraktif Terminal Operatörü",
            description="Devin AI gibi interaktif terminal döngüsüyle görevleri çalıştırır.",
            capabilities=["shell_execution", "file_management", "iterative_debugging"],
            bus=bus,
        )

    def _extract_project_slug_from_text(self, text: str) -> str:
        """Metin içindeki workspace/projects/<slug> izinden proje klasörünü çıkar."""
        if not text:
            return ""
        match = re.search(
            r"workspace[\\/]+projects[\\/]+([^\\/\s'\"`]+)",
            text,
            re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    def _resolve_pytest_project_dir(self, task: Task) -> Path:
        """Pytest kısa yolu için en güvenli proje klasörünü bul."""
        projects_root = Path("workspace") / "projects"
        deferred_candidate: Optional[Path] = None

        context = getattr(task, "context", None)
        if isinstance(context, dict):
            project_slug = str(context.get("project_slug", "") or "").strip()
            if project_slug:
                candidate = projects_root / project_slug
                if candidate.exists():
                    return candidate
                deferred_candidate = candidate

        for raw_text in (
            getattr(task, "description", ""),
            getattr(task, "goal", ""),
        ):
            project_slug = self._extract_project_slug_from_text(str(raw_text or ""))
            if not project_slug:
                continue
            candidate = projects_root / project_slug
            if candidate.exists():
                return candidate
            if deferred_candidate is None:
                deferred_candidate = candidate

        if projects_root.exists():
            project_dirs = [path for path in projects_root.iterdir() if path.is_dir()]
            if project_dirs:
                return max(project_dirs, key=lambda path: path.stat().st_mtime)

        if deferred_candidate is not None:
            return deferred_candidate

        raise RuntimeError("Pytest için proje workspace klasörü çözülemedi.")

    def _extract_module_name(self, error_text: str) -> str:
        """ModuleNotFoundError içinden eksik modül adını çıkar."""
        if not error_text:
            return "modul_adi"

        patterns = [
            r"No module named ['\"]([^'\"]+)['\"]",
            r"ModuleNotFoundError:\s*No module named ['\"]([^'\"]+)['\"]",
        ]
        for pattern in patterns:
            match = re.search(pattern, error_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "modul_adi"

    def _extract_tool_error_text(self, tool_output: dict) -> str:
        """Tool çıktısından hata analizi için anlamlı metni çıkar."""
        if not isinstance(tool_output, dict):
            return str(tool_output or "")

        parts = []
        for key in ("error", "stderr", "stdout"):
            value = str(tool_output.get(key, "") or "").strip()
            if value:
                parts.append(value)

        return "\n".join(parts)

    def _tool_output_indicates_error(self, tool_output: dict) -> bool:
        """Tool sonucunun hata içerip içermediğini belirle."""
        if not isinstance(tool_output, dict):
            return False

        return_code = tool_output.get("return_code")
        return (
            tool_output.get("success") is False
            or bool(tool_output.get("error"))
            or (return_code is not None and return_code != 0)
        )

    def _detect_error_metadata(self, error_text: str) -> Optional[dict]:
        """Bilinen hata desenlerini fix hint ile eşleştir."""
        normalized_error = str(error_text or "")
        normalized_lower = normalized_error.lower()
        if not normalized_lower:
            return None

        for error_type, config in ERROR_PATTERNS.items():
            patterns = config.get("patterns", [])
            matched = False
            if error_type == "VersionConflict":
                matched = any(
                    (
                        pattern == "VersionConflict"
                        and re.search(r"\bVersionConflict\b", normalized_error)
                    )
                    or (
                        pattern == "version conflict"
                        and re.search(r"\bversion conflict\b", normalized_lower)
                    )
                    for pattern in patterns
                )
            else:
                matched = any(pattern.lower() in normalized_lower for pattern in patterns)

            if matched:
                fix_hint = str(config.get("fix_hint", "") or "")
                if "{modul_adi}" in fix_hint:
                    fix_hint = fix_hint.format(
                        modul_adi=self._extract_module_name(normalized_error)
                    )
                print(f"[{error_type}] {fix_hint}")
                return {
                    "error_type": error_type,
                    "fix_hint": fix_hint,
                }

        return None

    async def run(self, task: Task) -> AgentResponse:
        """Pytest görevleri için think/act döngüsünü bypass et."""
        task_description = str(getattr(task, "description", "") or "")
        if "pytest" not in task_description.lower():
            return await super().run(task)

        from tools.interactive_shell import InteractiveShell

        self.status = AgentStatus.ACTING
        self._memory.add_to_short_term(
            self.agent_id, "user", f"Task: {task_description}", {"task_id": task.task_id}
        )

        try:
            project_dir = self._resolve_pytest_project_dir(task)
            pytest_cwd = (
                project_dir.parent if project_dir.name == "src" else project_dir
            )
            pytest_cwd.mkdir(parents=True, exist_ok=True)
            print(f"[Executor] pytest kısa yol başlatıldı: {pytest_cwd.resolve()}")

            shell = InteractiveShell(str(pytest_cwd), pytest_cwd.name)
            pytest_cmd = (
                f"{sys.executable} -m pytest tests/ -v --tb=short "
                "--no-header -p no:warnings"
            )
            pytest_result = shell.run(pytest_cmd, timeout=120)
            final_result = self._format_tool_output(
                "shell",
                {"tool": "shell", "command": pytest_cmd},
                pytest_result,
            )
            shortcut_success = bool(
                pytest_result.get("success", pytest_result.get("return_code", 0) == 0)
            )
            error_text = self._extract_tool_error_text(pytest_result)
            error_metadata = (
                self._detect_error_metadata(error_text)
                if not shortcut_success
                else None
            )
            response_metadata = {
                "steps_taken": 1,
                "tool_names": ["shell"],
                "return_code": pytest_result.get("return_code"),
            }
            if error_metadata:
                response_metadata.update(error_metadata)
            response = AgentResponse(
                content={
                    "result": final_result,
                    "pytest_output": final_result,
                    "saved_files": [],
                    "steps": 1,
                    "terminal_history": shell.format_history(last_n=5),
                },
                success=shortcut_success,
                error=error_text if not shortcut_success else None,
                metadata=response_metadata,
            )
            self._memory.add_to_short_term(
                self.agent_id,
                "assistant",
                str(response.content),
                {"task_id": task.task_id, "success": response.success},
            )
            self.status = AgentStatus.IDLE
            return response
        except Exception as e:
            print(f"[Executor] ❌ Pytest kısa yol hatası: {e}")
            self.status = AgentStatus.ERROR
            return AgentResponse(
                content=None,
                success=False,
                error=str(e),
                metadata={"steps_taken": 0, "tool_names": []},
            )

    # ─── Think ────────────────────────────────────────────────────────────────
    async def think(self, task: Task) -> ThoughtProcess:
        return ThoughtProcess(
            reasoning="İnteraktif terminal döngüsü başlatılıyor.",
            plan=["Görevi analiz et", "Komutları sırayla çalıştır", "Hataları düzelt", "Bitir"],
            tool_calls=[],
            confidence=0.9,
        )

    # ─── Act — Ana ReAct Döngüsü ──────────────────────────────────────────────
    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """
        Devin tarzı interaktif döngü:
        LLM → tool_call → çalıştır → sonucu LLM'e ver → tekrar
        
        CONTEXT CLEANUP: Her retry'da conversation history temizlenir,
        sadece görev tanımı ve son hata tutulur.
        """
        from tools.interactive_shell import InteractiveShell
        import asyncio

        project_slug = task.context.get("project_slug", "default")
        project_dir = Path("workspace") / "projects" / project_slug
        project_dir.mkdir(parents=True, exist_ok=True)

        shell = InteractiveShell(str(project_dir), project_slug)

        # Proje yapısını hazırla
        project_structure = self._get_project_structure(project_dir)

        # Konuşma geçmişi — LLM'e önceki adımları göster
        conversation: list[dict] = []

        # İlk kullanıcı mesajı
        task_prompt = (
            f"Görev: {task.description}\n\n"
            f"Bağlam: {self._summarize_context(task.context)}\n\n"
            "Yukarıdaki görevi tamamlamak için terminal komutlarını adım adım çalıştır. "
            "Her adımda bir tool_call yaz, çıktıyı gördükten sonra bir sonraki adıma geç."
        )
        conversation.append({"role": "user", "content": task_prompt})

        final_result = ""
        saved_files: list[str] = []
        step_logs: list[dict] = []
        success = True
        parse_fail_count = 0  # Parse başarısızlık sayacı
        last_error_metadata: Optional[dict] = None
        last_error_text = ""
        step = 0

        while step < MAX_STEPS:
            # System prompt'u faz bilgisiyle güncelle
            system = SYSTEM_PROMPT.format(
                project_structure=project_structure,
            )

            # LLM'den yanıt al (OUTPUT TOKEN LİMİTİ: 500)
            response_text = await self._call_llm(
                messages=conversation,
                system_prompt=system,
                temperature=0.1,
                max_tokens=1024,  # 1500 → 500 → 200 (Executor kısa komutlar üretir)
            )

            # Tool call'u parse et
            tool_call = self._parse_tool_call(response_text)

            if not tool_call:
                # JSON parse başarısız — LLM'e tekrar sor
                parse_fail_count += 1
                print(f"[Executor] ⚠️ Tool call parse başarısız (hatalı parse: {parse_fail_count}/3)")
                
                if parse_fail_count >= 3:
                    print(f"[Executor] ❌ 3 parse hatası alındı, görev iptal ediliyor.")
                    success = False
                    final_result = "Ardışık 3 parse hatası oluştu, aracı komut üretemedi."
                    break
                else:
                    conversation.append({"role": "assistant", "content": response_text})
                    conversation.append({
                        "role": "user",
                        "content": "HATA: SADECE geçerli bir tool_call JSON bloğu döndür. Markdown veya açıklama yazma."
                    })
                continue

            # Parse başarılı, sayacı sıfırla, adım sayacını artır
            parse_fail_count = 0
            step += 1
            
            tool_name = tool_call.get("tool", "")
            print(f"[Executor] 🔧 Adım {step+1}/{MAX_STEPS}: {tool_name} → {self._summarize_call(tool_call)}")

            # ── DONE ──────────────────────────────────────────────────────────
            if tool_name == "done":
                # Check terminal history for the previous command outputs
                recent_logs = shell.format_history(last_n=2)
                final_result = f"Görev tamamlandı. Son terminal çıktıları:\n{recent_logs}\nLLM Done Notu: {tool_call.get('result', '')}"
                print(f"[Executor] ✅ Tamamlandı: {tool_call.get('result', 'Görev tamamlandı.')}")
                break

            # ── Komutu çalıştır ───────────────────────────────────────────────
            tool_output = self._execute_tool(tool_call, shell)

            # Log tut
            step_logs.append({
                "step": step + 1,
                "tool": tool_name,
                "call": tool_call,
                "output": tool_output,
            })

            # Dosya yazıldıysa kaydet
            if tool_name == "write_file" and tool_output.get("success"):
                fname = Path(tool_call.get("path", "")).name
                if fname and fname not in saved_files:
                    saved_files.append(fname)

            # Çıktıyı formatlayıp conversation'a ekle
            output_msg = self._format_tool_output(tool_name, tool_call, tool_output)
            if self._tool_output_indicates_error(tool_output):
                last_error_text = self._extract_tool_error_text(tool_output)
                detected_error = self._detect_error_metadata(last_error_text)
                if detected_error:
                    last_error_metadata = detected_error
                    output_msg += f"\nFIX_HINT: {detected_error['fix_hint']}"
            conversation.append({"role": "assistant", "content": response_text})
            conversation.append({"role": "user", "content": output_msg})
            
            # Auto-done after successful test runs
            if tool_name == "shell" and tool_output.get("return_code") == 0:
                cmd = tool_call.get("command", "").lower()
                # Check if this was a test command
                if any(test_keyword in cmd for test_keyword in ["pytest", "test", "unittest", "nose"]):
                    print(f"[Executor] ✅ Tests completed successfully, auto-calling done")
                    final_result = f"Tests completed successfully.\n\nTest output:\n{tool_output.get('stdout', '')[:500]}"
                    success = True
                    break
            
            # CONTEXT CLEANUP: Her 4 adımda bir eski adımları temizle (8+ mesaj)
            if len(conversation) > 8:  # 4 mesaj çifti = 8 mesaj (önce: 12)
                print(f"[Executor] 🧹 Context temizleniyor (>8 mesaj)")
                # İlk görev mesajını tut, son 4 mesajı tut (2 adım)
                first_msg = conversation[0]
                recent_msgs = conversation[-4:]
                conversation = [first_msg] + recent_msgs

        else:
            # MAX_STEPS aşıldı
            final_result = f"MAX_STEPS ({MAX_STEPS}) aşıldı. Son durum: {shell.format_history(last_n=3)}"
            success = False
            print(f"[Executor] ⚠️ Max adım aşıldı!")

        response_metadata = {
            "steps_taken": len(step_logs),
            "tool_names": [s["tool"] for s in step_logs],
        }
        if not success and last_error_metadata:
            response_metadata.update(last_error_metadata)

        return AgentResponse(
            content={
                "result": final_result,
                "saved_files": saved_files,
                "steps": len(step_logs),
                "terminal_history": shell.format_history(last_n=5),
            },
            success=success,
            error=last_error_text if (not success and last_error_text) else None,
            metadata=response_metadata,
        )

    # ─── Tool Execution ───────────────────────────────────────────────────────
    def _extract_command(self, params: dict) -> str:
        cmd = (
            params.get("command")
            or params.get("cmd")
            or (params.get("tool_input") or {}).get("command")
            or (params.get("tool_input") or {}).get("cmd")
            or ""
        )
        if isinstance(cmd, list):
            cmd = " ".join(str(c) for c in cmd)
        return cmd

    def _execute_tool(self, tool_call: dict, shell) -> dict:
        """Tool call'u çalıştır ve sonucu döndür."""
        tool_name = tool_call.get("tool", "")

        if tool_name in ("shell", "bash"):
            cmd = self._extract_command(tool_call)
            if not cmd and tool_call.get("tool") == "run_pytest":
                cmd = "pytest"
            cmd = cmd.strip()
            
            if not cmd:
                return {"success": False, "stdout": "", "stderr": "Komut boş!"}
            
            # Server/long-running command detection
            if self._is_server_command(cmd):
                print(f"[Executor] ⚠️ Server komutu tespit edildi, atlanıyor: {cmd[:60]}")
                return {
                    "success": True,
                    "stdout": "[ATLANDI] Server komutu tespit edildi. Sunucular arka planda çalıştırılmalı, test edilemez.",
                    "stderr": "",
                    "return_code": 0,
                }
            
            # Interactive program kontrolü
            if self._is_interactive_cmd(cmd, shell):
                return {
                    "success": True,
                    "stdout": "[ATLANDI] Interaktif program çalıştırılamaz.",
                    "stderr": "", 
                    "return_code": 0,
                }
            
            # Normal commands: use 30s timeout (reduced from 90s)
            return shell.run(cmd, timeout=30)

        elif tool_name == "read_file":
            return shell.read_file(tool_call.get("path", ""))

        elif tool_name == "write_file":
            return shell.write_file(
                tool_call.get("path", ""),
                tool_call.get("content", "")
            )

        elif tool_name == "list_dir":
            return shell.list_dir(tool_call.get("path", "."))

        else:
            return {"success": False, "error": f"Bilinmeyen tool: {tool_name}"}

    def _is_interactive_cmd(self, cmd: str, shell) -> bool:
        """Python scriptleri input/sonsuz dongu heuristigiyle engelleme."""
        return False

    def _is_server_command(self, cmd: str) -> bool:
        """
        Detect if command starts a long-running server that will block indefinitely.
        
        Args:
            cmd: Shell command to check
            
        Returns:
            True if command looks like a server start command
        """
        cmd_lower = cmd.lower().strip()
        
        # Server command patterns
        server_patterns = [
            "uvicorn",           # FastAPI/ASGI server
            "flask run",         # Flask dev server
            "streamlit run",     # Streamlit app
            "python app.py",     # Common server script name
            "python main.py",    # Common server script name (if it contains server code)
            "gunicorn",          # Production WSGI server
            "hypercorn",         # ASGI server
            "daphne",            # Django ASGI server
            "waitress-serve",    # Waitress server
            "django runserver",  # Django dev server
            "npm start",         # Node.js dev server
            "npm run dev",       # Node.js dev server
            "yarn start",        # Yarn dev server
            "yarn dev",          # Yarn dev server
        ]
        
        # Check if command contains any server pattern
        for pattern in server_patterns:
            if pattern in cmd_lower:
                return True
        
        # Additional check: if running a Python file that might be a server
        # Look for patterns like "python <file>.py" where file might be app/main/server
        if "python" in cmd_lower and any(name in cmd_lower for name in ["app.py", "server.py", "main.py"]):
            # Only flag as server if it doesn't have obvious test/script flags
            if not any(flag in cmd_lower for flag in ["--help", "-h", "--version", "-v", "test"]):
                return True
        
        return False

    # ─── Tool Call Parser ─────────────────────────────────────────────────────
    def _parse_tool_call(self, response_text: str) -> Optional[dict]:
        """LLM çıktısından tool_call JSON bloğunu çıkar. Truncated JSON'ı tamamlamaya çalışır."""

        def try_complete_json(text: str) -> str:
            """Truncated JSON'ı tamamlamaya çalış - returns completed text string."""
            text = text.strip()
            if not text:
                return text
            
            # Clean up escaped characters that break JSON parsing
            text = text.replace('\\*', '*')
            text = text.replace('\\"', '"')
            text = text.replace("\\'", "'")
            
            # Count unclosed structures
            open_braces = text.count('{') - text.count('}')
            open_brackets = text.count('[') - text.count(']')
            
            # Check if we're inside a string (odd number of unescaped quotes)
            in_string = text.count('"') % 2 == 1
            
            if in_string:
                text += '"'
            text += ']' * open_brackets
            text += '}' * open_braces
            
            return text

        def normalize_tool_call(parsed: dict) -> Optional[dict]:
            """Tool call'u normalize et ve alias'ları çöz."""
            if not isinstance(parsed, dict):
                return None

            tool_key = None
            for key in ['tool', 'action', 'command', 'type', 'tool_name']:
                if key in parsed:
                    tool_key = key
                    break

            if not tool_key:
                return None

            tool_name = parsed[tool_key]

            alias_map = {
                'bash': 'shell',
                'run': 'shell',
                'python': 'shell',
                'python_file': 'shell',
                'execute': 'shell',
                'run_pytest': 'shell',
                'read': 'read_file',
                'write': 'write_file',
                'list': 'list_dir',
                'ls': 'list_dir',
            }

            if tool_name in alias_map:
                tool_name = alias_map[tool_name]

            normalized = {'tool': tool_name}

            for key, value in parsed.items():
                if key != tool_key:
                    normalized[key] = value

            return normalized

        raw_text = (response_text or "").strip()
        
        # Strip markdown code block markers if present using regex
        import re
        raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text.strip())
        raw_text = re.sub(r'\s*```$', '', raw_text)
        raw_text = raw_text.strip()
        
        # Clean up escaped characters that break JSON parsing
        raw_text = raw_text.replace('\\*', '*')
        raw_text = raw_text.replace('\\"', '"')
        raw_text = raw_text.replace("\\'", "'")

        # 1) Önce direkt json.loads() dene
        if raw_text:
            try:
                parsed = json.loads(raw_text)
                normalized = normalize_tool_call(parsed)
                if normalized:
                    return normalized
            except json.JSONDecodeError:
                # Try to complete and parse again
                completed = try_complete_json(raw_text)
                try:
                    parsed = json.loads(completed)
                    normalized = normalize_tool_call(parsed)
                    if normalized:
                        return normalized
                except json.JSONDecodeError:
                    pass

        # 2) Başarısızsa ```json ... ``` bloğunu dene
        match_json_block = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
        if match_json_block:
            json_content = match_json_block.group(1).strip()
            try:
                parsed = json.loads(json_content)
                normalized = normalize_tool_call(parsed)
                if normalized:
                    return normalized
            except json.JSONDecodeError:
                # Try to complete and parse again
                completed = try_complete_json(json_content)
                try:
                    parsed = json.loads(completed)
                    normalized = normalize_tool_call(parsed)
                    if normalized:
                        return normalized
                except json.JSONDecodeError:
                    pass

        # 3) O da başarısızsa { ile başlayan ilk bloğu bul
        try:
            start = raw_text.find("{")
            if start != -1:
                depth = 0
                end_found = False
                for idx, ch in enumerate(raw_text[start:], start):
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = raw_text[start:idx + 1]
                            try:
                                parsed = json.loads(candidate)
                                normalized = normalize_tool_call(parsed)
                                if normalized:
                                    return normalized
                            except json.JSONDecodeError:
                                pass
                            end_found = True
                            break

                # If no closing brace found, try to complete the JSON
                if not end_found:
                    candidate = raw_text[start:]
                    completed = try_complete_json(candidate)
                    try:
                        parsed = json.loads(completed)
                        normalized = normalize_tool_call(parsed)
                        if normalized:
                            return normalized
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        # Tüm parse denemeleri başarısız
        print(f"[Executor] ⚠️ Tool call parse edilemedi. Ham yanıt: {raw_text[:200] if isinstance(raw_text, str) else str(raw_text)[:200]}")
        return {}


    # ─── Format Helpers ───────────────────────────────────────────────────────
    def _format_tool_output(self, tool_name: str, call: dict, output: dict) -> str:
        """Çıktıyı LLM için okunabilir formatta döndür."""
        if tool_name == "shell":
            cmd = self._extract_command(call)
            rc = output.get("return_code", "?")
            stdout = output.get("stdout", "").strip()
            stderr = output.get("stderr", "").strip()
            lines = [f"$ {cmd}", f"[exit code: {rc}]"]
            if stdout:
                lines.append(f"STDOUT:\n{stdout}")
            if stderr:
                lines.append(f"STDERR:\n{stderr}")
            if not stdout and not stderr:
                lines.append("(çıktı yok)")
            return "\n".join(lines)

        elif tool_name == "read_file":
            if output.get("success"):
                content = output.get("content", "")
                content_preview = content[:3000] if isinstance(content, str) else str(content)[:3000]
                return f"Dosya içeriği ({call.get('path')}):\n```\n{content_preview}\n```"
            return f"Dosya okunamadı: {output.get('error', 'bilinmeyen hata')}"

        elif tool_name == "write_file":
            if output.get("success"):
                return f"✅ Dosya yazıldı: {output.get('path')} ({output.get('lines', 0)} satır)"
            return f"❌ Dosya yazılamadı: {output.get('error')}"

        elif tool_name == "list_dir":
            if output.get("success"):
                entries = output.get("entries", [])
                lines = [f"📁 {call.get('path', '.')}:"]
                for e in entries[:30]:
                    icon = "📂" if e["type"] == "dir" else "📄"
                    size = f" ({e['size']}B)" if e.get("size") else ""
                    lines.append(f"  {icon} {e['name']}{size}")
                return "\n".join(lines)
            return f"Dizin listelenemedi: {output.get('error')}"

        return str(output)

    def _summarize_call(self, call: dict) -> str:
        """Tool call'un kısa özetini döndür (log için)."""
        tool = call.get("tool", "")
        if tool == "shell":
            return call.get("cmd", "")[:60]
        elif tool in ("read_file", "write_file", "list_dir"):
            return call.get("path", "")
        elif tool == "done":
            return call.get("result", "")[:60]
        return str(call)[:60]

    def _summarize_context(self, context: dict) -> str:
        """Task context'ini kısa özet olarak döndür."""
        lines = []
        for key in ("expected_output", "phase_info", "existing_files", "fix_hint"):
            val = context.get(key)
            if val:
                val_str = str(val)[:200] if isinstance(val, str) else str(val)[:200]
                lines.append(f"{key}: {val_str}")
        return "\n".join(lines) if lines else "(bağlam yok)"

    def _get_project_structure(self, project_dir: Path) -> str:
        """Proje klasör yapısını kısa özet olarak döndür."""
        lines = []
        for subdir in ["src", "tests", "docs"]:
            d = project_dir / subdir
            if d.exists():
                files = [f.name for f in d.iterdir() if f.is_file()]
                if files:
                    lines.append(f"{subdir}/: {', '.join(files[:10])}")
        return "\n".join(lines) if lines else "(henüz dosya yok)"
