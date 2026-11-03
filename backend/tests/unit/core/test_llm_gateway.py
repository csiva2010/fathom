from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from src.core.errors import LLMUnavailable
from src.core.llm import LLMGateway, build_llm_gateway
from src.core.llm.gateway import NamedModel
from src.core.tracing import current_step, record_llm_call, record_tool, recording
from tests.conftest import make_settings
from tests.fakes import scripted, structured


class Answer(BaseModel):
    text: str


async def test_falls_back_to_next_model() -> None:
    primary, secondary = scripted(RuntimeError("503")), scripted("from secondary")
    gateway = LLMGateway([NamedModel("a:1", primary), NamedModel("b:2", secondary)])
    reply = await gateway.ainvoke([HumanMessage("hi")])
    assert reply.text == "from secondary"
    assert gateway.available and gateway.model_names == ["a:1", "b:2"]


async def test_binds_tools_only_when_given() -> None:
    model = scripted("one", "two")
    gateway = LLMGateway([NamedModel("a:1", model)])
    await gateway.ainvoke([HumanMessage("hi")])
    await gateway.ainvoke(
        [HumanMessage("hi")], tools=[{"type": "function", "function": {"name": "t"}}]
    )
    assert len(model.bound_tools) == 1


async def test_structured_output() -> None:
    gateway = LLMGateway([NamedModel("a:1", scripted(structured("Answer", text="ok")))])
    assert await gateway.astructured(Answer, [HumanMessage("hi")]) == Answer(text="ok")


async def test_all_models_failing_raises() -> None:
    gateway = LLMGateway([NamedModel("a:1", scripted(RuntimeError("down")))])
    with pytest.raises(LLMUnavailable):
        await gateway.ainvoke([HumanMessage("hi")])
    with pytest.raises(LLMUnavailable):
        await LLMGateway([]).astructured(Answer, [])
    assert not LLMGateway([]).available


async def test_non_ai_reply_counts_as_failure() -> None:
    class Weird(type(scripted())):  # type: ignore[misc]
        async def ainvoke(self, *args: object, **kwargs: object) -> object:  # type: ignore[override]
            return "not a message"

    gateway = LLMGateway([NamedModel("a:1", Weird(replies=[], calls=[], bound_tools=[]))])
    with pytest.raises(LLMUnavailable):
        await gateway.ainvoke([HumanMessage("hi")])


def test_build_gateway_skips_models_without_keys(tmp_path: Path) -> None:
    llm = {
        "models": [
            {"provider": "gemini", "model": "gemini-flash-latest"},
            {"provider": "anthropic", "model": "claude-sonnet-5-5"},
            {"provider": "openai", "model": "gpt-test"},
        ]
    }
    assert build_llm_gateway(make_settings(tmp_path, llm=llm)).model_names == []
    full = build_llm_gateway(
        make_settings(
            tmp_path, llm=llm, gemini_api_key="g", anthropic_api_key="a", openai_api_key="o"
        )
    )
    assert full.model_names == [
        "gemini:gemini-flash-latest",
        "anthropic:claude-sonnet-5-5",
        "openai:gpt-test",
    ]


async def test_calls_are_recorded_on_the_open_trace_step() -> None:
    usage = {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}
    primary = scripted(RuntimeError("503"))
    secondary = scripted(
        "untraced", AIMessage("hi", usage_metadata=usage), structured("Answer", text="ok")
    )
    gateway = LLMGateway([NamedModel("a:1", primary), NamedModel("b:2", secondary)])

    await gateway.ainvoke([HumanMessage("untraced")])  # no step open: nothing recorded
    primary.replies.extend([RuntimeError("503"), RuntimeError("503")])
    with recording() as step:
        await gateway.ainvoke([HumanMessage("hi")])
        await gateway.astructured(Answer, [HumanMessage("hi")])
    assert step.llm_calls == 2 and step.fallbacks == 2
    assert step.models == ["b:2"]
    assert (step.input_tokens, step.output_tokens) == (10, 4)  # structured reply had no usage
    assert current_step() is None


async def test_unparseable_structured_reply_falls_back() -> None:
    bad = scripted(structured("Answer", wrong="field"), AIMessage("no tool call"))
    gateway = LLMGateway([NamedModel("a:1", bad), NamedModel("b:2", scripted())])
    with pytest.raises(LLMUnavailable):
        await gateway.astructured(Answer, [HumanMessage("hi")])  # parsing error
    with pytest.raises(LLMUnavailable):
        await gateway.astructured(Answer, [HumanMessage("hi")])  # nothing parsed


def test_record_tool_needs_an_open_step() -> None:
    record_tool("ignored")
    with recording() as step:
        record_tool("get_quotes")
        record_llm_call("m", None)
    assert step.tools == ["get_quotes"] and step.llm_calls == 1 and step.input_tokens == 0
