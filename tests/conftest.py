import os
import sys

# Make the project root importable regardless of where pytest is run from.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Force the mock brain during tests so no Ollama is required.
os.environ.setdefault("OLLAMA_USE_MOCK", "true")
os.environ.setdefault("CONTROL_ENABLED", "true")
os.environ.setdefault("CONTROL_ALLOWLIST", "uptime;echo hello")
os.environ.setdefault("TTS_ENGINE", "edge-tts")

# Auth test credentials. Cookie is NOT Secure so it works over http in tests.
os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("JARVIS_USERNAME", "admin")
os.environ.setdefault("JARVIS_PASSWORD", "testpass")
os.environ.setdefault("JARVIS_COOKIE_SECURE", "false")
