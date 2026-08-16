"""Text-to-speech for Jarvis's British male voice.

Default engine is Microsoft's free `edge-tts` (voice `en-GB-RyanNeural`, a
natural British male voice). A fully-offline `piper` engine is also supported
and automatically used when `TTS_ENGINE=piper`.

Generated audio is written to the static/audio folder and served to the
browser as a normal file so it can be played back.
"""
from __future__ import annotations

import uuid
import os

import config


class TTSError(RuntimeError):
    pass


class TTS:
    def __init__(self, cfg: config.Config = None):
        self.cfg = cfg or config.config

    # ------------------------------------------------------------------ #
    def synthesize(self, text: str) -> str:
        """Synthesize `text` and return a URL path to the audio file."""
        os.makedirs(self.cfg.AUDIO_DIR, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.mp3"
        path = os.path.join(self.cfg.AUDIO_DIR, filename)

        if self.cfg.TTS_ENGINE == "piper":
            self._piper(text, path)
        else:
            self._edge_tts(text, path)

        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise TTSError("TTS produced no audio.")
        return f"/audio/{filename}"

    # ------------------------------------------------------------------ #
    def _edge_tts(self, text: str, path: str) -> None:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover
            raise TTSError(
                "edge-tts is not installed. Run: pip install edge-tts"
            ) from exc

        import asyncio

        communicate = edge_tts.Communicate(
            text,
            voice=self.cfg.TTS_VOICE,
            rate=self.cfg.TTS_SPEED,
        )

        async def _run() -> None:
            await communicate.save(path)

        try:
            asyncio.run(_run())
        except RuntimeError:  # already running loop (e.g. inside an event loop)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_run())
            finally:
                loop.close()

    # ------------------------------------------------------------------ #
    def _piper(self, text: str, path: str) -> None:
        """Offline fallback using Piper. Model auto-downloads on first use."""
        try:
            import piper  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise TTSError(
                "piper is not installed. Install the 'piper-tts' package or "
                "switch TTS_ENGINE=edge-tts."
            ) from exc

        import subprocess

        # piper supports '--model' pointing to a .onnx file; keep it configurable.
        model = os.getenv("PIPER_MODEL", "en_GB-southern_english_male-medium")
        subprocess.run(
            [
                "piper",
                "--model",
                model,
                "--output_file",
                path,
            ],
            input=text.encode("utf-8"),
            check=True,
        )
