"""Jarvis AI Assistant — FastAPI web application.

Endpoints:
  GET  /                    -> the web UI
  GET  /api/health          -> health check
  POST /api/chat            -> send a text query, get Jarvis's reply + audio
  GET  /api/config          -> frontend-facing flags (what's enabled)
  GET  /audio/{filename}    -> serves generated speech audio
  POST /api/action          -> run a specific action (status/run/call)
"""
from __future__ import annotations

import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from actions import ActionDeniedError, Actions
from brain import Brain, BrainError, route_action, strip_action_tags
from command_runner import CommandDeniedError
from tts import TTSError, TTS

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
AUDIO_DIR = config.config.AUDIO_DIR

app = FastAPI(title="Jarvis AI Assistant")

# Single shared instances (avoids re-creating objects on every request).
brain = Brain()
tts = TTS()
actions = Actions()


# --------------------------------------------------------------------- #
# Request/response models
# --------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None


class ActionRequest(BaseModel):
    action: str          # 'call' | 'status' | 'run'
    user_message: str = ""
    message: str = ""


# --------------------------------------------------------------------- #
# Static assets + web UI
# --------------------------------------------------------------------- #
app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "assistant": config.config.ASSISTANT_NAME,
        "provider": brain.provider,
        "tts_engine": config.config.TTS_ENGINE,
        "tts_voice": config.config.TTS_VOICE,
        "phone_enabled": config.config.PHONE_ENABLED,
        "control_enabled": config.config.CONTROL_ENABLED,
    }


@app.get("/api/config")
def config_view():
    """Flags the frontend needs (never expose secrets here)."""
    return {
        "name": config.config.ASSISTANT_NAME,
        "phone_enabled": actions.phone_configured(),
        "control_enabled": config.config.CONTROL_ENABLED,
        "admin_pin_required": bool(config.config.ADMIN_PIN),
        "audio_tts": config.config.TTS_ENGINE,
    }


# --------------------------------------------------------------------- #
# Main chat endpoint
# --------------------------------------------------------------------- #
@app.post("/api/chat")
def chat(req: ChatRequest):
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="No message provided.")

    # 1) Get the reply from the brain.
    try:
        reply = brain.ask(message, req.history)
    except BrainError as exc:
        return JSONResponse(status_code=503, content={
            "error": str(exc),
            "hint": "Ollama is not reachable. Run the install script (it installs "
                    "and pulls a model), or set OLLAMA_USE_MOCK=true for a demo brain.",
        })

    # 2) Detect + strip any action tag.
    action = route_action(reply)
    speak_text = strip_action_tags(reply)

    # 3) Synthesize speech.
    audio_url = None
    try:
        audio_url = tts.synthesize(speak_text)
    except TTSError as exc:
        audio_url = None  # UI can still show text if TTS fails.

    return {
        "reply": speak_text,
        "action": action,
        "audio": audio_url,
        "provider": brain.provider,
    }


# --------------------------------------------------------------------- #
# Explicit action execution (phone call / run command / status)
# --------------------------------------------------------------------- #
@app.post("/api/action")
def run_action(req: ActionRequest):
    try:
        result = actions.dispatch(req.action, req.user_message, req.message)
        return {"ok": True, "result": result}
    except (ActionDeniedError, CommandDeniedError) as exc:
        return JSONResponse(status_code=403, content={"ok": False, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


# --------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------- #
def main():
    import uvicorn

    uvicorn.run(
        "app:app",
        host=config.config.HOST,
        port=config.config.PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
