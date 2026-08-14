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
def client():
    from fastapi.testclient import TestClient
    import app

    # Force mock brain in the app instance.
    import config as cfgmod
    importlib.reload(cfgmod)
    cfgmod.config.OLLAMA_USE_MOCK = True
    app.brain._mock = True
    return TestClient(app.app)


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


def test_config(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "phone_enabled" in data and "control_enabled" in data


def test_chat_returns_reply(client):
    r = client.post("/api/chat", json={"message": "Hello Jarvis"})
    assert r.status_code == 200
    data = r.json()
    assert data["reply"]
    assert data["provider"] == "mock"
    assert "audio" in data


def test_chat_empty_message_400(client):
    r = client.post("/api/chat", json={"message": "   "})
    assert r.status_code == 400


def test_action_phone_denied(client):
    r = client.post("/api/action", json={"action": "call"})
    assert r.status_code == 403
    assert "disabled" in r.json()["error"].lower()


def test_action_status_ok(client):
    r = client.post("/api/action", json={"action": "status"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_action_unknown(client):
    r = client.post("/api/action", json={"action": "explode"})
    assert r.status_code == 403
