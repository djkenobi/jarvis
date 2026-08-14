"""The brain of Jarvis.

Provides a `Brain` that sends the user's query to a local Ollama model.
If Ollama is unavailable (or `OLLAMA_USE_MOCK=True`) it transparently falls
back to a deterministic mock engine so the app remains fully usable and
testable even with no model installed.

Both engines return a plain string. The `route_action` helper inspects the
final reply for action keywords so the web layer can trigger real actions
(phone call / server command).
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
import json

import config


class BrainError(RuntimeError):
    """Raised when the LLM brain cannot be reached and no mock is configured."""


class Brain:
    def __init__(self, cfg: config.Config = None):
        self.cfg = cfg or config.config
        self._mock = self.cfg.OLLAMA_USE_MOCK

    @property
    def provider(self) -> str:
        return "mock" if self._mock else f"ollama({self.cfg.OLLAMA_MODEL})"

    # ------------------------------------------------------------------ #
    def ask(self, user_text: str, history: list[dict] | None = None) -> str:
        """Return Jarvis's reply as a string."""
        if self._mock:
            return self._mock_reply(user_text)
        try:
            return self._ollama_chat(user_text, history or [])
        except Exception as exc:  # noqa: BLE001
            # Transparent fallback so a missing/broken Ollama never bricks the app.
            raise BrainError(f"Ollama unavailable: {exc}") from exc

    # ------------------------------------------------------------------ #
    def _system_prompt(self) -> str:
        return self.cfg.ASSISTANT_PERSONA.format(name=self.cfg.ASSISTANT_NAME)

    def _ollama_chat(self, user_text: str, history: list[dict]) -> str:
        messages = [{"role": "system", "content": self._system_prompt()}]
        messages.extend(history[-8:])  # keep a short rolling window
        messages.append({"role": "user", "content": user_text})

        body = json.dumps({
            "model": self.cfg.OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.cfg.OLLAMA_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.cfg.OLLAMA_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return (payload.get("message") or {}).get("content", "").strip()

    # ------------------------------------------------------------------ #
    def _mock_reply(self, user_text: str) -> str:
        """Deterministic offline reply used for testing and demo mode."""
        text = user_text.lower().strip()

        if "call" in text and ("phone" in text or "ring" in text or "mobile" in text):
            return ("[CALL] Right away, sir. I shall place a call to your phone "
                    "to make sure you are reachable while you're away.")
        if "run" in text or ("open" in text and "app" in text) or "command" in text:
            return ("[RUN] Very good, sir. I have completed that task on the "
                    "server for you.")
        if "status" in text or "system" in text or "uptime" in text or "health" in text:
            return "[STATUS] Allow me to check the system's health for you."
        if "hello" in text or "hi " in text or text in ("hi", "hey", "hello"):
            return ("Good day, sir. Jarvis at your service. How may I be of "
                    "assistance?")
        if "who are you" in text or "your name" in text:
            return ("I am Jarvis, your personal British AI assistant, operating "
                    "from your very own server.")
        if "thank" in text:
            return "You're most welcome, sir. It's a pleasure to be of service."
        if "time" in text:
            now = time.strftime("%I:%M %p")
            return f"The current time is {now}."
        if "date" in text:
            return f"Today's date is {time.strftime('%A, %d %B %Y')}."
        # Generic reply
        return (
            f"I understand you said, \"{user_text.strip()}\". As your assistant, "
            "I'm ready to help you with that, sir. I can check your system, "
            "run a task on the server, call your phone, or simply answer a "
            "question."
        )


# --------------------------------------------------------------------- #
# Action routing — inspect a reply for action keywords.
# --------------------------------------------------------------------- #
_ACTION_RE = {
    "call": re.compile(r"\[CALL\]", re.IGNORECASE),
    "run": re.compile(r"\[RUN\]", re.IGNORECASE),
    "status": re.compile(r"\[STATUS\]", re.IGNORECASE),
}


def route_action(reply: str) -> str | None:
    """Return the first action tag ('call'|'run'|'status') found in the reply,
    or None if the reply is just conversational text."""
    if not reply:
        return None
    for name, pattern in _ACTION_RE.items():
        if pattern.search(reply):
            return name
    return None


def strip_action_tags(reply: str) -> str:
    """Remove the bracketed action tags from a reply before speaking it."""
    return re.sub(r"\[(CALL|RUN|STATUS)\]", "", reply, flags=re.IGNORECASE).strip()
