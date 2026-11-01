"""The LangGraph workflow (OR-01 to OR-08).

    START -> load_context -> router -+-> advice_redirect ------------------+
                                     +-> clarify --------------------------+
                                     +-> Send(agent) x N (parallel) -> fallback -> synthesizer -+
                                                                                               |
                                     compliance <-------------------------------------------- -+
                                         |
                                        END

The router's plan fans out with LangGraph's Send API; agent outputs merge through the
`agent_outputs` reducer. All six agents are registered in production. A graph built with
fewer (tests, partial deployments) replaces a missing agent with its substitute (Tax ->
Q&A, which covers the tax KB) or sends it to a stub node that records a NodeError, so the
user is told that part isn't available instead of failing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from src.core.config.settings import WorkflowConfig
from src.core.llm import LLMGateway
from src.workflow.agent_runner import Agent, AgentNode, agent_unavailable_node, fallback_node
from src.workflow.compliance import ComplianceNode
from src.workflow.context import ContextLoader, LoadContextNode
from src.workflow.responses import advice_redirect_node, clarify_node
from src.workflow.router import RouterNode
from src.workflow.state import AgentName, FinanceState
from src.workflow.synthesizer import SynthesizerNode

UNAVAILABLE = "agent_unavailable"

# Until an agent is registered, a stand-in that fully covers its questions answers for it.
SUBSTITUTES = {AgentName.TAX: AgentName.FINANCE_QA}


@dataclass
class WorkflowDeps:
    gateway: LLMGateway
    context_loader: ContextLoader
    agents: Mapping[AgentName, Agent]
    config: WorkflowConfig


def route_after_router(
    state: FinanceState, registered: Mapping[AgentName, Agent]
) -> str | list[Send]:
    plan = state.get("plan")
    if plan is None or plan.needs_clarification:
        return "clarify"
    if plan.is_advice_request:
        return "advice_redirect"
    targets: list[AgentName] = []
    missing: list[AgentName] = []
    for agent in plan.agents:
        if agent in registered:
            targets.append(agent)
        elif SUBSTITUTES.get(agent) in registered:
            targets.append(SUBSTITUTES[agent])
        else:
            missing.append(agent)
    # With nothing else able to answer, Q&A still explains the concepts involved.
    if not targets and AgentName.FINANCE_QA in registered:
        targets.append(AgentName.FINANCE_QA)
    sends = [Send(agent.value, state) for agent in dict.fromkeys(targets)]
    sends += [Send(UNAVAILABLE, {"agent": agent.value}) for agent in missing]
    return sends


def build_workflow(
    deps: WorkflowDeps, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[Any, Any, Any, Any]:
    config = deps.config
    graph = StateGraph(FinanceState)

    graph.add_node("load_context", LoadContextNode(deps.context_loader, config.max_message_chars))
    graph.add_node("router", RouterNode(deps.gateway, config))
    graph.add_node("clarify", clarify_node)
    graph.add_node("advice_redirect", advice_redirect_node)
    for name, agent in deps.agents.items():
        graph.add_node(
            name.value,
            AgentNode(
                agent,
                timeout_seconds=config.agent_timeout_seconds,
                retries=config.agent_retries,
            ),
        )
    graph.add_node(UNAVAILABLE, agent_unavailable_node)  # type: ignore[type-var]
    graph.add_node("fallback", fallback_node)
    graph.add_node("synthesizer", SynthesizerNode(deps.gateway))
    graph.add_node("compliance", ComplianceNode(deps.gateway))

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "router")
    destinations = ["clarify", "advice_redirect", UNAVAILABLE, *(a.value for a in deps.agents)]
    graph.add_conditional_edges(
        "router",
        lambda state: route_after_router(state, deps.agents),
        destinations,
    )
    for node in (*(a.value for a in deps.agents), UNAVAILABLE):
        graph.add_edge(node, "fallback")
    graph.add_edge("fallback", "synthesizer")
    graph.add_edge("synthesizer", "compliance")
    graph.add_edge("clarify", "compliance")
    graph.add_edge("advice_redirect", "compliance")
    graph.add_edge("compliance", END)

    return graph.compile(checkpointer=checkpointer)
