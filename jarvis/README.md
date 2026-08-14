# Jarvis AI Assistant

A self-hosted, voice-controlled AI assistant web app with a **British male voice**,
designed to run on your own **Ubuntu server**. Jarvis answers your queries by
voice, and — when you enable the features — can **run tasks on the server** and
**call your phone** when you're away.

---

## Features

- 🎙️ **Talk to Jarvis** — press the mic and speak (uses your browser's built-in
  speech recognition). You can also just type.
- 🇬🇧 **British male voice** — answers out loud using Microsoft's `en-GB-RyanNeural`
  neural voice (offline `piper` engine also supported).
- 🧠 **Local AI brain (Ollama)** — runs entirely on your server. No cloud, no API key,
  fully private. Includes a built-in *mock brain* for testing without any model.
- 🖥️ **Control the server** — Jarvis can check system status and run whitelisted
  commands (safe, sandboxed; off by default).
- 📞 **Call your phone** — Twilio integration to ring and speak to you when you're
  away (fully coded, **disabled until you add credentials**).
- 🔒 **Confirm before actions** — every action asks for confirmation (and an optional
  admin PIN) before it runs.
- 🚀 **One-command install** — `install.sh` sets up everything on Ubuntu.

---

## Quick start

### 1. Copy the project to your server

```bash
git clone <your-repo-or-scp-the-folder> jarvis
cd jarvis
```

### 2. Install everything

```bash
sudo ./install.sh
```

This installs system packages, Ollama + a model (`llama3.2`), a Python virtual
environment, all Python dependencies, and a `jarvis` systemd service. Then it
starts the service and prints the URL.

> Options: `MODEL=qwen2.5 ./install.sh` to pick another model, or
> `NO_OLLAMA=1 ./install.sh` to skip Ollama (use the mock brain).

### 3. Open it in your browser

```
http://YOUR_SERVER_IP:8000
```

### 4. Configure (edit `.env`, then `sudo systemctl restart jarvis`)

See **`.env.example`** for all settings. Common tweaks:

```bash
# Optional admin PIN required before any action runs
ADMIN_PIN=1234

# Enable safe server control + whitelist exact commands
CONTROL_ENABLED=true
CONTROL_ALLOWLIST=uptime;df -h /;free -m;ls -la /home

# Enable phone calling (add real Twilio credentials)
PHONE_ENABLED=true
TWILIO_ACCOUNT_SID=ACxxxx
TWILIO_AUTH_TOKEN=your_token
TWILIO_FROM_NUMBER=+1XXXXXXXXXX      # a Twilio phone number
JARVIS_PHONE_NUMBER=+639XXXXXXXXXX   # your phone
```

---

## How it works

```
 You (voice or text)
        │  Web Speech API (STT) / text input
        ▼
   ┌─────────────────┐        ┌──────────────────┐
   │   Browser UI    │  HTTP  │   FastAPI server │
   │  (static/)      │◄──────►│   (app.py)       │
   └─────────────────┘        └────────┬─────────┘
                                       │
          ┌────────────────────────────┼─────────────────────────────┐
          ▼                            ▼                             ▼
   ┌─────────────┐             ┌──────────────┐             ┌──────────────────┐
   │  Ollama     │             │  edge-tts    │             │  Actions         │
   │  brain      │             │  TTS         │             │  (phone/control) │
   │  (local LLM)│             │  British male│             │                  │
   └─────────────┘             └──────────────┘             └──────────────────┘
```

1. You speak → browser transcribes to text.
2. `POST /api/chat` sends it to Jarvis's brain (Ollama, or the mock engine).
3. Jarvis replies with text; the reply is checked for an action tag
   (`[CALL]`, `[RUN]`, `[STATUS]`).
4. The reply is converted to a British male voice (edge-tts) and sent back as audio.
5. If an action was requested, the UI asks you to **confirm**, then
   `POST /api/action` runs it (phone call or a whitelisted server command).

---

## Testing (before/after deployment)

Run the full test harness (uses the mock brain, so no Ollama needed):

```bash
./test.sh        # unit + smoke tests
./test.sh live   # also boots the server and hits the live HTTP endpoints
```

You can also run just the unit tests:

```bash
source .venv/bin/activate
python -m pytest -q
```

The suite verifies: the brain (incl. action-intent detection), safe command
runner (whitelist + denial), phone-call denial when unconfigured, TTS generation,
and every HTTP endpoint.

---

## Security notes

- **Server control is sandboxed**: only exact commands in `CONTROL_ALLOWLIST` can run.
  It's disabled by default.
- **Actions require confirmation** in the UI (and optionally an admin PIN).
- **Don't expose this on the public internet** without adding auth. The simplest
  safe setup is to keep it on your LAN, or put it behind a VPN / authenticated
  reverse proxy.
- Twilio credentials are read from `.env`, never sent to the browser.

---

## Project layout

```
jarvis/
├── app.py               # FastAPI server + endpoints
├── config.py            # all settings (env-var driven)
├── brain.py             # Ollama client + mock brain + action routing
├── tts.py               # British-male text-to-speech (edge-tts / piper)
├── actions.py           # phone-call + action dispatch
├── command_runner.py    # safe, whitelisted server-command execution
├── static/              # web UI (index.html, styles.css, app.js)
├── static/audio/        # generated speech clips
├── tests/               # pytest suite
├── requirements.txt
├── .env.example         # config template
├── install.sh           # one-shot Ubuntu installer
├── test.sh              # test harness
└── README.md
```
