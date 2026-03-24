"""
agents/coder_agent.py
CoderAgent: Writes, reviews, debugs, and tests code.
"""
from typing import Optional
import os

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess, ToolResult
from core.message_bus import MessageBus
from tools.file_manager import write_file

# YASAK DOSYA İSİMLERİ
BANNED_FILENAMES = {
    "output.py",
    "script.py",
    "main_output.py",
    "result.py",
    "code.py",
    "solution.py",
    "temp.py",
    "test_output.py",
}

INVALID_FILENAME_TOKENS = {
    "dosya_adi",
    "dosyaadi",
    "isim",
    "kod_buraya",
    "placeholder",
    "example",
    "ornek",
}

SYSTEM_PROMPT = """Sen MAOS Coder ajanısın. Görevin: verilen task için çalışan Python kodu yazmak.

🎯 TEMEL PRENSIP: Hemen işe koyul. Uzun analiz yapma, direkt kodu yaz.

📝 ÇIKTI FORMATI (ZORUNLU):
Cevabına MUTLAKA [FILE: ile başla. Başka hiçbir şeyle başlama.

[FILE:dosya_adi.py]
kod buraya
[/FILE]

- JSON YASAK: {"code": ...} kullanma
- Markdown YASAK: ```python kullanma
- Her dosya için ayrı [FILE:] bloğu
- [/FILE] kapanış tagını ASLA atlama

🚨 BİR SEFERDE BİR DOSYA:
- Tek response'da SADECE 1 dosya yaz
- Dosyayı TAMAMEN bitir, yarım bırakma
- "...devam edecek", "# TODO", "pass" YASAK
- Her fonksiyon EKSİKSİZ olmalı

✅ DOSYA YAZILDIKTAN SONRA:
- Dosyanın kaydedildiğini doğrula
- Syntax hatası var mı kontrol et
- Varsa düzelt, yoksa bitir

📋 KOD KURALLARI:
- PEP8 uyumlu (max 88 karakter/satır)
- Type hints zorunlu: def func(x: int) -> str:
- Try/except ile hata yakala
- input() YASAK → sys.argv veya parametre kullan
- Dosya yolları: Path(__file__).parent ile
- Import: sys.path.insert(0, os.path.dirname(__file__))

🔧 SYNTAX KONTROL (KRİTİK):
- if b == 0: (DOĞRU) vs if b == : (YANLIŞ)
- Parantezler dengeli olmalı
- String'ler kapatılmalı
- İndentasyon 4 boşluk

📁 DOSYA İSİMLERİ:
YASAK: output.py, script.py, code.py, temp.py, result.py
KULLAN: main.py, database.py, api.py, utils.py

📋 TEST IMPORT KURALLARI:
- Test dosyası yazmadan önce src/ klasöründe main.py veya app.py olup olmadığını kontrol et
- main.py varsa: from main import app
- app.py varsa: from app import app
- İkisi de varsa: main.py'yi tercih et
- Hiçbiri yoksa: from main import app (orchestrator oluşturacak)

🧪 TEST KURALLARI:
- Sadece mevcut src/ dosyalarından import et
- Async fonksiyonlar için @pytest.mark.asyncio kullan
- unittest.TestCase YASAK
- Mock yerine minimal çalışan kod yaz

🧪 FASTAPI TEST CLIENT KURALLARI (KRİTİK):
- FastAPI testleri için MUTLAKA fastapi.testclient.TestClient kullan
- httpx.AsyncClient KULLANMA (yeni httpx versiyonlarında app= parametresi hata verir)
- @pytest.mark.asyncio decorator KULLANMA (TestClient senkron çalışır)
- Örnek pattern:
  from fastapi.testclient import TestClient
  from main import app
  
  client = TestClient(app)
  
  def test_endpoint():  # async DEĞİL, normal def
      response = client.get("/")
      assert response.status_code == 200

⚠️ ÖZEL KURALLAR:
- Flet icons: ft.Icons.ADD (büyük harf)
- FastAPI: @app.get('/health') endpoint ekle
- Mevcut dosya varsa güncelle, yeniden yazma
- Maksimum 2 dosya: 1 src + 1 test

ÖRNEK ÇIKTI:
[FILE:calculator.py]
import sys
from typing import Union

def topla(a: int, b: int) -> int:
    '''İki sayıyı toplar.'''
    return a + b

if __name__ == "__main__":
    x = int(sys.argv[1])
    y = int(sys.argv[2])
    print(topla(x, y))
[/FILE]

UNUTMA: Hemen [FILE: ile başla, kodu TAMAMEN yaz, [/FILE] ile kapat."""


class CoderAgent(BaseAgent):
    """
    Generates, reviews, and debugs code. Writes tests for every function.
    """

    def __init__(self, agent_id: str = "coder", bus: Optional[MessageBus] = None):
        name_str = "Hızlı Yazılımcı Ajan" if agent_id == "coder_fast" else "Mimar Yazılımcı Ajan"
        super().__init__(
            agent_id=agent_id,
            name=name_str,
            role="Kod Üretimi, İnceleme ve Hata Ayıklama",
            description="Her fonksiyon için testlerle birlikte temiz, verimli ve iyi belgelenmiş kod yazar.",
            capabilities=["code_generation", "debugging", "refactoring", "testing"],
            bus=bus,
        )
        self.register_tool("run_code", self._run_saved_python_file)
        self.register_tool("write_file", write_file)

    async def _run_saved_python_file(
        self,
        file_path: str,
        project_slug: str = "default",
        timeout: int = 30,
    ) -> ToolResult:
        """Kaydedilmiş gerçek dosyayı proje src/ cwd ile çalıştır."""
        import asyncio
        import sys
        from pathlib import Path

        start = asyncio.get_event_loop().time()
        file_path_obj = Path(file_path).resolve()

        try:
            file_content = file_path_obj.read_text(encoding="utf-8", errors="ignore")
            if "input(" in file_content:
                return ToolResult(
                    success=True,
                    data={"output": "Interactive program, otomatik test edilemez", "skipped": True},
                    error=None,
                    execution_time_ms=0,
                )
            if "while True" in file_content or "while 1:" in file_content:
                return ToolResult(
                    success=True,
                    data={"output": "Sonsuz döngü tespit edildi, otomatik test edilemez", "skipped": True},
                    error=None,
                    execution_time_ms=0,
                )
        except Exception:
            pass

        project_root = (Path("workspace/projects") / project_slug).resolve()
        project_src = (project_root / "src").resolve()
        project_tests = (project_root / "tests").resolve()
        working_dir = project_src if project_src.exists() else file_path_obj.parent

        env = os.environ.copy()
        existing_path = env.get("PYTHONPATH", "")
        new_paths = [
            str(project_src),
            str(project_tests),
            str(project_root),
            str(file_path_obj.parent),
        ]
        env["PYTHONPATH"] = os.pathsep.join(new_paths + ([existing_path] if existing_path else []))

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(file_path_obj),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(working_dir),
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            elapsed = (asyncio.get_event_loop().time() - start) * 1000
            return ToolResult(
                success=False,
                data=None,
                error=f"Timeout: {timeout} saniye aşıldı",
                execution_time_ms=elapsed,
            )

        elapsed = (asyncio.get_event_loop().time() - start) * 1000
        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        return_code = proc.returncode

        return ToolResult(
            success=(return_code == 0),
            data={
                "output": stdout,
                "errors": stderr,
                "return_code": return_code,
                "execution_time_ms": elapsed,
            },
            error=stderr if return_code != 0 else None,
            execution_time_ms=elapsed,
        )

    def _auto_fix_common_errors(self, code: str) -> str:
        """LLM'in sık yaptığı syntax hatalarını otomatik düzelt.
        
        Regex ile yaygın syntax hatalarını düzeltir:
        - if/while/for ifadelerinde eksik karşılaştırma değeri
        - sys.path.insert eksik ilk parametre
        - Boş parantez içi karşılaştırma
        """
        import re
        
        # if/while/for ifadelerinde eksik karşılaştırma değeri
        # "if b == :" → "if b == 0:"
        code = re.sub(r'(if|while)\s+(\w+)\s*(==|!=|<|>|<=|>=)\s*:', r'\1 \2 \3 0:', code)
        
        # sys.path.insert eksik ilk parametre
        # "sys.path.insert(, ...)" → "sys.path.insert(0, ...)"
        code = re.sub(r'sys\.path\.insert\s*\(\s*,', 'sys.path.insert(0,', code)
        
        # Boş parantez içi karşılaştırma
        # "== :" veya "!= :" → "== 0:" veya "!= 0:"
        code = re.sub(r'(==|!=)\s*:', r'\1 0:', code)
        
        # Flet Icons Fix (ft.icons.xxx -> ft.Icons.xxx)
        code = code.replace("ft.icons.", "ft.Icons.")
        
        return code

    def _fix_unterminated_strings(self, code: str) -> str:
        """Unterminated string literal'ları otomatik düzelt.
        
        AST parse ile syntax hatası tespit eder ve düzeltir.
        """
        import ast
        
        try:
            # Önce ast ile parse etmeyi dene
            ast.parse(code)
            return code  # Zaten geçerli
        except SyntaxError as e:
            # Sadece unterminated string hatalarını düzelt
            error_msg = str(e).lower()
            if "unterminated" not in error_msg and "eol" not in error_msg:
                return code  # Farklı syntax hatası, dokunma
            
            # Hatalı satırı bul
            error_line = e.lineno
            if not error_line:
                return code
            
            lines = code.splitlines()
            if error_line > len(lines):
                return code
            
            # Hatalı satırı düzelt
            bad_line = lines[error_line - 1]
            
            # Tek tırnak sayısını say (escape edilmemiş)
            single_count = bad_line.count("'") - bad_line.count("\\'")
            double_count = bad_line.count('"') - bad_line.count('\\"')
            
            if single_count % 2 != 0:
                # Satır sonuna tek tırnak ekle
                lines[error_line - 1] = bad_line.rstrip() + "'"
            elif double_count % 2 != 0:
                # Satır sonuna çift tırnak ekle
                lines[error_line - 1] = bad_line.rstrip() + '"'
            else:
                return code  # Düzeltemiyoruz
            
            fixed_code = "\n".join(lines)
            
            # Tekrar kontrol et
            try:
                ast.parse(fixed_code)
                print(f"[Coder] ✅ Unterminated string düzeltildi (satır {error_line})")
                return fixed_code
            except SyntaxError:
                return code  # Düzeltemedik, orijinali döndür
        except Exception:
            return code  # Başka bir hata, dokunma

    def _is_truncated(self, code: str) -> bool:
        """Kodun yarıda kesilip kesilmediğini kontrol et.
        
        Kontroller:
        - String içinde kesilme (tek/çift tırnak dengesi)
        - Açık parantez/bracket dengesi
        - Son satır yarım mı
        - Triple quote açık mı
        """
        if not code or not code.strip():
            return True
        
        stripped = code.strip()
        lines = stripped.splitlines()
        last_line = lines[-1].strip() if lines else ""
        
        # 1. Açık string literal kontrolü (escape karakterleri hariç)
        single_quotes = code.count("'") - code.count("\\'")
        double_quotes = code.count('"') - code.count('\\"')
        if single_quotes % 2 != 0 or double_quotes % 2 != 0:
            return True
        
        # 2. Açık parantez kontrolü
        open_parens = code.count("(") - code.count(")")
        open_brackets = code.count("[") - code.count("]")
        open_braces = code.count("{") - code.count("}")
        if open_parens > 0 or open_brackets > 0 or open_braces > 0:
            return True
        
        # 3. Son satır yarım mı?
        incomplete_endings = [
            "def ", "class ", "if ", "elif ", "else:", "for ",
            "while ", "try:", "except", "finally:", "with ",
            "return", "import ", "from ", ",", "\\", "+"
        ]
        for ending in incomplete_endings:
            if last_line.endswith(ending) or last_line == ending.strip():
                return True
        
        # 4. Triple quote açık mı?
        triple_single = code.count("'''")
        triple_double = code.count('"""')
        if triple_single % 2 != 0 or triple_double % 2 != 0:
            return True
        
        return False

    def _check_syntax(self, code: str, filename: str) -> tuple[bool, str]:
        """DÜZELTME B: Syntax post-processing kontrolü.
        
        py_compile ile syntax kontrolü yapar.
        Returns: (is_valid, error_message)
        """
        import py_compile
        import tempfile
        
        # [FILE:] formatı içeriyorsa syntax check yapma
        # Bu sistem formatı, Python kodu değil
        if "[FILE:" in code:
            return True, ""  # Geçerli say, devam et
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                tmp = f.name
            
            py_compile.compile(tmp, doraise=True)
            os.unlink(tmp)
            return True, ""
        except py_compile.PyCompileError as e:
            try:
                os.unlink(tmp)
            except:
                pass
            return False, str(e)
        except Exception as e:
            try:
                os.unlink(tmp)
            except:
                pass
            return False, f"Syntax check error: {str(e)}"

    async def _check_existing_files(self, project_slug: str) -> list:
        """Projede zaten hangi dosyalar var, listele."""
        from pathlib import Path
        src_dir = Path("workspace/projects") / project_slug / "src"
        tests_dir = Path("workspace/projects") / project_slug / "tests"

        existing = []
        for d in [src_dir, tests_dir]:
            if d.exists():
                for f in d.iterdir():
                    if f.suffix == ".py" and f.name != ".gitkeep":
                        existing.append({
                            "name": f.name,
                            "path": str(f),
                            "size": f.stat().st_size,
                        })
        return existing

    async def think(self, task: Task) -> ThoughtProcess:
        """Analyze the coding task and plan the implementation."""
        context = task.context.get("research", "")
        project_slug = task.context.get("project_slug", "default")

        # Mevcut dosya kontrolü — duplikasyonu önle
        existing_files = await self._check_existing_files(project_slug)
        existing_note = ""
        if existing_files:
            task.context["existing_files"] = existing_files
            existing_info = "\n".join([f"- {f['name']}" for f in existing_files])
            task.context["existing_files_info"] = f"Mevcut dosyalar:\n{existing_info}"
            existing_note = f"\n\nMEVCUT DOSYALAR (yeniden oluşturma, güncelle):\n{existing_info}"

        plan_prompt = (
            f"Görev: {task.description}\n"
            f"Bağlam: {context}"
            f"{existing_note}\n\n"
            "Uygulamayı planla. Hangi dosyaları oluşturacaksın? "
            "Hangi kütüphaneleri kullanacaksın? SADECE JSON yanıt ver: "
            '{\"plan\": [\"adim1\", \"adim2\"], \"files_to_create\": [\"dosya.py\"], \"libraries\": [\"lib\"]}'
        )
        response = await self._call_llm(
            messages=[{"role": "user", "content": plan_prompt}],
            system_prompt="Sen kıdemli bir yazılım mimarısın.",
            temperature=0.3,
            max_tokens=1000,  # 500 → 1000 (2x artırıldı)
        )
        
        # Error handling: if LLM returns None or empty, return default ThoughtProcess
        if not response or not response.strip():
            print("[Coder] ⚠️ think() LLM response is None/empty, using default plan")
            return ThoughtProcess(
                reasoning="Direct implementation",
                plan=["Write the code as specified in task description"],
                tool_calls=[],
                confidence=0.9,
            )
        
        parsed = self._parse_json_response(response)
        
        # Error handling: if JSON parsing fails, return default ThoughtProcess
        if not parsed or not isinstance(parsed, dict):
            print(f"[Coder] ⚠️ think() JSON parsing failed, using default plan. Response: {response[:100]}")
            return ThoughtProcess(
                reasoning="Direct implementation",
                plan=["Write the code as specified in task description"],
                tool_calls=[],
                confidence=0.9,
            )

        return ThoughtProcess(
            reasoning=f"Implementation plan: {parsed.get('plan', [])}",
            plan=parsed.get("plan", [task.description]),
            tool_calls=[{"tool": "write_file"}, {"tool": "run_code"}],
            confidence=0.85,
        )

    def _extract_file_blocks(self, text: str, task_hint: str = "") -> list[dict]:
        """Extract code blocks from LLM response — supports multiple formats.

        Priority order:
        1. [FILE:name.py]...[/FILE]        ← ideal format
        2. [FILE:name.py]... (no closing)  ← truncated output
        3. ```python # name.py ...```      ← markdown with filename comment
        4. ```name.py ...```               ← markdown with filename tag
        5. ```python ...```                ← plain markdown, filename inferred
        """
        import re
        stripped = (text or "").strip()
        if (
            stripped.startswith("{")
            or stripped.startswith("[{")
            or (stripped.startswith("[") and not stripped.startswith("[FILE:"))
        ):
            print("[Coder] ❌ JSON format reddedildi, yeniden deneniyor")
            return []

        files = []

        # Format 1: [FILE:name.py]...[/FILE] (tam format)
        pattern1 = r'\[FILE:([^\]]+)\]\n?(.*?)\[/FILE\]'
        matches1 = re.findall(pattern1, text, re.DOTALL)
        for filename, content in matches1:
            filename = filename.strip()
            content = self._clean_content(content)
            if content:
                files.append({"filename": filename, "content": content})

        # Format 1b: Eksik [/FILE] tagı — token limiti nedeniyle kesilmiş
        if not files:
            pattern1b = r'\[FILE:([^\]]+)\]\n?(.*?)(?=\[FILE:|$)'
            matches1b = re.findall(pattern1b, text, re.DOTALL)
            for filename, content in matches1b:
                filename = filename.strip()
                content = self._clean_content(content)
                if content and len(content) > 50 and filename.endswith('.py'):
                    files.append({"filename": filename, "content": content})

        # Format 2: ```python # name.py ... ```
        pattern2 = r'```python\s*#\s*([^\n]+)\n(.*?)```'
        matches2 = re.findall(pattern2, text, re.DOTALL)
        for filename, content in matches2:
            filename = filename.strip()
            content = self._clean_content(content)
            if content and filename and not any(f['filename'] == filename for f in files):
                files.append({"filename": filename, "content": content})

        # Format 3: ```name.py ... ```
        pattern3 = r'```([a-zA-Z0-9_\-\.]+\.[a-z]+)\n(.*?)```'
        matches3 = re.findall(pattern3, text, re.DOTALL)
        for filename, content in matches3:
            filename = filename.strip()
            content = self._clean_content(content)
            if content and filename and '.' in filename:
                if not any(f['filename'] == filename for f in files):
                    files.append({"filename": filename, "content": content})

        # Format 4: ```python ... ``` (dosya ismi yok — task_hint'ten türet)
        if not files:
            pattern4 = r'```(?:python|py)\n(.*?)```'
            matches4 = re.findall(pattern4, text, re.DOTALL)
            if matches4:
                # Task hint'ten akıllı dosya ismi üret
                filename = self._infer_filename(task_hint, matches4[0])
                for i, content in enumerate(matches4):
                    content = self._clean_content(content)
                    if content and len(content) > 50:
                        if i == 0:
                            fname = filename
                        else:
                            base = filename.replace('.py', '')
                            fname = f"{base}_{i}.py"
                        if not any(f['filename'] == fname for f in files):
                            files.append({"filename": fname, "content": content})

        return files

    def _extract_json_fallback_blocks(self, text: str, task_hint: str = "") -> list[dict]:
        """[FILE:] bulunamazsa JSON benzeri cevaplardan dosya blokları çıkar."""
        import json
        import re

        stripped = (text or "").strip()
        
        # Strip markdown code fences before parsing JSON
        cleaned = re.sub(r'^```(?:json)?\s*', '', stripped)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip()
        
        if not (cleaned.startswith("[") or cleaned.startswith("{")):
            return []

        parsed = None
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            # Log the error with the raw response for debugging
            print(f"[Coder] ⚠️ JSON parse error: {e}")
            print(f"[Coder] ⚠️ Raw response (first 200 chars): {repr(cleaned[:200])}")
            parsed = self._repair_truncated_json(cleaned)

        if parsed is not None:
            files = self._extract_from_parsed_json(parsed, task_hint)
            if files:
                print(f"[Coder] ✅ JSON formatından {len(files)} dosya çıkarıldı")
                return files

        files = self._extract_from_json_regex(stripped, task_hint)
        if files:
            print(f"[Coder] ✅ JSON-regex fallback ile {len(files)} dosya çıkarıldı")
        return files

    def _repair_truncated_json(self, text: str):
        """Kesilen JSON yanıtlarını tamir etmeye çalış."""
        import json
        
        # Yöntem 1: Basit kapanış ekleme
        suffixes = ['"}]', '"}}]', '"}]}', '"]', '}]', ']', '}']
        for suffix in suffixes:
            try:
                return json.loads(text + suffix)
            except json.JSONDecodeError:
                continue
        
        # Yöntem 2: Son tamamlanmış JSON nesnesine kadar kes
        if text.startswith('['):
            import re
            # "}, {" veya "},\n{" kalıplarını ara (nesne sınırları)
            # Ancak tırnak içindeki eşleşmeleri atla
            last_good = -1
            in_string = False
            escape = False
            depth = 0
            
            for i, ch in enumerate(text):
                if escape:
                    escape = False
                    continue
                if ch == '\\' and in_string:
                    escape = True
                    continue
                if ch == '"' and not escape:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                    
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:  # Üst seviye nesne kapandı
                        last_good = i
            
            if last_good > 0:
                truncated = text[:last_good + 1] + ']'
                try:
                    return json.loads(truncated)
                except json.JSONDecodeError:
                    pass
        
        return None
    
    def _extract_from_parsed_json(self, parsed, task_hint: str) -> list:
        """Parse edilmiş JSON'dan dosya bloklarını çıkar."""
        files = []
        file_list = []
        
        if isinstance(parsed, list):
            file_list = parsed
        elif isinstance(parsed, dict):
            if "files" in parsed and isinstance(parsed["files"], list):
                file_list = parsed["files"]
            else:
                file_list = [parsed]
        
        for item in file_list:
            if not isinstance(item, dict):
                continue
            
            fname = (item.get("filename") or item.get("file") or 
                    item.get("name") or "")
            if isinstance(fname, str):
                fname = fname.strip()
            else:
                fname = ""
            
            code = (item.get("content") or item.get("code") or 
                   item.get("source") or "")
            
            if not code or not isinstance(code, str) or not code.strip():
                continue
            
            code = code.strip()
            
            if not fname:
                fname = self._infer_filename(task_hint, code)
            
            if not any(f['filename'] == fname for f in files):
                files.append({"filename": fname, "content": code})
        
        return files
    
    def _extract_from_json_regex(self, text: str, task_hint: str) -> list:
        """JSON-benzeri metinden regex ile dosya adı ve içerik çıkar (son çare)."""
        import re, json
        files = []
        
        # "file"/"filename"/"name": "xxx" kalıplarını bul
        name_pattern = r'"(?:file(?:name)?|name)"\s*:\s*"([^"]+)"'
        name_matches = list(re.finditer(name_pattern, text))
        
        # "content"/"code"/"source": "..." kalıplarını bul
        content_pattern = r'"(?:content|code|source)"\s*:\s*"'
        content_matches = list(re.finditer(content_pattern, text))
        
        if not content_matches:
            return files
        
        for content_match in content_matches:
            start = content_match.end()
            
            # JSON string değerini karakter karakter oku (escape'leri atla)
            pos = start
            while pos < len(text):
                if text[pos] == '\\' and pos + 1 < len(text):
                    pos += 2  # Escape sequence, atla
                elif text[pos] == '"':
                    break  # String sonu
                else:
                    pos += 1
            
            raw_content = text[start:pos]
            
            # JSON escape'lerini çöz
            try:
                decoded = json.loads('"' + raw_content + '"')
            except (json.JSONDecodeError, Exception):
                # Manuel decode
                decoded = (raw_content
                    .replace('\\n', '\n')
                    .replace('\\t', '\t')
                    .replace('\\"', '"')
                    .replace('\\\\', '\\'))
            
            if not decoded or not decoded.strip() or len(decoded.strip()) < 20:
                continue
            
            decoded = decoded.strip()
            
            # Bu content'e en yakın filename'i bul
            fname = ""
            content_pos = content_match.start()
            best_dist = float('inf')
            for nm in name_matches:
                dist = abs(nm.start() - content_pos)
                if dist < best_dist:
                    best_dist = dist
                    fname = nm.group(1)
            
            if not fname:
                fname = self._infer_filename(task_hint, decoded)
            
            if not any(f['filename'] == fname for f in files):
                files.append({"filename": fname, "content": decoded})
        
        return files

    def _clean_content(self, content: str) -> str:
        """Eger icerik raw JSON string olarak (\\n literal ile) geldiyse decode et."""
        content = content.strip()
        # Sadece eger gercek satır sonu (\n) yoksa VE string icinde literal '\n' varsa (JSON escape ise)
        if '\\n' in content and '\n' not in content:
            try:
                # String literal'i gercek karakterlere cevir (\\n -> \n, \\" -> ")
                content = content.encode('utf-8').decode('unicode_escape')
            except Exception:
                pass
        return content

    def _infer_filename(self, task_hint: str, code: str) -> str:
        """Task açıklamasına ve koda bakarak dosya ismi tahmin et."""
        task_lower = task_hint.lower()
        code_lower = code.lower()

        # Task'taki anahtar kelimelere göre
        mapping = {
            ("board", "tahta", "satranç", "chess"): "board.py",
            ("piece", "taş", "king", "queen", "rook", "bishop", "knight", "pawn"): "pieces.py",
            ("game", "oyun", "engine"): "game.py",
            ("cli", "arayüz", "interface", "input", "main"): "main.py",
            ("test",): "test_main.py",
            ("database", "db", "model", "sqlite"): "database.py",
            ("api", "route", "endpoint", "fastapi"): "api.py",
            ("util", "helper", "yardımcı"): "utils.py",
        }
        for keywords, fname in mapping.items():
            if any(k in task_lower or k in code_lower for k in keywords):
                return fname
        return "module.py"

    def _is_valid_generated_filename(self, filename: str) -> bool:
        """Üretilen dosya adının kayda uygun olup olmadığını kontrol et."""
        import re

        lowered = filename.lower()
        if any(token in lowered for token in INVALID_FILENAME_TOKENS):
            return False
        return re.fullmatch(r"[A-Za-z0-9_.]+", filename) is not None

    def _should_skip_generated_file(self, filename: str, content: str) -> bool:
        """Placeholder isimleri ve anlamsız kısa içerikleri atla."""
        if len(content.strip()) < 50:
            return True
        return not self._is_valid_generated_filename(filename)




    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """Generate code using marker-based format, save files to workspace."""
        print("[CODER ACT] starting act()")
        print(f"[CODER ACT] thought: {thought}")
        
        context = task.context.get("research", "")
        history = self.short_term_memory.get_messages()
        project_slug = task.context.get("project_slug", "default")

        # Cluster mode: Model override varsa kullan
        model_override = task.context.get("model_override")
        original_llm = None
        if model_override:
            from core.llm_client import LLMClient
            original_llm = self._llm
            self._llm = LLMClient(agent_id=self.agent_id, model_key=model_override)
            print(f"[Coder] Cluster mode: {model_override} kullanılıyor")

        try:
            # Phase context — injected by orchestrator for phased projects
            phase_info = task.context.get("phase_info", "")
            file_api = task.context.get("file_api", "")
            existing_files = task.context.get("existing_files", "")

            phase_note = ""
            if phase_info or file_api:
                phase_note = f"\n\n{'='*60}\n"
                phase_note += "⚠️ KRİTİK: MEVCUT DOSYALAR — TEKRAR YAZMA!\n"
                if file_api:
                    phase_note += f"\nMevcut dosya API'leri (SADECE IMPORT ET):\n{file_api}\n"
                if phase_info:
                    phase_note += f"\n{phase_info}\n"
                phase_note += (
                    "\nKURAL: Yukarıdaki dosyaları ASLA yeniden oluşturma!\n"
                    "Sadece 'from dosya_adi import SinifAdi' ile import et.\n"
                    "SADECE YENİ dosyalar oluştur.\n"
                    f"{'='*60}"
                )
            elif existing_files:
                phase_note = f"\n\nMevcut dosyalar (import et, tekrar yazma): {existing_files}"

            # NEW: Check for contract in context
            contract_note = ""
            contract = task.context.get("project_contract")
            if contract:
                # Build contract summary for prompt
                contract_summary = self._format_contract_for_prompt(contract)
                contract_note = f"\n\n{'='*60}\n"
                contract_note += "📋 PROJECT CONTRACT (FOLLOW EXACTLY):\n\n"
                contract_note += contract_summary
                contract_note += "\n\nIMPORTANT: Follow the contract exactly. Use the defined field names, types, and interfaces.\n"
                contract_note += f"{'='*60}\n"

            coding_prompt = (
                "CEVABINA [FILE: ile başla, başka hiçbir şeyle başlama.\n"
                "JSON KULLANMA. {\"code\": YAZMA. SADECE [FILE:dosya.py]...[/FILE].\n\n"
                f"Gorev: {task.description}"
                f"{phase_note}\n"
                f"{contract_note}\n"
                f"Baglam/Arastirma: {context}\n\n"
                "KESİN KURAL: Kod üretirken SADECE [FILE:dosya.py]...[/FILE] formatını kullan. "
                "JSON formatı YASAK. {\"code\": ...} YASAK. Sadece [FILE:] bloğu.\n\n"
                "ZORUNLU FORMAT - BUNU KULLANMAZSAN CEVAP GEÇERSİZ:\n"
                "[FILE:dosyaadi.py]\n"
                "# tam Python kodu buraya\n"
                "[/FILE]\n\n"
                "KURALLAR:\n"
                "1. Her dosya için ayrı [FILE:isim.py]...[/FILE] bloğu yaz\n"
                "2. Kodu ASLA yarım bırakma, her fonksiyon eksiksiz olmalı\n"
                "3. [/FILE] kapanış tagını ASLA unutma\n"
                "4. Markdown kod bloğu (```python) KULLANMA\n"
                "5. Açıklama/yorum yazma, sadece kod yaz\n"
                "6. Mevcut dosyaları TEKRAR YAZMA, sadece IMPORT ET\n\n"
                "Şimdi görevi çözen TAM ve EKSİKSİZ kodu yaz:"
            )


            messages = history + [{"role": "user", "content": coding_prompt}]

            print("[CODER ACT] calling LLM")
            response = await self._call_llm(
                messages=messages,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.5,
                max_tokens=16000,  # Codestral 256K destekliyor
            )

            # DEBUG: Token count and raw content inspection
            import json
            raw_text = getattr(response, 'text', None) or getattr(response, 'content', None) or response
            token_estimate = len(str(raw_text).split()) if raw_text else 0
            print(f"[CODER RAW] out tokens: ~{token_estimate}, content: {repr(str(raw_text)[:200]) if raw_text else 'NONE'}")
            
            # CRITICAL DEBUG: If response is very short (35-40 tokens), log everything
            if token_estimate < 50:
                print(f"[CODER CRITICAL] Response is only {token_estimate} tokens!")
                print(f"[CODER CRITICAL] Full raw response: {repr(response)}")
                print(f"[CODER CRITICAL] Response type: {type(response)}")
                print(f"[CODER CRITICAL] Response length: {len(response)} chars")

            # DEBUG: Ham LLM çıktısını göster (parser sorunlarını tespit için)
            print(f"[Coder DEBUG] Ham çıktı ilk 800 karakter:")
            print(f"---RAW START---")
            print(response[:800])
            print(f"---RAW END--- (toplam {len(response)} karakter)")
            
            # DEBUG: Log full response when it's suspiciously short
            if len(response) < 100:
                print(f"[Coder CRITICAL] Response is suspiciously short ({len(response)} chars)!")
                print(f"[Coder CRITICAL] Full response: {repr(response)}")

            # Primary: extract [FILE:...][/FILE] blocks (immune to JSON errors)
            file_blocks = self._extract_file_blocks(response, task_hint=task.description)
            
            # DEBUG: Log extraction result
            print(f"[Coder DEBUG] Extracted {len(file_blocks)} file blocks from response")
            if not file_blocks:
                print(f"[Coder DEBUG] No file blocks found! Response starts with: {response[:100]}")

            # Eger hicbir [FILE:...] blogu bulunamadiysa RETRY yap -- JSON/metin dosyaya yazilmasin!
            if not file_blocks:
                print(f"[Coder] ⚠️ [FILE:] bloğu bulunamadı, fallback tetikleniyor...")
                print(f"[Coder] ⚠️ Original response was {len(response)} chars, starting with: {response[:150]}")
                
                retry_prompt = (
                    "ÖNCEKİ CEVABINDA JSON KULLANDIN. BU GEÇERSİZ.\n"
                    "SADECE [FILE:dosya.py] formatında yaz.\n"
                    "KRITIK HATA: Önceki çıktın [FILE:] formatında değildi!\n\n"
                    "KESİN KURAL: Kod üretirken SADECE [FILE:dosya.py]...[/FILE] formatını kullan.\n"
                    "JSON formatı YASAK. {\"code\": ...} YASAK. Sadece [FILE:] bloğu.\n"
                    "CEVABINA [FILE: ile başla, başka hiçbir şeyle başlama.\n"
                    "JSON VEYA MARKDOWN KULLANMAK KESİNLİKLE YASAKTIR.\n"
                    "SADECE şu formatı kullan:\n\n"
                    "[FILE:dosya_adi.py]\n"
                    "# Python kodu buraya\n"
                    "[/FILE]\n\n"
                    "Lütfen kodu baştan, EKSİKSİZ şekilde ve SADECE bu formatta yaz."
                )
                print(f"[Coder] ⚠️ [FILE:] bloğu bulunamadı, fallback tetikleniyor...")
                response2 = await self._call_llm(
                    messages=[{"role": "user", "content": retry_prompt}],
                    system_prompt=SYSTEM_PROMPT,
                    temperature=0.3,
                    max_tokens=16000,  # retry da aynı limit
                )
                file_blocks = self._extract_file_blocks(response2, task_hint=task.description)
                
                # DEBUG: Log retry result
                print(f"[Coder DEBUG] Retry extracted {len(file_blocks)} file blocks")
                if not file_blocks:
                    print(f"[Coder DEBUG] Retry also failed! Response2 starts with: {response2[:100]}")
                    print(f"[Coder DEBUG] Full response2 length: {len(response2)} chars")
                
                # Son care: JSON degil ama [FILE:] de yoksa — en azindan kod iceriyorsa yaz
                if not file_blocks and response2.strip():
                    is_json = response2.strip().startswith("{") or response2.strip().startswith("[{")
                    has_code = any(kw in response2 for kw in ("def ", "import ", "class ", "if __name__"))
                    if not is_json and has_code:
                        print("[Coder] UYARI: [FILE:] formatı bulunamadı, ham kod main.py olarak kaydediliyor")
                        file_blocks = [{"filename": "main.py", "content": response2}]
                    else:
                        # Hicbir sey bulunamadiysa hata dondur
                        print("[Coder] KRITIK: Hiçbir geçerli kod bloğu bulunamadı!")
                        print(f"[Coder] KRITIK: Response length: {len(response)} chars")
                        print(f"[Coder] KRITIK: Response2 length: {len(response2)} chars")
                        print(f"[Coder] KRITIK: Response2 full content: {repr(response2)}")
                        return AgentResponse(
                            content=None,
                            success=False,
                            error="LLM [FILE:] formatında kod üretemedi. Lütfen görevi yeniden deneyin.",
                            metadata={"raw_response": response2[:500], "response_length": len(response2)},
                        )

            saved_files = []
            run_results = []
            main_code = ""
            main_filename = "script.py"

            for file_info in file_blocks:
                filename = file_info.get("filename", "main.py")
                content = file_info.get("content", "")
                if not content.strip():
                    continue

                # ⛔ MEVCUT DOSYA KORUMASI: Eğer dosya zaten mevcutsa VE bu görev
                # o dosyayı yazmayı hedeflemiyorsa, üzerine yazmayı engelle
                from pathlib import Path as _Path
                
                # Preserve relative path for checking
                _relative_path = filename
                if _relative_path.startswith("src/") or _relative_path.startswith("src\\"):
                    _relative_path = _relative_path[4:]
                elif _relative_path.startswith("tests/") or _relative_path.startswith("tests\\"):
                    _relative_path = _relative_path[6:]
                
                _clean = _Path(_relative_path).name
                _proj_root = _Path("workspace/projects") / project_slug
                _existing_path = _proj_root / "src" / _relative_path
                if _existing_path.exists() and existing_files and _clean in existing_files:
                    # Bu dosya zaten var ve existing_files listesinde
                    # Görev açıklaması bu dosyanın adını içermiyorsa → üzerine yazma
                    task_mentions_file = _clean.replace('.py', '') in task.description.lower()
                    if not task_mentions_file:
                        print(f"[Coder] 🛡️ Mevcut dosya koruması: '{_clean}' zaten var, üzerine yazılmadı!")
                        print(f"[Coder]    Görev bu dosyayı hedeflemiyor, atlanıyor.")
                        continue

                # Route files into project directory
                from pathlib import Path
                
                # Use the same relative_path from above (already stripped src/tests prefix)
                relative_path = _relative_path
                clean_filename = _clean
                
                # ⛔ YASAK DOSYA ADI KONTROLÜ
                if clean_filename in BANNED_FILENAMES:
                    print(f"[Coder] ⛔ Yasak dosya adı tespit edildi: '{clean_filename}'")
                    print(f"[Coder] Bu dosya kaydedilmeyecek.")
                    continue  # Bu dosyayı atla

                if self._should_skip_generated_file(clean_filename, content):
                    print(f"[Coder] ⚠️ Geçersiz dosya adı atlandı: {clean_filename}")
                    continue
                
                project_root = Path("workspace/projects") / project_slug
                
                # Dosya türüne göre klasör belirle (preserve subdirectories)
                if "test_" in clean_filename or clean_filename.startswith("test"):
                    save_path = project_root / "tests" / relative_path
                elif clean_filename.endswith(".html") or clean_filename.endswith(".jinja2"):
                    # HTML/template dosyaları src/templates/ içine
                    save_path = project_root / "src" / "templates" / relative_path
                elif clean_filename.endswith(".css"):
                    # CSS dosyaları src/static/ içine
                    save_path = project_root / "src" / "static" / relative_path
                elif clean_filename.endswith(".js"):
                    # JavaScript dosyaları src/ içine (static değil)
                    save_path = project_root / "src" / relative_path
                else:
                    save_path = project_root / "src" / relative_path
                    if not main_code:  # first src file is main
                        main_code = content
                        main_filename = clean_filename
                
                # Create any missing intermediate directories
                save_path.parent.mkdir(parents=True, exist_ok=True)

                # DÜZELTME B: Syntax kontrolü (Python dosyaları için)
                if clean_filename.endswith('.py'):
                    # 0. Truncation (Kesilme) onarimi (Kaldigi yerden devam et)
                    trunc_retries = 0
                    while self._is_truncated(content) and trunc_retries < 3:
                        trunc_retries += 1
                        print(f"[Coder] ⚠️ Kod yarıda kesildi: {clean_filename}")
                        print(f"[Coder] 🔄 LLM'den kalan kismı yazması isteniyor... (Deneme: {trunc_retries}/3)")
                        
                        last_chars = content[-250:]
                        append_prompt = (
                            f"Önceki yazdığın kod '{clean_filename}' dosyası için şu satırda max-token limitine takılarak kesildi:\n"
                            f"...\n{last_chars}\n\n"
                            f"Lütfen SADECE KALAN KISMINI yazmaya devam et. Dosyanın başını tekrar YAZMA. "
                            f"Tam olarak kaldığın o son karakterden sonrasını gönder.\n"
                            f"FORMAT:\n[FILE:{clean_filename}]\nkalan_kod_buraya\n[/FILE]"
                        )
                        
                        chunk_retries = 0
                        chunk_is_valid = False
                        
                        while chunk_retries < 2 and not chunk_is_valid:
                            chunk_retries += 1
                            try:
                                response_append = await self._call_llm(
                                    messages=[{"role": "user", "content": append_prompt}],
                                    system_prompt=SYSTEM_PROMPT,
                                    temperature=0.2,
                                    max_tokens=8000,
                                )
                                
                                append_blocks = self._extract_file_blocks(response_append)
                                if append_blocks:
                                    appended = append_blocks[0].get("content", "")
                                else:
                                    raw = response_append.strip()
                                    if raw.startswith("```"):
                                        lines = raw.split("\n")
                                        if len(lines) > 2:
                                            raw = "\n".join(lines[1:-1])
                                    appended = raw
                                
                                from utils.code_utils import align_and_validate_chunk
                                is_valid, new_combined, error_msg = align_and_validate_chunk(content, appended)
                                
                                if is_valid:
                                    content = new_combined
                                    chunk_is_valid = True
                                    print(f"[Coder] ✅ Kalan kısım eklendi ve hizalandı (+{len(appended)} karakter)")
                                else:
                                    print(f"[Coder] ⚠️ Hizalama hatası ({chunk_retries}/2): {error_msg}. Tekrar deneniyor...")
                            except Exception as e:
                                print(f"[Coder] ❌ Kalan kısmı ekleme hatası: {e}")
                                if chunk_retries >= 2:
                                    break
                                    
                        if not chunk_is_valid:
                            print("[Coder] ❌ Max chunk retry limitine ulaşıldı, hizalama başarısız, ham kod ekleniyor.")
                            content += "\n" + appended
                            break
                    
                    # 1. ÖNCE regex ile otomatik düzeltme yap
                    original_content = content
                    content = self._auto_fix_common_errors(content)
                    
                    # 2. Unterminated string düzeltmeleri
                    content = self._fix_unterminated_strings(content)
                    
                    if content != original_content:
                        print(f"[Coder] 🔧 Auto-fix uygulandı: {clean_filename}")
                        # Debug: İlk 200 karakter göster
                        print(f"[Coder] 🔍 Önce: {original_content[:200]}")
                        print(f"[Coder] 🔍 Sonra: {content[:200]}")
                    
                    # 3. Syntax kontrolü yap
                    is_valid, syntax_error = self._check_syntax(content, clean_filename)
                    if not is_valid:
                        print(f"[Coder] ❌ Syntax hatası tespit edildi: {clean_filename}")
                        print(f"[Coder] Hata: {syntax_error}")
                        
                        # 3. Max 2 deneme ile LLM'e düzeltmeyi dene
                        for attempt in range(2):
                            print(f"[Coder] 🔄 Syntax düzeltme denemesi {attempt + 1}/2")
                            
                            # Hata satır numarasını çıkar
                            error_line = "bilinmiyor"
                            if "line" in syntax_error.lower():
                                import re
                                match = re.search(r'line (\d+)', syntax_error, re.IGNORECASE)
                                if match:
                                    error_line = match.group(1)
                            
                            fix_prompt = (
                                f"ÖNCEKİ ÇIKTIN HATALIYDI: {syntax_error}\n\n"
                                f"KESIN KURALLAR:\n"
                                f"1. Tüm string'leri kapat: ' ile açtıysan ' ile kapat\n"
                                f"2. Tüm parantezleri kapat: ( ile açtıysan ) ile kapat\n"
                                f"3. Tüm f-string'leri kapat: f'{{…}}' formatında\n"
                                f"4. Kodu ASLA yarım bırakma, tüm fonksiyonları tamamla\n"
                                f"5. [FILE:dosya.py] formatını kullan\n\n"
                                f"Önceki hatalı satır: {error_line}\n\n"
                                f"Hatalı kod:\n```python\n{content}\n```\n\n"
                                f"Şimdi SADECE düzeltilmiş kodu yaz:\n"
                                f"- Başında ```python veya ``` OLMASIN\n"
                                f"- Düz kod döndür, başka hiçbir şey yok\n"
                                f"- Markdown formatı kullanma!"
                            )
                            
                            try:
                                fixed_code = await self._call_llm(
                                    messages=[{"role": "user", "content": fix_prompt}],
                                    system_prompt="Sen bir Python syntax düzeltme uzmanısın. Sadece düzeltilmiş kodu döndür.",
                                    temperature=0.1,
                                    max_tokens=6000,  # 3000 → 6000 (2x artırıldı)
                                )
                                
                                # Strip markdown if present
                                if fixed_code.strip().startswith("```"):
                                    lines = fixed_code.strip().split("\n")
                                    fixed_code = "\n".join(lines[1:-1])
                                
                                # ✅ LLM çıktısına da auto-fix uygula!
                                print(f"[Coder] 🔧 LLM çıktısına auto-fix uygulanıyor...")
                                fixed_code = self._auto_fix_common_errors(fixed_code)
                                
                                # Düzeltilmiş kodu kontrol et
                                is_valid_fixed, syntax_error_fixed = self._check_syntax(fixed_code, clean_filename)
                                if is_valid_fixed:
                                    print(f"[Coder] ✅ Syntax hatası düzeltildi!")
                                    content = fixed_code
                                    is_valid = True  # ✅ is_valid'i güncelle!
                                    break
                                else:
                                    print(f"[Coder] ❌ Düzeltme başarısız: {syntax_error_fixed}")
                                    syntax_error = syntax_error_fixed
                            except Exception as e:
                                print(f"[Coder] ❌ Düzeltme hatası: {e}")
                        
                        # 4. Hala hatalıysa dosyayı KAYDETME
                        if not is_valid:
                            print(f"[Coder] ⛔ KRITIK: Syntax hatası düzeltilemedi, dosya kaydedilmeyecek: {clean_filename}")
                            continue  # Bu dosyayı atla, kaydetme

                # Save to workspace
                save_result = await self.use_tool("write_file", path=str(save_path), content=content)
                if save_result.success:
                    saved_files.append(str(save_path))

                # Run non-test Python files to check for errors
                if save_result.success and clean_filename.endswith(".py") and not clean_filename.startswith("test_"):
                    actual_save_path = str(save_path.resolve())
                    if save_result.success and save_result.data and save_result.data.get("path"):
                        actual_save_path = str(save_result.data["path"])

                    run_result = await self.use_tool(
                        "run_code",
                        file_path=actual_save_path,
                        project_slug=project_slug,
                    )
                    run_results.append({
                        "file": actual_save_path,
                        "success": run_result.success,
                        "output": run_result.data.get("output", "") if run_result.data else "",
                        "errors": run_result.data.get("errors", "") if run_result.data else run_result.error,
                    })

                    # Auto-fix if errors
                    if not run_result.success and run_result.error:
                        fixed = await self._fix_code(content, run_result.error, task.description)
                        if fixed:
                            fixed_save_result = await self.use_tool("write_file", path=str(save_path), content=fixed)
                            saved_files.append(f"{str(save_path)} (fixed)")
                            actual_fixed_path = actual_save_path
                            if fixed_save_result.success and fixed_save_result.data and fixed_save_result.data.get("path"):
                                actual_fixed_path = str(fixed_save_result.data["path"])

                            rerun_result = await self.use_tool(
                                "run_code",
                                file_path=actual_fixed_path,
                                project_slug=project_slug,
                            )
                            run_results.append({
                                "file": f"{actual_fixed_path} (fixed)",
                                "success": rerun_result.success,
                                "output": rerun_result.data.get("output", "") if rerun_result.data else "",
                                "errors": rerun_result.data.get("errors", "") if rerun_result.data else rerun_result.error,
                            })
                            content = fixed

            return AgentResponse(
                content={
                    "code": main_code,
                    "filename": main_filename,
                    "language": "python",
                    "saved_files": saved_files,
                    "run_results": run_results,
                    "files": file_blocks,
                },
                success=True,
                metadata={
                    "files_created": saved_files,
                    "files_count": len(saved_files),
                },
            )
        
        finally:
            # Cluster mode: Original LLM'i geri yükle
            if original_llm:
                self._llm = original_llm

    async def _fix_code(self, code: str, error: str, task_description: str) -> Optional[str]:
        """Attempt to auto-fix code given an error message."""
        fix_prompt = (
            f"Bu Python kodunda bir hata var:\n\n```python\n{code}\n```\n\n"
            f"Hata:\n{error}\n\n"
            f"Orijinal görev: {task_description}\n\n"
            "Kodu düzelt ve SADECE düzeltilmiş Python kodunu döndür, hiçbir açıklama veya markdown ekleme."
        )
        try:
            fixed = await self._call_llm(
                messages=[{"role": "user", "content": fix_prompt}],
                system_prompt="Sen bir Python hata ayıklayıcısısın (debugger). Sadece düzeltilmiş kodu döndür.",
                temperature=0.2,
                max_tokens=6000,  # 3000 → 6000 (2x artırıldı)
            )
            # Strip markdown if present
            if fixed.strip().startswith("```"):
                lines = fixed.strip().split("\n")
                fixed = "\n".join(lines[1:-1])
            return fixed
        except Exception:
            return None

    def _extract_filename(self, code: str) -> str:
        """Kodun içinden dosya adını otomatik çıkar."""
        import re
        # # filename: xxx.py şeklinde yorum varsa onu kullan
        match = re.search(r'#\s*filename:\s*(\S+\.py)', code)
        if match:
            return match.group(1)
        # class veya def isminden türet
        match = re.search(r'(?:class|def)\s+(\w+)', code)
        if match:
            return f"{match.group(1).lower()}.py"
        return "script.py"

    def _format_contract_for_prompt(self, contract: dict) -> str:
        """Format contract as readable text for LLM prompt."""
        lines = []
        
        if contract.get("data_models"):
            lines.append("DATA MODELS:")
            for model in contract["data_models"]:
                lines.append(f"  - {model['name']}: {model.get('description', '')}")
                for field in model.get("fields", []):
                    lines.append(f"    • {field['name']}: {field['type']}")
        
        if contract.get("api_endpoints"):
            lines.append("\nAPI ENDPOINTS:")
            for endpoint in contract["api_endpoints"]:
                lines.append(f"  - {endpoint['method']} {endpoint['path']}")
        
        if contract.get("file_structure"):
            lines.append("\nFILE STRUCTURE:")
            for file in contract["file_structure"]:
                lines.append(f"  - {file['path']}: {file['responsibility']}")
                lines.append(f"    exports: {', '.join(file['exports'])}")
        
        if contract.get("shared_constants"):
            lines.append("\nSHARED CONSTANTS:")
            for key, value in contract["shared_constants"].items():
                lines.append(f"  - {key} = {value}")
        
        return "\n".join(lines)
