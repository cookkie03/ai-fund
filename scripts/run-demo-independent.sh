#!/usr/bin/env bash
# ==============================================================================
# AI Fund Independent Demo Runner
# Avvia e mantiene in background i processi demo (backend + cockpit) fuori dal cgroup di Telegram
# ==============================================================================
set -euo pipefail

ROOT_DIR="/home/luca/ai-fund"
cd "$ROOT_DIR"

PORT_BACKEND=48765
PORT_FRONTEND=4318
DB_PATH="/tmp/ai-fund-demo-20261124.db"

# Verifica se il backend è già attivo
if ! curl -s "http://127.0.0.1:${PORT_BACKEND}/v1/health" >/dev/null 2>&1; then
    echo "Avvio backend AI Fund su porta ${PORT_BACKEND}..."
    nohup env TRADING_AGENT_API_PORT="${PORT_BACKEND}" TRADING_AGENT_DB="${DB_PATH}" uv run --env-file .env trading-agent run > /tmp/ai-fund-backend.log 2>&1 &
fi

# Verifica se il frontend è già attivo
if ! curl -s "http://127.0.0.1:${PORT_FRONTEND}/" >/dev/null 2>&1; then
    echo "Avvio frontend AI Fund su porta ${PORT_FRONTEND}..."
    nohup env COCKPIT_RUNTIME_URL="http://127.0.0.1:${PORT_BACKEND}" npm --prefix "${ROOT_DIR}/frontend" run dev -- --port "${PORT_FRONTEND}" > /tmp/ai-fund-frontend.log 2>&1 &
fi

echo "AI Fund demo operativa su http://127.0.0.1:${PORT_FRONTEND}"
