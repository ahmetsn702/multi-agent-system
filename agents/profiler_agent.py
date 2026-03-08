"""
agents/profiler_agent.py
ProfilerAgent: Scans all project sessions and outputs, builds a
detailed user profile and saves it to user_profile.txt.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus

WORKSPACE_DIR = Path(__file__).parent.parent / "workspace"
PROFILE_PATH = Path(__file__).parent.parent / "user_profile.txt"

SYSTEM_PROMPT = """Sen bir kullanıcı analisti ve profil uzmanısın.
Sana çeşitli oturum logları, proje verileri ve kullanıcı hedefleri verilecek.
Bu verileri analiz edip kullanıcının:
  - İlgi alanlarını ve proje tercihlerini
  - Teknik seviyesini (başlangıç / orta / ileri)
  - Favori programlama dillerini ve araçlarını
  - Çalışma alışkanlıklarını (kısa hedef mi yazar, detaylı mı?)
  - Güçlü ve geliştirmesi gereken alanlarını
  - Gelecek proje önerilerini
çıkarmanı istiyorum.

KURALLAR:
1. Her bölüm net başlık ve madde işareti ile olmalı.
2. Spekülasyon yapma, sadece veride gördüklerini yaz.
3. Kullanıcıya hitap et — "Ahmet" veya "Kullanıcı" diye.
4. Türkçe yaz.

ÇIKTI — YALNIZCA BU JSON:
{
  "name": "Ahmet",
  "technical_level": "orta / ileri",
  "interests": ["konu1", "konu2"],
  "preferred_languages": ["Python"],
  "preferred_tools": ["tool1"],
  "project_patterns": "kısa açıklamayla nasıl çalıştığı",
  "strengths": ["güçlü alan 1"],
  "growth_areas": ["gelişim alanı 1"],
  "project_history": [{"name": "proje", "complexity": "yüksek", "date": "tarih"}],
  "recommendations": ["öneri 1", "öneri 2"],
  "summary": "2-3 cümlelik genel değerlendirme"
}"""


class ProfilerAgent(BaseAgent):
    """
    Reads all workspace sessions and project outputs,
    builds a user profile, and saves it to user_profile.txt.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="profiler",
            name="Profil Analisti",
            role="Kullanıcı Profili Çıkarma",
            description="Tüm oturum ve proje verilerini analiz ederek kullanıcı profilini txt olarak kaydeder.",
            capabilities=["user_profiling", "data_analysis", "pattern_recognition"],
            bus=bus,
        )

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    def _collect_session_data(self) -> list[dict]:
        """Read all session JSON files from workspace/projects/."""
        sessions = []
        if not WORKSPACE_DIR.exists():
            return sessions

        for project_dir in WORKSPACE_DIR.glob("projects/*/"):
            # Read plan.json if exists
            plan_file = project_dir / "plan.json"
            if plan_file.exists():
                try:
                    sessions.append({
                        "project": project_dir.name,
                        "type": "plan",
                        "data": json.loads(plan_file.read_text(encoding="utf-8", errors="ignore"))
                    })
                except Exception:
                    pass

            # Read session_*.json files
            for session_file in project_dir.glob("session_*.json"):
                try:
                    sessions.append({
                        "project": project_dir.name,
                        "type": "session",
                        "data": json.loads(session_file.read_text(encoding="utf-8", errors="ignore"))
                    })
                except Exception:
                    pass

            # Collect src file names (coding patterns)
            src_files = list((project_dir / "src").glob("*.py")) if (project_dir / "src").exists() else []
            test_files = list((project_dir / "tests").glob("*.py")) if (project_dir / "tests").exists() else []
            if src_files or test_files:
                sessions.append({
                    "project": project_dir.name,
                    "type": "files",
                    "data": {
                        "src": [f.name for f in src_files],
                        "tests": [f.name for f in test_files],
                    }
                })

        return sessions

    def _build_context_text(self, sessions: list[dict]) -> str:
        """Convert session data into a concise text for the LLM."""
        lines = []
        seen_projects = set()

        for s in sessions:
            proj = s.get("project", "unknown")
            if proj not in seen_projects:
                seen_projects.add(proj)
                lines.append(f"\n=== Proje: {proj} ===")

            if s["type"] == "plan":
                goal = s["data"].get("goal", s["data"].get("user_goal", ""))
                if goal:
                    lines.append(f"  Hedef: {goal}")
                tasks = s["data"].get("tasks", [])
                if tasks:
                    lines.append(f"  Görev sayisi: {len(tasks)}")

            elif s["type"] == "session":
                data = s["data"]
                cost = data.get("cost_usd") or data.get("total_cost", "")
                tokens = data.get("total_tokens", "")
                iterations = data.get("iterations", data.get("iteration_count", ""))
                if cost:
                    lines.append(f"  Maliyet: ${cost}")
                if tokens:
                    lines.append(f"  Token: {tokens}")
                if iterations:
                    lines.append(f"  Iterasyon: {iterations}")

            elif s["type"] == "files":
                src = s["data"].get("src", [])
                tests = s["data"].get("tests", [])
                if src:
                    lines.append(f"  Kaynak dosyalar: {', '.join(src)}")
                if tests:
                    lines.append(f"  Test dosyaları: {', '.join(tests)}")

        if not lines:
            lines.append("Henüz kaydedilmiş proje verisi bulunamadı.")

        return "\n".join(lines)

    def _format_profile_txt(self, parsed: dict) -> str:
        """Convert parsed JSON profile to a readable TXT."""
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        lines = [
            "=" * 72,
            "       KULLANICI PROFİLİ — Multi-Agent Sistemi",
            f"       Oluşturulma: {now}",
            "=" * 72,
            "",
            f"  İsim          : {parsed.get('name', 'Ahmet')}",
            f"  Teknik Seviye : {parsed.get('technical_level', '-')}",
            "",
        ]

        def section(title, items):
            lines.append(f"{'─'*60}")
            lines.append(f"  {title}")
            lines.append(f"{'─'*60}")
            if isinstance(items, list):
                for item in items:
                    lines.append(f"    • {item}")
            else:
                lines.append(f"    {items}")
            lines.append("")

        section("İLGİ ALANLARI", parsed.get("interests", []))
        section("TERCİH EDİLEN DİLLER & ARAÇLAR",
                parsed.get("preferred_languages", []) + parsed.get("preferred_tools", []))
        section("ÇALIŞMA TARZI", parsed.get("project_patterns", "-"))
        section("GÜÇLÜ ALANLAR", parsed.get("strengths", []))
        section("GELİŞİM ALANLARI", parsed.get("growth_areas", []))

        # Project history table
        history = parsed.get("project_history", [])
        if history:
            lines.append("─" * 60)
            lines.append("  PROJE GEÇMİŞİ")
            lines.append("─" * 60)
            lines.append(f"  {'Proje':<35} {'Karmaşıklık':<12} {'Tarih'}")
            lines.append(f"  {'─'*33} {'─'*10} {'─'*10}")
            for p in history:
                name = p.get("name", "?")[:33]
                comp = p.get("complexity", "?")[:10]
                date = p.get("date", "?")[:10]
                lines.append(f"  {name:<35} {comp:<12} {date}")
            lines.append("")

        section("GELECEKTEKİ ÖNERİLER", parsed.get("recommendations", []))

        lines.append("─" * 60)
        lines.append("  GENEL DEĞERLENDİRME")
        lines.append("─" * 60)
        lines.append(f"  {parsed.get('summary', '-')}")
        lines.append("")
        lines.append("=" * 72)
        lines.append(f"  Dosya yolu: {PROFILE_PATH}")
        lines.append("=" * 72)

        return "\n".join(lines)

    # ──────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────

    async def think(self, task: Task) -> ThoughtProcess:
        sessions = self._collect_session_data()
        return ThoughtProcess(
            reasoning=f"{len(sessions)} veri noktası bulundu, profil analizi yapılacak.",
            plan=["Oturum verilerini topla", "LLM ile analiz et", "TXT dosyasına kaydet"],
            tool_calls=[],
            confidence=0.95,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """Collect data, analyze with LLM, write user_profile.txt."""
        sessions = self._collect_session_data()
        context_text = self._build_context_text(sessions)

        prompt = (
            "Aşağıdaki multi-agent sistem oturum verileri bir kullanıcıya ait.\n"
            "Bu verileri analiz ederek kullanıcının profilini çıkar.\n\n"
            f"VERİ:\n{context_text}\n\n"
            "Kullanıcı adı büyük ihtimalle Ahmet. "
            "Proje isimlerinden ve hedeflerinden ilgi alanlarını, "
            "teknik seviyesini ve çalışma tercihlerini çıkar."
        )

        response = await self._call_llm(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            temperature=0.4,
            max_tokens=1500,
        )

        parsed = self._parse_json_response(response)

        # Enrich project history from actual workspace data
        if not parsed.get("project_history"):
            parsed["project_history"] = [
                {"name": s["project"], "complexity": "orta", "date": "2026"}
                for s in sessions if s["type"] == "plan"
            ]

        profile_txt = self._format_profile_txt(parsed)

        # Save to disk
        PROFILE_PATH.write_text(profile_txt, encoding="utf-8")

        return AgentResponse(
            content={
                "profile": parsed,
                "profile_txt": profile_txt,
                "saved_to": str(PROFILE_PATH),
                "sessions_analyzed": len(sessions),
            },
            success=True,
            metadata={"profile_path": str(PROFILE_PATH)},
        )

    # ──────────────────────────────────────────────
    # Convenience: run directly without a task
    # ──────────────────────────────────────────────

    async def generate_profile(self) -> str:
        """Call this directly to generate and save the user profile."""
        from core.base_agent import Task
        task = Task(
            task_id="profiler_run",
            description="Kullanıcı profilini analiz et ve kaydet",
            assigned_to="profiler",
        )
        response = await self.run(task)
        if response.success:
            return response.content.get("saved_to", "")
        return ""
