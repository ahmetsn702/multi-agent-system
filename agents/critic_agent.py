"""
agents/critic_agent.py
CriticAgent: Reviews outputs from other agents and provides structured feedback with scores.
"""
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus

SYSTEM_PROMPT = """Sen kıdemli bir yazılım mimarı ve kod inceleme uzmanısın.
Sana sunulan kodu/çıktıyı 5 kritere göre 1-10 aralığında puanla.

PUANLAMA KRİTERLERİ (her biri 1-10):
  1. correctness    : Kod tam çalışıyor mu, eksik fonksiyon var mı?
  2. quality        : PEP8, docstring, type hints, hata yönetimi
  3. test_coverage  : Unit testler yazılmış mı, edge case'ler kapsanıyor mu?
  4. architecture   : Dosya yapısı ve sınıf tasarımı mantıklı mı?
  5. security       : Hardcoded path, güvensiz input, SQL injection vb. risk var mı?

KARAR KURALI:
  Ortalama >= 7.0  →  ONAYLANIR  (approved: true)
  Ortalama <  7.0  →  REVİZYON   (approved: false)

ÇIKTI — YALNIZCA BU JSON FORMATI (Markdown, açıklama veya başka metin OLMAYACAK):
{
  "scores": {
    "correctness": 8,
    "quality": 7,
    "test_coverage": 6,
    "architecture": 8,
    "security": 9
  },
  "average": 7.6,
  "approved": true,
  "issues": ["sorun 1", "sorun 2"],
  "improvements": ["iyileştirme 1"],
  "summary": "genel değerlendirme 1-2 cümle"
}"""


class CriticAgent(BaseAgent):
    """
    Reviews outputs from other agents. Scores < 7 trigger revision requests.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="critic",
            name="Eleştirmen Ajan",
            role="Kalite Güvence ve Geri Bildirim",
            description="Ajan çıktılarını inceler ve puanlanmış, eyleme dönüştürülebilir geri bildirimler sağlar. Kalite puanı 7/10'un altındaysa revizyon talep eder.",
            capabilities=["review", "feedback", "quality_assurance", "scoring"],
            bus=bus,
        )

    def route_by_score(self, score: int, revision_count: int) -> str:
        if score >= 7:
            return "EXECUTOR"            # Direkt çalıştır
        elif score >= 4 and revision_count < 2:
            return "CODER_REVISE"        # Coder'a geri, max 2 kez
        elif score >= 4 and revision_count >= 2:
            return "EXECUTOR_ANYWAY"     # 2 revizyon yeterliydi, devam
        else:  # score < 4
            return "PLANNER_REPLAN"      # Baştan planla, görev yanlış anlaşıldı

    async def think(self, task: Task) -> ThoughtProcess:
        """Determine what dimensions to evaluate."""
        content_type = task.context.get("content_type", "çıktı")
        return ThoughtProcess(
            reasoning=f"Bu {content_type} üzerinde doğruluk, tamlık, netlik ve yapılabilirlik (feasibility) boyutlarında inceleme yapacağım.",
            plan=["İçeriği analiz et", "Her boyutu puanla", "Sorunları tanımla", "Öneriler sun"],
            tool_calls=[],
            confidence=0.9,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """Review the content and return structured feedback with 5-criteria scoring."""
        content_to_review = task.context.get("content", task.description)
        content_type = task.context.get("content_type", "output")
        revision_count = task.context.get("revision_count", 0)

        review_prompt = (
            f"İçerik türü: {content_type}\n\n"
            f"İncelenecek içerik:\n{str(content_to_review)[:3000]}\n\n"
            "Bu çıktıyı 5 kritere göre değerlendir ve YALNIZCA JSON formatında yanıt ver:\n"
            '{"scores": {"correctness": 8, "quality": 7, "test_coverage": 6, "architecture": 8, "security": 9}, '
            '"average": 7.6, "approved": true, "issues": [], "improvements": [], "summary": "kısa değerlendirme"}'
        )

        response = await self._call_llm(
            messages=[{"role": "user", "content": review_prompt}],
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=600,
        )

        parsed = self._parse_json_response(response)

        # V2: Parse 5-criteria scores
        scores = parsed.get("scores", {})
        score = parsed.get("average", 0)

        # Compute average from scores dict if average missing
        if not score and scores:
            score = round(sum(scores.values()) / len(scores), 1)
        elif not score:
            # Fallback: old single score field
            score = parsed.get("score", 5)

        # Determine approved from score
        approved = parsed.get("approved", score >= 7.0)

        routing = self.route_by_score(int(score), revision_count)

        final_feedback = {
            "score": score,
            "approved": approved,
            "routing": routing,
            "revision_count": revision_count,
            "scores": scores,
            "issues": parsed.get("issues", []),
            "improvements": parsed.get("improvements", []),
            "summary": parsed.get("summary", ""),
        }

        return AgentResponse(
            content=final_feedback,
            success=True,
            metadata={
                "score": score,
                "approved": approved,
                "routing": routing,
                "revision_count": revision_count,
            },
        )

    async def review_code(self, code: str, task_description: str) -> dict:
        """Convenience method to review a code snippet directly."""
        task = Task(
            task_id="code_review",
            description=f"Review code for: {task_description}",
            assigned_to="critic",
            context={
                "content": code,
                "content_type": "Python code",
                "original_task": task_description,
            },
        )
        response = await self.run(task)
        return response.content if response.success else {"review": {"verdict": "ERROR"}}
