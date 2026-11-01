"""Auth flow, session cookie and per-user profile through the real FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import FakeGoogleClient, make_settings

API = "/api/v1"


def test_protected_routes_require_a_session(client: TestClient) -> None:
    for path in ("/me", "/market/overview", "/market/quotes?symbols=AAPL"):
        response = client.get(API + path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"


def test_stub_login_sets_httponly_cookie_and_redirects(client: TestClient) -> None:
    response = client.get(f"{API}/auth/google/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173"
    cookie = response.headers["set-cookie"]
    assert "fa_session=" in cookie
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()

    me = client.get(f"{API}/me").json()
    assert me["email"] == "dev.user@example.com"
    assert me["profile"]["onboarding_complete"] is False


def test_google_flow_redirects_then_signs_in(
    tmp_path: Path, client_for, fake_google: FakeGoogleClient
) -> None:
    client: TestClient = client_for(make_settings(tmp_path, auth={"mode": "google"}))

    start = client.get(f"{API}/auth/google/login", follow_redirects=False)
    assert start.status_code in (302, 307)
    assert start.headers["location"].startswith("https://accounts.example/consent")

    callback = client.get(f"{API}/auth/google/callback?code=abc&state=xyz", follow_redirects=False)
    assert callback.status_code == 303
    assert client.get(f"{API}/me").json()["name"] == "Ada Lovelace"


def test_google_callback_errors_redirect_with_reason(
    tmp_path: Path, client_for, fake_google: FakeGoogleClient
) -> None:
    client: TestClient = client_for(make_settings(tmp_path, auth={"mode": "google"}))

    cancelled = client.get(
        f"{API}/auth/google/callback?error=access_denied", follow_redirects=False
    )
    assert cancelled.headers["location"].endswith("?auth_error=cancelled")

    fake_google.identity = None
    failed = client.get(f"{API}/auth/google/callback?code=bad", follow_redirects=False)
    assert failed.headers["location"].endswith("?auth_error=sign_in_failed")
    assert client.get(f"{API}/me").status_code == 401


def test_logout_clears_session(signed_in: TestClient) -> None:
    response = signed_in.post(f"{API}/auth/logout", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 204
    assert signed_in.get(f"{API}/me").status_code == 401


def test_cross_origin_post_is_rejected(signed_in: TestClient) -> None:
    response = signed_in.post(f"{API}/auth/logout", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_origin"


def test_invalid_cookie_and_deleted_user(signed_in: TestClient) -> None:
    container = signed_in.app.state.container  # type: ignore[attr-defined]
    signed_in.cookies.set("fa_session", "garbage")
    assert signed_in.get(f"{API}/me").status_code == 401

    signed_in.cookies.set("fa_session", container.session_tokens.issue("no-such-user").token)
    assert signed_in.get(f"{API}/me").json()["error"]["message"].startswith("Your account")


def test_session_is_refreshed_when_half_expired(signed_in: TestClient) -> None:
    container = signed_in.app.state.container  # type: ignore[attr-defined]
    me = signed_in.get(f"{API}/me").json()
    tokens = container.session_tokens
    tokens._ttl *= 100  # make the existing 12h token look more than half used
    signed_in.cookies.set("fa_session", jwt_for(tokens, me["id"], hours=1))
    response = signed_in.get(f"{API}/me")
    assert response.status_code == 200
    assert "fa_session=" in response.headers.get("set-cookie", "")


def jwt_for(tokens, user_id: str, hours: int) -> str:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    now = datetime.now(UTC)
    return pyjwt.encode(
        {
            "sub": user_id,
            "iat": now,
            "exp": now + timedelta(hours=hours),
            "iss": "ai-finance-assistant",
        },
        tokens._secret,
        algorithm="HS256",
    )


def test_profile_update_completes_onboarding(signed_in: TestClient) -> None:
    response = signed_in.put(
        f"{API}/me/profile",
        json={
            "experience_level": "intermediate",
            "risk_profile": "moderate",
            "risk_answers": {"horizon": 3, "drop_reaction": "hold"},
            "accept_disclaimer": True,
        },
    )
    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["onboarding_complete"] is True
    assert profile["risk_profile"] == "moderate"

    # Persisted for the next request
    assert signed_in.get(f"{API}/me").json()["profile"]["experience_level"] == "intermediate"


def test_profile_validation_uses_error_envelope(signed_in: TestClient) -> None:
    response = signed_in.put(f"{API}/me/profile", json={"risk_profile": "yolo"})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_failed"
    assert "risk_profile" in body["message"]


# --- Guest mode (AUTH__MODE=guest) ---------------------------------------------


def test_auth_config_reports_mode(client: TestClient) -> None:
    assert client.get(f"{API}/auth/config").json() == {
        "mode": "stub",
        "google_enabled": True,
        "guest_enabled": False,
    }


def test_guest_mode_disables_google_and_creates_isolated_guests(tmp_path: Path, client_for) -> None:
    guest_settings = make_settings(tmp_path, auth={"mode": "guest"})
    config = client_for(guest_settings).get(f"{API}/auth/config").json()
    assert config == {"mode": "guest", "google_enabled": False, "guest_enabled": True}

    first: TestClient = client_for(guest_settings)
    for path in ("/auth/google/login", "/auth/google/callback?code=x"):
        blocked = first.get(API + path, follow_redirects=False)
        assert blocked.headers["location"].endswith("?auth_error=google_disabled")

    response = first.post(f"{API}/auth/guest")
    assert response.status_code == 204
    assert "HttpOnly" in response.headers["set-cookie"]
    me = first.get(f"{API}/me").json()
    assert me["is_guest"] is True
    assert me["name"] == "Guest"
    assert me["email"] == ""

    second: TestClient = client_for(guest_settings)
    second.post(f"{API}/auth/guest")
    assert second.get(f"{API}/me").json()["id"] != me["id"]

    # Guests can save their own profile like any user.
    updated = first.put(f"{API}/me/profile", json={"risk_profile": "conservative"}).json()
    assert updated["profile"]["risk_profile"] == "conservative"


def test_guest_endpoint_is_off_unless_guest_mode(client: TestClient) -> None:
    response = client.post(f"{API}/auth/guest")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Guest sign-in is not enabled."


def test_google_users_are_not_guests(signed_in: TestClient) -> None:
    assert signed_in.get(f"{API}/me").json()["is_guest"] is False
