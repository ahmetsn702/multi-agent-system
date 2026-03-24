"""
tools/docker_runner.py
DockerRunner: Kodu Docker container'da izole calistirir.
Docker kurulu degilse normal subprocess'e fallback yapar.
"""
import subprocess
from pathlib import Path


def is_docker_available() -> bool:
    """Docker'in sistemde kurulu ve calisip calismadigini kontrol et."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def run_in_docker(code: str, project_path: str, timeout: int = 60) -> dict:
    """
    Python kodunu Docker container'da calistir.
    Container: python:3.11-slim
    Mount: project_path -> /workspace

    Args:
        code: Calistirilacak Python kodu
        project_path: Mount edilecek proje klasoru
        timeout: Maksimum bekleme suresi (saniye)

    Returns:
        Calistirma sonucu dict'i
    """
    if not is_docker_available():
        # Fallback: normal subprocess
        print("[Docker] Docker bulunamadi, normal subprocess kullaniliyor")
        try:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "mode": "subprocess",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timeout ({timeout}s)", "mode": "subprocess"}
        except Exception as e:
            return {"success": False, "error": str(e), "mode": "subprocess"}

    project_path = str(Path(project_path).resolve())
    cmd = [
        "docker", "run",
        "--rm",                         # Bitince container'i sil
        "--network", "none",            # Internet erisimi yok
        "--memory", "256m",             # Max 256MB RAM
        "--cpus", "0.5",                # Max 0.5 CPU
        "-v", f"{project_path}:/workspace",
        "-w", "/workspace",
        "python:3.11-slim",
        "python", "-c", code,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout + 10,
        )
        mode = "docker"
        print(f"[Docker] docker modunda calistirildi")
        return {
            "success": result.returncode == 0,
            "output": result.stdout[:3000],
            "error": result.stderr[:1000],
            "mode": mode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Docker timeout", "mode": "docker"}
    except Exception as e:
        return {"success": False, "error": str(e), "mode": "docker"}
