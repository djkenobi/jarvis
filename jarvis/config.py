"""Central configuration for the Jarvis assistant.

All settings can be overridden through environment variables or a `.env` file
(which is loaded by `dotenv` in `app.py`). See `.env.example` for the full list.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


DEFAULT_PERSONA = (
    "You are {name}, a highly capable, calm and witty British AI personal "
    "assistant. You speak with a refined, polite, British-English manner. "
    "You are concise but helpful. Answer the user's query directly and "
    "clearly. When the user asks you to perform an action you can do "
    "(calling their phone, or running a safe command on the server), say so "
    "in a short sentence that starts with the action keyword like "
    "[CALL] or [RUN] so your handler can react."
)


class Config:
    # --- Server ---
    HOST = os.getenv("JARVIS_HOST", "0.0.0.0")
    PORT = _env_int("JARVIS_PORT", 8000)

    # --- LLM brain (Ollama) ---
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
    OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "60"))
    # Force the built-in mock brain even if Ollama is reachable (great for testing).
    OLLAMA_USE_MOCK = _env_bool("OLLAMA_USE_MOCK", False)

    # --- Assistant persona ---
    ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Jarvis")
    ASSISTANT_PERSONA = os.getenv("ASSISTANT_PERSONA", DEFAULT_PERSONA)

    # --- Speech (TTS) ---
    # 'edge-tts' = Microsoft Edge neural voices (free, needs internet).
    # 'piper'    = fully offline (needs a model downloaded on first use).
    TTS_ENGINE = os.getenv("TTS_ENGINE", "edge-tts").strip().lower()
    TTS_VOICE = os.getenv("TTS_VOICE", "en-GB-RyanNeural")  # British male
    TTS_SPEED = os.getenv("TTS_SPEED", "+0%")
    AUDIO_DIR = os.getenv("AUDIO_DIR", str(BASE_DIR / "static" / "audio"))

    # --- Phone calling (Twilio) — disabled until you add credentials ---
    PHONE_ENABLED = _env_bool("PHONE_ENABLED", False)
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")  # Twilio number
    JARVIS_PHONE_NUMBER = os.getenv("JARVIS_PHONE_NUMBER", "")  # your number

    # --- Server control ---
    CONTROL_ENABLED = _env_bool("CONTROL_ENABLED", False)
    # Semicolon-separated list of exact commands Jarvis is allowed to run.
    # e.g. CONTROL_ALLOWLIST="uptime;df -h;free -m"
    CONTROL_ALLOWLIST = [
        c.strip() for c in os.getenv("CONTROL_ALLOWLIST", "").split(";") if c.strip()
    ]

    # --- Security ---
    # Optional PIN the user must type in the UI before an action runs.
    # Leave empty to only require a click-confirm in the UI.
    ADMIN_PIN = os.getenv("ADMIN_PIN", "")


config = Config()
