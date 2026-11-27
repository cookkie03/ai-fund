#!/usr/bin/env bash
# ==============================================================================
# Development Launcher: Backend Engine + Frontend Cockpit
# Single-command runner with coordinated logs and clean SIGINT shutdown.
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Color helpers
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BOLD}${GREEN}=== Trading Agent Local Development Launcher ===${NC}"

# Check prerequisites
if ! command -v uv &>/dev/null; then
    echo -e "${RED}Error: 'uv' is not installed or not in PATH.${NC}" >&2
    exit 1
fi

if ! command -v npm &>/dev/null; then
    echo -e "${RED}Error: 'npm' is not installed or not in PATH.${NC}" >&2
    exit 1
fi

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Warning: .env not found. Creating from .env.example...${NC}"
    cp .env.example .env
fi

# Ports to check
ENGINE_PORT="${TRADING_AGENT_API_PORT:-8765}"
FRONTEND_PORT="${COCKPIT_PORT:-5174}"

# Conflict detection
check_port() {
    local port="$1"
    local name="$2"
    if command -v lsof &>/dev/null; then
        if lsof -Pi :"$port" -sTCP:LISTEN -t >/dev/null ; then
            echo -e "${RED}Error: Port $port is already in use (needed by $name).${NC}" >&2
            echo -e "${YELLOW}Check running instances with: lsof -i :$port${NC}" >&2
            exit 1
        fi
    elif command -v ss &>/dev/null; then
        if ss -tuln | grep -q ":$port "; then
            echo -e "${RED}Error: Port $port is already in use (needed by $name).${NC}" >&2
            exit 1
        fi
    fi
}

check_port "$ENGINE_PORT" "Backend Engine"
check_port "$FRONTEND_PORT" "Frontend Cockpit"

# Sync dependencies if needed
echo -e "${BLUE}Verifying environment dependencies...${NC}"
uv sync --quiet

if [ ! -d "frontend/node_modules" ]; then
    echo -e "${BLUE}Installing frontend dependencies...${NC}"
    (cd frontend && npm install --silent)
fi

# Track child PIDs
ENGINE_PID=""
FRONTEND_PID=""

cleanup() {
    echo -e "\n${YELLOW}Shutting down processes...${NC}"
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    fi
    if [ -n "$ENGINE_PID" ] && kill -0 "$ENGINE_PID" 2>/dev/null; then
        kill -TERM "$ENGINE_PID" 2>/dev/null || true
    fi
    wait 2>/dev/null || true
    echo -e "${GREEN}Clean shutdown complete.${NC}"
}

trap cleanup INT TERM EXIT

echo -e "${GREEN}Starting Backend Engine on http://127.0.0.1:${ENGINE_PORT}...${NC}"
uv run --env-file .env trading-agent run 2>&1 | sed -e "s/^/$(printf '%b' "${BLUE}[engine]${NC} ")/" &
ENGINE_PID=$!

echo -e "${GREEN}Starting Frontend Cockpit on http://127.0.0.1:${FRONTEND_PORT}...${NC}"
(
    cd frontend
    COCKPIT_RUNTIME_URL="http://127.0.0.1:${ENGINE_PORT}" \
    COCKPIT_PORT="${FRONTEND_PORT}" \
    npm run dev 2>&1 | sed -e "s/^/$(printf '%b' "${GREEN}[cockpit]${NC} ")/"
) &
FRONTEND_PID=$!

echo -e "${BOLD}${GREEN}Cockpit ready at: http://127.0.0.1:${FRONTEND_PORT}${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop both services.${NC}\n"

# Wait for children
wait -n "$ENGINE_PID" "$FRONTEND_PID"
