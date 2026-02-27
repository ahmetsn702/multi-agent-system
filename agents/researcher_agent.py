"""
agents/researcher_agent.py
ResearcherAgent: Gathers and synthesizes information using web search.
"""
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus
from tools.web_search import web_search

SYSTEM_PROMPT = """Sen deneyimli bir yazılım danışmanısın.
Verilen görev için gerekli teknik bilgiyi, yaklaşımı ve kütüphaneleri belirliyorsun.

KURALLAR:
1. Özet MUTLAKA 300-600 kelime arasında olmalı. Daha uzun veya kısa olursa tekrar yaz.
2. Yanıtta mutlaka şu 4 bölüm olmalı:
   a) Önerilen Yaklaşım: hangi design pattern veya mimari kullanılacak
   b) Gerekli Kütüphaneler: standart kütüphane (stdlib) varsa onu seç
   c) Dikkat Edilmesi Gerekenler: edge case ve potansiyel hatalar
   d) Örnek İskelet: 5-10 satirlik Python yapı örneği
3. Web aramasına gerek yoksa kendi bilginle yaz.
4. Markdown kullanma, sadece JSON döndür.

ÇIKTI — YALNIZCA BU JSON FORMATI:
{
  "summary": "300-600 kelimelik teknik araştırma özeti",
  "libraries": ["lib1", "lib2"],
  "approach": "önerilen teknik yaklaşım",
  "risks": ["Risk 1", "Risk 2"],
  "code_skeleton": "# 5-10 satir Python örneği buraya"
}"""


class ResearcherAgent(BaseAgent):
    """
    Gathers information via DuckDuckGo web search and synthesizes results.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="researcher",
            name="Araştırmacı Ajan",
            role="Bilgi Toplama ve Sentezleme",
            description="İnternette arama yapar ve karmaşık konuları özlü, alıntılı raporlar halinde sentezler.",
            capabilities=["web_search", "information_synthesis", "documentation_analysis"],
            bus=bus,
        )
        self.register_tool("web_search", web_search)

    async def think(self, task: Task) -> ThoughtProcess:
        """Determine what to search for."""
        query_prompt = (
            f"Görev: {task.description}\n\n"
            "Bunu cevaplamak için en etkili 2-3 arama sorgusu nedir? "
            "JSON ile yanıt ver: {\"queries\": [\"sorgu1\", \"sorgu2\"]}"
        )
        response = await self._call_llm(
            messages=[{"role": "user", "content": query_prompt}],
            system_prompt="Sen bir arama stratejisi uzmanısın. Sadece geçerli JSON çıktısı ver.",
            temperature=0.3,
            max_tokens=300,
        )
        parsed = self._parse_json_response(response)
        queries = parsed.get("queries", [task.description[:100]])

        return ThoughtProcess(
            reasoning=f"Will search for: {queries}",
            plan=[f"Search: {q}" for q in queries],
            tool_calls=[{"tool": "web_search", "query": q} for q in queries],
            confidence=0.8,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """Execute searches and synthesize results."""
        all_results = []

        # Run all searches
        for tool_call in thought.tool_calls:
            if tool_call.get("tool") == "web_search":
                result = await self.use_tool("web_search", query=tool_call["query"])
                if result.success and result.data:
                    all_results.extend(result.data.get("results", []))

        # Remove duplicate URLs
        seen_urls = set()
        unique_results = []
        for r in all_results:
            if r.get("url") not in seen_urls:
                seen_urls.add(r.get("url"))
                unique_results.append(r)

        # Synthesize with LLM
        results_text = "\n\n".join(
            f"Title: {r['title']}\nURL: {r['url']}\nSnippet: {r['snippet']}"
            for r in unique_results[:8]
        )

        synthesis_prompt = (
            f"Araştırma görevi: {task.description}\n\n"
            f"Web arama sonuçları:\n{results_text}\n\n"
            "Bu bulguları kapsamlı bir rapor halinde sentezle."
        )

        synthesis = await self._call_llm(
            messages=[{"role": "user", "content": synthesis_prompt}],
            system_prompt=SYSTEM_PROMPT,
            temperature=0.4,
            max_tokens=2000,
        )

        parsed_synthesis = self._parse_json_response(synthesis)

        return AgentResponse(
            content={
                "synthesis": parsed_synthesis,
                "raw_results": unique_results,
                "search_count": len(thought.tool_calls),
                "result_count": len(unique_results),
            },
            success=True,
            metadata={"sources": [r.get("url") for r in unique_results]},
        )
