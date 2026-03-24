"""
agents/coder_agent.py
CoderAgent: Writes, reviews, debugs, and tests code.
"""
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus
from tools.code_runner import run_python_code
from tools.file_manager import write_file

SYSTEM_PROMPT = """Sen uzman bir Python yazilimcisin. Temiz, PEP8 uyumlu, docstringli kod yaziyorsun.
Hatalari try/except ile yakala, type hints kullan.

DOSYA YOLU KURALLARI (HER DOSYADA UYGULA):
  from pathlib import Path
  BASE_DIR = Path(__file__).parent
  # Tum dosya erisimi BASE_DIR uzerinden olmali

📋 TEST IMPORT KURALLARI:
- Test dosyası yazmadan önce src/ klasöründe main.py veya app.py olup olmadığını kontrol et
- main.py varsa: from main import app
- app.py varsa: from app import app
- İkisi de varsa: main.py'yi tercih et
- Hiçbiri yoksa: from main import app (orchestrator oluşturacak)

Test dosyalarinda import:
  import sys
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

🧪 TEST CLIENT KURALLARI:
- FastAPI testleri için MUTLAKA fastapi.testclient.TestClient kullan
- httpx.AsyncClient KULLANMA (yeni httpx versiyonlarında hata verir)
- @pytest.mark.asyncio decorator KULLANMA (TestClient senkron çalışır)
- Örnek pattern:
  from fastapi.testclient import TestClient
  from main import app
  
  client = TestClient(app)
  
  def test_endpoint():  # async DEĞİL
      response = client.get("/")
      assert response.status_code == 200

CIKTI FORMATI — KESINLIKLE BU FORMATI KULLAN:

Once kisa bir analiz yaz, sonra her dosya icin su blogu kullan:

[FILE:dosya_adi.py]
# tum Python kodu buraya — hicbir kisaltma olmadan, eksiksiz
[/FILE]

[FILE:test_dosya_adi.py]
# test kodu buraya
[/FILE]

KURAL:
- Her [FILE:...] blogu eksiksiz ve calisir Python kodu icermeli
- Kodu asla kisaltma, asla ... veya pass birakma
- Sadece .py dosyalari
- JSON veya markdown KULLANMA — sadece [FILE:...][/FILE] bloklari

DOSYA YÖNETİMİ KURALLARI — KESİNLİKLE UYGULA:
1. Her görevi yazmaya başlamadan önce workspace'deki mevcut
   dosyaları zihninde listele. Şunları sor:
   - Bu işlevi yapan bir dosya zaten var mı?
   - Varsa yeni dosya oluşturma, mevcut dosyayı güncelle.
2. Dosya isimlendirme — tek bir kural:
   - UI için: ui.py
   - Veritabanı için: database.py
   - Ana mantık için: main.py veya core.py
   - Test için: test_{modül_adı}.py
   Asla: ui_v2.py, ui_new.py, ui_fixed.py, app_gui.py gibi isimler kullanma.
3. Bir görevde maksimum 2 dosya üret:
   - 1 kaynak dosya (src/)
   - 1 test dosyası (tests/)
   Daha fazlası yasak.
4. Eğer önceki bir ajan aynı dosyayı zaten yazdıysa,
   o dosyayı tamamen yeniden yazma.
   Sadece eksik olan fonksiyonu o dosyaya ekle.
"""


class CoderAgent(BaseAgent):
    """
    Generates, reviews, and debugs code. Writes tests for every function.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="coder",
            name="Yazılımcı Ajan",
            role="Kod Üretimi, İnceleme ve Hata Ayıklama",
            description="Her fonksiyon için testlerle birlikte temiz, verimli ve iyi belgelenmiş kod yazar.",
            capabilities=["code_generation", "debugging", "refactoring", "testing"],
            bus=bus,
        )
        self.register_tool("run_code", run_python_code)
        self.register_tool("write_file", write_file)

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
            system_prompt="Sen kıdemli bir yazılım mimarısın. Sadece geçerli JSON çıktısı ver.",
            temperature=0.3,
            max_tokens=500,
        )
        parsed = self._parse_json_response(response)

        return ThoughtProcess(
            reasoning=f"Implementation plan: {parsed.get('plan', [])}",
            plan=parsed.get("plan", [task.description]),
            tool_calls=[{"tool": "write_file"}, {"tool": "run_code"}],
            confidence=0.85,
        )

    def _extract_file_blocks(self, text: str) -> list[dict]:
        """Extract [FILE:name.py]...[/FILE] blocks from LLM response.
        This format is immune to JSON-breaking characters in Python code."""
        import re
        pattern = r'\[FILE:([^\]]+)\]\n?(.*?)\[/FILE\]'
        matches = re.findall(pattern, text, re.DOTALL)
        files = []
        for filename, content in matches:
            filename = filename.strip()
            content = content.strip()
            if content:
                files.append({"filename": filename, "content": content})
        return files

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """Generate code using marker-based format, save files to workspace."""
        context = task.context.get("research", "")
        history = self.short_term_memory.get_messages()
        project_slug = task.context.get("project_slug", "default")

        # Phase context — injected by orchestrator for phased projects
        phase_info = task.context.get("phase_info", "")
        existing_files = task.context.get("existing_files", "")

        phase_note = ""
        if phase_info:
            phase_note = f"\n\nFAZ BİLGİSİ: {phase_info}"
        elif existing_files:
            phase_note = f"\n\nMevcut dosyalar (import et, tekrar yazma): {existing_files}"

        coding_prompt = (
            f"Gorev: {task.description}"
            f"{phase_note}\n"
            f"Baglam/Arastirma: {context}\n\n"
            "Bu gorevi cozen, tam ve eksiksiz Python kodu yaz.\n"
            "Her dosya icin [FILE:dosyaadi.py] ... [/FILE] formatini kullan.\n"
            "Kodu asla kisaltma, her fonksiyon eksiksiz olmali."
        )

        messages = history + [{"role": "user", "content": coding_prompt}]

        response = await self._call_llm(
            messages=messages,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=4000,
        )

        # Primary: extract [FILE:...][/FILE] blocks (immune to JSON errors)
        file_blocks = self._extract_file_blocks(response)

        # Fallback: try JSON parsing if no blocks found
        if not file_blocks:
            parsed = self._parse_json_response(response)
            raw_files = parsed.get("files", [])
            file_blocks = [
                {"filename": f.get("filename", "output.py"),
                 "content": f.get("content", f.get("code", ""))}
                for f in raw_files if f.get("content") or f.get("code")
            ]
            # Also check legacy single-file format
            if not file_blocks and parsed.get("code"):
                file_blocks = [{
                    "filename": parsed.get("filename", "script.py"),
                    "content": parsed.get("code", "")
                }]
        else:
            parsed = {}

        saved_files = []
        run_results = []
        main_code = ""
        main_filename = "script.py"

        for file_info in file_blocks:
            filename = file_info.get("filename", "output.py")
            content = file_info.get("content", "")
            if not content.strip():
                continue

            # Route files into project directory
            if filename.startswith("test_"):
                save_path = f"projects/{project_slug}/tests/{filename}"
            else:
                save_path = f"projects/{project_slug}/src/{filename}"
                if not main_code:  # first src file is main
                    main_code = content
                    main_filename = filename

            # Save to workspace
            save_result = await self.use_tool("write_file", path=save_path, content=content)
            if save_result.success:
                saved_files.append(save_path)

            # Run non-test Python files to check for errors
            if filename.endswith(".py") and not filename.startswith("test_"):
                run_result = await self.use_tool("run_code", code=content)
                run_results.append({
                    "file": save_path,
                    "success": run_result.success,
                    "output": run_result.data.get("output", "") if run_result.data else "",
                    "errors": run_result.data.get("errors", "") if run_result.data else run_result.error,
                })

                # Auto-fix if errors
                if not run_result.success and run_result.error:
                    fixed = await self._fix_code(content, run_result.error, task.description)
                    if fixed:
                        await self.use_tool("write_file", path=save_path, content=fixed)
                        saved_files.append(f"{save_path} (fixed)")

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
                max_tokens=3000,
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
