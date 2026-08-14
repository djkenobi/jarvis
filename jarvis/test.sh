#!/usr/bin/env bash
#
# Test harness for Jarvis. Run from the project root.
#   ./test.sh           -> full test (uses the mock brain so no Ollama needed)
#   ./test.sh live      -> also starts the server and hits live HTTP endpoints
#
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[PASS]${NC} $*"; }
bad()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

echo "== Jarvis test harness =="

# ---- environment ----
if [[ ! -d .venv ]]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
pip install --quiet pytest

export OLLAMA_USE_MOCK=true

echo
echo "== Running unit tests =="
python -m pytest -q

echo
echo "== Import smoke test =="
python -c "import app, brain, tts, actions, command_runner, config; print('all modules import OK')"

echo
echo "== Brain smoke test =="
python -c "
from brain import Brain
b = Brain()
r = b.ask('Hello Jarvis')
assert r and isinstance(r, str)
print('mock brain replied:', r[:60])
"

echo
echo "== TTS smoke test =="
if python -c "
import tts
t = tts.TTS()
url = t.synthesize('Good day, sir. Jarvis at your service.')
print('TTS URL:', url)
" 2>/dev/null; then
  ok "TTS synthesized audio (edge-tts, British male)."
else
  warn "TTS edge-tts failed (needs internet). Audio will fall back to silent; text still works."
fi

if [[ "${1:-}" == "live" ]]; then
  echo
  echo "== Live server test =="
  PORT="${JARVIS_PORT:-8000}"
  uvicorn app:app --host 127.0.0.1 --port "$PORT" >/tmp/jarvis_test.log 2>&1 &
  SERVER_PID=$!
  trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
  sleep 2

  echo -n "health: "
  curl -s "http://127.0.0.1:$PORT/api/health" | python -c "import sys,json; d=json.load(sys.stdin); print('OK', d)" || bad "health endpoint failed"

  echo -n "chat: "
  curl -s -X POST "http://127.0.0.1:$PORT/api/chat" \
    -H "Content-Type: application/json" \
    -d '{"message":"Hello Jarvis"}' | python -c "import sys,json; d=json.load(sys.stdin); print('reply=', d.get('reply','')[:50])" || bad "chat endpoint failed"

  echo -n "index: "
  curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:$PORT/" || bad "index endpoint failed"

  echo -n "action-denied: "
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/action" \
    -H "Content-Type: application/json" -d '{"action":"call"}')
  [[ "$CODE" == "403" ]] && ok "action correctly denied (403)" || bad "expected 403, got $CODE"

  echo "server log tail:"
  tail -5 /tmp/jarvis_test.log
fi

echo
echo "== Done. All checks passed. =="
