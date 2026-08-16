"""Safe, sandboxed command execution on the server that hosts Jarvis.

Only commands explicitly listed in `CONTROL_ALLOWLIST` (in config / .env) can
be executed. Everything else is rejected. This keeps the "control my computer"
feature useful but safe — nothing arbitrary can be run.
"""
from __future__ import annotations

import shlex
import subprocess
import time

import config


class CommandDeniedError(PermissionError):
    pass


# Safe built-in status checks that don't require whitelisting (read-only).
_BUILTINS = {
    "status": (
        "uptime && echo '---' && free -h && echo '---' && df -h / && "
        "echo '---' && top -bn1 | head -12"
    ),
}


class CommandRunner:
    def __init__(self, cfg: config.Config = None):
        self.cfg = cfg or config.config

    def enabled(self) -> bool:
        return self.cfg.CONTROL_ENABLED

    # ------------------------------------------------------------------ #
    def run_builtin(self, name: str) -> dict:
        if name not in _BUILTINS:
            raise CommandDeniedError(f"Unknown built-in: {name}")
        return self._execute(_BUILTINS[name], label=f"status check '{name}'")

    # ------------------------------------------------------------------ #
    def run_command(self, command: str) -> dict:
        """Run a whitelisted shell command and return its output."""
        if not self.enabled():
            raise CommandDeniedError("Server control is disabled (CONTROL_ENABLED=false).")
        command = command.strip()
        if command not in self.cfg.CONTROL_ALLOWLIST:
            raise CommandDeniedError(
                f"Command not in allowlist: {command!r}. "
                f"Add it to CONTROL_ALLOWLIST in your .env to enable it."
            )
        return self._execute(command, label=f"command '{command}'")

    # ------------------------------------------------------------------ #
    def _execute(self, command: str, label: str) -> dict:
        started = time.time()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "ok": True,
                "label": label,
                "command": command,
                "exit_code": proc.returncode,
                "stdout": (proc.stdout or "").strip(),
                "stderr": (proc.stderr or "").strip(),
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "label": label,
                "command": command,
                "error": "Command timed out after 30s.",
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "label": label, "command": command, "error": str(exc)}
