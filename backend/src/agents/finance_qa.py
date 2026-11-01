"""Finance Q&A agent (AG-01): explains concepts at the user's level, grounded in the KB.

Retrieval runs first with the router's standalone question. If nothing clears the
relevance threshold and the glossary has no entry, the agent says it doesn't know instead
of guessing (KB-06), without spending an LLM call. Otherwise the LLM explains from the
numbered excerpts and cites them as [n]; it can search again or define terms with tools.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from src.agents.base_agent import AgentRun, AgentTool, BaseAgent, Prepared, as_data
from src.core.llm import LLMGateway
from src.rag.knowledge_base import KnowledgeBase
from src.rag.models import GlossaryTerm
from src.rag.retriever import RetrievalResult
from src.workflow.state import AgentName, AgentOutput, FinanceState

NO_CONTEXT_ANSWER = (
    "I couldn't find that in my knowledge base, so I'd rather not guess. Try rephrasing "
    "the question, or browse the Learn tab for related topics."
)
KB_UNAVAILABLE_ANSWER = (
    "My knowledge base isn't available right now, so I can't give you a sourced answer. "
    "Please try again in a moment."
)
EXCERPT_WORDS = 70


class SearchKbArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300, description="What to look up")


class DefineTermArgs(BaseModel):
    term: str = Field(min_length=1, max_length=80, description="Finance term to define")


def format_definition(term: GlossaryTerm) -> str:
    related = f" Related: {', '.join(term.related)}." if term.related else ""
    return f"{term.term}: {term.definition}{related}"


class FinanceQAAgent(BaseAgent):
    name = AgentName.FINANCE_QA
    role_prompt = """You are the Finance Q&A agent. You explain personal-finance and \
investing concepts clearly and accurately.
- Base the answer on the numbered knowledge-base excerpts. Cite them inline as [1], [2]
  right after the sentence they support. Only cite numbers you were given.
- If the excerpts don't cover part of the question, say so briefly rather than guessing.
- Use the search_kb tool for a missing sub-topic and define_term for a jargon term."""

    category: str | None = None  # the Tax agent narrows retrieval to one category

    def __init__(self, gateway: LLMGateway, knowledge_base: KnowledgeBase | None, **kwargs: int):
        super().__init__(gateway, **kwargs)
        self._kb = knowledge_base

    def tools(self) -> Sequence[AgentTool]:
        return (
            AgentTool(
                "search_kb",
                "Search the finance knowledge base. Returns numbered excerpts to cite as [n].",
                SearchKbArgs,
                self._search_tool,
            ),
            AgentTool(
                "define_term",
                "Look up a finance term in the glossary.",
                DefineTermArgs,
                self._define_tool,
            ),
        )

    async def prepare(self, state: FinanceState, run: AgentRun) -> Prepared:
        if self._kb is None:
            return Prepared(early=self._answer_only(KB_UNAVAILABLE_ANSWER, 0.0))
        query = self.question(state)
        user = state.get("user")
        result = await self._kb.retriever.search(
            query, category=self.category, level=user.experience_level if user else None
        )
        term = self._kb.glossary.lookup(query)
        if not result.found and term is None:
            return Prepared(early=self._answer_only(NO_CONTEXT_ANSWER, 0.2))

        parts = []
        if term is not None:
            parts.append(as_data("glossary", format_definition(term)))
        if result.found:
            parts.append(as_data("knowledge_base", self._excerpts(run, result)))
        return Prepared(context="\n\n".join(parts), data={"result": result, "term": term})

    def _answer_only(self, text: str, confidence: float) -> AgentOutput:
        return AgentOutput(
            agent=self.name,
            answer_md=text,
            confidence=confidence,
            follow_ups=["What topics can you explain?", "What is an index fund?"],
        )

    def _excerpts(self, run: AgentRun, result: RetrievalResult) -> str:
        lines = []
        for hit, citation in zip(result.chunks, result.citations_per_chunk(), strict=True):
            number = run.cite(citation)
            chunk = hit.chunk
            lines.append(f"[{number}] {chunk.title} > {chunk.section}\n{chunk.text}")
        return "\n\n".join(lines)

    async def _search_tool(self, run: AgentRun, args: SearchKbArgs) -> str:
        assert self._kb is not None
        result = await self._kb.retriever.search(args.query, category=self.category)
        if not result.found:
            return "NO_CONTEXT: nothing in the knowledge base matches that query."
        return self._excerpts(run, result)

    async def _define_tool(self, run: AgentRun, args: DefineTermArgs) -> str:
        assert self._kb is not None
        term = self._kb.glossary.lookup(args.term)
        if term is not None:
            return format_definition(term)
        suggestions = self._kb.glossary.suggest(args.term)
        hint = f" Close matches: {', '.join(suggestions)}." if suggestions else ""
        return f"'{args.term}' is not in the glossary.{hint}"

    def offline_answer(self, state: FinanceState, run: AgentRun, prepared: Prepared) -> str:
        """Without an LLM: the glossary definition plus short quotes from the top sources."""
        lines: list[str] = []
        term: GlossaryTerm | None = prepared.data.get("term")
        if term is not None:
            lines.append(f"**{term.term}**: {term.definition}")
        result: RetrievalResult | None = prepared.data.get("result")
        if result is not None and result.found:
            lines.append("Here's what my sources say:")
            for hit, citation in list(
                zip(result.chunks, result.citations_per_chunk(), strict=True)
            )[:3]:
                words = hit.chunk.text.split()
                excerpt = " ".join(words[:EXCERPT_WORDS]) + (
                    "..." if len(words) > EXCERPT_WORDS else ""
                )
                lines.append(f"- **{hit.chunk.section}**: {excerpt} [{run.cite(citation)}]")
        return "\n\n".join(lines)

    def confidence(self, run: AgentRun, prepared: Prepared) -> float:
        result: RetrievalResult | None = prepared.data.get("result")
        if result is None or not result.found:
            return 0.5  # glossary only
        return round(min(0.95, 0.5 + 0.45 * result.chunks[0].score), 2)

    def follow_ups(self, state: FinanceState, run: AgentRun, prepared: Prepared) -> list[str]:
        term: GlossaryTerm | None = prepared.data.get("term")
        related = list(term.related) if term else []
        if self._kb is not None and not related and run.citations:
            top = self._kb.glossary.lookup(run.citations[0].title)
            related = list(top.related) if top else []
        questions = [f"What is {name}?" for name in related]
        if run.citations:
            questions.append(f"Tell me more about {run.citations[0].title.lower()}")
        return questions[:3]
