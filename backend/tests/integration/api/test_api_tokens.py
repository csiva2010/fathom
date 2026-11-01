"""Access tokens and the routes added for the MCP tools, through the real FastAPI app."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from src.data.db.models import ApiToken
from tests.integration.api.test_views_api import seed_sample, with_kb

API = "/api/v1"


def container(client: TestClient) -> Any:
    return client.app.state.container  # type: ignore[attr-defined]


def create_token(client: TestClient, name: str = "Claude Desktop") -> dict[str, Any]:
    response = client.post(f"{API}/me/tokens", json={"name": f"  {name}  "})
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


def test_token_lifecycle(signed_in: TestClient) -> None:
    assert signed_in.get(f"{API}/me/tokens").json() == {"tokens": []}
    created = create_token(signed_in)
    assert created["name"] == "Claude Desktop" and created["token"].startswith("fa_pat_")
    assert created["last_used_at"] is None

    listed = signed_in.get(f"{API}/me/tokens").json()["tokens"]
    assert [t["id"] for t in listed] == [created["id"]]
    assert "token" not in listed[0]  # shown once, never again

    # Only the hash is stored.
    with container(signed_in).session_factory() as db:
        stored = db.get(ApiToken, created["id"])
        assert stored is not None and created["token"] not in stored.token_hash

    assert signed_in.delete(f"{API}/me/tokens/{created['id']}").status_code == 204
    assert signed_in.get(f"{API}/me/tokens").json() == {"tokens": []}
    assert signed_in.delete(f"{API}/me/tokens/{created['id']}").status_code == 404
    assert signed_in.post(f"{API}/me/tokens", json={"name": ""}).status_code == 422


def test_bearer_token_authenticates_api_calls(signed_in: TestClient) -> None:
    token = create_token(signed_in)
    me_via_cookie = signed_in.get(f"{API}/me").json()
    signed_in.cookies.clear()
    assert signed_in.get(f"{API}/me").status_code == 401

    bearer = {"Authorization": f"Bearer {token['token']}"}
    me = signed_in.get(f"{API}/me", headers=bearer)
    assert me.status_code == 200 and me.json()["id"] == me_via_cookie["id"]
    assert "set-cookie" not in me.headers  # tokens never start a browser session

    with container(signed_in).session_factory() as db:
        stored = db.get(ApiToken, token["id"])
        assert stored is not None and stored.last_used_at is not None

    # A token can't manage tokens, so a leaked one can't mint more.
    for response in (
        signed_in.get(f"{API}/me/tokens", headers=bearer),
        signed_in.post(f"{API}/me/tokens", json={"name": "x"}, headers=bearer),
        signed_in.delete(f"{API}/me/tokens/{token['id']}", headers=bearer),
    ):
        assert response.status_code == 403
        assert "Profile page" in response.json()["error"]["message"]

    bad = signed_in.get(f"{API}/me", headers={"Authorization": "Bearer fa_pat_wrong"})
    assert bad.status_code == 401 and "revoked" in bad.json()["error"]["message"]


def test_revoked_token_is_rejected(signed_in: TestClient) -> None:
    token = create_token(signed_in)
    bearer = {"Authorization": f"Bearer {token['token']}"}
    assert signed_in.get(f"{API}/me", headers=bearer).status_code == 200
    signed_in.delete(f"{API}/me/tokens/{token['id']}")
    assert signed_in.get(f"{API}/me", headers=bearer).status_code == 401


def test_kb_passage_search(signed_in: TestClient) -> None:
    assert signed_in.get(f"{API}/kb/search?q=roth").status_code == 503  # no KB loaded yet
    client = with_kb(signed_in)

    found = client.get(f"{API}/kb/search?q=what+is+a+roth+ira").json()
    assert found["mode"] == "keyword" and found["results"]
    top = found["results"][0]
    assert top["citation"]["article_id"] == "roth-ira" and "after-tax" in top["text"]
    assert 0 < top["score"] <= 1

    assert client.get(f"{API}/kb/search?q=roth+ira&category=basics").json()["results"] == []
    assert client.get(f"{API}/kb/search?q=").status_code == 422


def test_analyze_holdings_without_saving(signed_in: TestClient) -> None:
    seed_sample(signed_in)
    body = {"holdings": [{"symbol": "vti", "quantity": 10, "cost_basis": 200}], "range": "6M"}
    analysis = signed_in.post(f"{API}/portfolios/analyze", json=body).json()
    assert analysis["total_value"] > 0 and analysis["benchmark"]["range"] == "6M"
    assert [h["symbol"] for h in analysis["holdings"]] == ["VTI"]
    assert [p["is_sample"] for p in signed_in.get(f"{API}/portfolios").json()["portfolios"]] == [
        True
    ]  # nothing saved

    empty = signed_in.post(f"{API}/portfolios/analyze", json={"holdings": []})
    assert empty.status_code == 422
