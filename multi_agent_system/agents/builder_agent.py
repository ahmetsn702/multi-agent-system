"""
agents/builder_agent.py
Flet (veya diger bazi arayuz) projelerinde derleme islemlerini yurutur.
"""

import sys
import subprocess
from pathlib import Path
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus


class BuilderAgent(BaseAgent):
    """
    Proje kodlarini (or. Flet) APK veya calisabilir dosya olarak derler.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="builder",
            name="Derleyici Ajan",
            role="Proje Derleme Operatörü",
            description="Flet projelerini APK gibi formatlara derler.",
            capabilities=["apk_build", "shell_execution"],
            bus=bus,
        )

    async def think(self, task: Task) -> ThoughtProcess:
        return ThoughtProcess(
            reasoning="Derleme işlemi başlıyor.",
            plan=["Paket kontrolü", "Derleme komutunu çalıştır", "Çıktıyı raporla"],
            tool_calls=[],
            confidence=0.9,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        project_dir = task.context.get("project_dir", "")
        if not project_dir:
            return AgentResponse(content={"result": "Proje dizini bulunamadı."}, success=False)

        slug = task.context.get("project_slug", "default")
        # Ensure project dir matches standard workspace
        actual_project_dir = Path("workspace") / "projects" / slug
        src_dir = actual_project_dir / "src"

        if not src_dir.exists():
            return AgentResponse(content={"result": "src/ dizini bulunamadı."}, success=False)

        print("[BuilderAgent] 📦 Flet paketi kontrol ediliyor...")
        try:
            # pip install flet
            subprocess.run([sys.executable, "-m", "pip", "install", "flet", "-q"], check=True)
            
            print(f"[BuilderAgent] 🚀 Flet build apk başlatılıyor: orijinal cwd={actual_project_dir}")
            
            # Flet gradle.properties ASCII Path Fix -> Klasörü kopyalayarak çöz
            import shutil
            ascii_build_dir = Path(r"C:\flet_build") / slug
            
            # Varsa temizle
            if ascii_build_dir.exists():
                try:
                    shutil.rmtree(ascii_build_dir)
                except Exception as e:
                    print(f"[BuilderAgent] ⚠️ Eski ASCII geçici dizin silinirken hata: {e}")
            
            print(f"[BuilderAgent] 📂 Proje ASCII dizinine kopyalanıyor: {ascii_build_dir}")
            try:
                # Sadece src/ dizini ve gereksinimleri kopyalasak bile flet build apk src istiyor
                # Tüm projeyi kopyalamak daha güvenli (assets vb için)
                # Kopyalarken .git gibi klasörler erişim hatası / kilitlenmelere sebep olabilir
                shutil.copytree(actual_project_dir, ascii_build_dir, ignore=shutil.ignore_patterns('.git'))
            except Exception as e:
                return AgentResponse(content={"result": f"ASCII kopyalama hatası: {str(e)}"}, success=False)

            # flet build apk
            import os
            def _run_build():
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                env["PYTHONLEGACYWINDOWSSTDIO"] = "0"
                
                process = subprocess.Popen(
                    [
                        "flet", "build", "apk", "src",
                        "--no-rich-output", "--yes"
                    ],
                    cwd=ascii_build_dir,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
                
                output_lines = []
                for line in process.stdout:
                    print(f"[BuilderAgent] {line}", end="")
                    output_lines.append(line)
                    
                process.wait()
                
                if process.returncode != 0:
                    raise RuntimeError(f"APK build hatası (Return code: {process.returncode})")
                    
                class BuildResult:
                    def __init__(self, stdout):
                        self.stdout = stdout
                return BuildResult("".join(output_lines))
                
            try:
                result = _run_build()
            except FileNotFoundError:
                print("[BuilderAgent] ⚠️ 'flet' komutu bulunamadı. Yeniden yüklenip deneniyor...")
                subprocess.run([sys.executable, "-m", "pip", "install", "flet", "--force-reinstall", "-q"], check=True)
                result = _run_build()
                
            # Derleme tamamlandı, APK'yı al
            apk_source_path = None
            
            # ascii_build_dir altında tüm alt dizinlerde *.apk ara
            found_apks = list(ascii_build_dir.rglob("*.apk"))
            if found_apks:
                apk_source_path = found_apks[0]
                
            apk_dest_dir = actual_project_dir / "build" / "apk"
            apk_dest_dir.mkdir(parents=True, exist_ok=True)
            
            if apk_source_path:
                dest_file = apk_dest_dir / apk_source_path.name
                print(f"[BuilderAgent] 📦 APK dosyası taşınıyor: {apk_source_path} -> {dest_file}")
                shutil.copy2(apk_source_path, dest_file)
                print(f"[BuilderAgent] ✅ APK kopyalandı: {dest_file}")
            else:
                print("[BuilderAgent] ⚠️ Derleme tamamlandı ancak APK dosyası ASCII dizininde bulunamadı!")

            # Temizlik
            print(f"[BuilderAgent] 🧹 Geçici ASCII dizini siliniyor...")
            try:
                shutil.rmtree(ascii_build_dir)
            except Exception as e:
                print(f"[BuilderAgent] ⚠️ İzler silinirken hata (elle silebilirsiniz): {e}")
            
            print("[BuilderAgent] ✅ APK build başarılı.")
            return AgentResponse(
                content={"result": "APK build başarılı", "stdout": result.stdout},
                success=True
            )
        except Exception as e:
            return AgentResponse(content={"result": f"Exception: {str(e)}"}, success=False)
