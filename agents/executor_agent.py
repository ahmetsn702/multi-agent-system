"""
agents/executor_agent.py
ExecutorAgent: Runs shell commands, manages files, sets up environments.
"""
from typing import Optional
import re
import subprocess
import sys
import uuid

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus
from tools.code_runner import run_python_code, run_code, run_tests
from tools.file_manager import (
    create_dir, delete_file, list_dir, read_file, write_file, get_workspace_path
)
from tools.shell_executor import run_shell

SYSTEM_PROMPT = """Return ONLY a JSON tool call. No explanation, no markdown, no text.

Format:
{{"tool": "bash", "command": "YOUR_COMMAND"}}
or
{{"tool": "done", "result": "SUMMARY"}}

Project structure:
{project_structure}"""


class ExecutorAgent(BaseAgent):
    """
    Executes shell commands, runs Python scripts, and manages workspace files safely.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="executor",
            name="Yürütücü Ajan",
            role="Sistem Operasyonları ve Dosya Yönetimi",
            description="Çalışma alanı sanal ortamında komutları güvenli bir şekilde yürütür ve dosyaları yönetir.",
            capabilities=["shell_execution", "file_management", "environment_setup", "python_execution"],
            bus=bus,
        )
        self.register_tool("run_shell", run_shell)
        self.register_tool("run_python", run_python_code)
        self.register_tool("run_code", run_code)
        self.register_tool("run_tests", run_tests)
        self.register_tool("read_file", read_file)
        self.register_tool("write_file", write_file)
        self.register_tool("list_dir", list_dir)
        self.register_tool("create_dir", create_dir)
        self.register_tool("delete_file", delete_file)

    async def _run_subprocess(
        self,
        command: str,
        project_slug: str,
        timeout: int = 60
    ) -> dict:
        """
        Komutu gerçek subprocess ile çalıştır.
        Güvenli komutlar: python, pip, pytest, git
        Yasak komutlar: rm -rf, del /f, format, shutdown
        """
        import os
        from pathlib import Path

        BANNED_PATTERNS = [
            "rm -rf", "rm -r /", "del /f", "format c:",
            "shutdown", "mkfs", ":(){:|:&};:", "dd if="
        ]

        cmd_lower = command.lower()
        for banned in BANNED_PATTERNS:
            if banned in cmd_lower:
                return {
                    "success": False,
                    "output": "",
                    "error": f"GÜVENLİK: Bu komut yasak: {banned}",
                    "blocked": True,
                }

        project_root = Path("workspace/projects") / project_slug
        project_src = project_root / "src"

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([
            str(project_src),
            str(project_root),
            str(Path.cwd()),
        ])

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(project_root),
                env=env,
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout[:3000],
                "error": result.stderr[:1000],
                "return_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": f"Timeout: {timeout} saniye aşıldı.",
                "return_code": -1,
            }
        except Exception as e:
            return {"success": False, "output": "", "error": str(e), "return_code": -1}

    async def _auto_install_dependencies(self, code: str, project_slug: str):
        """Kodda import edilen dış kütüphaneleri otomatik yükle."""
        import re as _re

        STDLIB = {
            "os", "sys", "re", "json", "time", "datetime", "math",
            "random", "pathlib", "subprocess", "asyncio", "threading",
            "collections", "itertools", "functools", "typing", "abc",
            "io", "csv", "sqlite3", "hashlib", "base64", "urllib",
            "http", "email", "logging", "unittest", "copy", "string",
            "tkinter", "struct", "socket", "ssl", "shutil", "glob",
            "argparse", "textwrap", "decimal", "fractions", "statistics",
            "enum", "dataclasses", "contextlib", "tempfile",
        }

        imports = _re.findall(r'^(?:import|from)\s+(\w+)', code, _re.MULTILINE)
        third_party = [pkg for pkg in imports if pkg not in STDLIB]

        PACKAGE_MAP = {
            "cv2": "opencv-python",
            "PIL": "Pillow",
            "sklearn": "scikit-learn",
            "bs4": "beautifulsoup4",
            "dotenv": "python-dotenv",
        }

        for pkg in set(third_party):
            pip_name = PACKAGE_MAP.get(pkg, pkg)
            install_result = await self._run_subprocess(
                f"pip install {pip_name} -q",
                project_slug,
                timeout=120,
            )
            if install_result["success"]:
                print(f"[Executor] ✅ {pip_name} yüklendi")
            else:
                print(f"[Executor] ❌ {pip_name} yüklenemedi: {install_result['error'][:100]}")

    def extract_code_from_response(self, response: str) -> str:
        """LLM cevabından kod bloğunu çıkar — her formatta çalışır"""
        # Önce ```python ... ``` bloğunu dene
        pattern = r"```python\s*(.*?)\s*```"
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
            
        # Sonra ``` ... ``` bloğunu dene
        pattern = r"```\s*(.*?)\s*```"
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
            
        # Hiç ``` yoksa — tüm cevabı kod olarak kabul et
        # Ama "import" veya "def" veya "class" içeriyorsa
        if any(keyword in response for keyword in ["import ", "def ", "class ", "print("]):
            return response.strip()
            
        # Hiçbiri değilse boş döndür
        return ""

    async def save_code_to_file(self, code: str, filename: str, project_slug: str) -> dict:
        """Kodu workspace/projects/{slug}/src/ içine kaydet"""
        from pathlib import Path
        
        if not code or not code.strip():
            return {"success": False, "error": "Kaydedilecek kod boş!"}
            
        # Path oluştur
        project_root = Path("workspace") / "projects" / project_slug
        src_dir = project_root / "src"
        
        # Klasörü garantile
        src_dir.mkdir(parents=True, exist_ok=True)
        
        # Dosya adını temizle
        if not filename.endswith(".py"):
            filename = filename + ".py"
            
        target = src_dir / filename
        
        try:
            target.write_text(code, encoding="utf-8")
            return {
                "success": True,
                "path": str(target),
                "lines": len(code.splitlines()),
                "size": len(code.encode("utf-8"))
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def think(self, task: Task) -> ThoughtProcess:
        """Plan the sequence of operations needed."""
        context = task.context or {}
        
        coder_output = (
            context.get("coder_output") or
            context.get("code") or
            context.get("result") or
            context.get("content") or
            str(context.get("all_previous_results", "")) or
            ""
        )
        
        if isinstance(coder_output, dict):
            coder_output = (
                coder_output.get("code") or
                coder_output.get("content") or
                str(coder_output)
            )
        
        if coder_output and any(
            kw in str(coder_output) 
            for kw in ["import ", "def ", "class ", "print("]
        ):
            filename = context.get("filename", "script.py")
            return ThoughtProcess(
                reasoning="Coder çıktısı bulundu, direkt kaydediyorum.",
                plan=[f"{filename} dosyasını kaydet ve çalıştır"],
                tool_calls=[{
                    "type": "save_and_run",
                    "filename": filename,
                    "code": coder_output,
                    "raw_response": str(coder_output)
                }],
                confidence=0.95,
            )

        plan_prompt = (
            f"Görev: {task.description}\n\n"
            f"Önceki Bağlam/Çıktılar: {task.context}\n\n"
            "Hangi belirli işlemlerin yürütülmesi gerekiyor? "
            "Kabuk komutları, dosya işlemleri veya çalıştırılacak Python betikleri hakkında açık olun."
        )
        response = await self._call_llm(
            messages=[{"role": "user", "content": plan_prompt}],
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=2000,
        )
        
        parsed = self._parse_json_response(response)
        
        operations = parsed.get("operations", [])
        if parsed.get("action") == "save_and_run":
            operations.append({
                "type": "save_and_run",
                "filename": parsed.get("filename", f"script_{uuid.uuid4().hex[:6]}.py"),
                "code": parsed.get("code", ""),
                "raw_response": response
            })
            
        return ThoughtProcess(
            reasoning=f"Will execute {len(operations)} operations.",
            plan=[op.get("description", str(op.get("type"))) for op in operations],
            tool_calls=operations,
            confidence=0.85,
        )

    def validate_path(self, path: str) -> bool:
        from pathlib import Path
        workspace = Path(get_workspace_path()).resolve()
        target = Path(path).resolve()
        if not str(target).startswith(str(workspace)):
            raise PermissionError(f"Güvenlik ihlali: {path} workspace dışında!")
        return True

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """Execute the planned operations."""
        results = []
        all_success = True
        
        project_slug = task.context.get("project_slug", "default")

        # Görev başında proje yapısını garantile
        from tools.file_manager import ensure_project_structure
        ensure_project_structure(project_slug)

        for operation in thought.tool_calls:
            op_type = operation.get("type", "")
            description = operation.get("description", "")
            is_destructive = operation.get("is_destructive", False)

            if op_type == "save_and_run":
                llm_response = operation.get("raw_response", operation.get("code", ""))
                # LLM cevabından kodu çıkar
                code = self.extract_code_from_response(llm_response)
                
                if not code:
                    # Kod bulunamadı — görevi başarısız say ve logla
                    return AgentResponse(
                        success=False,
                        content={"error": "LLM cevabında çalıştırılabilir kod bulunamadı"},
                        metadata={"fix_hint": "CODE_EXTRACTION_FAILED: LLM sadece metin döndürdü, kod üretmedi"}
                    )
                
                filename = operation.get("filename", f"script_{uuid.uuid4().hex[:6]}.py")
                save_res = await self.save_code_to_file(code, filename, project_slug)
                
                if not save_res.get("success"):
                    return AgentResponse(
                        success=False,
                        content={"error": f"Dosya kaydedilemedi: {save_res.get('error')}"},
                        metadata={"fix_hint": "FILE_SAVE_FAILED"}
                    )
                    
                # Çalıştır
                run_res = await self.use_tool("run_code", file_path=save_res["path"])
                results.append({
                    "operation": "save_and_run",
                    "type": "save_and_run",
                    "success": run_res.success,
                    "data": run_res.data,
                    "error": run_res.error,
                })
                if not run_res.success:
                    all_success = False
                continue

            target_path = operation.get("target_path", "")
            if target_path and op_type in ["file_read", "file_write", "file_list", "create_dir", "delete_file", "python_file"]:
                try:
                    self.validate_path(target_path)
                except PermissionError as e:
                    results.append({
                        "operation": description,
                        "type": op_type,
                        "success": False,
                        "error": str(e),
                    })
                    all_success = False
                    continue

            # Skip destructive ops unless explicitly confirmed in task context
            if is_destructive and not task.context.get("confirmed_destructive", False):
                results.append({
                    "operation": description,
                    "status": "skipped",
                    "reason": "Destructive operation requires explicit confirmation",
                })
                continue

            result = None
            if op_type in ("shell", "bash"):
                command = operation.get("command_or_content", "")
                result_data = await self._run_subprocess(command, project_slug)
                results.append({
                    "operation": description,
                    "type": "shell",
                    "success": result_data["success"],
                    "data": {"output": result_data["output"]},
                    "error": result_data.get("error", ""),
                })
                if not result_data["success"]:
                    all_success = False
                continue

            elif op_type == "python":
                code = operation.get("command_or_content", "")
                result = await self.use_tool("run_python", code=code)

            elif op_type == "python_file":
                file_path = operation.get("target_path", "")
                if file_path:
                    workspace = get_workspace_path()
                    import os
                    full_path = os.path.join(workspace, file_path)
                    result = await self.use_tool("run_code", file_path=full_path)

            elif op_type == "file_read":
                path = operation.get("target_path", "")
                result = await self.use_tool("read_file", path=path)

            elif op_type == "file_write":
                path = operation.get("target_path", "")
                content = operation.get("command_or_content", "")
                result = await self.use_tool("write_file", path=path, content=content)

            elif op_type == "file_list":
                path = operation.get("target_path", "")
                result = await self.use_tool("list_dir", path=path)

            elif op_type == "create_dir":
                path = operation.get("target_path", "")
                result = await self.use_tool("create_dir", path=path)

            if result:
                results.append({
                    "operation": description,
                    "type": op_type,
                    "success": result.success,
                    "data": result.data,
                    "error": result.error,
                    "execution_time_ms": getattr(result, "execution_time_ms", 0),
                })
                if not result.success:
                    all_success = False

        return AgentResponse(
            content={
                "operations_executed": len(results),
                "results": results,
                "workspace": get_workspace_path(),
            },
            success=all_success,
            metadata={"operation_count": len(results)},
        )

    async def list_workspace(self) -> list:
        """List all files in the workspace."""
        result = await self.use_tool("list_dir", path="")
        return result.data.get("entries", []) if result.success else []

    def _parse_tool_call(self, response_text: str) -> Optional[dict]:
        """
        LLM çıktısından tool_call JSON bloğunu çıkar ve normalize et.
        
        Desteklenen formatlar:
        - ```tool_call ... ```
        - ```json ... ```
        - Düz { ... } JSON
        
        Alias mapping ve argument normalization yapılır.
        Truncated JSON'ı tamamlamaya çalışır.
        """
        import json
        
        def try_complete_json(json_str: str) -> Optional[dict]:
            """Truncated JSON'ı tamamlamaya çalış."""
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # JSON incomplete - try to complete it
                # Count open braces/brackets
                open_braces = json_str.count('{') - json_str.count('}')
                open_brackets = json_str.count('[') - json_str.count(']')
                
                # Check if we're in the middle of a string
                in_string = json_str.count('"') % 2 == 1
                
                completed = json_str
                if in_string:
                    completed += '"'
                
                # Close any open brackets/braces
                completed += ']' * open_brackets
                completed += '}' * open_braces
                
                try:
                    return json.loads(completed)
                except json.JSONDecodeError:
                    return None
        
        def normalize_tool_call(parsed: dict) -> Optional[dict]:
            """Tool call'u normalize et: alias'ları çöz ve argümanları düzenle."""
            if not isinstance(parsed, dict):
                return None
            
            # 1. Tool key'ini bul (tool, action, command, type, tool_name)
            tool_key = None
            for key in ['tool', 'action', 'command', 'type', 'tool_name']:
                if key in parsed:
                    tool_key = key
                    break
            
            if not tool_key:
                return None
            
            tool_name = str(parsed[tool_key]).strip()
            
            # 2. Tool alias mapping
            tool_aliases = {
                'bash': 'bash',
                'run': 'bash',
                'shell': 'bash',
                'cmd': 'bash',
                'execute': 'bash',
                'read': 'read_file',
                'read_file': 'read_file',
                'cat': 'read_file',
                'write': 'write_file',
                'write_file': 'write_file',
                'save': 'write_file',
                'finish': 'done',
                'complete': 'done',
                'exit': 'done',
                'end': 'done',
                'done': 'done',
            }
            
            normalized_tool = tool_aliases.get(tool_name.lower(), tool_name)
            
            # 3. Normalized tool_call oluştur
            normalized = {'tool': normalized_tool}
            
            # 4. Argümanları normalize et
            if normalized_tool == 'bash':
                # bash için: command, cmd, script, code → command
                cmd_value = None
                for key in ['command', 'cmd', 'script', 'code', 'tool_input']:
                    if key in parsed:
                        val = parsed[key]
                        if isinstance(val, dict):
                            cmd_value = val.get('command') or val.get('cmd')
                        else:
                            cmd_value = val
                        break
                
                if cmd_value:
                    normalized['command'] = str(cmd_value).strip()
                    
            elif normalized_tool == 'read_file':
                # read_file için: path, file, filename, filepath → path
                path_value = None
                for key in ['path', 'file', 'filename', 'filepath']:
                    if key in parsed:
                        path_value = parsed[key]
                        break
                
                if path_value:
                    normalized['path'] = str(path_value).strip()
                    
            elif normalized_tool == 'write_file':
                # write_file için: path + content
                path_value = None
                for key in ['path', 'file', 'filename', 'filepath']:
                    if key in parsed:
                        path_value = parsed[key]
                        break
                
                content_value = None
                for key in ['content', 'data', 'text', 'code']:
                    if key in parsed:
                        content_value = parsed[key]
                        break
                
                if path_value:
                    normalized['path'] = str(path_value).strip()
                if content_value:
                    normalized['content'] = str(content_value)
                    
            elif normalized_tool == 'done':
                # done için: result, message, summary → result
                result_value = None
                for key in ['result', 'message', 'summary', 'output']:
                    if key in parsed:
                        result_value = parsed[key]
                        break
                
                if result_value:
                    normalized['result'] = str(result_value).strip()
            
            # 5. Diğer tüm key'leri kopyala (tool_key hariç)
            for key, value in parsed.items():
                if key != tool_key and key not in normalized:
                    normalized[key] = value
            
            return normalized
        
        # Format 1: ```tool_call ... ``` bloğunu ara
        pattern = r'```tool_call\s*(.*?)\s*```'
        match = re.search(pattern, response_text, re.DOTALL)
        if match:
            parsed = try_complete_json(match.group(1).strip())
            if parsed:
                return normalize_tool_call(parsed)

        # Format 2: ```json ... ``` bloğunu dene
        pattern2 = r'```json\s*(.*?)\s*```'
        match2 = re.search(pattern2, response_text, re.DOTALL)
        if match2:
            parsed = try_complete_json(match2.group(1).strip())
            if parsed:
                return normalize_tool_call(parsed)

        # Format 3: Düz { ... } JSON'ı dene
        try:
            start = response_text.index('{')
            # Try to find the end of JSON
            depth = 0
            end_found = False
            for i, ch in enumerate(response_text[start:], start):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = response_text[start:i+1]
                        parsed = json.loads(candidate)
                        normalized = normalize_tool_call(parsed)
                        if normalized:
                            return normalized
                        end_found = True
                        break
            
            # If no closing brace found, try to complete the JSON
            if not end_found:
                candidate = response_text[start:]
                parsed = try_complete_json(candidate)
                if parsed:
                    normalized = normalize_tool_call(parsed)
                    if normalized:
                        return normalized
        except (ValueError, json.JSONDecodeError):
            pass

        return None
