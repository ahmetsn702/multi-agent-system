"""
MemoryAgent: Önceki projeleri indexler ve yeni görevler için ilgili
bağlamı sağlar.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

MEMORY_DB_PATH = Path("workspace/memory/project_memory.json")


class MemoryAgent:
    """Proje hafızasını yönetir."""

    def __init__(self):
        MEMORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._memory = self._load()

    # ── Kayıt ──────────────────────────────────────────
    def save_project(self, project_slug: str, goal: str, result: dict):
        """GELİŞTİRME 4: Tamamlanan projeyi hafızaya kaydet.
        
        Orchestrator run() tamamlandıktan sonra çağrılır.
        Artık patterns_used ve successful_approaches da kaydedilir.
        """
        # Proje klasöründen dosya listesi al (filtreli)
        project_root = Path("workspace/projects") / project_slug
        files = []
        allowed_suffixes = {".py", ".js", ".ts", ".json", ".md", ".txt", ".yaml"}
        excluded_dirs = {"node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build"}
        excluded_files = {".gitkeep", "output.py"}

        if project_root.exists():
            for root, dirs, filenames in os.walk(project_root):
                # Ağır klasörleri traversal'dan tamamen çıkar
                dirs[:] = [d for d in dirs if d not in excluded_dirs]

                root_path = Path(root)
                for filename in filenames:
                    if filename in excluded_files or filename.endswith(".pyc"):
                        continue
                    file_path = root_path / filename
                    if file_path.suffix.lower() not in allowed_suffixes:
                        continue
                    files.append(str(file_path.relative_to(project_root)))

        # Önemli kod parçalarını çıkar (ilk 500 karakter)
        snippets = {}
        src_dir = project_root / "src"
        if src_dir.exists():
            for py_file in list(src_dir.glob("*.py"))[:5]:
                try:
                    content = py_file.read_text(encoding="utf-8", errors="ignore")
                    snippets[py_file.name] = content[:500]
                except Exception:
                    pass

        # GELİŞTİRME 4: Kullanılan pattern'leri ve başarılı yaklaşımları çıkar
        patterns_used = self._extract_patterns(files, snippets)
        successful_approaches = self._extract_approaches(goal, result)

        tasks_completed_list = result.get("tasks_completed", [])
        errors_encountered_list = result.get("errors_encountered", [])
        tasks_c_count = len(tasks_completed_list) if isinstance(tasks_completed_list, list) else tasks_completed_list
        errors_c_count = len(errors_encountered_list) if isinstance(errors_encountered_list, list) else 0

        entry = {
            "slug": project_slug,
            "goal": goal,
            "created_at": datetime.now().isoformat(),
            "files": files,
            "snippets": snippets,
            "cost": result.get("cost_usd", 0),
            "tasks_completed": tasks_c_count,
            "tags": self._extract_tags(goal),
            "patterns_used": patterns_used,  # GELİŞTİRME 4
            "successful_approaches": successful_approaches,  # GELİŞTİRME 4
        }

        self._memory["projects"][project_slug] = entry
        self._save()
        print(f"[Memory] 💾 Proje kaydedildi: {project_slug} ({len(files)} dosya, {len(patterns_used)} pattern)")
        
        # GELİŞTİRME 6 & AKTİF ÖĞRENME: ChromaDB'ye detaylı performans/maliyet datası ekle
        try:
            from core.vector_memory import get_vector_memory
            vector_mem = get_vector_memory()
            
            if vector_mem.enabled:
                cost = float(result.get("cost_usd", 0.0))
                total_tasks = tasks_c_count + errors_c_count
                success_rate = (tasks_c_count / total_tasks) if total_tasks > 0 else 1.0

                models_used = result.get("models_used", {})

                # Summary (Active Learning Pattern)
                summary = (
                    f"Cost: ${cost:.4f} | Success Rate: {success_rate:.2f}\n"
                    f"Models Used: {models_used}\n"
                    f"File Structure Pattern: {', '.join(files[:15])}\n"
                    f"Successful Task Sequence: {', '.join(tasks_completed_list) if isinstance(tasks_completed_list, list) else '-'}\n"
                    f"Failed Tasks to Avoid: {', '.join(errors_encountered_list) if isinstance(errors_encountered_list, list) and errors_encountered_list else 'None'}\n"
                    f"Design Patterns Applied: {', '.join(patterns_used)}\n"
                    f"Successful Approaches: {successful_approaches}"
                )
                
                # Code snippets listesi
                code_list = list(snippets.values())
                
                # Metadata
                metadata = {
                    "goal": goal[:200],  # for identification
                    "tags": self._extract_tags(goal),
                    "cost": cost,
                    "success_rate": success_rate,
                    "tasks_completed": tasks_c_count,
                    "created_at": datetime.now().isoformat()
                }
                
                vector_mem.add_project(project_slug, summary, code_list, metadata)
                print(f"[Memory] 🔍 Vector DB'ye detaylı performans eklendi: {project_slug} (Rate: {success_rate:.2f})")
        except Exception as e:
            print(f"[Memory] ⚠️  Vector DB ekleme hatası: {e}")


    # ── Arama ──────────────────────────────────────────
    def search_relevant(self, goal: str, max_results: int = 3) -> list[dict]:
        """Yeni görev için ilgili önceki projeleri bul.
        
        GELİŞTİRME 6: Önce ChromaDB semantic search dene, fallback olarak keyword matching.
        """
        # Önce vector search dene
        try:
            from core.vector_memory import get_vector_memory
            vector_mem = get_vector_memory()
            
            if vector_mem.enabled and vector_mem.count() > 0:
                vector_results = vector_mem.search_similar(goal, n=max_results)
                
                if vector_results:
                    print(f"[Memory] 🔍 Vector search: {len(vector_results)} sonuç bulundu")
                    # Vector sonuçlarını format'a dönüştür
                    results = []
                    for vr in vector_results:
                        slug = vr['slug']
                        if slug in self._memory["projects"]:
                            project = self._memory["projects"][slug]
                            results.append({
                                "slug": slug,
                                "goal": project["goal"],
                                "files": project["files"][:10],
                                "snippets": project.get("snippets", {}),
                                "relevance": vr.get("score", vr['similarity']),
                                "summary": vr.get("summary", ""),
                                "tags": project.get("tags", []),
                                "created_at": project["created_at"],
                                "search_method": "vector"
                            })
                    return results
        except Exception as e:
            print(f"[Memory] ⚠️  Vector search failed, falling back to keyword: {e}")
        
        # Fallback: Keyword matching (mevcut kod)
        print(f"[Memory] 🔍 Keyword search kullanılıyor")
        goal_tags = set(self._extract_tags(goal))
        goal_terms = self._extract_search_terms(goal)
        results = []

        for slug, project in self._memory["projects"].items():
            project_tags = set(project.get("tags", []))
            overlap = goal_tags & project_tags
            project_text = " ".join([
                slug,
                project.get("goal", ""),
                " ".join(project.get("files", [])),
                " ".join(project.get("tags", [])),
                " ".join(project.get("patterns_used", [])),
                " ".join(project.get("snippets", {}).values()),
            ]).lower()
            keyword_hits = sum(1 for term in goal_terms if term in project_text)
            relevance = len(overlap) * 10 + keyword_hits

            if overlap or keyword_hits:
                results.append({
                    "slug": slug,
                    "goal": project["goal"],
                    "files": project["files"][:5],
                    "snippets": project.get("snippets", {}),
                    "relevance": relevance,
                    "tags": list(project_tags),
                    "created_at": project["created_at"],
                    "search_method": "keyword"
                })

        # Relevance'a göre sırala
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:max_results]

    def query(self, topic: str) -> Optional[dict]:
        """GELİŞTİRME 4: Belirli bir konu hakkında hafızada arama yap.
        
        Researcher agent'ın web aramasından önce kullanması için.
        Basit keyword matching ile en ilgili projeyi döner.
        
        Args:
            topic: Aranacak konu (örn: "Flask JWT authentication")
            
        Returns:
            İlgili proje bulunursa dict, yoksa None
        """
        results = self.search_relevant(topic, max_results=1)
        if results:
            best_match = results[0]
            print(f"[Memory] ✓ İlgili proje bulundu: {best_match['slug']} (relevance: {best_match['relevance']})")
            return best_match
        print(f"[Memory] ✗ '{topic}' için ilgili proje bulunamadı")
        return None

    def format_context(self, goal: str) -> str:
        """Planner için ilgili proje bağlamını formatla."""
        relevant = self.search_relevant(goal)
        if not relevant:
            return ""

        lines = [
            "🧠 [AKTİF ÖĞRENME BAĞLAMI]",
            "Planner Ajanı Dikkatine: Aşağıdaki geçmiş projeler benzer hedeflere sahipti.",
            "Lütfen BAŞARILI olan görev sıralarını, dosya yapılarını ve yaklaşımları örnek al. Düşük maliyetli/yüksek başarılı yolları tercih et.",
            "Ayrıca BAŞARISIZ olan (Failed Tasks to Avoid) görev türlerinden/hatalarından KAÇIN.",
            "==========================================================="
        ]
        
        for r in relevant:
            summary = r.get("summary", "")
            if "Successful Task Sequence" in summary:
                lines.append(f"📌 Önceki Proje Hedefi: {r['goal']}")
                lines.append(f"   Alaka/Başarı Skoru: {r.get('relevance', 0)}")
                lines.append(summary)
            else:
                lines.append(f"📌 Önceki Proje Hedefi: {r['goal']} ({r['created_at'][:10]})")
                lines.append(f"   Dosya Yapısı: {', '.join(r['files'][:5])}")
                if r.get("snippets"):
                    first_file = next(iter(r["snippets"]))
                    snippet = r["snippets"][first_file][:150]
                    lines.append(f"   Örnek Kod ({first_file}):\n    {snippet.replace(chr(10), chr(10)+'    ')}")
            lines.append("-" * 40)

        return "\n".join(lines)

    def list_all(self) -> list[dict]:
        """Tüm kayıtlı projeleri listele."""
        projects = list(self._memory["projects"].values())
        projects.sort(key=lambda x: x["created_at"], reverse=True)
        return projects

    # ── Yardımcı ───────────────────────────────────────
    def _extract_tags(self, text: str) -> list[str]:
        """Metinden anahtar kelimeler çıkar."""
        text_lower = text.lower()
        tag_keywords = {
            "flask": ["flask", "web", "route", "endpoint"],
            "fastapi": ["fastapi", "async", "pydantic"],
            "sqlite": ["sqlite", "veritabanı", "database", "db"],
            "postgresql": ["postgresql", "postgres", "pg"],
            "jwt": ["jwt", "token", "auth", "doğrulama"],
            "cli": ["cli", "komut", "argparse", "terminal"],
            "telegram": ["telegram", "bot", "mesaj"],
            "test": ["test", "pytest", "unittest"],
            "docker": ["docker", "container", "deploy"],
            "api": ["api", "rest", "endpoint", "route"],
            "react": ["react", "frontend", "component"],
            "python": ["python", "py"],
            "hesap": ["hesap", "calculator", "matematik"],
            "todo": ["todo", "görev", "task"],
            "kullanici": ["kullanıcı", "user", "login", "register"],
            "space": ["uzay", "uydu", "satellite", "orbit", "yörünge", "tle", "sgp4", "iss", "debris", "celestrak", "eci", "lla"],
            "sentinel2": ["sentinel-2", "sentinel2", "copernicus", "cdse", "ndvi", "rasterio", "b04", "b08", "l2a", "jp2"],
            "plotly": ["plotly", "scatter3d", "surface", "3d", "html görselleştirme"],
        }

        tags = []
        for tag, keywords in tag_keywords.items():
            if any(kw in text_lower for kw in keywords):
                tags.append(tag)
        return tags

    def _extract_search_terms(self, text: str) -> set[str]:
        """Fallback aramada kullanilacak serbest anahtar kelimeleri cikar."""
        normalized = text.lower()
        for char in "-_/(),.:;[]{}":
            normalized = normalized.replace(char, " ")

        stopwords = {
            "ve", "ile", "icin", "gibi", "olan", "bir", "bu", "su",
            "the", "and", "for", "from", "into", "task", "gorev",
        }
        return {
            token for token in normalized.split()
            if len(token) >= 3 and token not in stopwords
        }

    def _extract_patterns(self, files: list[str], snippets: dict) -> list[str]:
        """GELİŞTİRME 4: Projede kullanılan design pattern'leri ve teknolojileri çıkar."""
        patterns = []
        
        # Dosya yapısından pattern'leri çıkar
        file_str = " ".join(files).lower()
        if "blueprint" in file_str or any("routes" in f for f in files):
            patterns.append("Flask Blueprint Pattern")
        if "model" in file_str and "view" in file_str:
            patterns.append("MVC Architecture")
        if any("test_" in f for f in files):
            patterns.append("Unit Testing")
        if "requirements.txt" in files:
            patterns.append("Dependency Management")
        if "dockerfile" in file_str:
            patterns.append("Docker Containerization")
            
        # Kod snippet'lerinden pattern'leri çıkar
        all_code = " ".join(snippets.values()).lower()
        if "sqlalchemy" in all_code:
            patterns.append("SQLAlchemy ORM")
        if "jwt" in all_code or "jsonwebtoken" in all_code:
            patterns.append("JWT Authentication")
        if "argparse" in all_code:
            patterns.append("CLI with argparse")
        if "async def" in all_code:
            patterns.append("Async/Await Pattern")
        if "class" in all_code and "def __init__" in all_code:
            patterns.append("Object-Oriented Design")
            
        return list(set(patterns))  # Tekrarları kaldır

    def _extract_approaches(self, goal: str, result: dict) -> str:
        """GELİŞTİRME 4: Başarılı yaklaşımları özetle."""
        approaches = []
        
        # Görevden yaklaşımları çıkar
        if "rest" in goal.lower() or "api" in goal.lower():
            approaches.append("RESTful API design kullanıldı")
        if "jwt" in goal.lower() or "auth" in goal.lower():
            approaches.append("Token-based authentication uygulandı")
        if "sqlite" in goal.lower() or "database" in goal.lower():
            approaches.append("Veritabanı entegrasyonu yapıldı")
            
        # Sonuçtan başarı metriklerini ekle
        tasks_completed_list = result.get("tasks_completed", [])
        tasks_completed = len(tasks_completed_list) if isinstance(tasks_completed_list, list) else tasks_completed_list
        if tasks_completed > 0:
            approaches.append(f"{tasks_completed} görev başarıyla tamamlandı")
            
        avg_score = result.get("avg_critic_score", 0)
        if avg_score >= 7:
            approaches.append(f"Yüksek kod kalitesi (Critic skoru: {avg_score:.1f}/10)")
            
        return "; ".join(approaches) if approaches else "Standart yaklaşım kullanıldı"


    def _load(self) -> dict:
        if MEMORY_DB_PATH.exists():
            try:
                return json.loads(MEMORY_DB_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"projects": {}, "version": "1.0"}

    def _save(self):
        MEMORY_DB_PATH.write_text(
            json.dumps(self._memory, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# Singleton
_memory_agent: Optional[MemoryAgent] = None


def get_memory_agent() -> MemoryAgent:
    global _memory_agent
    if _memory_agent is None:
        _memory_agent = MemoryAgent()
    return _memory_agent
