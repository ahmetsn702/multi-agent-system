"""
tools/interactive_shell.py
Stateful, persistent shell session — Devin AI tarzı interaktif terminal.

Özellikler:
- cwd (current working directory) korunur
- env değişkenleri korunur
- Her komutu gerçek subprocess ile çalıştırır
- Timeout, güvenlik filtresi, output limit
"""
import os
import locale
import subprocess
import sys
from pathlib import Path
from typing import Optional

BANNED_PATTERNS = [
    # Yıkıcı Dosya İşlemleri
    "rm -rf /", "rm -r /", "del /f /s /q c:\\", "rd /s /q c:\\", "rmdir /s /q c:\\",
    
    # Format ve Çökertme Komutları
    "format c:", "mkfs", "dd if=/dev/zero", "cat /dev/zero",
    "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
    
    # Fork Bomb ve Aşırı Kaynak Tüketimi
    ":(){:|:&};:", 
    
    # Reverse Shell & Açık Port (Network) Zafiyetleri
    "nc -e", "netcat -e", "/dev/tcp", "bash -i", "/bin/sh -i", 
    
    # Yetki Yükseltme ve Zararlı Paylaşım
    "chmod -R 777 /", "chown -R",
    
    # Dosya gizleme ve kritik sistem dosyalarına müdahale
    "attrib +h", "icacls", "takeown",
    "> /etc/passwd", "> /etc/shadow"
]


class InteractiveShell:
    """
    Kalıcı çalışma dizini ve ortam değişkenleriyle stateful terminal session.
    Devin AI'nın terminal kullanımına benzer şekilde çalışır.
    """

    def __init__(self, project_dir: str, project_slug: str = "default"):
        self.project_dir = Path(project_dir).resolve()
        self.project_slug = project_slug
        self.cwd = self.project_dir
        self.env = os.environ.copy()

        # PYTHONPATH'e proje src/ dizinini ekle
        src_path = str(self.project_dir / "src")
        root_path = str(self.project_dir)
        cwd_path = str(Path.cwd())
        existing = self.env.get("PYTHONPATH", "")
        
        paths = [src_path, root_path, cwd_path]
        if existing:
            paths.append(existing)
        self.env["PYTHONPATH"] = os.pathsep.join(paths)
        self.env["PYTHONIOENCODING"] = "utf-8"
        self.env["PYTHONUTF8"] = "1"

        # Komut geçmişi (model context için)
        self.history: list[dict] = []

    def _decode_output(self, output: bytes) -> str:
        """Komut çıktısını Windows kod sayfalarıyla uyumlu şekilde decode et."""
        if not output:
            return ""

        encodings = [
            "utf-8",
            locale.getpreferredencoding(False),
            "cp1254",
            "cp850",
        ]
        tried: set[str] = set()
        for encoding in encodings:
            normalized = str(encoding or "").strip()
            if not normalized or normalized.lower() in tried:
                continue
            tried.add(normalized.lower())
            try:
                return output.decode(normalized)
            except UnicodeDecodeError:
                continue

        return output.decode("utf-8", errors="replace")

    def _is_safe(self, command: str) -> tuple[bool, str]:
        """Güvenlik kontrolü — tehlikeli komutları engelle."""
        cmd_lower = command.lower().strip()
        for pattern in BANNED_PATTERNS:
            if pattern in cmd_lower:
                return False, f"GÜVENLİK: Tehlikeli komut engellendi: '{pattern}'"
        return True, ""

    def run(self, command: str, timeout: int = 30) -> dict:
        """
        Komutu mevcut cwd'de çalıştır.
        
        Args:
            command: Shell command to execute
            timeout: Maximum execution time in seconds (default: 30s)
        
        Returns:
            dict: {success, stdout, stderr, return_code, cwd}
        """
        safe, reason = self._is_safe(command)
        if not safe:
            result = {"success": False, "stdout": "", "stderr": reason,
                      "return_code": -1, "cwd": str(self.cwd)}
            self.history.append({"cmd": command, **result})
            return result

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout,
                cwd=str(self.cwd),
                env=self.env,
            )
            
            stdout = self._decode_output(proc.stdout)[:4000]  # Max 4000 karakter
            stderr = self._decode_output(proc.stderr)[:2000]

            # cd komutunu yakala ve cwd'yi güncelle
            if command.strip().startswith("cd ") and proc.returncode == 0:
                new_dir = command.strip()[3:].strip().strip('"').strip("'")
                candidate = (self.cwd / new_dir).resolve()
                if candidate.exists():
                    self.cwd = candidate

            result = {
                "success": proc.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "return_code": proc.returncode,
                "cwd": str(self.cwd),
            }
        except subprocess.TimeoutExpired:
            result = {
                "success": False,
                "stdout": "",
                "stderr": f"TIMEOUT: Komut {timeout}s içinde tamamlanamadı.",
                "return_code": -1,
                "cwd": str(self.cwd),
            }
        except Exception as e:
            result = {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "cwd": str(self.cwd),
            }

        self.history.append({"cmd": command, **result})
        return result

    def read_file(self, path: str) -> dict:
        """Dosya içeriğini oku."""
        try:
            target = (self.cwd / path).resolve()
            # Güvenlik: proje dışına çıkma
            if not str(target).startswith(str(Path("workspace").resolve())):
                # Proje dizini içinde mi kontrol et
                if not str(target).startswith(str(self.project_dir)):
                    return {"success": False, "content": "", 
                            "error": f"Güvenlik: {path} proje dışında"}
            content = target.read_text(encoding="utf-8", errors="replace")
            return {"success": True, "content": content[:8000], "path": str(target)}
        except Exception as e:
            return {"success": False, "content": "", "error": str(e)}

    def write_file(self, path: str, content: str) -> dict:
        """Dosyaya içerik yaz."""
        try:
            target = (self.cwd / path).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(target), 
                    "lines": len(content.splitlines())}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_dir(self, path: str = ".") -> dict:
        """Dizin içeriğini listele."""
        try:
            target = (self.cwd / path).resolve()
            entries = []
            for item in sorted(target.iterdir()):
                entries.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                })
            return {"success": True, "path": str(target), "entries": entries}
        except Exception as e:
            return {"success": False, "entries": [], "error": str(e)}

    def format_history(self, last_n: int = 10) -> str:
        """Son N komutu ve çıktılarını model için formatla."""
        lines = []
        for entry in self.history[-last_n:]:
            lines.append(f"$ {entry['cmd']}")
            if entry.get("stdout"):
                lines.append(entry["stdout"].rstrip())
            if entry.get("stderr") and not entry.get("success"):
                lines.append(f"[STDERR] {entry['stderr'].rstrip()}")
            lines.append(f"[exit: {entry.get('return_code', '?')}]")
            lines.append("")
        return "\n".join(lines)
