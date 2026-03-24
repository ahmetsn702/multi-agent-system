"""
agents/researcher_agent.py
ResearcherAgent: Gathers and synthesizes information using Google Search grounding via Vertex AI.
"""
from typing import Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus

try:
    from google.genai import types
    GOOGLE_SEARCH_AVAILABLE = True
except ImportError:
    GOOGLE_SEARCH_AVAILABLE = False
    types = None

SYSTEM_PROMPT = """You are the Researcher agent inside MAOS — Multi-Agent Orchestration System.

Your job is to investigate technical questions and produce actionable findings that the Coder can use directly. You do not write production code. You gather, evaluate, and recommend.

## Core Responsibility

Given a research task, produce a concise technical brief. This brief should answer the specific question asked and give the Coder enough context to make good implementation decisions without needing to do their own research.

## What You Research

- Library and framework selection: which options exist, how they compare, which is most appropriate
- Technical approach: what architecture or pattern fits the problem
- API and integration details: how a specific service, library, or protocol works
- Known pitfalls: common failure modes, edge cases, or gotchas
- Environment and dependency requirements: what needs to be installed or configured

## Behavior Principles

Be specific. "Use a popular library" is not useful. "Use pdfplumber over PyPDF2 because it handles complex layouts and returns structured text objects" is useful.

Be honest about uncertainty. If you are not confident in a recommendation, say so. Do not fabricate library names, API signatures, or version compatibility claims.

Stay scoped. Answer the question asked. Do not expand into adjacent topics unless directly relevant.

Prioritize recency and fit. A well-maintained library that fits the task is better than a popular one that does not.

## Output Format

Return a structured research brief in Turkish:

{
  "task_id": "p1_t1",
  "recommendation": "pdfplumber kullan",
  "rationale": "...",
  "implementation_notes": ["...", "..."],
  "alternatives_considered": ["PyPDF2", "pdfminer.six"],
  "confidence": "high"
}
"""


class ResearcherAgent(BaseAgent):
    """
    Gathers information via Google Search grounding (Vertex AI) and synthesizes results.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="researcher",
            name="Araştırmacı Ajan",
            role="Bilgi Toplama ve Sentezleme",
            description="Google Search grounding ile internette arama yapar ve karmaşık konuları özlü raporlar halinde sentezler.",
            capabilities=["google_search_grounding", "information_synthesis", "documentation_analysis"],
            bus=bus,
        )
        
        if not GOOGLE_SEARCH_AVAILABLE:
            print("[Researcher] ⚠️ google-genai paketi yüklü değil, Google Search grounding kullanılamayacak")

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
            max_tokens=512,
        )
        
        # Error handling: if LLM returns None or parsing fails, use task description
        if response is None:
            print("[Researcher] ⚠️ LLM response is None, using task description as query")
            queries = [task.description[:100]]
        else:
            parsed = self._parse_json_response(response)
            queries = parsed.get("queries") or [task.description[:100]]
            
            # Additional check: if queries is empty list
            if not queries:
                print("[Researcher] ⚠️ No queries parsed, using task description as query")
                queries = [task.description[:100]]

        return ThoughtProcess(
            reasoning=f"Will search for: {queries}",
            plan=[f"Search: {q}" for q in queries],
            tool_calls=[{"tool": "web_search", "query": q} for q in queries],
            confidence=0.8,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """GELİŞTİRME 4: Execute searches using Google Search grounding and synthesize results.
        
        Önce Memory Agent'a bakar, ilgili proje varsa web aramasını azaltır.
        """
        # GELİŞTİRME 4: Memory Agent'a sor
        from core.memory_agent import get_memory_agent
        memory = get_memory_agent()
        memory_result = memory.query(task.description)
        
        memory_context = ""
        if memory_result:
            # İlgili proje bulundu, web aramasını azalt
            print(f"[Researcher] 💾 Memory'den ilgili proje bulundu: {memory_result['slug']}")
            memory_context = (
                f"\n\n### Önceki İlgili Proje:\n"
                f"Proje: {memory_result['goal']}\n"
                f"Dosyalar: {', '.join(memory_result['files'][:3])}\n"
                f"Pattern'ler: {', '.join(memory_result.get('tags', []))}\n"
            )
            # Snippet varsa ekle
            if memory_result.get("snippets"):
                first_file = next(iter(memory_result["snippets"]))
                snippet = memory_result["snippets"][first_file][:200]
                memory_context += f"\n```python\n# {first_file}\n{snippet}\n```\n"
            
            # Web aramasını azalt (sadece 1 sorgu)
            thought.tool_calls = thought.tool_calls[:1]
            print(f"[Researcher] 🔍 Web araması azaltıldı: {len(thought.tool_calls)} sorgu")
        
        # Prepare Google Search grounding config
        search_config = None
        if GOOGLE_SEARCH_AVAILABLE and types:
            search_config = {"tools": [types.Tool(google_search=types.GoogleSearch())]}
        
        all_search_results = []
        
        # Run all searches using Google Search grounding
        for tool_call in thought.tool_calls:
            query = tool_call.get("query", "")
            if not query:
                continue
            
            print(f"[Researcher] 🔍 Google Search: {query}")
            
            try:
                # Make LLM call with Google Search grounding enabled
                search_prompt = f"Araştır: {query}\n\nDetaylı ve kapsamlı bilgi ver. Kaynakları belirt."
                
                response = await self._call_llm(
                    messages=[{"role": "user", "content": search_prompt}],
                    system_prompt="Sen bir araştırmacısın. Google Search kullanarak kapsamlı bilgi topla ve kaynakları belirt.",
                    temperature=0.3,
                    max_tokens=2048,
                    extra_config=search_config,
                )
                
                if response:
                    all_search_results.append({
                        "query": query,
                        "content": response,
                    })
                    print(f"[Researcher] ✅ Arama tamamlandı: {len(response)} karakter")
                else:
                    print(f"[Researcher] ⚠️ Arama sonucu boş: {query}")
                    
            except Exception as e:
                print(f"[Researcher] ❌ Arama hatası: {e}")
                continue

        # Combine all search results
        combined_results = "\n\n---\n\n".join(
            f"Sorgu: {r['query']}\n\n{r['content']}"
            for r in all_search_results
        )

        # GELİŞTİRME 4: Memory context'i synthesis'e ekle
        synthesis_prompt = (
            f"Araştırma görevi: {task.description}\n\n"
        )
        if memory_context:
            synthesis_prompt += f"{memory_context}\n\n"
        synthesis_prompt += (
            f"Google Search sonuçları:\n{combined_results}\n\n"
            "Bu bulguları kapsamlı bir rapor halinde sentezle. JSON formatında yanıt ver."
        )

        synthesis = await self._call_llm(
            messages=[{"role": "user", "content": synthesis_prompt}],
            system_prompt=SYSTEM_PROMPT,
            temperature=0.4,
            max_tokens=2000,
        )

        parsed_synthesis = self._parse_json_response(synthesis)

        # GELİŞTİRME 4: Memory kullanımını metadata'ya ekle
        return AgentResponse(
            content={
                "synthesis": parsed_synthesis,
                "raw_results": all_search_results,
                "search_count": len(thought.tool_calls),
                "result_count": len(all_search_results),
                "memory_used": memory_result is not None,  # GELİŞTİRME 4
                "search_method": "google_search_grounding",
            },
            success=True,
            metadata={
                "search_queries": [tc.get("query") for tc in thought.tool_calls],
                "memory_project": memory_result["slug"] if memory_result else None,  # GELİŞTİRME 4
            },
        )
