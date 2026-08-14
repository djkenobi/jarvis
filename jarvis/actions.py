"""Action layer for Jarvis: phone calls and server control.

Phone calling uses Twilio and is fully implemented but DISABLED until you add
credentials to your `.env` (PHONE_ENABLED=true + Twilio keys + numbers). See
`README.md` for how to switch it on.

Server control uses the safe whitelisted CommandRunner from `command_runner.py`.
"""
from __future__ import annotations

import re

import config
from command_runner import CommandRunner


class ActionDeniedError(PermissionError):
    pass


class Actions:
    def __init__(self, cfg: config.Config = None):
        self.cfg = cfg or config.config
        self.runner = CommandRunner(self.cfg)

    # ------------------------------------------------------------------ #
    # Phone calling
    # ------------------------------------------------------------------ #
    def phone_configured(self) -> bool:
        return bool(
            self.cfg.PHONE_ENABLED
            and self.cfg.TWILIO_ACCOUNT_SID
            and self.cfg.TWILIO_AUTH_TOKEN
            and self.cfg.TWILIO_FROM_NUMBER
            and self.cfg.JARVIS_PHONE_NUMBER
        )

    def call_phone(self, message: str = "Hello sir, this is Jarvis calling to "
                                        "let you know everything is under control.") -> dict:
        """Place a call to the owner's phone and speak `message`."""
        if not self.cfg.PHONE_ENABLED:
            raise ActionDeniedError(
                "Phone calling is disabled. Set PHONE_ENABLED=true and add your "
                "Twilio credentials and numbers to the .env file."
            )
        if not self.phone_configured():
            raise ActionDeniedError(
                "Twilio is not fully configured. Check TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER and JARVIS_PHONE_NUMBER."
            )
        try:
            from twilio.rest import Client
        except ImportError as exc:  # pragma: no cover
            raise ActionDeniedError(
                "The 'twilio' package is not installed. Run: pip install twilio"
            ) from exc

        # Build a TwiML message that speaks the text, then hangs up.
        from twilio.twiml.voice_response import VoiceResponse

        twiml = VoiceResponse()
        twiml.say(message, voice="alexa", language="en-GB")
        twiml.hangup()

        client = Client(self.cfg.TWILIO_ACCOUNT_SID, self.cfg.TWILIO_AUTH_TOKEN)
        call = client.calls.create(
            twiml=str(twiml),
            to=self.cfg.JARVIS_PHONE_NUMBER,
            from_=self.cfg.TWILIO_FROM_NUMBER,
        )
        return {"ok": True, "call_sid": call.sid, "message": message}

    # ------------------------------------------------------------------ #
    # Server control
    # ------------------------------------------------------------------ #
    def run_builtin(self, name: str) -> dict:
        return self.runner.run_builtin(name)

    def run_command(self, command: str) -> dict:
        return self.runner.run_command(command)

    # ------------------------------------------------------------------ #
    # Route an action tag from the brain's reply.
    # ------------------------------------------------------------------ #
    def dispatch(self, action: str, user_text: str, message: str) -> dict:
        """Execute a routed action and return a structured result."""
        action = (action or "").lower()
        if action == "call":
            return self.call_phone()
        if action == "status":
            return self.run_builtin("status")
        if action == "run":
            # Try to pick a command out of the request; else fall back to built-in status.
            command = self._extract_command(user_text)
            if command and command in self.cfg.CONTROL_ALLOWLIST:
                return self.run_command(command)
            return self.run_builtin("status")
        raise ActionDeniedError(f"Unknown action: {action}")

    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_command(text: str) -> str | None:
        """Look for an allowlisted command literally present in the request."""
        text_l = (text or "").lower()
        for cmd in config.config.CONTROL_ALLOWLIST:
            if cmd.lower() in text_l:
                return cmd
        return None
