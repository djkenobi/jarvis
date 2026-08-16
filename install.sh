#!/usr/bin/env bash
#
# Jarvis AI Assistant — one-shot installer for Ubuntu Server.
#
# What it does:
#   1. Installs system dependencies (python3-venv, pip, curl).
#   2. Installs Ollama (local AI brain) and pulls a default model.
#   3. Creates a Python virtual environment and installs the Python deps.
#   4. Installs Caddy as an HTTPS reverse proxy on port 443 with automatic
#      Let's Encrypt certificates for your domain.
#   5. Creates a systemd service so Jarvis auto-starts and stays running.
#
# Usage:
#   sudo ./install.sh                          # default install
#   DOMAIN=jarvis.example.com sudo ./install.sh  # different domain
#   MODEL=qwen2.5 ./install.sh                 # pick a different Ollama model
#   NO_OLLAMA=1 ./install.sh                   # skip Ollama install (use mock)
#   WITH_NGINX=1 ./install.sh                  # use Nginx instead of Caddy
#
# Prerequisites:
#   - Port 80 must be open (used for Let's Encrypt HTTP challenge).
#   - Port 443 must be open (final HTTPS site).
#   - Your domain's DNS A record must point at this server BEFORE you run this
#     (Caddy needs it to obtain a certificate). Check with:  dig +short DOMAIN
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
DOMAIN="${DOMAIN:-jarvis.dreampixelmedia.uk}"

[[ "$EUID" -eq 0 ]] || warn "Not running as root; systemd install may need sudo."

info "Jarvis installer starting."
info "Project dir : $APP_DIR"
info "Model       : $MODEL"
info "Domain      : $DOMAIN"
info "Run user    : $APP_USER"

# ---------- 1. system packages ----------
info "Installing system packages (best-effort)..."
if command -v apt-get >/dev/null 2>&1; then
  # Add retries + use a working mirror if your network proxies apt (see README).
  # Uncomment the APT_PROXY line if apt goes through an authenticated proxy:
  #   APT_PROXY=http://user:pass@proxy:port
  #   echo "Acquire::http::Proxy \"$APT_PROXY\";" > /etc/apt/apt.conf.d/95proxy
  info "Running apt-get update (with retries)..."
  apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 update -y \
    || warn "apt-get update failed (network/proxy). Continuing — install missing tools manually."

  # Build the package list dynamically so we can skip any that are already present.
  PKGS=()
  command -v python3        >/dev/null 2>&1 || PKGS+=(python3)
  command -v pip3           >/dev/null 2>&1 || PKGS+=(python3-pip)
  python3 -m venv --help    >/dev/null 2>&1 || PKGS+=(python3-venv)
  command -v curl           >/dev/null 2>&1 || PKGS+=(curl)
  command -v git            >/dev/null 2>&1 || PKGS+=(git)
  command -v gcc            >/dev/null 2>&1 || PKGS+=(build-essential)
  command -v ffmpeg         >/dev/null 2>&1 || PKGS+=(ffmpeg)
  if [[ "${#PKGS[@]}" -gt 0 ]]; then
    info "Installing: ${PKGS[*]}"
    apt-get -o Acquire::Retries=5 install -y "${PKGS[@]}" \
      || warn "Some system packages could not be installed via apt (network/proxy)."
  else
    info "All required system tools already present."
  fi
else
  warn "apt-get not found — skipping system package install. Install python3-venv, pip, curl manually."
fi

# Verify the critical Python bits exist, else stop with a clear message.
if ! command -v python3 >/dev/null 2>&1 || ! python3 -m venv --help >/dev/null 2>&1; then
  die "python3 or python3-venv is missing and could not be installed via apt. Fix apt (see README 'apt/proxy fix') then re-run."
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
PIP_EXTRA=()
if [[ -n "${PIP_INDEX_URL:-}" ]]; then
  PIP_EXTRA+=(--index-url "$PIP_INDEX_URL")
fi
pip install --upgrade pip "${PIP_EXTRA[@]}"
pip install -r "$APP_DIR/requirements.txt" "${PIP_EXTRA[@]}"

# ---------- 4. default .env ----------
AUTH_USERNAME="${AUTH_USERNAME:-admin}"
GEN_PASSWORD=""
if [[ ! -f "$APP_DIR/.env" ]]; then
  info "Creating default .env from .env.example"
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  # Generate a strong password for the login (unless the user supplied one).
  if [[ -n "${JARVIS_PASSWORD:-}" ]]; then
    GEN_PASSWORD="$JARVIS_PASSWORD"
  else
    GEN_PASSWORD="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 18)"
  fi
  # Write auth settings into the new .env.
  sed -i "s/^AUTH_ENABLED=.*/AUTH_ENABLED=true/" "$APP_DIR/.env"
  sed -i "s/^JARVIS_USERNAME=.*/JARVIS_USERNAME=$AUTH_USERNAME/" "$APP_DIR/.env"
  sed -i "s|^JARVIS_PASSWORD=.*|JARVIS_PASSWORD=$GEN_PASSWORD|" "$APP_DIR/.env"
  sed -i "s/^JARVIS_COOKIE_SECURE=.*/JARVIS_COOKIE_SECURE=true/" "$APP_DIR/.env"
else
  info ".env already exists — leaving it untouched."
  warn "If you haven't already, set AUTH_ENABLED=true, JARVIS_USERNAME and"
  warn "JARVIS_PASSWORD in $APP_DIR/.env to enable the login screen."
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

# ---------- 6. HTTPS reverse proxy on port 443 ----------
# Default: Caddy (auto-managed Let's Encrypt certificates, simplest).
# Alt: WITH_NGINX=1 uses Nginx + certbot instead.
PORT="${JARVIS_PORT:-8000}"

if [[ "${WITH_NGINX:-0}" == "1" ]]; then
  info "Setting up Nginx + certbot HTTPS for $DOMAIN ..."
  apt-get install -y nginx certbot python3-certbot-nginx 2>/dev/null || true
  cat > /etc/nginx/sites-available/jarvis <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$PORT;
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
  nginx -t || warn "Nginx config test failed."
  systemctl reload nginx || true
  info "Obtaining Let's Encrypt certificate for $DOMAIN ..."
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
    --redirect --register-unsafely-without-email || {
      warn "certbot failed (DNS not pointing here yet?). Fix DNS then run:"
      warn "  sudo certbot --nginx -d $DOMAIN"
    }
else
  info "Installing Caddy reverse proxy (automatic HTTPS on port 443)..."
  if ! command -v caddy >/dev/null 2>&1; then
    # Official Caddy install (deb). Falls back to the static binary if the
    # repo is blocked by your network.
    if command -v apt-get >/dev/null 2>&1; then
      apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl 2>/dev/null || true
      curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null \
      && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null \
      && apt-get update -y 2>/dev/null \
      && apt-get install -y caddy 2>/dev/null
    fi
    if ! command -v caddy >/dev/null 2>&1; then
      info "Caddy apt repo blocked — installing static binary instead."
      (cd /tmp && curl -fsSL -o caddy.tar.gz \
        "https://github.com/caddyserver/caddy/releases/latest/download/caddy_2.8.4_linux_amd64.tar.gz" \
        && tar -xzf caddy.tar.gz caddy \
        && mv caddy /usr/local/bin/ \
        && chmod +x /usr/local/bin/caddy) || warn "Caddy binary download failed — install manually."
    fi
  fi

  if command -v caddy >/dev/null 2>&1; then
    Caddyfile="/etc/caddy/Caddyfile"
    # Backup existing config if present.
    [[ -f "$Caddyfile" ]] && cp "$Caddyfile" "${Caddyfile}.bak" 2>/dev/null || true
    cat > "$Caddyfile" <<EOF
# Jarvis AI Assistant
$DOMAIN {
    encode zstd gzip
    reverse_proxy 127.0.0.1:$PORT
}
EOF
    systemctl enable caddy >/dev/null 2>&1 || true
    systemctl restart caddy || warn "Caddy failed to start."
    info "Caddy will obtain a Let's Encrypt certificate for $DOMAIN automatically."
  else
    warn "Caddy is not installed. Install it manually, then the service will still run on port $PORT."
  fi
fi

# ---------- done ----------
PORT="${JARVIS_PORT:-8000}"
info "---------------------------------------------------------"
info "Jarvis installed. Next steps:"
echo ""
echo "  Login to Jarvis at https://$DOMAIN"
if [[ -n "$GEN_PASSWORD" ]]; then
  echo "    username : $AUTH_USERNAME"
  echo "    password : $GEN_PASSWORD   <-- SAVE THIS (only shown once)"
else
  echo "    use the username/password set in $APP_DIR/.env"
fi
echo ""
echo "  Other settings in $APP_DIR/.env you may want to adjust:"
echo "       ADMIN_PIN=1234"
echo "       CONTROL_ENABLED=true"
echo "       CONTROL_ALLOWLIST=uptime;df -h /;free -m"
echo "       PHONE_ENABLED=true  (plus Twilio keys + numbers)"
echo "  Restart after editing:  sudo systemctl restart jarvis"
echo ""
info "Service status:  sudo systemctl status jarvis"
info "Logs:            sudo journalctl -u jarvis -f"
info "Proxy:           sudo systemctl status caddy   (or nginx if WITH_NGINX=1)"
info "Certificate:     Caddy renews automatically. If DNS wasn't ready, run:"
info "                   curl https://$DOMAIN  (once DNS points here)"
echo -e "---------------------------------------------------------"
