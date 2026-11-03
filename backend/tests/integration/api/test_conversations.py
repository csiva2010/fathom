"""Conversations API and the chat SSE stream (CH-01 to CH-07, AU-03)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from src.agents.portfolio_analysis import SCREENSHOT_UNAVAILABLE_ANSWER
from src.data.db.repositories.conversation_repository import DEFAULT_TITLE, title_from
from src.web_app.routers.conversations import SCREENSHOT_QUESTION
from tests.conftest import make_settings

API = "/api/v1"


def events(response: Any, *, traces: bool = False) -> list[dict[str, Any]]:
    """The SSE payloads; per-node `trace` events only when asked for."""
    assert response.headers["content-type"].startswith("text/event-stream")
    data = [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]
    return [e for e in data if traces or e["type"] != "trace"]


def new_conversation(client: TestClient) -> str:
    response = client.post(f"{API}/conversations", json={})
    assert response.status_code == 201
    return str(response.json()["id"])


def send(client: TestClient, conversation_id: str, text: str) -> Any:
    return client.post(f"{API}/conversations/{conversation_id}/messages", json={"content": text})


def test_chat_requires_sign_in(client: TestClient) -> None:
    assert client.get(f"{API}/conversations").status_code == 401
    assert client.post(f"{API}/conversations/x/messages", json={"content": "hi"}).status_code == 401


def test_conversation_lifecycle_and_streamed_answer(signed_in: TestClient) -> None:
    first = new_conversation(signed_in)
    second = new_conversation(signed_in)
    listed = signed_in.get(f"{API}/conversations").json()["conversations"]
    assert {c["id"] for c in listed} == {first, second}
    assert listed[0]["title"] == DEFAULT_TITLE

    # No LLM is configured in tests: rule routing plus the agent's offline answer.
    stream = events(send(signed_in, first, "How is AAPL doing today?"), traces=True)
    steps = [e["step"] for e in stream if e["type"] == "trace"]
    assert [s["node"] for s in steps][:2] == ["load_context", "router"]
    assert steps[1]["detail"]["method"] == "rules"
    stream = [e for e in stream if e["type"] != "trace"]
    types = [e["type"] for e in stream]
    assert types[:2] == ["route", "agent_start"] and types[-1] == "done"
    assert stream[0]["agents"] == ["market_analysis"]
    assert {e["artifact"]["kind"] for e in stream if e["type"] == "artifact"} == {
        "quote_card",
        "indicators",
    }
    assert any(e["type"] == "freshness" for e in stream)
    done = stream[-1]["message"]
    streamed = "".join(e["text"] for e in stream if e["type"] == "token")
    assert streamed == done["content"] and done["role"] == "assistant"

    # The follow-up resolves "its" from the previous turn (checkpointed memory, CH-02).
    follow_up = events(send(signed_in, first, "and what about its volatility?"))
    assert follow_up[-1]["message"]["content"].startswith("**AAPL**")

    # The first message named the conversation and moved it to the top.
    listed = signed_in.get(f"{API}/conversations").json()["conversations"]
    assert listed[0]["id"] == first and listed[0]["title"] == "How is AAPL doing today?"

    detail = signed_in.get(f"{API}/conversations/{first}").json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert detail["messages"][1]["id"] == done["id"]
    assert detail["messages"][1]["artifacts"] == done["artifacts"]
    assert detail["messages"][1]["trace"] == done["trace"] == steps

    assert signed_in.delete(f"{API}/conversations/{first}").status_code == 204
    assert signed_in.get(f"{API}/conversations/{first}").status_code == 404
    assert [c["id"] for c in signed_in.get(f"{API}/conversations").json()["conversations"]] == [
        second
    ]


def test_bad_turns_fail_before_the_stream_opens(signed_in: TestClient) -> None:
    conversation = new_conversation(signed_in)
    for text, status in (("   ", 422), ("x" * 4001, 422), ("", 422)):
        response = send(signed_in, conversation, text)
        assert response.status_code == status
        assert response.headers["content-type"] == "application/json"
    missing = send(signed_in, "does-not-exist", "hello")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_conversations_are_private(tmp_path: Path, client_for) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(tmp_path, auth={"mode": "guest"})
    alice: TestClient = client_for(settings)
    bob: TestClient = client_for(settings)
    alice.post(f"{API}/auth/guest")
    bob.post(f"{API}/auth/guest")

    private = new_conversation(alice)
    assert bob.get(f"{API}/conversations").json()["conversations"] == []
    assert bob.get(f"{API}/conversations/{private}").status_code == 404
    assert send(bob, private, "hello").status_code == 404
    assert bob.delete(f"{API}/conversations/{private}").status_code == 404
    assert alice.get(f"{API}/conversations/{private}").status_code == 200


def test_title_from_first_message() -> None:
    assert title_from("  What   is an ETF? ") == "What is an ETF?"
    long = title_from(
        "How does dollar cost averaging compare with investing a lump sum all at once"
    )
    assert long.endswith("…") and len(long) <= 61 and not long.endswith(" …")
    assert title_from("x" * 80) == "x" * 60 + "…"
    assert title_from("   ") == DEFAULT_TITLE


PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def test_screenshot_message_reaches_the_portfolio_agent(signed_in: TestClient) -> None:
    conversation_id = new_conversation(signed_in)
    response = signed_in.post(
        f"{API}/conversations/{conversation_id}/messages",
        json={"content": "", "image": {"media_type": "image/png", "data": PNG}},
    )
    stream = events(response)
    assert stream[0]["agents"] == ["portfolio_analysis"]
    # No vision model is configured in tests, so the agent says it can't read images.
    assert stream[-1]["message"]["content"].startswith(SCREENSHOT_UNAVAILABLE_ANSWER)

    messages = signed_in.get(f"{API}/conversations/{conversation_id}").json()["messages"]
    assert messages[0]["content"] == SCREENSHOT_QUESTION and messages[0]["has_image"] is True
    assert messages[1]["has_image"] is False


def test_bad_screenshots_fail_before_the_stream_opens(signed_in: TestClient) -> None:
    conversation_id = new_conversation(signed_in)
    url = f"{API}/conversations/{conversation_id}/messages"
    jpeg_bytes_as_png = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 16).decode()
    bad = signed_in.post(
        url, json={"content": "hi", "image": {"media_type": "image/png", "data": jpeg_bytes_as_png}}
    )
    assert bad.status_code == 422 and "isn't a valid" in bad.json()["error"]["message"]
    gif = signed_in.post(
        url, json={"content": "hi", "image": {"media_type": "image/gif", "data": PNG}}
    )
    assert gif.status_code == 422
