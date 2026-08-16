"""Unit tests for Jarvis. Run with: pytest -q (or via test.sh)."""
import os
import importlib

import pytest


@pytest.fixture(scope="module")
def fresh_config():
    """Reload config so env overrides from conftest take effect."""
    import config

    importlib.reload(config)
    return config.config


# --------------------------------------------------------------------- #
# Brain
# --------------------------------------------------------------------- #
def test_mock_brain_answers(fresh_config):
    from brain import Brain

    b = Brain(fresh_config)
    assert b.provider == "mock"
    reply = b.ask("Hello Jarvis")
    assert isinstance(reply, str) and reply.strip()


def test_mock_brain_detects_call_intent(fresh_config):
    from brain import Brain, route_action

    reply = Brain(fresh_config).ask("Please call my phone")
    assert route_action(reply) == "call"


def test_mock_brain_detects_run_intent(fresh_config):
    from brain import Brain, route_action

    reply = Brain(fresh_config).ask("Please run a command on the server")
    assert route_action(reply) == "run"


def test_mock_brain_detects_status_intent(fresh_config):
    from brain import Brain, route_action

    reply = Brain(fresh_config).ask("What is the system status?")
    assert route_action(reply) == "status"


def test_route_action_none_for_plain_text():
    from brain import route_action, strip_action_tags

    assert route_action("Just a normal greeting, sir.") is None
    assert strip_action_tags("[CALL] Call your phone.") == "Call your phone."


# --------------------------------------------------------------------- #
# Auth helpers
# --------------------------------------------------------------------- #
def test_authenticate_success(fresh_config):
    import auth

    assert auth.authenticate(fresh_config, "admin", "testpass") is True


def test_authenticate_failure(fresh_config):
    import auth

    assert auth.authenticate(fresh_config, "admin", "nope") is False
    assert auth.authenticate(fresh_config, "evil", "testpass") is False


def test_session_secret_generated():
    import auth
    import config

    # Force a fresh secret by pointing at a temp file.
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmp:
        class FakeCfg:
            SESSION_SECRET = ""
            SESSION_SECRET_FILE = os.path.join(tmp, "secret")
        s1 = auth.get_session_secret(FakeCfg())
        s2 = auth.get_session_secret(FakeCfg())
        assert s1 and len(s1) >= 32
        assert s1 == s2  # persisted, stable across calls


# --------------------------------------------------------------------- #
# Command runner (server control)
# --------------------------------------------------------------------- #
def test_command_runner_whitelisted(fresh_config):
    from command_runner import CommandRunner

    r = CommandRunner(fresh_config)
    result = r.run_command("uptime")
    assert result["ok"] is True
    assert "load" in result["stdout"]


def test_command_runner_denies_unknown(fresh_config):
    from command_runner import CommandRunner, CommandDeniedError

    r = CommandRunner(fresh_config)
    with pytest.raises(CommandDeniedError):
        r.run_command("rm -rf /")


def test_command_runner_builtin_status(fresh_config):
    from command_runner import CommandRunner

    r = CommandRunner(fresh_config)
    result = r.run_builtin("status")
    assert result["ok"] is True
    assert result["exit_code"] == 0


# --------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------- #
def test_phone_disabled_raises(fresh_config):
    from actions import Actions, ActionDeniedError

    a = Actions(fresh_config)
    with pytest.raises(ActionDeniedError):
        a.call_phone()


def test_actions_dispatch_status(fresh_config):
    from actions import Actions

    a = Actions(fresh_config)
    result = a.dispatch("status", "", "")
    assert result["ok"] is True


# --------------------------------------------------------------------- #
# API endpoints (FastAPI TestClient)
# --------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def _app():
    """Build the app once, force the mock brain."""
    import app

    import config as cfgmod
    importlib.reload(cfgmod)
    cfgmod.config.OLLAMA_USE_MOCK = True
    app.brain._mock = True
    return app.app


@pytest.fixture()
def client(_app):
    """An unauthenticated TestClient (fresh cookies per test)."""
    from fastapi.testclient import TestClient

    return TestClient(_app)


@pytest.fixture()
def auth_client(_app):
    """A TestClient that has logged in."""
    from fastapi.testclient import TestClient

    c = TestClient(_app)
    resp = c.post(
        "/api/auth/login",
        json={"username": "admin", "password": "testpass"},
    )
    assert resp.status_code == 200
    return c


# ---- Public endpoints (no auth required) ----------------------------- #
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["assistant"] == "Jarvis"


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "JARVIS" in r.text


def test_auth_status_public(client):
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert data["authed"] is False


# ---- Auth enforcement ------------------------------------------------ #
def test_config_requires_auth(client):
    assert client.get("/api/config").status_code == 401


def test_chat_requires_auth(client):
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401


def test_action_requires_auth(client):
    assert client.post("/api/action", json={"action": "status"}).status_code == 401


def test_audio_requires_auth(client):
    assert client.get("/audio/whatever.mp3").status_code == 401


def test_login_wrong_password(client):
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert r.status_code == 401


def test_login_missing_password_returns_401(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": ""})
    assert r.status_code == 401


# ---- Authenticated endpoints ------------------------------------------ #
def test_config(auth_client):
    r = auth_client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "phone_enabled" in data and "control_enabled" in data


def test_chat_returns_reply(auth_client):
    r = auth_client.post("/api/chat", json={"message": "Hello Jarvis"})
    assert r.status_code == 200
    data = r.json()
    assert data["reply"]
    assert data["provider"] == "mock"
    assert "audio" in data


def test_chat_empty_message_400(auth_client):
    r = auth_client.post("/api/chat", json={"message": "   "})
    assert r.status_code == 400


def test_action_phone_denied(auth_client):
    r = auth_client.post("/api/action", json={"action": "call"})
    assert r.status_code == 403
    assert "disabled" in r.json()["error"].lower()


def test_action_status_ok(auth_client):
    r = auth_client.post("/api/action", json={"action": "status"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_action_unknown(auth_client):
    r = auth_client.post("/api/action", json={"action": "explode"})
    assert r.status_code == 403


def test_logout_clears_session(client):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "testpass"})
    assert r.status_code == 200
    assert client.get("/api/config").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/config").status_code == 401
