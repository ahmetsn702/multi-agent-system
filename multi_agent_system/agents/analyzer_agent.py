"""
agents/analyzer_agent.py
AnalyzerAgent: Mevcut kod tabanını okur, bug tespit eder,
fix planı çıkarır. Yeni kod yazmaz.
"""
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus
from tools.code_analyzer import analyze_from_source


SYSTEM_PROMPT = """Sen kıdemli bir yazılım mühendisisin. Mevcut kod tabanlarını inceler,
sorunları tespit eder ve düzeltme planı oluşturursun.

GÖREVIN:
1. Verilen proje analizini dikkatle incele
2. Projenin ne yapmak istediğini anla
3. Bug'ları, eksiklikleri ve güvenlik sorunlarını listele
4. Somut bir fix planı oluştur

ÇIKTI — YALNIZCA BU JSON FORMATI:
{
  "project_purpose": "Bu projenin amacı nedir (1-2 cümle)",
  "tech_stack": ["kullanılan teknolojiler"],
  "bugs_found": [
    {
      "severity": "critical|high|medium|low",
      "file": "dosya.py",
      "line": 42,
      "description": "Bug açıklaması",
      "fix": "Nasıl düzeltilir"
    }
  ],
  "missing_features": ["eksik özellik 1", "eksik özellik 2"],
  "security_issues": ["güvenlik sorunu 1"],
  "fix_plan": [
    {
      "priority": 1,
      "task": "Yapılacak iş",
      "assigned_to": "coder",
      "reason": "Neden önemli"
    }
  ],
  "summary": "Genel değerlendirme (2-3 cümle)"
}"""


class AnalyzerAgent(BaseAgent):
    """
    Mevcut projeleri analiz eden ajan.
    Klasör, ZIP veya GitHub URL'inden proje okur,
    LLM ile derinlemesine inceler ve fix planı üretir.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="analyzer",
            name="Kod Analiz Ajanı",
            role="Tersine Mühendislik ve Bug Tespiti",
            description=(
                "Mevcut kod tabanını okur, bağımlılıkları haritalar, "
                "bug'ları tespit eder ve düzeltme planı üretir."
            ),
            capabilities=[
                "reverse_engineering",
                "bug_detection",
                "dependency_mapping",
                "security_audit",
                "fix_planning",
            ],
            bus=bus,
        )

    async def think(self, task: Task) -> ThoughtProcess:
        """Analiz stratejisini planla."""
        source = task.context.get("source", task.description)
        return ThoughtProcess(
            reasoning=f"Kaynak analiz edilecek: {source}",
            plan=[
                "Projeyi tara ve dosya yapısını çıkar",
                "Python dosyalarını AST ile parse et",
                "Şüpheli kalıpları tespit et",
                "LLM ile genel değerlendirme yap",
                "Fix planı oluştur",
            ],
            tool_calls=[{"tool": "analyze_from_source"}],
            confidence=0.9,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """
        Projeyi analiz et ve bug/fix raporu üret.

        Args:
            thought: think() çıktısı
            task: Görev (context["source"] analiz kaynağı)

        Returns:
            AgentResponse: analysis, bugs_found, fix_plan, summary içerir
        """
        source = task.context.get("source", task.description)

        # 1. Projeyi tara
        print(f"[AnalyzerAgent] 🔍 Analiz başlıyor: {source}")
        analysis = analyze_from_source(source)

        if "error" in analysis:
            return AgentResponse(
                content=None,
                success=False,
                error=analysis["error"],
            )

        stats = analysis.get("stats", {})
        print(
            f"[AnalyzerAgent] 📊 {stats.get('file_count', 0)} dosya, "
            f"{stats.get('total_lines', 0)} satır, "
            f"{stats.get('issue_count', 0)} potansiyel sorun"
        )

        # 2. LLM için bağlam oluştur (token limitine dikkat)
        issues_text = ""
        if analysis.get("issues"):
            issues_sample = analysis["issues"][:20]
            issues_text = "\n".join(
                f"  - [{i['description']}] {i['file']}:{i['line']} → {i['code']}"
                for i in issues_sample
            )

        syntax_errors_text = ""
        if analysis.get("syntax_errors"):
            syntax_errors_text = (
                "\nSYNTAX HATALARI:\n" +
                "\n".join(f"  - {f}" for f in analysis["syntax_errors"])
            )

        # Dosya haritası (kısa özet)
        file_map_text = ""
        for rel, info in list(analysis.get("file_map", {}).items())[:15]:
            if "functions" in info:
                fns = ", ".join(info["functions"][:5])
                file_map_text += f"  {rel}: {len(info['functions'])} fn [{fns}]\n"

        context_prompt = (
            f"PROJE: {analysis['project_name']}\n"
            f"ÖZET: {analysis['summary']}\n\n"
            f"DOSYA YAPISI:\n{analysis['structure'][:800]}\n\n"
            f"DOSYA HARİTASI:\n{file_map_text}\n"
            f"{syntax_errors_text}\n"
            f"ŞÜPHELİ KODLAR ({len(analysis.get('issues', []))} adet):\n"
            f"{issues_text}\n\n"
            f"Kullanıcı isteği: {task.description}"
        )

        # 3. LLM analizi
        llm_response = await self._call_llm(
            messages=[{"role": "user", "content": context_prompt}],
            system_prompt=SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=3000,
        )

        parsed = self._parse_json_response(llm_response)
        if not isinstance(parsed, dict):
            parsed = {"summary": llm_response[:500], "raw": True}

        # 4. Ham analizi de ekle (Coder bağlam için kullanır)
        return AgentResponse(
            content={
                "project_name": analysis["project_name"],
                "source": source,
                "stats": stats,
                "structure": analysis["structure"],
                "file_map": analysis.get("file_map", {}),
                "dependency_graph": analysis.get("dependency_graph", {}),
                "raw_issues": analysis.get("issues", []),
                "syntax_errors": analysis.get("syntax_errors", []),
                # LLM analizi
                "project_purpose": parsed.get("project_purpose", ""),
                "tech_stack": parsed.get("tech_stack", []),
                "bugs_found": parsed.get("bugs_found", []),
                "missing_features": parsed.get("missing_features", []),
                "security_issues": parsed.get("security_issues", []),
                "fix_plan": parsed.get("fix_plan", []),
                "summary": parsed.get("summary", ""),
            },
            success=True,
            metadata={
                "files_analyzed": stats.get("file_count", 0),
                "bugs_found": len(parsed.get("bugs_found", [])),
                "fix_steps": len(parsed.get("fix_plan", [])),
            },
        )

    def format_report(self, content: dict) -> str:
        """
        Analiz sonucunu okunabilir terminal metnine dönüştür.

        Args:
            content: act() çıktısındaki content dict

        Returns:
            str: Formatlanmış rapor
        """
        lines = [
            f"\n{'═' * 60}",
            f"  🔍 KOD ANALİZ RAPORU — {content.get('project_name', '?')}",
            f"{'═' * 60}",
            f"  Amaç    : {content.get('project_purpose', '-')}",
            f"  Stack   : {', '.join(content.get('tech_stack', ['-']))}",
            "",
        ]

        stats = content.get("stats", {})
        lines += [
            f"  📊 İstatistikler",
            f"  {'─' * 40}",
            f"  Dosya   : {stats.get('file_count', 0)}",
            f"  Satır   : {stats.get('total_lines', 0)}",
            f"  Fonksiyon: {stats.get('total_functions', 0)}",
            f"  Sınıf   : {stats.get('total_classes', 0)}",
            f"  Sorun   : {stats.get('issue_count', 0)}",
            "",
        ]

        bugs = content.get("bugs_found", [])
        if bugs:
            lines.append(f"  🐛 Bulunan Bug'lar ({len(bugs)})")
            lines.append(f"  {'─' * 40}")
            for b in bugs[:5]:
                severity = b.get("severity", "?").upper()
                icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(severity, "⚪")
                lines.append(f"  {icon} [{severity}] {b.get('file', '')}:{b.get('line', '')}")
                lines.append(f"     {b.get('description', '')}")
                lines.append(f"     → {b.get('fix', '')}")
            lines.append("")

        security = content.get("security_issues", [])
        if security:
            lines.append(f"  🔒 Güvenlik Sorunları")
            lines.append(f"  {'─' * 40}")
            for s in security:
                lines.append(f"  ⚠️  {s}")
            lines.append("")

        fix_plan = content.get("fix_plan", [])
        if fix_plan:
            lines.append(f"  🛠️  Fix Planı ({len(fix_plan)} adım)")
            lines.append(f"  {'─' * 40}")
            for step in fix_plan:
                lines.append(
                    f"  {step.get('priority', '?')}. [{step.get('assigned_to', 'coder').upper()}] "
                    f"{step.get('task', '')}"
                )
            lines.append("")

        lines += [
            f"  📝 Genel Değerlendirme",
            f"  {'─' * 40}",
            f"  {content.get('summary', '-')}",
            f"{'═' * 60}\n",
        ]

        return "\n".join(lines)
