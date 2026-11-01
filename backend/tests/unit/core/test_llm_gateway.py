from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from src.core.errors import LLMUnavailable
from src.core.llm import LLMGateway, build_llm_gateway
from src.core.llm.gateway import NamedModel
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
