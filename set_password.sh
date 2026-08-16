#!/usr/bin/env bash
#
# Set or change Jarvis's login password in .env, then restart the service.
#
# Usage:
#   ./set_password.sh                    # prompts for a new password
#   ./set_password.sh "MyNewPass123!"    # set it non-interactively
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$APP_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[!] No .env found. Run ./install.sh first (it creates one)." >&2
  exit 1
fi

NEW_PASS="${1:-}"
if [[ -z "$NEW_PASS" ]]; then
  read -rsp "New password: " NEW_PASS
  echo
  [[ -z "$NEW_PASS" ]] && { echo "[!] Empty password."; exit 1; }
fi

# Update or add JARVIS_PASSWORD.
if grep -q '^JARVIS_PASSWORD=' "$ENV_FILE"; then
  sed -i "s|^JARVIS_PASSWORD=.*|JARVIS_PASSWORD=$NEW_PASS|" "$ENV_FILE"
else
  printf 'JARVIS_PASSWORD=%s\n' "$NEW_PASS" >> "$ENV_FILE"
fi

# Make sure auth is on.
sed -i "s/^AUTH_ENABLED=.*/AUTH_ENABLED=true/" "$ENV_FILE"

echo "[+] Password updated in $ENV_FILE"
if systemctl list-units --type=service | grep -q 'jarvis.service'; then
  echo "[+] Restarting jarvis service..."
  systemctl restart jarvis || true
fi
echo "[+] Done."
