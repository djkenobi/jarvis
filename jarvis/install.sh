#!/usr/bin/env bash
#
# Jarvis AI Assistant — one-shot installer for Ubuntu Server.
#
# What it does:
#   1. Installs system dependencies (python3-venv, pip, curl).
#   2. Installs Ollama (local AI brain) and pulls a default model.
#   3. Creates a Python virtual environment and installs the Python deps.
#   4. Creates a systemd service so Jarvis auto-starts and stays running.
#   5. (Optional) Configures an Nginx reverse proxy on port 80.
#
# Usage:
#   sudo ./install.sh                 # default install
#   MODEL=qwen2.5 ./install.sh        # pick a different Ollama model
#   NO_OLLAMA=1 ./install.sh          # skip Ollama install (use mock brain)
#
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[x]${NC} $*"; exit 1; }

# ---------- locate project directory ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
SERVICE_NAME="jarvis"
SERVICE_USER="${JARVIS_USER:-$(id -un)}"
APP_USER="$(id -un)"

MODEL="${MODEL:-llama3.2}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"

[[ "$EUID" -eq 0 ]] || warn "Not running as root; systemd install may need sudo."

info "Jarvis installer starting."
info "Project dir : $APP_DIR"
info "Model       : $MODEL"
info "Run user    : $APP_USER"

# ---------- 1. system packages ----------
info "Installing system packages..."
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip curl ca-certificates \
                     git build-essential ffmpeg
else
  warn "apt-get not found — skipping system package install. Install python3-venv, pip, curl manually."
fi

# ---------- 2. Ollama (local brain) ----------
if [[ "${NO_OLLAMA:-0}" != "1" ]]; then
  if ! command -v ollama >/dev/null 2>&1; then
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
  else
    info "Ollama already installed."
  fi
  # Ensure the service is running before pulling the model.
  systemctl enable ollama 2>/dev/null || true
  systemctl start ollama 2>/dev/null || true
  info "Pulling model '$MODEL' (this may take a while on first run)..."
  ollama pull "$MODEL"
else
  warn "NO_OLLAMA=1 — skipping Ollama install. Set OLLAMA_USE_MOCK=true in .env to use the demo brain."
fi

# ---------- 3. Python environment ----------
info "Creating virtual environment..."
if [[ ! -d "$APP_DIR/.venv" ]]; then
  python3 -m venv "$APP_DIR/.venv"
fi
source "$APP_DIR/.venv/bin/activate"
info "Installing Python dependencies..."
pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt"

# ---------- 4. default .env ----------
if [[ ! -f "$APP_DIR/.env" ]]; then
  info "Creating default .env from .env.example"
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
else
  info ".env already exists — leaving it untouched."
fi

# ---------- 5. systemd service ----------
info "Installing systemd service '$SERVICE_NAME'..."
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Jarvis AI Assistant
After=network.target ollama.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/.venv/bin"
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python -m uvicorn app:app --host \${JARVIS_HOST:-0.0.0.0} --port \${JARVIS_PORT:-8000}
Restart=on-failure
RestartSec=3
User=$APP_USER

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl start "$SERVICE_NAME" || warn "Service failed to start — run: journalctl -u $SERVICE_NAME -e"

# ---------- 6. optional nginx ----------
if [[ "${WITH_NGINX:-0}" == "1" ]]; then
  info "Installing Nginx reverse proxy..."
  apt-get install -y nginx 2>/dev/null || true
  cat > /etc/nginx/sites-available/jarvis <<EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:\${JARVIS_PORT:-8000};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
  ln -sf /etc/nginx/sites-available/jarvis /etc/nginx/sites-enabled/jarvis
  rm -f /etc/nginx/sites-enabled/default
  nginx -t && systemctl reload nginx || warn "Nginx config test failed."
fi

# ---------- done ----------
PORT="${JARVIS_PORT:-8000}"
info "---------------------------------------------------------"
info "Jarvis installed. Next steps:"
echo ""
echo "  1. Edit $APP_DIR/.env to set your preferences, for example:"
echo "       ADMIN_PIN=1234"
echo "       CONTROL_ENABLED=true"
echo "       CONTROL_ALLOWLIST=uptime;df -h /;free -m"
echo "       PHONE_ENABLED=true  (plus Twilio keys + numbers)"
echo "  2. Restart the service after editing:"
echo "       sudo systemctl restart jarvis"
echo "  3. Open Jarvis in your browser:"
echo "       http://YOUR_SERVER_IP:$PORT"
echo ""
info "Service status:  sudo systemctl status jarvis"
info "Logs:            sudo journalctl -u jarvis -f"
echo -e "---------------------------------------------------------"
