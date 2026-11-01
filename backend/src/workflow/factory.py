"""Wire the workflow from long-lived app objects (container, scripts, tests)."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from src.agents.finance_qa import FinanceQAAgent
from src.agents.market_analysis import MarketAnalysisAgent
from src.core.config.settings import WorkflowConfig
from src.core.llm import LLMGateway
from src.core.services.market.market_data_service import MarketDataService
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
) -> dict[AgentName, Agent]:
    """Agents implemented so far; the router can still plan the others (they degrade)."""
    options = {"max_tool_rounds": config.max_tool_rounds, "history": config.history_messages}
    return {
        AgentName.FINANCE_QA: FinanceQAAgent(gateway, knowledge_base, **options),
        AgentName.MARKET: MarketAnalysisAgent(gateway, market, **options),
    }


def create_workflow(
    config: WorkflowConfig,
    gateway: LLMGateway,
    knowledge_base: KnowledgeBase | None,
    market: MarketDataService,
    context_loader: ContextLoader,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    agents = build_agents(config, gateway, knowledge_base, market)
    deps = WorkflowDeps(
        gateway=gateway, context_loader=context_loader, agents=agents, config=config
    )
    return build_workflow(deps, checkpointer)
