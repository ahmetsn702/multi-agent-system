"""
agents/critic_agent.py
CriticAgent: Reviews outputs from other agents and provides structured feedback with scores.
"""
import json
import re
from pathlib import Path
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

- **approve** (routing: EXECUTOR): Overall score 6.0 or above. Code moves to Executor.
- **revise** (routing: CODER_REVISE): Overall score between 4.0 and 5.9. Return specific feedback.
- **replan** (routing: PLANNER_REPLAN): Any dimension scores below 3, or correctness below 5.

## Feedback Requirements

For every dimension that scores below 7, provide at least one specific, actionable note. Do not write "improve error handling." Write "the file open operation on line 34 has no exception handler — if the file does not exist, the program crashes with an unhandled FileNotFoundError."

## Output Format

Return JSON only with a numeric score field:

{
  "score": 7.2,
  "scores": {
    "correctness": 8,
    "quality": 6,
    "test_coverage": 5,
    "architecture": 7,
    "security": 9
  },
  "approved": true,
  "routing": "CODER_REVISE",
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
        # Updated threshold to match system prompt: 6.0 for approval
        if score >= 6.0:
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

    @staticmethod
    def _strip_json_code_block(response_text: object) -> str:
        """Strip markdown code fences from JSON response."""
        import re
        text = response_text if isinstance(response_text, str) else str(response_text or "")
        text = text.strip()
        
        # Strip markdown code fences using explicit pattern
        cleaned = re.sub(r'^```(?:json)?\s*', '', text)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        return cleaned.strip()

    @staticmethod
    def _extract_score_from_text(response_text: str) -> Optional[float]:
        patterns = (
            r'"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            r"\bscore\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
            r"\boverall\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
        )
        for pattern in patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if not match:
                continue
            try:
                return float(match.group(1))
            except (TypeError, ValueError):
                continue
        return None

    def _parse_critic_response(self, response_text: object, use_default: bool = True) -> dict:
        if isinstance(response_text, dict):
            return response_text

        cleaned = self._strip_json_code_block(response_text)
        candidates = [cleaned]

        if cleaned and not (cleaned.startswith("{") and cleaned.endswith("}")):
            json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if json_match:
                candidates.insert(0, json_match.group(0).strip())

        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

        score = self._extract_score_from_text(cleaned)
        if score is not None:
            return {
                "score": score,
                "approved": score >= 7.0,
                "issues": [],
                "suggestions": [],
                "summary": cleaned[:300],
            }

        if not use_default:
            return {}

        # Parsing failed completely — return UNSCORED status
        self.logger.warning(f"Failed to parse critic response: {cleaned[:200]}")
        return {
            "score": 0.0,
            "approved": False,
            "status": "UNSCORED",
            "issues": ["Failed to parse LLM response after retry"],
            "suggestions": ["Re-run the review"],
            "summary": "UNSCORED - critic response could not be parsed",
        }

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """Review the content and return structured feedback with 5-criteria scoring."""
        content_to_review = task.context.get("content", task.description)
        content_type = task.context.get("content_type", "output")
        revision_count = task.context.get("revision_count", 0)
        
        # Empty content check — no code to evaluate means score 0
        if not content_to_review or (isinstance(content_to_review, str) and len(content_to_review.strip()) < 10):
            print("[Critic] ⚠️  Empty or minimal content provided (< 10 chars), scoring 0.0")
            return AgentResponse(
                content={
                    "score": 0.0,
                    "approved": False,
                    "routing": "CODER_REVISE",
                    "revision_count": revision_count,
                    "scores": {},
                    "issues": ["Empty content - no code to evaluate"],
                    "suggestions": ["Generate actual code for the task"],
                    "improvements": [],
                    "summary": "No content to review - cannot approve empty output",
                    "skipped": True,
                },
                success=True,
                metadata={"score": 0.0, "approved": False, "skipped": True},
            )
        
        # GELİŞTİRME 6: Screenshot path kontrolü ve base64 encoding
        raw_screenshot_path = task.context.get("screenshot_path")
        screenshot_path = str(raw_screenshot_path).strip() if raw_screenshot_path else None
        has_screenshot = bool(screenshot_path and Path(screenshot_path).exists())
        screenshot_b64 = None
        
        if has_screenshot:
            try:
                import base64
                with open(screenshot_path, "rb") as f:
                    screenshot_bytes = f.read()

                # None/boş kontrolü: encode öncesi veri yoksa görsel değerlendirmeyi atla
                if screenshot_bytes is None or len(screenshot_bytes) == 0:
                    print("[Critic] ⚠️  Screenshot içeriği boş, base64 encode atlandı")
                    has_screenshot = False
                else:
                    screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                    if screenshot_b64 is None:
                        print("[Critic] ⚠️  Screenshot base64 sonucu None, görsel değerlendirme atlandı")
                        has_screenshot = False
                    else:
                        print(f"[Critic] 📸 Screenshot base64 encoded: {len(screenshot_b64)} chars")
            except Exception as e:
                print(f"[Critic] ⚠️  Screenshot encoding error: {e}")
                has_screenshot = False

        review_prompt = (
            f"İçerik türü: {content_type}\n\n"
            f"İncelenecek içerik:\n{str(content_to_review)[:3000]}\n\n"
        )
        
        # Screenshot varsa ekle
        if has_screenshot:
            review_prompt += (
                f"\n📸 UI Screenshot eklendi (görsel olarak)\n"
                f"ÖNEMLI: 6. kriter olarak 'ui_quality' ekle ve GÖRSELDEN görsel tasarımı değerlendir.\n"
                f"Screenshot'tan değerlendir:\n"
                f"- Renk uyumu ve tema tutarlılığı\n"
                f"- Layout düzeni ve boşluk kullanımı\n"
                f"- Responsive tasarım (mobil uyumluluk)\n"
                f"- Tipografi ve okunabilirlik\n\n"
            )
        
        review_prompt += (
            "Bu çıktıyı 5 kritere göre değerlendir ve YALNIZCA JSON formatında yanıt ver.\n"
            "ÖNEMLI: Yanıtında mutlaka 'routing' field'ı döndür:\n"
            "  - 'EXECUTOR' (skor >= 7, onayla ve çalıştır)\n"
            "  - 'CODER_REVISE' (skor 4-6.9, revize et)\n"
            "  - 'PLANNER_REPLAN' (skor < 4, baştan planla)\n\n"
            "Yanıtını MUTLAKA şu JSON formatında ver:\n"
            "{\n"
            "  \"score\": 7.5,\n"
            "  \"approved\": true,\n"
            "  \"routing\": \"EXECUTOR\",\n"
            "  \"issues\": [],\n"
            "  \"suggestions\": [],\n"
            "  \"summary\": \"...\"\n"
            "}\n"
            "Score 0-10 arasında olmalı.\n\n"
        )
        
        if has_screenshot:
            review_prompt += (
                'Örnek format (screenshot varsa):\n'
                '{"score": 7.5, "approved": true, "routing": "EXECUTOR", "issues": [], "suggestions": [], "summary": "kısa değerlendirme"}\n'
            )
        else:
            review_prompt += (
                'Örnek format:\n'
                '{"score": 7.6, "approved": true, "routing": "EXECUTOR", "issues": [], "suggestions": [], "summary": "kısa değerlendirme"}\n'
            )

        # GELİŞTİRME 6: Multimodal mesaj (screenshot varsa)
        if has_screenshot and screenshot_b64:
            # Gemini vision format: content as array with text and image
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": review_prompt},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64
                        }
                    }
                ]
            }]
        else:
            messages = [{"role": "user", "content": review_prompt}]

        response = await self._call_llm(
            messages=messages,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=600,
        )

        parsed = self._parse_critic_response(response, use_default=False)

        # Eger JSON parse basarisiz olduysa bir kez daha dene
        if not isinstance(parsed, dict) or "score" not in parsed:
            retry_prompt = (
                review_prompt
                + "\n\nKRITIK: Yalnizca asagidaki JSON formatini dondur, baska hicbir sey yazma:\n"
                '{"score":7.0,"approved":true,"routing":"EXECUTOR","issues":[],"suggestions":[],"summary":"kisa degerlendirme"}'
            )
            response = await self._call_llm(
                messages=[{"role": "user", "content": retry_prompt}],
                system_prompt=SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=600,
            )
            parsed = self._parse_critic_response(response)

        if not isinstance(parsed, dict):
            parsed = {}

        # V2: Parse 5-criteria scores (veya 6 screenshot varsa)
        scores = parsed.get("scores", {})
        if not isinstance(scores, dict):
            scores = {}
        try:
            score = float(parsed.get("score", 0.0))
        except Exception:
            score = 0.0

        # DEBUG: Log raw score to verify it varies
        self.logger.debug(f"Critic raw score from LLM: {score}")
        self.logger.debug(f"Critic individual scores: {scores}")
        self.logger.debug(f"Critic raw LLM output (first 500 chars): {str(response)[:500]}")

        # Compute average from scores dict if average missing
        if not score and scores:
            score = round(sum(scores.values()) / len(scores), 1)
            self.logger.debug(f"Critic computed score from individual scores: {score}")
        elif not score:
            # If parsing completely failed, mark as UNSCORED
            self.logger.warning("Critic score extraction failed, marking UNSCORED")
            score = 0.0
            parsed["status"] = "UNSCORED"

        # BUG FIX 1: approved default False olmalı (True değil!)
        approved = parsed.get("approved", False)
        
        # BUG FIX 1: routing field'ı LLM'den al, yoksa score'a göre hesapla
        routing = parsed.get("routing")
        if not routing:
            routing = self.route_by_score(int(score), revision_count)

        final_feedback = {
            "score": score,
            "approved": approved,
            "routing": routing,
            "revision_count": revision_count,
            "scores": scores,
            "issues": parsed.get("issues", []),
            "suggestions": parsed.get("suggestions", []),
            "improvements": parsed.get("suggestions", parsed.get("improvements", [])),
            "summary": parsed.get("summary", ""),
            "has_screenshot": has_screenshot,  # GELİŞTİRME 6
            "screenshot_path": screenshot_path if has_screenshot else None,  # GELİŞTİRME 6
        }

        response_obj = AgentResponse(
            content=final_feedback,
            success=True,
            metadata={"score": score, "approved": approved},
        )
        if not hasattr(response_obj, "metadata") or response_obj.metadata is None:
            response_obj.metadata = {}
        response_obj.metadata["score"] = float(score)
        response_obj.metadata["approved"] = bool(approved)
        print(f"[Critic DEBUG] metadata set: {response_obj.metadata}")
        return response_obj

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
