"""Wire the workflow from long-lived app objects (container, scripts, tests)."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from src.agents.base_agent import AgentOptions
from src.agents.finance_qa import FinanceQAAgent
from src.agents.goal_planning import GoalPlanningAgent
from src.agents.market_analysis import MarketAnalysisAgent
from src.agents.news_synthesizer import NewsSynthesizerAgent
from src.agents.portfolio_analysis import PortfolioAnalysisAgent
from src.agents.tax_education import TaxEducationAgent
from src.core.config.settings import WorkflowConfig
from src.core.llm import LLMGateway
from src.core.services.market.market_data_service import MarketDataService
from src.core.services.portfolio_service import PortfolioAnalysisService
from src.rag.knowledge_base import KnowledgeBase
from src.workflow.agent_runner import Agent
from src.workflow.context import ContextLoader
from src.workflow.graph import WorkflowDeps, build_workflow
from src.workflow.state import AgentName


def build_agents(
    config: WorkflowConfig,
    gateway: LLMGateway,
    knowledge_base: KnowledgeBase | None,
    market: MarketDataService,
    portfolios: PortfolioAnalysisService | None = None,
) -> dict[AgentName, Agent]:
    """All six specialist agents (AG-01 to AG-06)."""
    options: AgentOptions = {
        "max_tool_rounds": config.max_tool_rounds,
        "history": config.history_messages,
    }
    portfolios = portfolios or PortfolioAnalysisService(market)
    return {
        AgentName.FINANCE_QA: FinanceQAAgent(gateway, knowledge_base, **options),
        AgentName.PORTFOLIO: PortfolioAnalysisAgent(gateway, portfolios, market, **options),
        AgentName.MARKET: MarketAnalysisAgent(gateway, market, **options),
        AgentName.GOAL: GoalPlanningAgent(gateway, **options),
        AgentName.NEWS: NewsSynthesizerAgent(gateway, market, knowledge_base, **options),
        AgentName.TAX: TaxEducationAgent(gateway, knowledge_base, **options),
    }


def create_workflow(
    config: WorkflowConfig,
    gateway: LLMGateway,
    knowledge_base: KnowledgeBase | None,
    market: MarketDataService,
    context_loader: ContextLoader,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    portfolios: PortfolioAnalysisService | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    agents = build_agents(config, gateway, knowledge_base, market, portfolios)
    deps = WorkflowDeps(
        gateway=gateway, context_loader=context_loader, agents=agents, config=config
    )
    return build_workflow(deps, checkpointer)
