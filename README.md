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
- 🔑 **Login/auth** — protected by a username + password with signed session
  cookies. All data endpoints reject unauthenticated requests.
- 🔐 **HTTPS on port 443** — served at your own domain (default
  `jarvis.dreampixelmedia.uk`) with automatic Let's Encrypt certificates via
  Caddy.
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
environment, all Python dependencies, a `jarvis` systemd service, and an HTTPS
reverse proxy (Caddy) that automatically obtains a Let's Encrypt certificate
for your domain on port 443.

> Options:
> - `MODEL=qwen2.5 ./install.sh` to pick another model.
> - `NO_OLLAMA=1 ./install.sh` to skip Ollama (use the mock brain).
> - `DOMAIN=jarvis.example.com sudo ./install.sh` to use a different domain.
> - `WITH_NGINX=1 sudo ./install.sh` to use Nginx + certbot instead of Caddy.

### 3. Open it in your browser

```
https://jarvis.dreampixelmedia.uk
```

### Important: DNS before install

**Before running `install.sh`, point your domain's DNS at this server** — the
Let's Encrypt certificate can only be issued once `jarvis.dreampixelmedia.uk`
resolves to your server's public IP. Create an **A record**:

```
jarvis  IN  A   <YOUR_SERVER_PUBLIC_IP>
```

Verify with:
```bash
dig +short jarvis.dreampixelmedia.uk
```

You must also open **ports 80 and 443** (TCP) on your server's firewall for the
certificate challenge and the final HTTPS site:

```bash
# ufw
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# or your cloud provider's security group must allow 80 and 443 (e.g. AWS SG,
# DigitalOcean/Azure/Linode firewall, etc.)
```

### 4. Configure (edit `.env`, then `sudo systemctl restart jarvis`)

See **`.env.example`** for all settings. Common tweaks:

```bash
# Optional admin PIN required before any action runs
ADMIN_PIN=1234

# Login credentials (the installer generates a strong password and prints it)
AUTH_ENABLED=true
JARVIS_USERNAME=admin
JARVIS_PASSWORD=your_password_here

# Set the session cookie Secure flag — keep true behind HTTPS
JARVIS_COOKIE_SECURE=true

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

To change the login password later, use the helper (it also restarts the service):
```bash
./set_password.sh            # prompts
./set_password.sh "NewPass1" # non-interactive
```

### How login works

- The **installer creates a strong password** automatically and prints the
  username/password once (save it).
- The web UI shows a **sign-in screen**; sessions last 7 days (cookie-based).
- **Every data endpoint** (`/api/chat`, `/api/action`, `/api/config`,
  `/audio/...`) returns `401` when not authenticated. `/`, static assets, and
  `/api/auth/*` remain public so the login page can load.
- The session cookie is signed and `Secure` when `JARVIS_COOKIE_SECURE=true`.

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

## Checking / diagnosing the deployment

Run the diagnostic script anytime to see whether Jarvis is up, listening on 443,
and reachable over HTTPS — it checks ports, services, config, DNS, and
reachability in one go:

```bash
./status.sh             # quick summary
./status.sh --verbose   # include raw output
DOMAIN=jarvis.example.com ./status.sh   # override domain
```

It flags problems as `[XX]` (fix these) and `[!!]` (review).

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

## Troubleshooting: apt "403 Forbidden" / "Connection reset by peer"

If `install.sh` (or `apt-get`) fails with errors like:

```
Error reading from server - read (104: Connection reset by peer) [IP: 185.125.190.81 80]
403 Forbidden [IP: 172.18.30.2 8090]
E: Failed to fetch http://archive.ubuntu.com/... 403 Forbidden
```

…it means **your server's network is proxying or blocking Ubuntu's package
repos** (`archive.ubuntu.com`), so `apt` can't download packages. This is a
server/network problem, not a Jarvis bug. Fix `apt` first, then re-run the
installer.

**Step 1 — Diagnose:**
```bash
curl -sI -m 10 http://archive.ubuntu.com/ubuntu/ ; echo
sudo apt-get update ; echo
env | grep -i proxy          # if a proxy is set, that's usually the culprit
```

**Step 2 — Tell apt about your proxy** (if you have one, e.g. `172.18.30.2:8090`):
```bash
echo 'Acquire::http::Proxy "http://172.18.30.2:8090";' | sudo tee /etc/apt/apt.conf.d/95proxy
echo 'Acquire::https::Proxy "http://172.18.30.2:8090";' | sudo tee -a /etc/apt/apt.conf.d/95proxy
sudo apt-get update
```
> If your proxy needs a username/password: `http://user:pass@proxy:port`.

**Step 3 — Or switch to a mirror that your network allows.** Pick your nearest
Ubuntu mirror and rewrite the sources file:
```bash
# Ubuntu 22.04 (jammy) example using a mirror
sudo sed -i 's|http://archive.ubuntu.com/ubuntu|http://ph.archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list
sudo apt-get update
```
(Replace `ph.archive.ubuntu.com` with any working mirror, e.g. your region's.)

**Step 4 — Re-run the installer.** The installer is now *best-effort* for apt:
it skips already-installed tools and won't abort the whole run if apt fails —
but you still need `python3` + `python3-venv` available (the installer checks
and tells you if they're missing).

**If PyPI is also proxied/blocked**, the `pip install` step will fail too.
You can point pip at a mirror or proxy:
```bash
PIP_INDEX_URL=https://pypi.org/simple sudo ./install.sh
# or a corporate index: PIP_INDEX_URL=https://pypi.yourcorp.com/simple
```

---

## Security notes

- **Login is required** by default now that the app is publicly reachable over
  HTTPS. Every data endpoint rejects unauthenticated requests with `401`.
- **Server control is sandboxed**: only exact commands in `CONTROL_ALLOWLIST` can run.
  It's disabled by default.
- **Actions require confirmation** in the UI (and optionally an admin PIN).
- Twilio credentials are read from `.env`, never sent to the browser.
- Use a strong `JARVIS_PASSWORD` and keep `JARVIS_COOKIE_SECURE=true`. Consider
  restricting access further with a VPN or IP allowlist if you want defense in
  depth.

---

## Project layout

```
jarvis/
├── app.py               # FastAPI server + endpoints
├── config.py            # all settings (env-var driven)
├── brain.py             # Ollama client + mock brain + action routing
├── tts.py               # British-male text-to-speech (edge-tts / piper)
├── auth.py              # login / session handling
├── actions.py           # phone-call + action dispatch
├── command_runner.py    # safe, whitelisted server-command execution
├── static/              # web UI (index.html, styles.css, app.js)
├── static/audio/        # generated speech clips
├── tests/               # pytest suite
├── requirements.txt
├── .env.example         # config template
├── install.sh           # one-shot Ubuntu installer
├── set_password.sh      # change the login password
├── status.sh            # diagnostic / health check
├── test.sh              # test harness
└── README.md
```
