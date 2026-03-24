"""
agents/optimizer_agent.py
OptimizerAgent: Uretilen kodu performans ve kalite acisindan optimize eder.
"""
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus


SYSTEM_PROMPT = """Sen kıdemli bir Python optimizasyon uzmanısın.
Verilen kodu şu açılardan optimize et:
1) Gereksiz döngüler (O(n^2) -> O(n) mümkünse)
2) Tekrar eden kod blokları (DRY)
3) Gereksiz importlar
4) Büyük fonksiyonları küçük parçalara bölme
5) Uygun yerde list comprehension kullanımı
6) format() yerine f-string kullanımı

Kritik kurallar:
- Fonksiyonel davranışı bozma.
- Güvenlik riskleri ekleme.
- Geçersiz/sentaks hatalı kod üretme.

Sadece geçerli JSON döndür:
{
  "optimizations": ["...","..."],
  "score_before": 6.5,
  "score_after": 8.5,
  "optimized_code": "..."
}
"""


class OptimizerAgent(BaseAgent):
    """Coder tarafından üretilen kodu optimize eder."""

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="optimizer",
            name="Optimizer Ajanı",
            role="Kod Optimizasyonu",
            description="Kodda performans ve kalite iyileştirmeleri önerir ve optimize edilmiş kod üretir.",
            capabilities=["optimization", "performance", "refactoring", "code_quality"],
            bus=bus,
        )

    async def think(self, task: Task) -> ThoughtProcess:
        return ThoughtProcess(
            reasoning="Kodu performans, tekrar, okunabilirlik ve Python best-practice açısından optimize edeceğim.",
            plan=[
                "Kod kokularını tespit et",
                "Optimizasyonları uygula",
                "Öncesi/sonrası kalite skorunu üret",
            ],
            tool_calls=[],
            confidence=0.9,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        code = str(task.context.get("code", "") or "")
        if not code.strip():
            return AgentResponse(
                success=True,
                content={
                    "optimizations": [],
                    "score_before": 0.0,
                    "score_after": 0.0,
                    "optimized_code": "",
                },
            )

        prompt = (
            f"Görev: {task.description}\n\n"
            f"Dosya: {task.context.get('file_path', 'unknown.py')}\n\n"
            "Aşağıdaki kodu optimize et ve sadece JSON döndür:\n\n"
            f"{code}\n"
        )

        raw = await self._call_llm(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=12000,
        )

        parsed = self._parse_json_response(raw)
        if not isinstance(parsed, dict):
            parsed = {}

        optimizations = parsed.get("optimizations", [])
        if isinstance(optimizations, str):
            optimizations = [optimizations]
        if not isinstance(optimizations, list):
            optimizations = []
        optimizations = [str(item) for item in optimizations if str(item).strip()]

        def _to_float(value, fallback: float) -> float:
            try:
                return float(value)
            except Exception:
                return fallback

        score_before = _to_float(parsed.get("score_before"), 6.0)
        score_after = _to_float(parsed.get("score_after"), max(score_before, 7.0))
        optimized_code = str(parsed.get("optimized_code", "") or "").strip()
        if not optimized_code:
            optimized_code = code
            if score_after < score_before:
                score_after = score_before

        return AgentResponse(
            success=True,
            content={
                "optimizations": optimizations,
                "score_before": round(score_before, 1),
                "score_after": round(score_after, 1),
                "optimized_code": optimized_code,
            },
            metadata={"optimization_count": len(optimizations)},
        )
