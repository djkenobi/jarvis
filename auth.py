"""Authentication for Jarvis.

Uses Starlette's signed-session middleware. When auth is enabled, the user must
log in with JARVIS_USERNAME / JARVIS_PASSWORD (from config / .env). A signed,
httpOnly, SameSite=Lax cookie keeps the session.

The session cookie secret is either taken from SESSION_SECRET in config or
generated randomly on first run and persisted to a file so sessions survive
restarts.
"""
from __future__ import annotations

import hmac
import secrets

from fastapi import HTTPException, Request

import config


def _ensure_secret(cfg: config.Config) -> str:
    """Return the session secret, generating + persisting one if unset."""
    if cfg.SESSION_SECRET:
        return cfg.SESSION_SECRET
    try:
        with open(cfg.SESSION_SECRET_FILE, "r", encoding="utf-8") as fh:
            existing = fh.read().strip()
        if existing:
            return existing
    except OSError:
        pass

    secret = secrets.token_hex(32)
    try:
        with open(cfg.SESSION_SECRET_FILE, "w", encoding="utf-8") as fh:
            fh.write(secret)
    except OSError:
        pass  # non-fatal; a per-process secret is acceptable if unwritable
    return secret


def get_session_secret(cfg: config.Config = None) -> str:
    cfg = cfg or config.config
    return _ensure_secret(cfg)


def authenticate(cfg: config.Config, username: str, password: str) -> bool:
    """Constant-time check of supplied credentials against config."""
    expected_user = cfg.JARVIS_USERNAME or ""
    expected_pass = cfg.JARVIS_PASSWORD or ""
    return (
        hmac.compare_digest(username or "", expected_user)
        and hmac.compare_digest(password or "", expected_pass)
    )


def require_auth(request: Request) -> None:
    """FastAPI dependency that enforces login unless auth is disabled."""
    cfg = config.config
    if not cfg.AUTH_ENABLED:
        return
    if not cfg.JARVIS_PASSWORD:
        raise HTTPException(status_code=503, detail=(
            "Authentication is enabled but no password is set. "
            "Set JARVIS_PASSWORD in .env (or run ./set_password.sh)."
        ))
    if not request.session.get("authed"):
        raise HTTPException(status_code=401, detail="Not authenticated.")
