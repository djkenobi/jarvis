#!/usr/bin/env bash
#
# Jarvis diagnostic / status script.
# Checks ports, services, DNS, HTTPS reachability and config in one go.
#
# Usage:
#   ./status.sh                          # quick summary
#   ./status.sh --verbose                # also show raw outputs
#   DOMAIN=jarvis.example.com ./status.sh  # override the domain
#
set -uo pipefail

DOMAIN="${DOMAIN:-jarvis.dreampixelmedia.uk}"
PORT="${JARVIS_PORT:-8000}"
VERBOSE=0
[[ "${1:-}" == "--verbose" ]] && VERBOSE=1

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS(){ echo -e "${GREEN}[OK]${NC} $*"; }
FAIL(){ echo -e "${RED}[XX]${NC} $*"; }
WARN(){ echo -e "${YELLOW}[!!]${NC} $*"; }
RAW() { [[ "$VERBOSE" -eq 1 ]] && { echo -e "${CYAN}      $*${NC}"; }; }

echo "=============================================="
echo "  Jarvis diagnostic — $DOMAIN"
echo "=============================================="
echo

# ---------------- 1. Ports ----------------
echo "1) Ports"
if command -v ss >/dev/null 2>&1; then
  L80=$(ss -ltn 2>/dev/null | grep -c ':80 ')
  L443=$(ss -ltn 2>/dev/null | grep -c ':443 ')
  L8000=$(ss -ltn 2>/dev/null | grep -c ":${PORT} ")
  [[ "$L80" -gt 0 ]]   && PASS "port 80   listening"   || WARN "port 80   NOT listening (needed for cert challenge)"
  [[ "$L443" -gt 0 ]]  && PASS "port 443  listening (HTTPS)" || FAIL "port 443  NOT listening"
  [[ "$L8000" -gt 0 ]] && PASS "port ${PORT} listening (backend)" || WARN "port ${PORT} NOT listening"
else
  WARN "ss not available; skipping port checks"
fi
echo

# ---------------- 2. Services ----------------
echo "2) Services"
for svc in jarvis caddy nginx ollama; do
  if systemctl list-unit-files 2>/dev/null | grep -q "^$svc"; then
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
      PASS "service $svc is active"
    else
      WARN "service $svc is installed but NOT active"
    fi
  else
    WARN "service $svc not found (may not be installed)"
  fi
done
echo

# ---------------- 3. Config file ----------------
echo "3) Config (.env)"
if [[ -f "$APP_DIR/.env" ]]; then
  PASS ".env exists ($APP_DIR/.env)"
  # Warn about placeholder password
  if grep -qE '^JARVIS_PASSWORD=(change_me_please|)$' "$APP_DIR/.env"; then
    WARN "JARVIS_PASSWORD looks weak/empty — set a real password!"
  fi
else
  FAIL ".env NOT found — run ./install.sh first"
fi
if [[ -f "$APP_DIR/.env.example" ]]; then
  PASS ".env.example exists"
else
  WARN ".env.example missing (install.sh will recreate it)"
fi
echo

# ---------------- 4. Reverse proxy config ----------------
echo "4) Reverse proxy (Caddy/Nginx)"
if [[ -f /etc/caddy/Caddyfile ]]; then
  if grep -q "$DOMAIN" /etc/caddy/Caddyfile; then
    PASS "Caddyfile references $DOMAIN"
  else
    WARN "Caddyfile exists but does NOT reference $DOMAIN"
  fi
elif [[ -f /etc/nginx/sites-enabled/jarvis ]]; then
  if grep -q "$DOMAIN" /etc/nginx/sites-enabled/jarvis; then
    PASS "Nginx config references $DOMAIN"
  else
    WARN "Nginx config exists but does NOT reference $DOMAIN"
  fi
else
  FAIL "No Caddyfile or Nginx jarvis config found — proxy not configured"
fi
echo

# ---------------- 5. DNS ----------------
echo "5) DNS resolution"
if command -v dig >/dev/null 2>&1; then
  IP=$(dig +short "$DOMAIN" | head -1)
elif command -v nslookup >/dev/null 2>&1; then
  IP=$(nslookup "$DOMAIN" 2>/dev/null | grep -A1 'Name:' | grep 'Address' | awk '{print $2}' | head -1)
else
  IP=$(python3 -c "import socket,sys; print(socket.gethostbyname(sys.argv[1]))" "$DOMAIN" 2>/dev/null)
fi
if [[ -n "${IP:-}" ]]; then
  PASS "$DOMAIN -> $IP"
else
  FAIL "$DOMAIN does NOT resolve. Add an A record pointing to your server's public IP."
fi
echo

# ---------------- 6. HTTPS reachability ----------------
echo "6) HTTPS reachability"
if command -v curl >/dev/null 2>&1; then
  HTTPCODE=$(curl -s -o /dev/null -w "%{http_code}" -m 10 "https://$DOMAIN" 2>/dev/null || echo "000")
  if [[ "$HTTPCODE" == "000" ]]; then
    FAIL "could not reach https://$DOMAIN (connection failed / cert / network)"
    WARN "check DNS + firewall (ports 80 & 443) + that Caddy is running"
  else
    PASS "https://$DOMAIN responded with HTTP $HTTPCODE"
    case "$HTTPCODE" in
      200|302|401|403) RAW "looks reachable — a 401/302 is expected before login" ;;
      *) WARN "unexpected HTTP code $HTTPCODE" ;;
    esac
  fi
  RAW "HTTP code: $HTTPCODE"
else
  WARN "curl not available; skipping reachability test"
fi
echo

# ---------------- 7. Python app import ----------------
echo "7) Python app health"
if [[ -x "$APP_DIR/.venv/bin/python" ]]; then
  if (cd "$APP_DIR" && "$APP_DIR/.venv/bin/python" -c "import app; print('ok')" >/dev/null 2>&1); then
    PASS "Python app imports OK"
  else
    FAIL "Python app failed to import — check deps (run install.sh again)"
  fi
else
  WARN ".venv not found — run ./install.sh to set up the environment"
fi
echo

# ---------------- Summary ----------------
echo "=============================================="
echo "  Summary: fix anything marked [XX]."
echo "  [!!] = warnings to review. [OK] = all good."
echo "  Helpful commands:"
echo "    sudo systemctl status jarvis caddy"
echo "    sudo journalctl -u jarvis -f"
echo "    sudo journalctl -u caddy -f"
echo "  Open: https://$DOMAIN"
echo "=============================================="
