"""Jarvis AI Assistant — FastAPI web application.

Endpoints:
  GET    /                    -> the web UI
  GET    /api/health          -> health check (public)
  GET    /api/auth/status     -> login state (public)
  POST   /api/auth/login      -> authenticate (public)
  POST   /api/auth/logout     -> clear session
  GET    /api/config          -> frontend-facing flags (auth required)
  POST   /api/chat            -> send a query, get reply + audio (auth required)
  GET    /audio/{filename}    -> serves generated speech audio (auth required)
  POST   /api/action          -> run an action (auth required)
"""
from __future__ import annotations

import os
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

import auth
import config
from actions import ActionDeniedError, Actions
from brain import Brain, BrainError, route_action, strip_action_tags
from command_runner import CommandDeniedError
from tts import TTSError, TTS

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
AUDIO_DIR = config.config.AUDIO_DIR

app = FastAPI(title="Jarvis AI Assistant")

# Signed, httpOnly session cookie (login state).
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.get_session_secret(),
    max_age=60 * 60 * 24 * 7,      # 7 days
    same_site="lax",
    https_only=config.config.JARVIS_COOKIE_SECURE,
)

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


class LoginRequest(BaseModel):
    username: str
    password: str


# --------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------- #
@app.get("/api/auth/status")
def auth_status(request: Request):
    """Public: whether the current visitor is logged in + if login is needed."""
    if not config.config.AUTH_ENABLED:
        return {"enabled": False, "authed": True}
    return {"enabled": True, "authed": request.session.get("authed", False)}


@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request):
    if not config.config.AUTH_ENABLED:
        return {"ok": True, "authed": True}
    if auth.authenticate(config.config, req.username, req.password):
        request.session["authed"] = True
        return {"ok": True, "authed": True}
    raise HTTPException(status_code=401, detail="Invalid username or password.")


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.pop("authed", None)
    return {"ok": True}


# --------------------------------------------------------------------- #
# Static assets + web UI
# --------------------------------------------------------------------- #
@app.get("/")
def index():
    # Public: the frontend checks /api/auth/status and shows a login screen
    # when needed. Data endpoints are protected server-side.
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/audio/{filename}")
def audio(filename: str, _: None = Depends(auth.require_auth)):
    """Serve a generated speech clip (auth required, path-traversal safe)."""
    safe = os.path.basename(filename)
    path = os.path.join(AUDIO_DIR, safe)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Audio not found.")
    return FileResponse(path, media_type="audio/mpeg")


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
def config_view(_: None = Depends(auth.require_auth)):
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
def chat(req: ChatRequest, _: None = Depends(auth.require_auth)):
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
def run_action(req: ActionRequest, _: None = Depends(auth.require_auth)):
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
