"""
agents/critic_agent.py
CriticAgent: Reviews outputs from other agents and provides structured feedback with scores.
"""
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus

SYSTEM_PROMPT = """You are the Critic agent inside MAOS — Multi-Agent Orchestration System.

Your job is to review code produced by the Coder and score it. Your scores and feedback directly determine whether the code moves forward, gets revised, or triggers a full replan.

## Core Responsibility

Review submitted code files against the original task description. Score each dimension honestly based on actual code quality. Provide specific, actionable feedback. Do not be lenient. DO NOT default to middle scores — evaluate critically and vary your scores based on what you observe.

## Scoring Rubric (1-10 scale)

**1-2: Broken**
- Code doesn't run at all
- Syntax errors present
- Missing core logic entirely
- Critical security vulnerabilities

**3-4: Partially Working**
- Major functionality missing
- Logic errors that break key features
- No error handling whatsoever
- Significant architectural problems

**5-6: Works But Incomplete**
- Basic functionality present but limited
- Missing error handling for common cases
- No tests or minimal test coverage
- Code structure needs improvement
- Missing edge case handling

**7-8: Good**
- Functional and meets requirements
- Clean, readable code
- Proper error handling
- Good test coverage
- Follows best practices

**9-10: Excellent**
- Production-ready code
- Comprehensive tests including edge cases
- Well-structured and maintainable
- Security considerations addressed
- Documentation present

## Scoring Dimensions

Score each dimension from 1 to 10 using the rubric above.

**Correctness (1–10)**
Does the code do what the task requires? A score below 5 here means the code should not proceed under any circumstances.

**Quality (1–10)**
Is the code well-structured, readable, and maintainable? Are functions focused? Are names clear?

**Test Coverage (1–10)**
Are tests present? Do they cover main logic paths, edge cases, and expected failure modes? Tests that only check the happy path score no higher than 5.

**Architecture (1–10)**
Does the structure make sense for the scale and purpose? Are concerns separated appropriately?

**Security (1–10)**
Are inputs validated? Are secrets handled correctly? Are there obvious injection risks?

## Critical Instructions

- EVALUATE HONESTLY: Do not default to 6.0 or middle scores
- VARY YOUR SCORES: Different code quality should produce different scores
- BE SPECIFIC: Each score must reflect actual observations in the code
- JUSTIFY SCORES: Your feedback must explain why each dimension received its score

## Decision Thresholds

- **approve** (routing: EXECUTOR): Overall score 7.0 or above. Code moves to Executor.
- **revise** (routing: CODER_REVISE): Overall score between 4.0 and 6.9. Return specific feedback.
- **replan** (routing: PLANNER_REPLAN): Any dimension scores below 3, or correctness below 5.

## Feedback Requirements

For every dimension that scores below 7, provide at least one specific, actionable note. Do not write "improve error handling." Write "the file open operation on line 34 has no exception handler — if the file does not exist, the program crashes with an unhandled FileNotFoundError."

## Output Format

Return JSON only with numeric score and average fields:

{
  "scores": {
    "correctness": 8,
    "quality": 6,
    "test_coverage": 5,
    "architecture": 7,
    "security": 9
  },
  "average": 7.0,
  "approved": true,
  "issues": [
    "quality: function process_document() is 87 lines — split into focused functions",
    "test_coverage: add cases for empty input, malformed PDF, and file permission errors"
  ],
  "suggestions": [
    "Extract validation logic into separate validator class",
    "Add integration tests for the full pipeline"
  ],
  "summary": "Code is functional but needs refactoring and better test coverage"
}

## Behavior Principles

Be consistent. Apply the same standards regardless of task complexity.

Be specific. Every piece of feedback must point to something concrete in the code.

Do not approve code you would not ship. You are the last line of defense before code hits disk.

REMEMBER: Your score must reflect actual code quality. Do not default to 6.0. Evaluate and differentiate.
"""


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

        # BUG FIX 2: Empty context check - skip review if no content to review
        # This prevents false scores when critic is called with empty context
        if not content_to_review or (isinstance(content_to_review, str) and len(content_to_review.strip()) < 10):
            print("[Critic] ⚠️  Empty or minimal content provided (< 10 chars), skipping review")
            return AgentResponse(
                content={
                    "score": 10.0,  # Perfect score since there's nothing to critique
                    "approved": True,
                    "routing": "EXECUTOR",
                    "revision_count": revision_count,
                    "scores": {},
                    "issues": [],
                    "suggestions": [],
                    "improvements": [],
                    "summary": "No content to review - auto-approved",
                    "skipped": True,  # Flag to indicate this was skipped
                },
                success=True,
                metadata={
                    "score": 10.0,
                    "approved": True,
                    "routing": "EXECUTOR",
                    "revision_count": revision_count,
                    "skipped": True,
                },
            )

        review_prompt = (
            f"İçerik türü: {content_type}\n\n"
            f"İncelenecek içerik:\n{str(content_to_review)[:3000]}\n\n"
            "Bu çıktıyı 5 kritere göre değerlendir ve YALNIZCA JSON formatında yanıt ver:\n"
            '{"scores": {"correctness": 8, "quality": 7, "test_coverage": 6, "architecture": 8, "security": 9}, '
            '"average": 7.6, "approved": true, "issues": [], "suggestions": [], "summary": "kısa değerlendirme"}'
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

        # DEBUG: Log raw score to verify it varies
        self.logger.debug(f"Critic raw score from LLM: {score}")
        self.logger.debug(f"Critic individual scores: {scores}")

        # Compute average from scores dict if average missing
        if not score and scores:
            score = round(sum(scores.values()) / len(scores), 1)
        elif not score:
            # Fallback: old single score field
            score = parsed.get("score", 5)

        # Determine approved from score
        approved = parsed.get("approved", score >= 7.0)

        routing = self.route_by_score(int(score), revision_count)

        # normalized field: use "suggestions" (legacy: "improvements")
        suggestions = parsed.get("suggestions") or parsed.get("improvements") or []

        final_feedback = {
            "score": score,
            "approved": approved,
            "routing": routing,
            "revision_count": revision_count,
            "scores": scores,
            "issues": parsed.get("issues", []),
            "suggestions": suggestions,
            "improvements": suggestions,
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
